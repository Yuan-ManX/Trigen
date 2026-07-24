// 对话面板容器：头部标题 + 消息列表 + 输入栏
// Chat panel container: header title + message list + input bar
import { PanelLeftClose, Radio } from 'lucide-react'
import { useChat } from '../../store/useChat'
import { InputBar } from './InputBar'
import { MessageList } from './MessageList'

interface ChatPanelProps {
  onCollapse: () => void
}

export function ChatPanel({ onCollapse }: ChatPanelProps) {
  const send = useChat((s) => s.send)
  const isResponding = useChat((s) => s.isResponding)

  return (
    <aside className="flex flex-col w-[380px] shrink-0 border-r border-border bg-bg-panel">
      {/* 头部 */}
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
            对话创作
          </span>
        </div>
        <button
          onClick={onCollapse}
          aria-label="折叠对话面板"
          className="text-fg-muted hover:text-fg-primary transition-colors"
        >
          <PanelLeftClose size={16} />
        </button>
      </header>

      <MessageList onSuggestion={send} />
      <InputBar />
    </aside>
  )
}
