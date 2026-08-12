// Input bar: model selector + image upload + multiline input box + send button
import { Check, ChevronDown, Image as ImageIcon, Loader2, Search, Send, Square, X } from 'lucide-react'
import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from 'react'
import {
  fetchModelAvailability,
  fetchModels,
  isGenerationModel,
  uploadChatImage,
  type ModelAvailability,
  type ModelEntry,
} from '../../api/client'
import { useChat } from '../../store/useChat'
import { PromptGallery } from './PromptGallery'

/** Fallback model list used before API loads */
const FALLBACK_MODELS: ModelEntry[] = [
  { id: 'trigen-default', label: 'Trigen Default', provider: 'local', description: 'Offline rule engine', modalities: ['text'], max_tokens: 2048, context_window: 4096, is_open_source: false, is_local: true, api_key_env: '' },
  { id: 'gpt-4o', label: 'GPT-4o', provider: 'openai', description: 'OpenAI flagship multimodal', modalities: ['text', 'vision', 'audio'], max_tokens: 4096, context_window: 128000, is_open_source: false, is_local: false, api_key_env: 'OPENAI_API_KEY' },
  { id: 'gpt-4o-mini', label: 'GPT-4o Mini', provider: 'openai', description: 'Fast and efficient', modalities: ['text', 'vision'], max_tokens: 16384, context_window: 128000, is_open_source: false, is_local: false, api_key_env: 'OPENAI_API_KEY' },
  { id: 'claude-3-5-sonnet-20241022', label: 'Claude 3.5 Sonnet', provider: 'anthropic', description: 'Anthropic reasoning', modalities: ['text', 'vision'], max_tokens: 8192, context_window: 200000, is_open_source: false, is_local: false, api_key_env: 'ANTHROPIC_API_KEY' },
  { id: 'deepseek-chat', label: 'DeepSeek V3', provider: 'deepseek', description: 'Open-source MoE', modalities: ['text'], max_tokens: 8192, context_window: 64000, is_open_source: true, is_local: false, api_key_env: 'DEEPSEEK_API_KEY' },
  { id: 'qwen-plus', label: 'Qwen Plus', provider: 'qwen', description: 'Alibaba Cloud LLM', modalities: ['text'], max_tokens: 8192, context_window: 131072, is_open_source: false, is_local: false, api_key_env: 'DASHSCOPE_API_KEY' },
  { id: 'dall-e-3', label: 'DALL·E 3', provider: 'openai', description: 'Image generation', modalities: ['image_gen'], max_tokens: 1, context_window: 4000, is_open_source: false, is_local: false, api_key_env: 'OPENAI_API_KEY' },
  { id: 'meshy/text-to-3d', label: 'Meshy Text-to-3D', provider: 'openrouter', description: 'Text-to-3D mesh', modalities: ['3d'], max_tokens: 1, context_window: 4000, is_open_source: false, is_local: false, api_key_env: 'OPENROUTER_API_KEY' },
]

/** Provider display names */
const PROVIDER_LABELS: Record<string, string> = {
  openai: 'OpenAI',
  anthropic: 'Anthropic',
  google: 'Google Gemini',
  xai: 'xAI Grok',
  deepseek: 'DeepSeek',
  qwen: 'Alibaba Qwen',
  zhipu: 'Zhipu GLM',
  moonshot: 'Moonshot Kimi',
  baichuan: 'Baichuan',
  minimax: 'MiniMax',
  spark: 'iFlytek Spark',
  groq: 'Groq',
  together: 'Together AI',
  fireworks: 'Fireworks AI',
  mistral: 'Mistral AI',
  cohere: 'Cohere',
  perplexity: 'Perplexity',
  ai21: 'AI21 Labs',
  replicate: 'Replicate',
  huggingface: 'Hugging Face',
  stability: 'Stability AI',
  runway: 'Runway',
  meshy: 'Meshy',
  openrouter: 'OpenRouter',
  ollama: 'Ollama (Local)',
  local: 'Trigen',
}

/** Modality icons */
const MODALITY_ICONS: Record<string, string> = {
  text: 'T',
  vision: 'V',
  audio: 'A',
  video: 'Vid',
  image_gen: 'Img',
  '3d': '3D',
  animation: 'Anim',
  voice: 'Vol',
}

/** Group models by provider */
function groupByProvider(models: ModelEntry[]): Record<string, ModelEntry[]> {
  const groups: Record<string, ModelEntry[]> = {}
  for (const m of models) {
    if (!groups[m.provider]) groups[m.provider] = []
    groups[m.provider].push(m)
  }
  return groups
}

/** Model selector dropdown (categorized, with search) */
function ModelSelector() {
  const model = useChat((s) => s.model)
  const setModel = useChat((s) => s.setModel)
  const [open, setOpen] = useState(false)
  const [models, setModels] = useState<ModelEntry[]>(FALLBACK_MODELS)
  const [availability, setAvailability] = useState<Record<string, ModelAvailability>>({})
  const [searchQuery, setSearchQuery] = useState('')
  const [modalityFilter, setModalityFilter] = useState<string>('all')
  const searchRef = useRef<HTMLInputElement>(null)
  const ref = useRef<HTMLDivElement>(null)

  const current = models.find((m) => m.id === model) ?? models[0]

  // Fetch models from API on mount
  useEffect(() => {
    fetchModels()
      .then((catalog) => {
        if (catalog.length > 0) setModels(catalog)
      })
      .catch(() => {
        // Keep fallback models on error
      })
    // Fetch availability status (non-blocking; selector works without it)
    fetchModelAvailability()
      .then((items) => {
        const map: Record<string, ModelAvailability> = {}
        for (const a of items) map[a.id] = a
        setAvailability(map)
      })
      .catch(() => {
        // Availability is optional; selector still works
      })
  }, [])

  // Close dropdown when clicking outside
  useEffect(() => {
    if (!open) return
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open])

  // Focus search input when dropdown opens
  useEffect(() => {
    if (open && searchRef.current) {
      setTimeout(() => searchRef.current?.focus(), 50)
    }
  }, [open])

  // Filter models by search query and modality filter
  const filteredModels = useMemo(() => {
    let result = models
    if (modalityFilter !== 'all') {
      result = result.filter((m) => m.modalities.includes(modalityFilter))
    }
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase()
      result = result.filter(
        (m) =>
          m.id.toLowerCase().includes(q) ||
          m.label.toLowerCase().includes(q) ||
          m.provider.toLowerCase().includes(q) ||
          m.description.toLowerCase().includes(q)
      )
    }
    return result
  }, [models, searchQuery, modalityFilter])

  const grouped = groupByProvider(filteredModels)
  const providerOrder = ['local', 'openai', 'anthropic', 'google', 'xai', 'mistral', 'cohere', 'deepseek', 'qwen', 'zhipu', 'moonshot', 'perplexity', 'ai21', 'groq', 'together', 'fireworks', 'replicate', 'huggingface', 'stability', 'runway', 'meshy', 'openrouter', 'ollama', 'baichuan', 'minimax', 'spark']
  const sortedProviders = Object.keys(grouped).sort((a, b) => {
    const ia = providerOrder.indexOf(a)
    const ib = providerOrder.indexOf(b)
    if (ia === -1 && ib === -1) return a.localeCompare(b)
    if (ia === -1) return 1
    if (ib === -1) return -1
    return ia - ib
  })

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1.5 px-2 py-1 rounded-md text-[11px] text-fg-secondary hover:text-fg-primary hover:bg-bg-hover transition-colors border border-transparent hover:border-border"
      >
        <span className="font-medium">{current?.label ?? 'Select Model'}</span>
        <ChevronDown size={12} className={`transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>

      {open && (
        <div className="absolute bottom-full left-0 mb-1.5 w-80 rounded-md border border-border bg-bg-elevated shadow-lg overflow-hidden z-50">
          {/* Search input */}
          <div className="px-2.5 py-2 border-b border-border-subtle">
            <div className="relative">
              <Search size={12} className="absolute left-2 top-1/2 -translate-y-1/2 text-fg-muted" />
              <input
                ref={searchRef}
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search models..."
                className="w-full pl-7 pr-2 py-1.5 text-[11px] bg-bg-base border border-border-subtle rounded text-fg-primary placeholder:text-fg-muted outline-none focus:border-accent-cyan/50"
              />
            </div>
            {/* Modality filter chips */}
            <div className="flex items-center gap-1 mt-1.5 flex-wrap">
              {[
                { key: 'all', label: 'All' },
                { key: 'text', label: 'Text' },
                { key: 'vision', label: 'Vision' },
                { key: 'image_gen', label: 'Image' },
                { key: '3d', label: '3D' },
                { key: 'video', label: 'Video' },
                { key: 'audio', label: 'Audio' },
              ].map((chip) => (
                <button
                  key={chip.key}
                  onClick={() => setModalityFilter(chip.key)}
                  className={`text-[9px] px-1.5 py-0.5 rounded transition-colors ${
                    modalityFilter === chip.key
                      ? 'bg-accent-cyan/20 text-accent-cyan border border-accent-cyan/40'
                      : 'text-fg-muted hover:text-fg-secondary border border-transparent'
                  }`}
                >
                  {chip.label}
                </button>
              ))}
            </div>
          </div>
          <div className="px-3 py-1 text-[10px] uppercase tracking-wider text-fg-muted border-b border-border-subtle flex items-center justify-between">
            <span>Select Model</span>
            <span className="text-fg-muted normal-case">
              {filteredModels.length} / {models.length}
            </span>
          </div>
          <div className="max-h-72 overflow-y-auto">
            {sortedProviders.map((provider) => (
              <div key={provider}>
                <div className="px-3 py-1 text-[9px] uppercase tracking-wider text-accent-cyan/70 bg-bg-hover/50 sticky top-0">
                  {PROVIDER_LABELS[provider] ?? provider}
                </div>
                {grouped[provider].map((m) => {
                  const avail = availability[m.id]
                  const isAvailable = avail?.available ?? false
                  return (
                    <button
                      key={m.id}
                      onClick={() => {
                        setModel(m.id)
                        setOpen(false)
                      }}
                      className={`w-full flex items-start gap-2 px-3 py-2 text-left transition-colors ${
                        m.id === model ? 'bg-accent-cyan/10' : 'hover:bg-bg-hover'
                      } ${!isAvailable ? 'opacity-50' : ''}`}
                      title={avail?.reason ?? ''}
                    >
                      <div className="flex-1 min-w-0">
                        <div className={`text-xs font-medium flex items-center gap-1.5 ${m.id === model ? 'text-accent-cyan' : 'text-fg-primary'}`}>
                          {m.label}
                          {isAvailable ? (
                            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 inline-block" title={avail?.reason} />
                          ) : (
                            <span className="w-1.5 h-1.5 rounded-full bg-fg-muted/40 inline-block" title={avail?.reason ?? 'Unavailable'} />
                          )}
                        </div>
                        <div className="text-[10px] text-fg-muted flex items-center gap-1.5">
                          <span>{m.description}</span>
                        </div>
                        <div className="flex items-center gap-1 mt-0.5">
                          {m.modalities.map((mod) => (
                            <span
                              key={mod}
                              className="text-[8px] px-1 py-px rounded bg-bg-base text-fg-muted border border-border-subtle"
                            >
                              {MODALITY_ICONS[mod] ?? mod}
                            </span>
                          ))}
                          {m.is_local && (
                            <span className="text-[8px] px-1 py-px rounded bg-accent-gold/10 text-accent-gold">
                              LOCAL
                            </span>
                          )}
                          {m.is_open_source && !m.is_local && (
                            <span className="text-[8px] px-1 py-px rounded bg-emerald-500/10 text-emerald-400">
                              OSS
                            </span>
                          )}
                          {isGenerationModel(m) && (
                            <span className="text-[8px] px-1 py-px rounded bg-fuchsia-500/10 text-fuchsia-400">
                              GEN
                            </span>
                          )}
                        </div>
                      </div>
                      {m.id === model && (
                        <Check size={13} className="text-accent-cyan shrink-0 mt-0.5" />
                      )}
                    </button>
                  )
                })}
              </div>
            ))}
            {filteredModels.length === 0 && (
              <div className="px-3 py-6 text-center text-[11px] text-fg-muted">
                No models match your search
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

export function InputBar() {
  const [text, setText] = useState('')
  const [imagePreview, setImagePreview] = useState<string | null>(null)
  /** media_id returned by /api/agent/upload/image, forwarded in the message
   *  body so the backend can resolve the uploaded file. */
  const [imageMediaId, setImageMediaId] = useState<string | null>(null)
  /** True while an image upload is in-flight (shows a spinner overlay). */
  const [uploading, setUploading] = useState(false)
  /** True while a dragged file is hovering over the input area — used to
   *  render a drop-target highlight border. */
  const [dragOver, setDragOver] = useState(false)
  const send = useChat((s) => s.send)
  const stop = useChat((s) => s.stop)
  const isResponding = useChat((s) => s.isResponding)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const canSend = text.trim().length > 0 && !isResponding && !uploading

  const handleSend = () => {
    if (!canSend) return
    // Forward the uploaded image's media_id to the backend by prepending a
    // reference token. The chat WS message contract is unchanged
    // ({type:'message', data:{message, session_id, model}}).
    const message = imageMediaId
      ? `${text}\n\n[Image: ${imageMediaId}]`
      : text
    send(message)
    setText('')
    setImagePreview(null)
    setImageMediaId(null)
    // Reset textarea height
    if (textareaRef.current) textareaRef.current.style.height = 'auto'
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  // Auto-adjust height
  const handleInput = (value: string) => {
    setText(value)
    const el = textareaRef.current
    if (el) {
      el.style.height = 'auto'
      el.style.height = `${Math.min(el.scrollHeight, 140)}px`
    }
  }

  // Upload an image File to the workspace via /api/agent/upload/image, then
  // store the returned data_url for preview + media_id for forwarding.
  // Falls back to a local FileReader preview if the upload fails so the user
  // can still see the image they picked. Shared by the file-picker button
  // and the drag-and-drop handler.
  const uploadImageFile = (file: File) => {
    if (!file.type.startsWith('image/')) return
    setUploading(true)
    uploadChatImage(file)
      .then((img) => {
        setImagePreview(img.data_url)
        setImageMediaId(img.media_id)
      })
      .catch(() => {
        // Fallback: read locally so the user still sees their image, but
        // without a backend media_id (no [Image: ...] tag will be sent).
        const reader = new FileReader()
        reader.onload = () => {
          setImagePreview(reader.result as string)
          setImageMediaId(null)
        }
        reader.readAsDataURL(file)
      })
      .finally(() => setUploading(false))
  }

  // File-picker change handler — defers to the shared upload helper.
  const handleImageSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    uploadImageFile(file)
    // Reset the input so the same file can be selected again
    e.target.value = ''
  }

  // Drag-and-drop handlers — accept the first image file in the drop. The
  // wrapper div prevents the browser from opening the file when dropped
  // outside the target zone.
  const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    if (isResponding || uploading) return
    if (!Array.from(e.dataTransfer.types).includes('Files')) return
    e.preventDefault()
    setDragOver(true)
  }

  const handleDragLeave = (e: React.DragEvent<HTMLDivElement>) => {
    // Only clear when leaving the wrapper itself, not when crossing into a
    // child element — otherwise the highlight flickers on every child enter.
    if (e.currentTarget === e.target) setDragOver(false)
  }

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    if (isResponding || uploading) return
    e.preventDefault()
    setDragOver(false)
    const file = e.dataTransfer.files?.[0]
    if (!file) return
    uploadImageFile(file)
  }

  return (
    <div className="border-t border-border bg-bg-panel px-3 py-3">
      <div
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        className={`rounded-lg border bg-bg-elevated focus-within:border-accent-cyan/50 transition-colors px-3 py-2.5 ${
          dragOver
            ? 'border-accent-cyan ring-2 ring-accent-cyan/30'
            : 'border-border'
        }`}
      >
        {/* Drag-over hint — replaces the textarea placeholder visual when a
            file is being hovered so the user knows a drop will attach it. */}
        {dragOver && (
          <div className="flex items-center justify-center gap-2 py-3 mb-2 rounded-md border border-dashed border-accent-cyan/50 bg-accent-cyan/5 text-accent-cyan text-[11px] font-medium">
            <ImageIcon size={14} />
            <span>Drop image to attach</span>
          </div>
        )}
        {/* Prompt gallery — illustrated example prompts shown when the input
            is empty and Trigen is idle. Clicking inserts the prompt into the
            textarea (not sending it), so the user can refine before running. */}
        <PromptGallery
          onInsert={(prompt) => {
            handleInput(prompt)
            textareaRef.current?.focus()
          }}
          disabled={text.trim().length > 0 || isResponding}
        />

        {/* Image preview thumbnail (with upload-in-flight spinner overlay) */}
        {(imagePreview || uploading) && (
          <div className="mb-2 relative inline-block">
            <div className="relative h-16 w-16 rounded-md border border-border overflow-hidden bg-bg-base">
              {imagePreview ? (
                <img
                  src={imagePreview}
                  alt="Reference"
                  className="h-full w-full object-cover"
                />
              ) : (
                <div className="h-full w-full flex items-center justify-center">
                  <Loader2 size={16} className="text-accent-cyan animate-spin" />
                </div>
              )}
              {uploading && imagePreview && (
                <div className="absolute inset-0 bg-bg-base/60 flex items-center justify-center">
                  <Loader2 size={16} className="text-accent-cyan animate-spin" />
                </div>
              )}
            </div>
            <button
              onClick={() => {
                setImagePreview(null)
                setImageMediaId(null)
              }}
              aria-label="Remove image"
              disabled={uploading}
              className="absolute -top-1.5 -right-1.5 w-4 h-4 rounded-full bg-rose-500 text-white flex items-center justify-center hover:bg-rose-600 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <X size={9} />
            </button>
          </div>
        )}

        <textarea
          ref={textareaRef}
          value={text}
          onChange={(e) => handleInput(e.target.value)}
          onKeyDown={handleKeyDown}
          rows={3}
          placeholder={isResponding ? 'Trigen is creating…' : 'Describe the 3D scene you want…'}
          disabled={isResponding}
          className="w-full resize-none bg-transparent text-sm text-fg-primary placeholder:text-fg-muted outline-none leading-relaxed disabled:opacity-60 min-h-[72px]"
        />
        <div className="flex items-center justify-between mt-2 pt-2 border-t border-border-subtle">
          <div className="flex items-center gap-1">
            <ModelSelector />
            {/* Image upload button */}
            <button
              onClick={() => fileInputRef.current?.click()}
              disabled={isResponding || uploading}
              aria-label="Upload reference image"
              title="Upload a reference image for 3D generation (or drag & drop)"
              className="flex items-center justify-center w-7 h-7 rounded-md text-fg-secondary hover:text-fg-primary hover:bg-bg-hover transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {uploading ? <Loader2 size={13} className="animate-spin" /> : <ImageIcon size={13} />}
            </button>
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              onChange={handleImageSelect}
              className="hidden"
            />
          </div>
          {isResponding ? (
            <button
              onClick={stop}
              aria-label="Stop generating"
              title="Stop the current generation"
              className="shrink-0 flex items-center gap-1.5 px-3 h-8 rounded-md bg-rose-500/15 text-rose-300 border border-rose-500/30 hover:bg-rose-500/25 transition-all text-[11px] font-medium"
            >
              <Square size={13} />
              <span>Stop</span>
            </button>
          ) : (
            <button
              onClick={handleSend}
              disabled={!canSend}
              aria-label="Send message"
              className="shrink-0 flex items-center gap-1.5 px-3 h-8 rounded-md bg-accent-cyan text-bg-base disabled:bg-bg-hover disabled:text-fg-muted disabled:cursor-not-allowed hover:shadow-glow transition-all text-[11px] font-medium"
            >
              <Send size={13} />
              <span>Send</span>
            </button>
          )}
        </div>
      </div>
      <div className="mt-1.5 px-1 text-center">
        <span className="text-[10px] text-fg-muted">
          Enter to send · Shift+Enter for newline · Drop images to attach
        </span>
      </div>
    </div>
  )
}
