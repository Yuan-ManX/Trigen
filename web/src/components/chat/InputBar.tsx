// Input bar: model selector + image upload + multiline input box + send button
import { Check, ChevronDown, Image as ImageIcon, Send, X } from 'lucide-react'
import { useEffect, useRef, useState, type KeyboardEvent } from 'react'
import {
  fetchModelAvailability,
  fetchModels,
  isGenerationModel,
  type ModelAvailability,
  type ModelEntry,
} from '../../api/client'
import { useChat } from '../../store/useChat'

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

/** Model selector dropdown (ChatGPT-style, categorized) */
function ModelSelector() {
  const model = useChat((s) => s.model)
  const setModel = useChat((s) => s.setModel)
  const [open, setOpen] = useState(false)
  const [models, setModels] = useState<ModelEntry[]>(FALLBACK_MODELS)
  const [availability, setAvailability] = useState<Record<string, ModelAvailability>>({})
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

  const grouped = groupByProvider(models)
  const providerOrder = ['local', 'openai', 'anthropic', 'deepseek', 'qwen', 'zhipu', 'moonshot', 'groq', 'together', 'fireworks', 'openrouter', 'ollama', 'baichuan', 'minimax', 'spark']
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
        <div className="absolute bottom-full left-0 mb-1.5 w-72 rounded-md border border-border bg-bg-elevated shadow-lg overflow-hidden z-50">
          <div className="px-3 py-1.5 text-[10px] uppercase tracking-wider text-fg-muted border-b border-border-subtle flex items-center justify-between">
            <span>Select Model</span>
            <span className="text-fg-muted normal-case">{models.length} models</span>
          </div>
          <div className="max-h-80 overflow-y-auto">
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
          </div>
        </div>
      )}
    </div>
  )
}

export function InputBar() {
  const [text, setText] = useState('')
  const [imagePreview, setImagePreview] = useState<string | null>(null)
  const send = useChat((s) => s.send)
  const isResponding = useChat((s) => s.isResponding)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const canSend = text.trim().length > 0 && !isResponding

  const handleSend = () => {
    if (!canSend) return
    // Include image reference in the message if present
    const message = imagePreview
      ? `${text}\n\n[Reference image attached]`
      : text
    send(message)
    setText('')
    setImagePreview(null)
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

  // Handle image upload
  const handleImageSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    if (!file.type.startsWith('image/')) return

    const reader = new FileReader()
    reader.onload = () => {
      setImagePreview(reader.result as string)
    }
    reader.readAsDataURL(file)
    // Reset the input so the same file can be selected again
    e.target.value = ''
  }

  return (
    <div className="border-t border-border bg-bg-panel px-3 py-3">
      <div className="rounded-lg border border-border bg-bg-elevated focus-within:border-accent-cyan/50 transition-colors px-3 py-2.5">
        {/* Image preview thumbnail */}
        {imagePreview && (
          <div className="mb-2 relative inline-block">
            <img
              src={imagePreview}
              alt="Reference"
              className="h-16 w-16 object-cover rounded-md border border-border"
            />
            <button
              onClick={() => setImagePreview(null)}
              aria-label="Remove image"
              className="absolute -top-1.5 -right-1.5 w-4 h-4 rounded-full bg-rose-500 text-white flex items-center justify-center hover:bg-rose-600 transition-colors"
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
              disabled={isResponding}
              aria-label="Upload reference image"
              title="Upload a reference image for 3D generation"
              className="flex items-center justify-center w-7 h-7 rounded-md text-fg-secondary hover:text-fg-primary hover:bg-bg-hover transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <ImageIcon size={13} />
            </button>
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              onChange={handleImageSelect}
              className="hidden"
            />
          </div>
          <button
            onClick={handleSend}
            disabled={!canSend}
            aria-label="Send message"
            className="shrink-0 flex items-center gap-1.5 px-3 h-8 rounded-md bg-accent-cyan text-bg-base disabled:bg-bg-hover disabled:text-fg-muted disabled:cursor-not-allowed hover:shadow-glow transition-all text-[11px] font-medium"
          >
            <Send size={13} />
            <span>Send</span>
          </button>
        </div>
      </div>
      <div className="mt-1.5 px-1 text-center">
        <span className="text-[10px] text-fg-muted">
          Enter to send · Shift+Enter for newline
        </span>
      </div>
    </div>
  )
}
