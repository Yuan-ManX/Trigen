// Message list: auto-scrolls to bottom, shows compact hints in empty state.
// Proactive suggestions now render per-message inside MessageBubble as a
// "Quick Actions" chip strip — see MessageBubble.tsx.
import { useCallback, useEffect, useRef, useState } from 'react'
import { motion } from 'framer-motion'
import {
  ArrowDown,
  Boxes,
  Camera,
  Home,
  Lightbulb,
  Moon,
  Orbit,
  Palette,
  Snowflake,
  Sparkles,
  Spline,
  Sunset,
  Trees,
  Waves,
} from 'lucide-react'
import { useChat } from '../../store/useChat'
import { MessageBubble } from './MessageBubble'

interface SuggestionItem {
  icon: typeof Boxes
  label: string
  prompt: string
}

const SUGGESTIONS: SuggestionItem[] = [
  { icon: Sparkles, label: 'Solar System', prompt: 'Create a solar system scene with the sun and 8 orbiting planets' },
  { icon: Boxes, label: 'Red Cube', prompt: 'Create a red metallic cube at the origin' },
  { icon: Sunset, label: 'Sunset', prompt: 'Make a sunset' },
  { icon: Moon, label: 'Night', prompt: 'Make the scene look like night' },
  { icon: Home, label: 'Living Room', prompt: 'Create a living room' },
  { icon: Home, label: 'Bedroom', prompt: 'Make a bedroom' },
  { icon: Palette, label: 'Chess Board', prompt: 'Make a chess board' },
  { icon: Waves, label: 'Water', prompt: 'Add water' },
  { icon: Lightbulb, label: 'Point Light', prompt: 'Add a warm point light above the scene' },
  { icon: Orbit, label: 'Arrange Circle', prompt: 'Arrange all objects in a circle of radius 4' },
  { icon: Camera, label: 'Flythrough', prompt: 'Add a flythrough camera animation that loops every 8 seconds' },
  { icon: Spline, label: 'Spiral Stairs', prompt: 'Use the spiral_staircase skill to build a spiral staircase with 20 steps' },
  { icon: Trees, label: 'Forest', prompt: 'Use the forest skill to scatter 12 trees with varying heights across the ground plane' },
  { icon: Snowflake, label: 'Snowman', prompt: 'Use the snowman skill to build a snowman with a carrot nose, coal eyes, stick arms, and a top hat' },
  { icon: Sparkles, label: 'Particle Fire', prompt: 'Create a fire particle system' },
]

/** Animated three-dot typing indicator — shown when the Agent is responding
 *  but hasn't produced any visible text content yet. Gives the user
 *  immediate visual feedback that their message was received and the
 *  Agent is actively processing. */
function TypingIndicator() {
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -4 }}
      transition={{ duration: 0.2 }}
      className="flex justify-start"
    >
      <div className="space-y-2">
        <div className="flex items-center gap-1.5 text-[11px] text-fg-muted">
          <Sparkles size={12} className="text-accent-gold" />
          <span>Trigen AI</span>
        </div>
        <div className="inline-flex items-center gap-1.5 rounded-md rounded-tl-sm bg-bg-elevated border border-border px-4 py-3">
          <span className="w-2 h-2 rounded-full bg-accent-cyan/60 animate-bounce" style={{ animationDelay: '0ms' }} />
          <span className="w-2 h-2 rounded-full bg-accent-cyan/60 animate-bounce" style={{ animationDelay: '150ms' }} />
          <span className="w-2 h-2 rounded-full bg-accent-cyan/60 animate-bounce" style={{ animationDelay: '300ms' }} />
        </div>
      </div>
    </motion.div>
  )
}

interface MessageListProps {
  onSuggestion: (text: string) => void
}

export function MessageList({ onSuggestion }: MessageListProps) {
  const messages = useChat((s) => s.messages)
  const isResponding = useChat((s) => s.isResponding)
  const bottomRef = useRef<HTMLDivElement>(null)
  const scrollContainerRef = useRef<HTMLDivElement>(null)
  const [showScrollDown, setShowScrollDown] = useState(false)
  // Track whether the user has manually scrolled up — disables
  // auto-scroll so they can read history while the Agent keeps streaming.
  const userScrolledUp = useRef(false)

  // Detect whether the Agent is responding but hasn't produced any
  // visible assistant text yet — this is the moment to show the typing
  // indicator. We check: (a) isResponding is true, (b) the last message
  // is either a user message (Agent hasn't started yet) or an assistant
  // message that's streaming with no content/thinking/plan/toolCalls.
  const showTyping = isResponding && (() => {
    if (messages.length === 0) return true
    const last = messages[messages.length - 1]
    if (last.role === 'user') return true
    if (last.role === 'assistant' && last.streaming) {
      return !last.content && !(last.thinking?.length) && !(last.planSteps?.length) && !(last.toolCalls?.length)
    }
    return false
  })()

  // Auto-scroll to bottom when messages change — but only if the user
  // hasn't manually scrolled up to read history.
  useEffect(() => {
    if (userScrolledUp.current) return
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages, isResponding])

  // Track scroll position to show/hide the scroll-to-bottom button and
  // detect manual upward scrolling.
  const handleScroll = useCallback(() => {
    const el = scrollContainerRef.current
    if (!el) return
    const distFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight
    const isNearBottom = distFromBottom < 80
    setShowScrollDown(!isNearBottom && messages.length > 0)
    userScrolledUp.current = !isNearBottom
  }, [messages.length])

  // Reset scroll tracking when a new message arrives at the bottom —
  // if we're near the bottom, resume auto-scroll.
  useEffect(() => {
    const el = scrollContainerRef.current
    if (!el) return
    const distFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight
    if (distFromBottom < 80) {
      userScrolledUp.current = false
    }
  }, [messages.length])

  const scrollToBottom = useCallback(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
    userScrolledUp.current = false
    setShowScrollDown(false)
  }, [])

  if (messages.length === 0) {
    return (
      <div className="flex-1 overflow-y-auto px-3 py-3 min-h-0">
        {/* Hero */}
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3 }}
          className="flex flex-col items-center text-center pt-0.5 pb-3"
        >
          <div className="relative mb-2">
            <div className="absolute inset-0 bg-accent-cyan/20 blur-xl rounded-full" />
            <div className="relative w-9 h-9 rounded-lg bg-gradient-to-br from-accent-cyan/20 to-accent-gold/10 border border-accent-cyan/30 flex items-center justify-center shadow-glow">
              <Sparkles size={16} className="text-accent-cyan" />
            </div>
          </div>
          <h3 className="text-[13px] font-semibold text-fg-primary mb-0.5">
            AI 3D Creator
          </h3>
          <p className="text-[10.5px] text-fg-muted">
            Describe what you want to build
          </p>
        </motion.div>

        {/* Suggestion grid — 3 cols to reduce vertical footprint so the
            empty state fits in the visible area and the input bar doesn't
            obscure the last rows. */}
        <div className="grid grid-cols-3 gap-1">
          {SUGGESTIONS.map((s, i) => {
            const Icon = s.icon
            return (
              <motion.button
                key={s.label}
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.25, delay: 0.04 * i }}
                onClick={() => onSuggestion(s.prompt)}
                className="group flex flex-col items-center gap-1 rounded-md border border-border bg-bg-elevated/40 hover:bg-bg-hover hover:border-accent-cyan/40 transition-all px-1 py-1.5"
              >
                <Icon size={13} className="text-fg-muted group-hover:text-accent-cyan transition-colors" />
                <span className="text-[8.5px] font-medium text-fg-secondary group-hover:text-fg-primary transition-colors text-center leading-tight">
                  {s.label}
                </span>
              </motion.button>
            )
          })}
        </div>

        {/* Tips footer — surface the less-obvious interaction affordances
            so new users discover drag-drop, the Tools browser, and the
            destructive-action confirmation toggle without reading docs. */}
        <div className="mt-3 space-y-1">
          <div className="flex items-center gap-1.5 px-0.5 text-[9px] text-fg-muted/70">
            <span className="w-1 h-1 rounded-full bg-accent-cyan/50 shrink-0" />
            <span>Drag image into chat for 3D reference.</span>
          </div>
          <div className="flex items-center gap-1.5 px-0.5 text-[9px] text-fg-muted/70">
            <span className="w-1 h-1 rounded-full bg-accent-cyan/50 shrink-0" />
            <span>Browse 87 tools in the right-panel Tools tab.</span>
          </div>
          <div className="flex items-center gap-1.5 px-0.5 text-[9px] text-fg-muted/70">
            <span className="w-1 h-1 rounded-full bg-accent-cyan/50 shrink-0" />
            <span>Toggle shield to preview destructive actions.</span>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="relative flex-1 overflow-hidden min-h-0">
      <div
        ref={scrollContainerRef}
        onScroll={handleScroll}
        className="h-full overflow-y-auto px-4 py-3 space-y-3"
      >
        {messages.map((m) => (
          <MessageBubble key={m.id} message={m} />
        ))}

        {/* Typing indicator — appears when the Agent is processing but
            hasn't emitted any visible content yet. */}
        {showTyping && <TypingIndicator />}

        <div ref={bottomRef} />
      </div>

      {/* Scroll-to-bottom floating button — appears when the user has
          scrolled up to read history. Clicking smooth-scrolls back to
          the latest message. */}
      {showScrollDown && (
        <motion.button
          initial={{ opacity: 0, scale: 0.8, y: 4 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.8, y: 4 }}
          transition={{ duration: 0.15 }}
          onClick={scrollToBottom}
          aria-label="Scroll to latest message"
          title="Scroll to latest"
          className="absolute bottom-3 left-1/2 -translate-x-1/2 flex items-center justify-center w-8 h-8 rounded-full border border-border bg-bg-elevated shadow-lg text-fg-secondary hover:text-accent-cyan hover:border-accent-cyan/40 transition-colors z-10"
        >
          <ArrowDown size={14} />
          {isResponding && (
            <span className="absolute -top-1 -right-1 w-2.5 h-2.5 rounded-full bg-accent-cyan animate-pulse border border-bg-panel" />
          )}
        </motion.button>
      )}
    </div>
  )
}
