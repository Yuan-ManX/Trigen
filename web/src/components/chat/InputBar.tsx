// 输入栏：多行输入框 + 发送按钮，回车发送、Shift+回车换行
// Input bar: multiline input box + send button, Enter to send, Shift+Enter for newline
import { Send } from 'lucide-react'
import { useRef, useState, type KeyboardEvent } from 'react'
import { useChat } from '../../store/useChat'

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
    // 重置 textarea 高度
    // Reset textarea height
    if (textareaRef.current) textareaRef.current.style.height = 'auto'
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  // 自适应高度
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
          placeholder={isResponding ? 'Trigen 正在创作中…' : '描述你想创建的 3D 场景…'}
          disabled={isResponding}
          className="flex-1 resize-none bg-transparent text-sm text-fg-primary placeholder:text-fg-muted outline-none leading-relaxed py-1 disabled:opacity-60"
        />
        <button
          onClick={handleSend}
          disabled={!canSend}
          aria-label="发送消息"
          className="shrink-0 w-8 h-8 rounded-md flex items-center justify-center bg-accent-cyan text-bg-base disabled:bg-bg-hover disabled:text-fg-muted disabled:cursor-not-allowed hover:shadow-glow transition-all"
        >
          <Send size={14} />
        </button>
      </div>
      <div className="mt-1.5 px-1 text-[10px] text-fg-muted">
        Enter 发送 · Shift+Enter 换行
      </div>
    </div>
  )
}
