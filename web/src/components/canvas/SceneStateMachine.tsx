// Scene state machine overlay.
//
// A compact floating panel anchored to the bottom-right of the canvas that
// surfaces the editor's current state at a glance: edit/run mode, transform
// gizmo, grid snapping, and render quality. A short transition history
// (last 5 state changes with timestamps) is preserved so the user can see
// how the editor state evolved — useful when the Agent drives the editor
// remotely through tool calls.
import { AnimatePresence, motion } from 'framer-motion'
import {
  Activity,
  ChevronDown,
  Gauge,
  GitBranch,
  Grid3x3,
  History,
  Move3d,
  Pencil,
  Play,
  RotateCw,
  Scale3d,
} from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useEditor, type RenderQuality, type TransformMode } from '../../store/useEditor'

interface SceneStateMachineProps {
  /** Active editor mode (edit/run) — owned by AppShell. */
  mode: 'edit' | 'run'
}

interface TransitionEntry {
  id: number
  timestamp: number
  label: string
  from: string
  to: string
}

const TRANSFORM_META: Record<TransformMode, { label: string; icon: typeof Move3d }> = {
  translate: { label: 'Move', icon: Move3d },
  rotate: { label: 'Rotate', icon: RotateCw },
  scale: { label: 'Scale', icon: Scale3d },
}

const QUALITY_META: Record<RenderQuality, { label: string; color: string }> = {
  low: { label: 'Low', color: 'text-rose-400' },
  medium: { label: 'Med', color: 'text-accent-gold' },
  high: { label: 'High', color: 'text-emerald-400' },
}

/** Format a timestamp as HH:MM:SS for the history list. */
function formatTime(ts: number): string {
  const d = new Date(ts)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

export function SceneStateMachine({ mode }: SceneStateMachineProps) {
  const transformMode = useEditor((s) => s.transformMode)
  const gridSnapEnabled = useEditor((s) => s.gridSnapEnabled)
  const renderQuality = useEditor((s) => s.renderQuality)

  const [history, setHistory] = useState<TransitionEntry[]>([])
  // Start collapsed so the indicator reads as a compact strip and never
  // occludes the scene; expand on demand.
  const [collapsed, setCollapsed] = useState(true)
  const seqRef = useRef(0)

  // Track state transitions across all watched fields. Each change pushes a
  // new entry onto the history (capped at 5). Using refs for previous values
  // avoids stale-closure issues inside the effect.
  const prevRef = useRef({ mode, transformMode, gridSnapEnabled, renderQuality })

  useEffect(() => {
    const prev = prevRef.current
    const next = { mode, transformMode, gridSnapEnabled, renderQuality }
    if (
      prev.mode === next.mode &&
      prev.transformMode === next.transformMode &&
      prev.gridSnapEnabled === next.gridSnapEnabled &&
      prev.renderQuality === next.renderQuality
    ) {
      return
    }

    const entries: Omit<TransitionEntry, 'id' | 'timestamp'>[] = []
    if (prev.mode !== next.mode) {
      entries.push({ label: 'Mode', from: prev.mode, to: next.mode })
    }
    if (prev.transformMode !== next.transformMode) {
      entries.push({ label: 'Transform', from: prev.transformMode, to: next.transformMode })
    }
    if (prev.gridSnapEnabled !== next.gridSnapEnabled) {
      entries.push({
        label: 'Grid Snap',
        from: prev.gridSnapEnabled ? 'on' : 'off',
        to: next.gridSnapEnabled ? 'on' : 'off',
      })
    }
    if (prev.renderQuality !== next.renderQuality) {
      entries.push({ label: 'Quality', from: prev.renderQuality, to: next.renderQuality })
    }

    if (entries.length > 0) {
      const now = Date.now()
      setHistory((h) => [
        ...entries.map((e) => ({ ...e, id: seqRef.current++, timestamp: now })),
        ...h,
      ].slice(0, 5))
    }
    prevRef.current = next
  }, [mode, transformMode, gridSnapEnabled, renderQuality])

  const TransformIcon = TRANSFORM_META[transformMode].icon
  const ModeIcon = mode === 'edit' ? Pencil : Play
  const qualityMeta = QUALITY_META[renderQuality]

  return (
    <motion.div
      initial={{ opacity: 0, x: 16 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.25, ease: 'easeOut' }}
      className="pointer-events-auto absolute bottom-3 right-3 w-60 rounded-lg border border-border bg-bg-panel/85 backdrop-blur-md shadow-lg overflow-hidden z-20"
    >
      {/* Header */}
      <button
        onClick={() => setCollapsed((c) => !c)}
        className="w-full flex items-center justify-between px-3 py-2 border-b border-border-subtle hover:bg-bg-hover/40 transition-colors"
      >
        <div className="flex items-center gap-1.5">
          <Activity size={12} className="text-accent-cyan" />
          <span className="text-[11px] font-semibold text-fg-primary tracking-wide">
            State Machine
          </span>
        </div>
        <ChevronDown
          size={12}
          className={`text-fg-muted transition-transform ${collapsed ? '-rotate-90' : ''}`}
        />
      </button>

      <AnimatePresence initial={false}>
        {!collapsed && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.18, ease: 'easeInOut' }}
            className="overflow-hidden"
          >
            {/* Current state grid */}
            <div className="grid grid-cols-2 gap-px bg-border-subtle/40">
              <StateCell
                icon={<ModeIcon size={11} />}
                label="Mode"
                value={mode === 'edit' ? 'Edit' : 'Run'}
                valueClass={mode === 'edit' ? 'text-accent-cyan' : 'text-accent-gold'}
              />
              <StateCell
                icon={<TransformIcon size={11} />}
                label="Transform"
                value={TRANSFORM_META[transformMode].label}
                valueClass="text-accent-purple"
              />
              <StateCell
                icon={<Grid3x3 size={11} />}
                label="Snap"
                value={gridSnapEnabled ? 'On' : 'Off'}
                valueClass={gridSnapEnabled ? 'text-emerald-400' : 'text-fg-muted'}
              />
              <StateCell
                icon={<Gauge size={11} />}
                label="Quality"
                value={qualityMeta.label}
                valueClass={qualityMeta.color}
              />
            </div>

            {/* Transition history */}
            <div className="px-3 py-2 border-t border-border-subtle">
              <div className="flex items-center gap-1.5 mb-1.5">
                <History size={10} className="text-fg-muted" />
                <span className="text-[10px] uppercase tracking-wider text-fg-muted font-semibold">
                  Transitions
                </span>
              </div>
              <div className="space-y-1">
                <AnimatePresence initial={false}>
                  {history.length === 0 ? (
                    <motion.div
                      key="empty"
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      exit={{ opacity: 0 }}
                      className="flex items-center gap-1.5 text-[10px] text-fg-muted/70 italic"
                    >
                      <GitBranch size={10} />
                      <span>No state changes yet</span>
                    </motion.div>
                  ) : (
                    history.map((entry) => (
                      <motion.div
                        key={entry.id}
                        initial={{ opacity: 0, y: -4 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -4 }}
                        transition={{ duration: 0.15 }}
                        className="flex items-center gap-1.5 text-[10px] font-mono leading-tight"
                      >
                        <span className="text-fg-muted/70 tabular-nums">
                          {formatTime(entry.timestamp)}
                        </span>
                        <span className="text-fg-secondary font-sans font-medium">
                          {entry.label}
                        </span>
                        <span className="text-fg-muted">{entry.from}</span>
                        <span className="text-accent-cyan">→</span>
                        <span className="text-fg-primary">{entry.to}</span>
                      </motion.div>
                    ))
                  )}
                </AnimatePresence>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  )
}

/** Small grid cell that renders one labeled state value. */
function StateCell({
  icon,
  label,
  value,
  valueClass,
}: {
  icon: React.ReactNode
  label: string
  value: string
  valueClass: string
}) {
  return (
    <div className="bg-bg-panel/80 px-2.5 py-1.5">
      <div className="flex items-center gap-1 text-[9px] uppercase tracking-wider text-fg-muted font-semibold">
        <span className="text-fg-muted/80">{icon}</span>
        <span>{label}</span>
      </div>
      <div className={`text-[12px] font-semibold leading-tight mt-0.5 ${valueClass}`}>
        {value}
      </div>
    </div>
  )
}
