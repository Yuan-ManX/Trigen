// Message list: auto-scrolls to bottom, shows compact hints in empty state
import { useEffect, useRef } from 'react'
import { motion } from 'framer-motion'
import { Boxes, Lightbulb, Orbit, Sparkles } from 'lucide-react'
import { useChat } from '../../store/useChat'
import { MessageBubble } from './MessageBubble'

interface SuggestionItem {
  icon: typeof Boxes
  label: string
  prompt: string
}

const SUGGESTIONS: SuggestionItem[] = [
  { icon: Sparkles, label: 'Solar System', prompt: 'Create a solar system scene' },
  { icon: Boxes, label: 'Red Cube', prompt: 'Create a red metallic cube' },
  { icon: Lightbulb, label: 'Point Light', prompt: 'Add a point light' },
  { icon: Orbit, label: 'Arrange Circle', prompt: 'Arrange all objects in a circle' },
]

interface MessageListProps {
  onSuggestion: (text: string) => void
}

export function MessageList({ onSuggestion }: MessageListProps) {
  const messages = useChat((s) => s.messages)
  const isResponding = useChat((s) => s.isResponding)
  const bottomRef = useRef<HTMLDivElement>(null)

  // Scroll to bottom when messages change
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages, isResponding])

  if (messages.length === 0) {
    return (
      <div className="flex-1 overflow-y-auto px-4 py-4">
        {/* Hero */}
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3 }}
          className="flex flex-col items-center text-center pt-1 pb-4"
        >
          <div className="relative mb-2.5">
            <div className="absolute inset-0 bg-accent-cyan/20 blur-xl rounded-full" />
            <div className="relative w-10 h-10 rounded-lg bg-gradient-to-br from-accent-cyan/20 to-accent-gold/10 border border-accent-cyan/30 flex items-center justify-center shadow-glow">
              <Sparkles size={18} className="text-accent-cyan" />
            </div>
          </div>
          <h3 className="text-sm font-semibold text-fg-primary mb-0.5">
            AI 3D Creator
          </h3>
          <p className="text-[11px] text-fg-muted">
            Describe what you want to build
          </p>
        </motion.div>

        {/* Suggestion grid */}
        <div className="grid grid-cols-2 gap-1.5">
          {SUGGESTIONS.map((s, i) => {
            const Icon = s.icon
            return (
              <motion.button
                key={s.label}
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.25, delay: 0.05 * i }}
                onClick={() => onSuggestion(s.prompt)}
                className="group flex flex-col items-center gap-1.5 rounded-lg border border-border bg-bg-elevated/40 hover:bg-bg-hover hover:border-accent-cyan/40 transition-all px-2 py-2.5"
              >
                <Icon size={15} className="text-fg-muted group-hover:text-accent-cyan transition-colors" />
                <span className="text-[10px] font-medium text-fg-secondary group-hover:text-fg-primary transition-colors">
                  {s.label}
                </span>
              </motion.button>
            )
          })}
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
