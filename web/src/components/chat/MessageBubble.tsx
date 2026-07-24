// 消息气泡：用户消息靠右、助手消息靠左，支持流式光标与工具调用
// Message bubble: user messages on the right, assistant messages on the left, supports streaming cursor and tool calls
import { motion } from 'framer-motion'
import { AlertTriangle, Sparkles } from 'lucide-react'
import type { ChatMessage } from '../../store/useChat'
import { ToolCallCard } from './ToolCallCard'

interface MessageBubbleProps {
  message: ChatMessage
}

export function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === 'user'

  if (isUser) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.18 }}
        className="flex justify-end"
      >
        <div className="max-w-[88%] rounded-md rounded-tr-sm bg-accent-cyan/15 border border-accent-cyan/30 px-3 py-2 text-sm text-fg-primary whitespace-pre-wrap break-words">
          {message.content}
        </div>
      </motion.div>
    )
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.18 }}
      className="flex justify-start"
    >
      <div className="max-w-[92%] w-full space-y-2">
        <div className="flex items-center gap-1.5 text-[11px] text-fg-muted">
          <Sparkles size={12} className="text-accent-gold" />
          <span>Trigen AI</span>
        </div>

        {/* 工具调用 */}
        {/* Tool calls */}
        {message.toolCalls && message.toolCalls.length > 0 && (
          <div className="space-y-1.5">
            {message.toolCalls.map((c) => (
              <ToolCallCard key={c.id} call={c} />
            ))}
          </div>
        )}

        {/* 文本内容 */}
        {/* Text content */}
        {(message.content || message.streaming) && (
          <div className="rounded-md rounded-tl-sm bg-bg-elevated border border-border px-3 py-2 text-sm text-fg-primary whitespace-pre-wrap break-words">
            {message.content}
            {message.streaming && (
              <span className="inline-block w-1.5 h-3.5 ml-0.5 bg-accent-cyan align-middle animate-pulse" />
            )}
          </div>
        )}

        {/* 错误 */}
        {/* Error */}
        {message.error && (
          <div className="flex items-start gap-2 rounded-md border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-xs text-rose-300">
            <AlertTriangle size={13} className="mt-0.5 shrink-0" />
            <span className="break-words">{message.error}</span>
          </div>
        )}
      </div>
    </motion.div>
  )
}
