// Message list: auto-scrolls to bottom, shows compact hints in empty state
// Renders Agent-produced proactive suggestions after the latest assistant turn.
import { useEffect, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Boxes,
  Camera,
  Cog,
  FlaskConical,
  Lightbulb,
  Orbit,
  Snowflake,
  Sparkles,
  Spline,
  Trees,
  Wand2,
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
  { icon: Lightbulb, label: 'Point Light', prompt: 'Add a warm point light above the scene' },
  { icon: Orbit, label: 'Arrange Circle', prompt: 'Arrange all objects in a circle of radius 4' },
  { icon: Camera, label: 'Camera Flythrough', prompt: 'Add a flythrough camera animation that loops every 8 seconds' },
  { icon: Spline, label: 'Spiral Staircase', prompt: 'Use the spiral_staircase skill to build a spiral staircase with 20 steps' },
  { icon: Trees, label: 'Forest', prompt: 'Use the forest skill to scatter 12 trees with varying heights across the ground plane' },
  // Creative skill quick-start chips — each invokes a registered offline skill
  { icon: Cog, label: 'Gear Assembly', prompt: 'Use the gear_assembly skill to build a row of 3 interlocking gears with 12 teeth each' },
  { icon: FlaskConical, label: 'Molecule', prompt: 'Use the molecule skill to build a ball-and-stick molecule with 4 satellite atoms and bonds' },
  { icon: Snowflake, label: 'Snowman', prompt: 'Use the snowman skill to build a snowman with a carrot nose, coal eyes, stick arms, and a top hat' },
]

interface MessageListProps {
  onSuggestion: (text: string) => void
}

export function MessageList({ onSuggestion }: MessageListProps) {
  const messages = useChat((s) => s.messages)
  const isResponding = useChat((s) => s.isResponding)
  const agentSuggestions = useChat((s) => s.suggestions)
  const bottomRef = useRef<HTMLDivElement>(null)

  // Scroll to bottom when messages change
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages, isResponding, agentSuggestions])

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

        {/* Tips footer — surface the less-obvious interaction affordances
            so new users discover drag-drop, the Tools browser, and the
            destructive-action confirmation toggle without reading docs. */}
        <div className="mt-4 space-y-1.5">
          <div className="flex items-center gap-1.5 px-1 text-[9.5px] text-fg-muted/70">
            <span className="w-1 h-1 rounded-full bg-accent-cyan/50 shrink-0" />
            <span>Drag an image into the chat to use it as a 3D reference.</span>
          </div>
          <div className="flex items-center gap-1.5 px-1 text-[9.5px] text-fg-muted/70">
            <span className="w-1 h-1 rounded-full bg-accent-cyan/50 shrink-0" />
            <span>Browse all 87 tools in the right-panel Tools tab.</span>
          </div>
          <div className="flex items-center gap-1.5 px-1 text-[9.5px] text-fg-muted/70">
            <span className="w-1 h-1 rounded-full bg-accent-cyan/50 shrink-0" />
            <span>Toggle the shield to preview destructive actions before they run.</span>
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

      {/* Proactive suggestions produced by the Agent after the latest turn.
          Hidden while the Agent is streaming so they don't compete for focus. */}
      <AnimatePresence>
        {!isResponding && agentSuggestions.length > 0 && (
          <motion.div
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            transition={{ duration: 0.25 }}
            className="pt-1"
          >
            <div className="flex items-center gap-1.5 mb-1.5 px-0.5">
              <Wand2 size={11} className="text-accent-gold" />
              <span className="text-[10px] uppercase tracking-wider font-semibold text-fg-muted">
                Next steps
              </span>
            </div>
            <div className="grid grid-cols-1 gap-1.5">
              {agentSuggestions.slice(0, 3).map((s, i) => {
                const prompt = buildSuggestionPrompt(s)
                return (
                  <motion.button
                    key={`${s.name}-${i}`}
                    initial={{ opacity: 0, y: 4 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.2, delay: 0.04 * i }}
                    onClick={() => onSuggestion(prompt)}
                    title={s.rationale}
                    className="group text-left rounded-lg border border-border bg-bg-elevated/40 hover:bg-bg-hover hover:border-accent-gold/40 transition-all px-2.5 py-2"
                  >
                    <div className="flex items-baseline justify-between gap-2">
                      <span className="text-[11px] font-semibold text-fg-primary group-hover:text-accent-gold transition-colors">
                        {s.name}
                      </span>
                      <span className="text-[9px] text-fg-muted uppercase tracking-wider shrink-0">
                        {s.skill_or_tool}
                      </span>
                    </div>
                    <p className="text-[10px] text-fg-secondary mt-0.5 leading-relaxed">
                      {s.description}
                    </p>
                  </motion.button>
                )
              })}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <div ref={bottomRef} />
    </div>
  )
}

/** Convert a structured Suggestion into a concise natural-language prompt the
 *  user can send back to the Agent. Prefers the suggested arguments; falls back
 *  to the suggestion name so the click always produces an actionable message. */
function buildSuggestionPrompt(s: {
  name: string
  description: string
  arguments: Record<string, unknown>
}): string {
  const argValues = Object.values(s.arguments ?? {}).filter(Boolean)
  if (argValues.length === 0) return s.name
  // Join compact scalar values; ignore nested objects/arrays for brevity
  const parts = argValues
    .filter((v) => typeof v === 'string' || typeof v === 'number' || typeof v === 'boolean')
    .map((v) => String(v))
  if (parts.length === 0) return s.name
  return `${s.name}: ${parts.join(', ')}`
}
