// 消息列表：自动滚动到底部，空状态显示引导提示
// Message list: auto-scrolls to bottom, shows guided hints in empty state
import { useEffect, useRef } from 'react'
import { Boxes, MessageSquare } from 'lucide-react'
import { useChat } from '../../store/useChat'
import { MessageBubble } from './MessageBubble'

const SUGGESTIONS = [
  '创建一个红色的金属立方体',
  '在场景里放一个发光的球体',
  '生成三个不同颜色的圆柱体并排排列',
  '把所有物体的材质改成线框模式',
]

interface MessageListProps {
  onSuggestion: (text: string) => void
}

export function MessageList({ onSuggestion }: MessageListProps) {
  const messages = useChat((s) => s.messages)
  const isResponding = useChat((s) => s.isResponding)
  const bottomRef = useRef<HTMLDivElement>(null)

  // 消息变化时滚动到底部
  // Scroll to bottom when messages change
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages, isResponding])

  if (messages.length === 0) {
    return (
      <div className="flex-1 overflow-y-auto px-4 py-6">
        <div className="flex flex-col items-center text-center py-8">
          <div className="w-12 h-12 rounded-md bg-accent-cyan/10 border border-accent-cyan/30 flex items-center justify-center mb-4 shadow-glow">
            <Boxes size={22} className="text-accent-cyan" />
          </div>
          <h3 className="text-sm font-semibold text-fg-primary mb-1">
            开始用自然语言创作 3D
          </h3>
          <p className="text-xs text-fg-secondary max-w-[260px] leading-relaxed">
            描述你想要的场景，Trigen AI 会实时生成并编辑 3D 对象。
          </p>

          <div className="mt-6 w-full space-y-2">
            <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-fg-muted px-1">
              <MessageSquare size={11} />
              试试这些
            </div>
            {SUGGESTIONS.map((s) => (
              <button
                key={s}
                onClick={() => onSuggestion(s)}
                className="w-full text-left text-xs text-fg-secondary hover:text-fg-primary hover:border-accent-cyan/40 hover:bg-bg-hover transition-colors rounded-md border border-border bg-bg-elevated/50 px-3 py-2"
              >
                {s}
              </button>
            ))}
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
      {messages.map((m) => (
        <MessageBubble key={m.id} message={m} />
      ))}
      <div ref={bottomRef} />
    </div>
  )
}
