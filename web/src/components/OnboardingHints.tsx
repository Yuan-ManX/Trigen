// First-visit coachmark overlay: a short welcome tour that walks new users
// through the chat panel, scene templates, tools catalog, and keyboard
// shortcuts. Dismissal is persisted in localStorage so it only shows once
// (unless the user explicitly reopens it from the toolbar).
import { AnimatePresence, motion } from 'framer-motion'
import {
  ArrowLeft,
  ArrowRight,
  Brain,
  Check,
  Clapperboard,
  ClipboardCheck,
  Film,
  GitCommitVertical,
  Keyboard,
  MessageSquare,
  MousePointerClick,
  ShieldCheck,
  Sparkles,
  Tag,
  Users,
  Wand2,
  Workflow,
  X,
} from 'lucide-react'
import { useEffect, useState } from 'react'

const STORAGE_KEY = 'trigen_onboarding_done'

type StepId =
  | 'chat'
  | 'templates'
  | 'tools'
  | 'ensemble'
  | 'scene_intelligence'
  | 'pipeline'
  | 'annotations'
  | 'multi_select'
  | 'timeline'
  | 'checkpoints'
  | 'storyboard'
  | 'critique'
  | 'constraints'
  | 'shortcuts'

interface TourStep {
  id: StepId
  icon: typeof MessageSquare
  accent: string
  title: string
  body: string
  hint: string
}

const STEPS: TourStep[] = [
  {
    id: 'chat',
    icon: MessageSquare,
    accent: 'text-accent-cyan',
    title: 'Describe it, build it',
    body: 'Type natural language into the left chat panel — "a glossy red sphere on a marble pedestal, three-point lighting". The Agent plans tool calls, executes them, and streams the result back into the live scene.',
    hint: 'Tip: mention materials, lighting, and counts in one sentence for the richest results.',
  },
  {
    id: 'templates',
    icon: Sparkles,
    accent: 'text-accent-purple',
    title: 'Start from a template',
    body: 'Scene Templates drop in pre-built compositions — colonnade, forest, crystal garden, DNA helix, spiral galaxy, studio lighting, spiral staircase — so you can iterate on a populated scene instead of an empty grid.',
    hint: 'Tip: templates run through the same skill pipeline as chat, so every object stays editable.',
  },
  {
    id: 'tools',
    icon: Wand2,
    accent: 'text-accent-emerald',
    title: 'Tools and skills catalog',
    body: 'Browse the Skills tab in the right panel for one-click multi-step compositions, and use the Properties / Layers / Outliner tabs to inspect and tweak individual objects, materials, and transforms directly.',
    hint: 'Tip: the export_code tool can ship the current scene as Three.js, React+R3F, or a standalone HTML file.',
  },
  {
    id: 'ensemble',
    icon: Users,
    accent: 'text-accent-purple',
    title: 'Brainstorm with a specialist ensemble',
    body: 'For open-ended direction, ask the Agent to run an ensemble brainstorm: several read-only specialists (composition, material, lighting, motion, critique) weigh in on your scene in parallel, then a creative director reconciles their views into one prioritized brief. Try "ensemble: make this scene feel cinematic" or "what should I improve about this scene?"',
    hint: 'Tip: the ensemble never edits the scene itself — it returns a plan you can approve, then the Agent executes it with its normal tools.',
  },
  {
    id: 'scene_intelligence',
    icon: Brain,
    accent: 'text-accent-cyan',
    title: 'Scene intelligence, Quick Actions, and memory',
    body: 'The Agent sees your scene semantically: ask "describe the scene" and it uses the describe_scene tool to read layout, palette, lighting, balance, and geometry — then grounds its next reply in what it sees. After each turn, gold Quick Actions chips appear below the assistant message: one-tap follow-ups like "add a rim light" or "swap to matte material" culled from the suggest_next_actions tool. Want the Agent to remember something durable? Pin it. Say "remember that my target platform is mobile WebGL" or use the Memory tab in the right panel — pinned facts survive across sessions and steer every subsequent turn.',
    hint: 'Tip: open the Memory tab (Brain icon) to review, add, and forget pinned facts; categories color-code them so you can spot constraints at a glance.',
  },
  {
    id: 'pipeline',
    icon: Workflow,
    accent: 'text-accent-cyan',
    title: 'Compose pipelines visually',
    body: 'Open Settings → Pipeline Node Graph for a visual canvas where you wire LLM, image, 3D, video, and audio nodes together with bezier edges. Load a built-in template or build your own, then Run to stream per-node status back in real time.',
    hint: 'Tip: drag from an output port onto an input port to wire two nodes; the graph maps 1:1 to the backend pipeline JSON.',
  },
  {
    id: 'annotations',
    icon: Tag,
    accent: 'text-accent-emerald',
    title: 'Pin annotations on objects',
    body: 'In Edit mode, the AnnotationLayer renders pin markers and label bubbles you can attach to any object. Anchored annotations follow their object transform every frame, so notes stay glued as the scene animates. Ask the Agent "add an annotation on the sphere labeled Front Wheel" or use the add_annotation tool directly.',
    hint: 'Tip: annotations are part of the Scene data, so they serialize into exports and undo/redo just like any other edit.',
  },
  {
    id: 'multi_select',
    icon: MousePointerClick,
    accent: 'text-accent-purple',
    title: 'Multi-select and rigid groups',
    body: 'Shift-click objects in the viewport or Layers panel to build a multi-selection. Drag any one of them and the others move, rotate, and scale together as a rigid group (animated objects are skipped automatically). Ctrl/Cmd+A selects everything, Ctrl/Cmd+Shift+A deselects, and Ctrl/Cmd+G groups them permanently.',
    hint: 'Tip: the primary selection (last clicked) is the one the Properties tab inspects.',
  },
  {
    id: 'timeline',
    icon: Film,
    accent: 'text-rose-300',
    title: 'Animate with the timeline',
    body: 'The Timeline panel exposes per-keyframe tick marks on the scrubber, inline duration editing, per-row loop toggles, and an easing picker (linear / easeIn / easeOut / easeInOut) for keyframe animations. Press P to play/pause, Shift+P to stop, and scrub the timeline to scrub the animation directly.',
    hint: 'Tip: press R to cycle render quality while scrubbing long animations to keep the viewport responsive.',
  },
  {
    id: 'checkpoints',
    icon: GitCommitVertical,
    accent: 'text-accent-purple',
    title: "Checkpoint your scene's evolution",
    body: 'Open the Checkpoints panel (git-commit icon) in the right bar to capture the current scene as an immutable, semantically labeled revision (R1, R2, R3, …). Each revision auto-summarizes geometry counts, material palette, and light rig. Restore any earlier revision at any time, or diff two revisions to see exactly what was added, removed, or changed. Ask the Agent "checkpoint this scene", or use the checkpoint_scene / restore_checkpoint / checkpoint_diff tools directly.',
    hint: 'Tip: checkpoint before a risky or exploratory edit so you can always roll back — restoring never deletes later revisions.',
  },
  {
    id: 'storyboard',
    icon: Clapperboard,
    accent: 'text-rose-300',
    title: 'Direct the camera with a storyboard',
    body: 'Open the Storyboard panel (film-reel icon) in the right bar to compose an ordered sequence of camera shots — each with a position, look-at target, fov, duration, and easing curve. Play the cut to drive the camera through the shots as a scripted cinematic tour of your scene. Ask the Agent "compose a storyboard panning around the scene", or capture the current viewport camera as a shot and layer them into a reveal.',
    hint: 'Tip: set a shot to easeInOut for smooth arrives, and use loop to keep the tour cycling during a showcase.',
  },
  {
    id: 'critique',
    icon: ClipboardCheck,
    accent: 'text-accent-emerald',
    title: 'Self-review and auto-fix the scene',
    body: 'Open the Critique panel (clipboard-check icon) in the right bar to run a prescriptive design review of the current scene. It catches empty scenes, dim or missing lighting, floating objects, overlap, composition drift, palette monotony, and poor background contrast — each with a one-tap proposed fix. Hit "Auto-fix all" to apply the top-severity corrective tool calls in one shot, or apply fixes one finding at a time. Ask the Agent "how does this scene look?" or "auto-fix the scene" to trigger the same engine from chat.',
    hint: 'Tip: critique is read-only — applying a fix runs the proposed tool directly, so checkpoint first if you want to roll back.',
  },
  {
    id: 'constraints',
    icon: ShieldCheck,
    accent: 'text-accent-cyan',
    title: 'Author spatial constraints and solve them',
    body: 'Open the Constraints panel (link icon) in the right bar to declaratively pin spatial relationships between objects: above, below, above_floor, faces, centered, min_distance, and aligned. Add a rule like "lamp above table" or "chair faces desk", then hit Solve to run the greedy solver — it adjusts subject transforms (and rotation for faces) in one pass so the scene satisfies every rule. Ask the Agent "keep the lamp above the table" or "make the chair face the desk" to add and solve constraints from chat.',
    hint: 'Tip: solve moves subjects only — anchors stay put. Pair with checkpoint before a risky re-arrange so you can roll back.',
  },
  {
    id: 'shortcuts',
    icon: Keyboard,
    accent: 'text-amber-400',
    title: 'Move at the speed of thought',
    body: 'Press ? any time to see every keyboard shortcut. Space toggles Edit / Run mode, Ctrl/Cmd+Z undoes, Delete removes the selection, 1/2/3 switch between Move, Rotate, and Scale transforms, F frames the selection, A frames all, M toggles the minimap, and Ctrl/Cmd+K opens the Command Palette.',
    hint: 'Tip: press F to frame the camera on whatever you have selected; press A to frame the whole scene.',
  },
]

interface OnboardingHintsProps {
  /** Force the overlay open regardless of the stored dismissal flag. */
  forceOpen?: boolean
  /** Called when the user finishes or dismisses the tour. */
  onClose?: () => void
}

export function OnboardingHints({ forceOpen = false, onClose }: OnboardingHintsProps) {
  const [open, setOpen] = useState(false)
  const [index, setIndex] = useState(0)

  // First-visit detection: show only when nothing is persisted yet.
  useEffect(() => {
    if (forceOpen) {
      setOpen(true)
      setIndex(0)
      return
    }
    try {
      if (localStorage.getItem(STORAGE_KEY) === '1') return
    } catch {
      // localStorage may be unavailable (private mode); skip auto-show.
      return
    }
    setOpen(true)
    setIndex(0)
  }, [forceOpen])

  // Lock body scroll while the tour is active.
  useEffect(() => {
    if (!open) return
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = prev
    }
  }, [open])

  const dismiss = () => {
    try {
      localStorage.setItem(STORAGE_KEY, '1')
    } catch {
      // Ignore write failures; the in-memory state still closes the overlay.
    }
    setOpen(false)
    onClose?.()
  }

  const next = () => {
    if (index < STEPS.length - 1) {
      setIndex((i) => i + 1)
    } else {
      dismiss()
    }
  }

  const prev = () => {
    if (index > 0) setIndex((i) => i - 1)
  }

  // Escape to dismiss, arrow keys to navigate.
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault()
        dismiss()
      } else if (e.key === 'ArrowRight') {
        e.preventDefault()
        next()
      } else if (e.key === 'ArrowLeft') {
        e.preventDefault()
        prev()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, index])

  const step = STEPS[index]
  const StepIcon = step.icon
  const isLast = index === STEPS.length - 1

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.18 }}
          className="fixed inset-0 z-[60] flex items-center justify-center bg-black/70 backdrop-blur-sm p-4"
          onClick={dismiss}
          role="dialog"
          aria-modal="true"
          aria-label="Welcome to Trigen"
        >
          <motion.div
            initial={{ scale: 0.94, opacity: 0, y: 16 }}
            animate={{ scale: 1, opacity: 1, y: 0 }}
            exit={{ scale: 0.94, opacity: 0, y: 16 }}
            transition={{ duration: 0.22, ease: 'easeOut' }}
            onClick={(e) => e.stopPropagation()}
            className="relative w-[460px] max-w-full rounded-2xl border border-border bg-bg-panel shadow-2xl overflow-hidden"
          >
            {/* Accent banner */}
            <div className="absolute inset-x-0 top-0 h-24 bg-gradient-to-br from-accent-cyan/15 via-accent-purple/10 to-transparent pointer-events-none" />

            {/* Close button */}
            <button
              onClick={dismiss}
              aria-label="Dismiss tour"
              className="absolute top-3 right-3 flex items-center justify-center w-8 h-8 rounded-md text-fg-muted hover:text-fg-primary hover:bg-bg-hover transition-colors z-10"
            >
              <X size={16} />
            </button>

            {/* Step content */}
            <div className="relative px-7 pt-7 pb-5">
              <div className="flex items-center gap-3 mb-4">
                <div className="flex items-center justify-center w-11 h-11 rounded-xl border border-border bg-bg-elevated shadow-inner">
                  <StepIcon size={20} className={step.accent} />
                </div>
                <div>
                  <div className="text-[10px] uppercase tracking-wider text-fg-muted font-semibold">
                    Welcome · Step {index + 1} of {STEPS.length}
                  </div>
                  <h2 className="text-base font-semibold text-fg-primary leading-tight">
                    {step.title}
                  </h2>
                </div>
              </div>

              <p className="text-[12.5px] leading-relaxed text-fg-secondary mb-3">
                {step.body}
              </p>

              <div className="rounded-lg border border-border-subtle bg-bg-base/60 px-3 py-2">
                <p className="text-[11px] text-fg-muted leading-relaxed">
                  <span className="text-fg-secondary font-medium">Hint: </span>
                  {step.hint}
                </p>
              </div>
            </div>

            {/* Progress dots */}
            <div className="flex items-center justify-center gap-1.5 pb-3">
              {STEPS.map((s, i) => (
                <button
                  key={s.id}
                  onClick={() => setIndex(i)}
                  aria-label={`Go to step ${i + 1}`}
                  className={`h-1.5 rounded-full transition-all ${
                    i === index
                      ? 'w-6 bg-accent-cyan'
                      : 'w-1.5 bg-border hover:bg-fg-muted'
                  }`}
                />
              ))}
            </div>

            {/* Footer nav */}
            <footer className="flex items-center justify-between px-7 py-4 border-t border-border-subtle bg-bg-base/40">
              <button
                onClick={prev}
                disabled={index === 0}
                className="flex items-center gap-1.5 text-[11px] font-medium text-fg-muted hover:text-fg-primary disabled:opacity-30 disabled:hover:text-fg-muted transition-colors"
              >
                <ArrowLeft size={13} />
                Back
              </button>

              <button
                onClick={dismiss}
                className="text-[11px] text-fg-muted hover:text-fg-secondary transition-colors"
              >
                Skip tour
              </button>

              <button
                onClick={next}
                className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-md bg-accent-cyan/15 text-accent-cyan border border-accent-cyan/30 text-[11px] font-semibold hover:bg-accent-cyan/25 transition-colors"
              >
                {isLast ? (
                  <>
                    <Check size={13} />
                    Got it
                  </>
                ) : (
                  <>
                    Next
                    <ArrowRight size={13} />
                  </>
                )}
              </button>
            </footer>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}

/** Hook for toolbars that want to manually re-open the tour. */
export function useReopenOnboarding() {
  const [forceOpen, setForceOpen] = useState(false)
  const reopen = () => {
    try {
      localStorage.removeItem(STORAGE_KEY)
    } catch {
      /* ignore */
    }
    setForceOpen(true)
  }
  const handleClose = () => setForceOpen(false)
  return { forceOpen, reopen, handleClose }
}
