// Message list: auto-scrolls to bottom, shows compact hints in empty state.
// Proactive suggestions now render per-message inside MessageBubble as a
// "Quick Actions" chip strip — see MessageBubble.tsx.
import { useEffect, useRef } from 'react'
import { motion } from 'framer-motion'
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
  // Generative geometry quick-start chips — one-click procedural generation
  { icon: Boxes, label: 'Geodesic Dome', prompt: 'Create a geodesic dome with detail 2' },
  { icon: Spline, label: 'Fractal Tree', prompt: 'Create a fractal tree with branching 3 and depth 3' },
  { icon: Boxes, label: 'Gyroid Lattice', prompt: 'Create a gyroid lattice with resolution 8' },
  // Trigen tools quick-start chips — voxel, particles, LOD, and evaluation
  { icon: Boxes, label: 'Voxel Sculpt', prompt: 'Create a voxel sphere with radius 3' },
  { icon: Sparkles, label: 'Particle Fire', prompt: 'Create a fire particle system' },
  { icon: Boxes, label: 'LOD Chain', prompt: 'Generate LOD chain for the first object' },
  { icon: Cog, label: 'Self Evaluate', prompt: 'Evaluate the scene quality' },
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

      <div ref={bottomRef} />
    </div>
  )
}
