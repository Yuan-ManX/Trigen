// Input bar: model selector + multiline input box + send button
import { Check, ChevronDown, Send } from 'lucide-react'
import { useEffect, useRef, useState, type KeyboardEvent } from 'react'
import { useChat } from '../../store/useChat'

/** Available LLM models */
const MODELS = [
  { id: 'trigen-default', label: 'Trigen Default', desc: 'Offline rule engine' },
  { id: 'gpt-4o', label: 'GPT-4o', desc: 'OpenAI flagship multimodal' },
  { id: 'gpt-4o-mini', label: 'GPT-4o Mini', desc: 'Fast and efficient' },
  { id: 'claude-3.5-sonnet', label: 'Claude 3.5 Sonnet', desc: 'Anthropic reasoning' },
  { id: 'deepseek-v3', label: 'DeepSeek V3', desc: 'Open-source MoE' },
  { id: 'qwen-plus', label: 'Qwen Plus', desc: 'Alibaba Cloud LLM' },
] as const

/** Model selector dropdown (ChatGPT-style) */
function ModelSelector() {
  const model = useChat((s) => s.model)
  const setModel = useChat((s) => s.setModel)
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  const current = MODELS.find((m) => m.id === model) ?? MODELS[0]

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

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1.5 px-2 py-1 rounded-md text-[11px] text-fg-secondary hover:text-fg-primary hover:bg-bg-hover transition-colors border border-transparent hover:border-border"
      >
        <span className="font-medium">{current.label}</span>
        <ChevronDown size={12} className={`transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>

      {open && (
        <div className="absolute bottom-full left-0 mb-1.5 w-64 rounded-md border border-border bg-bg-elevated shadow-lg overflow-hidden z-50">
          <div className="px-3 py-1.5 text-[10px] uppercase tracking-wider text-fg-muted border-b border-border-subtle">
            Select Model
          </div>
          <div className="max-h-64 overflow-y-auto">
            {MODELS.map((m) => (
              <button
                key={m.id}
                onClick={() => {
                  setModel(m.id)
                  setOpen(false)
                }}
                className={`w-full flex items-start gap-2 px-3 py-2 text-left transition-colors ${
                  m.id === model ? 'bg-accent-cyan/10' : 'hover:bg-bg-hover'
                }`}
              >
                <div className="flex-1 min-w-0">
                  <div className={`text-xs font-medium ${m.id === model ? 'text-accent-cyan' : 'text-fg-primary'}`}>
                    {m.label}
                  </div>
                  <div className="text-[10px] text-fg-muted">{m.desc}</div>
                </div>
                {m.id === model && (
                  <Check size={13} className="text-accent-cyan shrink-0 mt-0.5" />
                )}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

export function InputBar() {
  const [text, setText] = useState('')
  const send = useChat((s) => s.send)
  const isResponding = useChat((s) => s.isResponding)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const canSend = text.trim().length > 0 && !isResponding

  const handleSend = () => {
    if (!canSend) return
    send(text)
    setText('')
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

  return (
    <div className="border-t border-border bg-bg-panel px-3 py-3">
      <div className="flex items-end gap-2 rounded-md border border-border bg-bg-elevated focus-within:border-accent-cyan/50 transition-colors px-2.5 py-1.5">
        <textarea
          ref={textareaRef}
          value={text}
          onChange={(e) => handleInput(e.target.value)}
          onKeyDown={handleKeyDown}
          rows={1}
          placeholder={isResponding ? 'Trigen is creating…' : 'Describe the 3D scene you want…'}
          disabled={isResponding}
          className="flex-1 resize-none bg-transparent text-sm text-fg-primary placeholder:text-fg-muted outline-none leading-relaxed py-1 disabled:opacity-60"
        />
        <button
          onClick={handleSend}
          disabled={!canSend}
          aria-label="Send message"
          className="shrink-0 w-8 h-8 rounded-md flex items-center justify-center bg-accent-cyan text-bg-base disabled:bg-bg-hover disabled:text-fg-muted disabled:cursor-not-allowed hover:shadow-glow transition-all"
        >
          <Send size={14} />
        </button>
      </div>
      <div className="mt-1.5 px-1 flex items-center justify-between">
        <ModelSelector />
        <span className="text-[10px] text-fg-muted">
          Enter to send · Shift+Enter for newline
        </span>
      </div>
    </div>
  )
}
