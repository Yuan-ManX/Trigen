// Message bubble: user messages on the right, assistant messages on the left, supports streaming cursor and tool calls
import { motion } from 'framer-motion'
import { AlertTriangle, Brain, ChevronDown, ChevronRight, RefreshCw, Sparkles } from 'lucide-react'
import { useState } from 'react'
import { useChat } from '../../store/useChat'
import type { ChatMessage, ThinkingTrace } from '../../store/useChat'
import { PlanTrace } from './PlanTrace'
import { ToolCallCard } from './ToolCallCard'

interface MessageBubbleProps {
  message: ChatMessage
}

/** Collapsible reasoning trace card */
function ThinkingCard({ traces }: { traces: ThinkingTrace[] }) {
  const [open, setOpen] = useState(false)
  const lastPhase = traces[traces.length - 1]?.phase ?? ''
  const reflectionCount = traces.filter((t) => t.phase === 'reflection').length
  const isReflecting = lastPhase === 'reflection'

  return (
    <div className={`rounded-md border overflow-hidden ${
      isReflecting ? 'border-rose-400/30 bg-rose-500/5' : 'border-accent-gold/25 bg-accent-gold/5'
    }`}>
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-2 px-3 py-2 text-left"
      >
        <Brain size={13} className={isReflecting ? 'text-rose-400' : 'text-accent-gold'} />
        <span className="text-[11px] font-medium text-fg-secondary">
          Reasoning · {lastPhase || 'thinking'}
          {traces.length > 1 && (
            <span className="text-fg-muted ml-1">({traces.length} steps)</span>
          )}
          {reflectionCount > 0 && (
            <span className="text-rose-400 ml-1">· {reflectionCount} reflection{reflectionCount > 1 ? 's' : ''}</span>
          )}
        </span>
        {open ? (
          <ChevronDown size={12} className="ml-auto text-fg-muted" />
        ) : (
          <ChevronRight size={12} className="ml-auto text-fg-muted" />
        )}
      </button>
      {open && (
        <div className="px-3 pb-2 space-y-1.5">
          {traces.map((t, i) => {
            const isReflection = t.phase === 'reflection'
            return (
              <div key={i} className={`text-[11px] leading-relaxed ${
                isReflection ? 'text-rose-300' : 'text-fg-secondary'
              }`}>
                <span className={`font-mono ${isReflection ? 'text-rose-400' : 'text-accent-gold/80'}`}>[{t.phase}]</span>{' '}
                {t.content}
                {t.tools && t.tools.length > 0 && (
                  <span className="text-fg-muted"> → {t.tools.join(', ')}</span>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

export function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === 'user'
  const retry = useChat((s) => s.retry)
  const isResponding = useChat((s) => s.isResponding)

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

        {/* Reasoning trace */}
        {message.thinking && message.thinking.length > 0 && (
          <ThinkingCard traces={message.thinking} />
        )}

        {/* Live execution-plan checklist */}
        {message.planSteps && message.planSteps.length > 0 && (
          <PlanTrace steps={message.planSteps} />
        )}

        {/* Tool calls */}
        {message.toolCalls && message.toolCalls.length > 0 && (
          <div className="space-y-1.5">
            {message.toolCalls.map((c) => (
              <ToolCallCard key={c.id} call={c} />
            ))}
          </div>
        )}

        {/* Text content */}
        {(message.content || message.streaming) && (
          <div className="rounded-md rounded-tl-sm bg-bg-elevated border border-border px-3 py-2 text-sm text-fg-primary whitespace-pre-wrap break-words">
            {message.content}
            {message.streaming && (
              <span className="inline-block w-1.5 h-3.5 ml-0.5 bg-accent-cyan align-middle animate-pulse" />
            )}
          </div>
        )}

        {/* Error */}
        {message.error && (
          <div className="rounded-md border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-xs text-rose-300">
            <div className="flex items-start gap-2">
              <AlertTriangle size={13} className="mt-0.5 shrink-0" />
              <span className="break-words flex-1">{message.error}</span>
            </div>
            <button
              onClick={() => retry()}
              disabled={isResponding}
              className="mt-2 flex items-center gap-1.5 px-2 py-1 rounded text-[10px] font-medium bg-rose-500/20 text-rose-200 hover:bg-rose-500/30 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              <RefreshCw size={10} className={isResponding ? 'animate-spin' : ''} />
              {isResponding ? 'Retrying…' : 'Retry'}
            </button>
          </div>
        )}
      </div>
    </motion.div>
  )
}
