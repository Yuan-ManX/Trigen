// Message list: auto-scrolls to bottom, shows compact hints in empty state.
// Proactive suggestions now render per-message inside MessageBubble as a
// "Quick Actions" chip strip — see MessageBubble.tsx.
import { useCallback, useEffect, useRef, useState } from 'react'
import { motion } from 'framer-motion'
import {
  Activity,
  ArrowDown,
  Boxes,
  Flame,
  Gem,
  Home,
  Lightbulb,
  Moon,
  Palette,
  Snowflake,
  Sparkles,
  Spline,
  Sunset,
  Trees,
  Waves,
} from 'lucide-react'
import { useChat } from '../../store/useChat'
import { useScene } from '../../store/useScene'
import { MessageBubble } from './MessageBubble'

interface SuggestionItem {
  icon: typeof Boxes
  label: string
  prompt: string
}

const SUGGESTIONS: SuggestionItem[] = [
  { icon: Sparkles, label: 'Solar System', prompt: 'Create a solar system' },
  { icon: Boxes, label: 'Red Cube', prompt: 'Create a red metallic cube at the origin' },
  { icon: Sunset, label: 'Sunset', prompt: 'Make a sunset' },
  { icon: Moon, label: 'Night', prompt: 'Make the scene look like night' },
  { icon: Home, label: 'Living Room', prompt: 'Create a living room' },
  { icon: Waves, label: 'Ocean', prompt: 'Create an ocean' },
  { icon: Trees, label: 'Forest', prompt: 'Make a forest' },
  { icon: Palette, label: 'Crystal Garden', prompt: 'Create a crystal garden' },
  { icon: Flame, label: 'Campfire', prompt: 'Make a campfire' },
  { icon: Home, label: 'Castle', prompt: 'Make a castle' },
  { icon: Spline, label: 'Staircase', prompt: 'Make a staircase' },
  { icon: Sparkles, label: 'Rainbow', prompt: 'Make a rainbow' },
  { icon: Snowflake, label: 'Snowfall', prompt: 'Make it look like winter then add snowfall' },
  { icon: Spline, label: 'City Skyline', prompt: 'Create a city' },
  { icon: Sparkles, label: 'Cave', prompt: 'Make a cave' },
  { icon: Sparkles, label: 'Cinematic Bloom', prompt: 'Add cinematic bloom and warm color grading' },
  { icon: Boxes, label: 'Hex Grid', prompt: 'Create a hex grid pattern on the ground' },
  { icon: Spline, label: 'Noise Deform', prompt: 'Create a box and add noise deformation' },
  { icon: Sparkles, label: 'Fibonacci', prompt: 'Create a fibonacci spiral of small spheres' },
]

/** Quick-start prompts surfaced when the scene is empty so the user can
 *  start creating with a single click. Uses the chat store's `send`. */
const QUICK_START_PROMPTS: SuggestionItem[] = [
  { icon: Sparkles, label: 'Glossy red sphere on a pedestal', prompt: 'Create a glossy red sphere on a pedestal' },
  { icon: Sunset, label: 'Sunset scene with warm lighting', prompt: 'Make a sunset scene with warm lighting' },
  { icon: Spline, label: 'Spiral staircase', prompt: 'Build a spiral staircase' },
  { icon: Gem, label: 'Crystal garden', prompt: 'Create a crystal garden' },
]

/** Map a total (objects + lights) to a 0-100 complexity score and label.
 *  Capped at 40 entities so typical scenes saturate near the high end. */
function complexityFor(total: number): { pct: number; label: string } {
  const pct = Math.min(100, Math.round((total / 40) * 100))
  if (total === 0) return { pct: 0, label: 'Empty' }
  if (total <= 5) return { pct, label: 'Light' }
  if (total <= 15) return { pct, label: 'Moderate' }
  if (total <= 30) return { pct, label: 'Complex' }
  return { pct, label: 'Heavy' }
}

/** Compact scene-context strip pinned at the top of the message list.
 *  Surfaces object count, light count, and a complexity meter so the user
 *  can gauge how heavy the current scene is without leaving the chat. */
function SceneContextIndicator() {
  const objects = useScene((s) => s.scene.objects.length)
  const lights = useScene((s) => s.scene.lights.length)
  const total = objects + lights
  const { pct, label } = complexityFor(total)
  // Color shifts from cyan (light) to gold (moderate) to rose (heavy).
  const meterColor =
    total <= 5 ? 'bg-accent-cyan' : total <= 15 ? 'bg-accent-gold' : 'bg-rose-400'

  return (
    <div className="sticky top-0 z-10 mb-1 py-1.5 bg-bg-panel/95 backdrop-blur-sm border-b border-border-subtle">
      <div className="flex items-center gap-2.5 text-[10px] text-fg-muted">
        <span className="flex items-center gap-1">
          <Boxes size={10} className="text-accent-cyan/70" />
          <span className="font-mono text-fg-secondary">{objects}</span>
          <span className="text-fg-muted/70">obj</span>
        </span>
        <span className="flex items-center gap-1">
          <Lightbulb size={10} className="text-accent-gold/70" />
          <span className="font-mono text-fg-secondary">{lights}</span>
          <span className="text-fg-muted/70">lights</span>
        </span>
        <div className="ml-auto flex items-center gap-1.5">
          <Activity size={10} className="text-fg-muted/70" />
          <div className="h-1 w-12 rounded-full bg-bg-base overflow-hidden">
            <div
              className={`h-full rounded-full transition-all duration-300 ${meterColor}`}
              style={{ width: `${pct}%` }}
            />
          </div>
          <span className="text-fg-muted font-mono w-12 text-right">{label}</span>
        </div>
      </div>
    </div>
  )
}

/** Prominent quick-start card shown when the scene has no objects yet.
 *  Clicking a prompt sends it straight to the Agent via the chat store. */
function QuickStartCard() {
  const send = useChat((s) => s.send)
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25 }}
      className="rounded-lg border border-accent-cyan/25 bg-gradient-to-br from-accent-cyan/8 to-accent-gold/5 p-2.5 mb-1"
    >
      <div className="flex items-center gap-1.5 mb-2">
        <Sparkles size={11} className="text-accent-cyan" />
        <span className="text-[11px] font-semibold text-fg-primary">Quick Start</span>
        <span className="text-[9px] text-fg-muted ml-auto">Empty scene</span>
      </div>
      <div className="grid grid-cols-2 gap-1.5">
        {QUICK_START_PROMPTS.map((p) => {
          const Icon = p.icon
          return (
            <button
              key={p.label}
              onClick={() => send(p.prompt)}
              className="group flex items-start gap-1.5 rounded-md border border-border bg-bg-elevated/60 hover:bg-bg-hover hover:border-accent-cyan/40 transition-all px-2 py-1.5 text-left"
            >
              <Icon size={11} className="text-fg-muted group-hover:text-accent-cyan transition-colors shrink-0 mt-0.5" />
              <span className="text-[9.5px] font-medium text-fg-secondary group-hover:text-fg-primary transition-colors leading-tight">
                {p.label}
              </span>
            </button>
          )
        })}
      </div>
    </motion.div>
  )
}

/** Animated typing indicator with phase-aware label — shown when the Agent
 *  is responding but hasn't produced any visible text content yet. The
 *  label cycles through processing phases to give the user a sense of
 *  what the Agent is doing. */
const TYPING_PHASES = ['Understanding', 'Planning', 'Executing', 'Reflecting'] as const

function TypingIndicator() {
  const [phaseIdx, setPhaseIdx] = useState(0)
  useEffect(() => {
    const timer = setInterval(() => {
      setPhaseIdx((i) => (i + 1) % TYPING_PHASES.length)
    }, 1800)
    return () => clearInterval(timer)
  }, [])

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
        <div className="inline-flex items-center gap-2 rounded-md rounded-tl-sm bg-bg-elevated border border-border px-4 py-3">
          <span className="w-2 h-2 rounded-full bg-accent-cyan/60 animate-bounce" style={{ animationDelay: '0ms' }} />
          <span className="w-2 h-2 rounded-full bg-accent-cyan/60 animate-bounce" style={{ animationDelay: '150ms' }} />
          <span className="w-2 h-2 rounded-full bg-accent-cyan/60 animate-bounce" style={{ animationDelay: '300ms' }} />
          <motion.span
            key={phaseIdx}
            initial={{ opacity: 0, x: -4 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.3 }}
            className="text-[10px] text-fg-muted ml-1 font-mono"
          >
            {TYPING_PHASES[phaseIdx]}…
          </motion.span>
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
  // Scene object count — drives the Quick Start card visibility when the
  // scene has no geometry yet, regardless of whether messages exist.
  const sceneObjectCount = useScene((s) => s.scene.objects.length)
  const sceneEmpty = sceneObjectCount === 0
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
        {/* Scene context strip — object/light counts + complexity meter */}
        <SceneContextIndicator />

        {/* Quick Start card — prominent when the scene is empty so the
            user can begin creating with a single click. */}
        {sceneEmpty && <QuickStartCard />}

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
        {/* Scene context strip — object/light counts + complexity meter,
            pinned to the top of the scroll area. */}
        <SceneContextIndicator />

        {/* Quick Start card — shown when the scene has no objects yet so
            the user can jump back into creating after clearing the scene. */}
        {sceneEmpty && <QuickStartCard />}

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
