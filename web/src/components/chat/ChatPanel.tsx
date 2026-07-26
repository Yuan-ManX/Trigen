// Chat panel container: header title + message list + input bar
import { Eraser, PanelLeftClose, Radio } from 'lucide-react'
import { useChat } from '../../store/useChat'
import { InputBar } from './InputBar'
import { MessageList } from './MessageList'

interface ChatPanelProps {
  onCollapse: () => void
}

export function ChatPanel({ onCollapse }: ChatPanelProps) {
  const send = useChat((s) => s.send)
  const isResponding = useChat((s) => s.isResponding)
  const clearMessages = useChat((s) => s.clearMessages)
  const hasMessages = useChat((s) => s.messages.length > 0)

  return (
    <aside className="flex flex-col w-[400px] h-full shrink-0 border-r border-border bg-bg-panel">
      {/* Header */}
      <header className="flex items-center justify-between h-11 px-4 border-b border-border">
        <div className="flex items-center gap-2">
          <Radio
            size={13}
            className={
              isResponding
                ? 'text-accent-gold animate-pulse'
                : 'text-accent-cyan'
            }
          />
          <span className="text-xs font-semibold text-fg-primary tracking-wide">
            Chat
          </span>
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={clearMessages}
            disabled={!hasMessages}
            aria-label="Clear chat messages"
            title="Clear chat"
            className="flex items-center justify-center w-7 h-7 rounded text-fg-muted hover:text-fg-primary hover:bg-bg-hover transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
          >
            <Eraser size={14} />
          </button>
          <button
            onClick={onCollapse}
            aria-label="Collapse chat panel"
            className="flex items-center justify-center w-7 h-7 rounded text-fg-muted hover:text-fg-primary hover:bg-bg-hover transition-colors"
          >
            <PanelLeftClose size={16} />
          </button>
        </div>
      </header>

      <MessageList onSuggestion={send} />
      <InputBar />
    </aside>
  )
}
