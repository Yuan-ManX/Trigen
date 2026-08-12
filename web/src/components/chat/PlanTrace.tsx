// PlanTrace: live execution-plan checklist rendered inline in an assistant
// message. Each step flips status (pending -> running -> done/failed) as the
// orchestrator emits plan / plan_update events. For multi-intent turns the
// `breakdown` prop renders a compact "create → material → light" sub-goal
// sequence above the linear steps so the user can scan the plan at a glance.
import { motion } from 'framer-motion'
import {
  ArrowRight,
  Check,
  ChevronDown,
  ChevronRight,
  CircleDashed,
  Loader2,
  Route,
  X,
} from 'lucide-react'
import { useMemo, useState } from 'react'
import type { PlanGoalBreakdown, PlanStep } from '../../types'

interface PlanTraceProps {
  steps: PlanStep[]
  goal?: string
  breakdown?: PlanGoalBreakdown[]
  assumptions?: string[]
  risks?: string[]
}

const STATUS_META: Record<
  PlanStep['status'],
  { icon: typeof Check; color: string; label: string; spin?: boolean }
> = {
  pending: { icon: CircleDashed, color: 'text-fg-muted', label: 'pending' },
  running: { icon: Loader2, color: 'text-accent-cyan', label: 'running', spin: true },
  done: { icon: Check, color: 'text-emerald-400', label: 'done' },
  failed: { icon: X, color: 'text-rose-400', label: 'failed' },
}

// Category → pastel accent class for sub-goal chips. Categories not listed
// fall back to the cyan default so the UI stays consistent when new
// categories are added to the backend taxonomy.
const BREAKDOWN_ACCENT: Record<string, string> = {
  creation: 'bg-fuchsia-500/15 text-fuchsia-300 border-fuchsia-500/30',
  transform: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30',
  material: 'bg-amber-500/15 text-amber-300 border-amber-500/30',
  lighting: 'bg-yellow-500/15 text-yellow-300 border-yellow-500/30',
  camera: 'bg-sky-500/15 text-sky-300 border-sky-500/30',
  editor: 'bg-cyan-500/15 text-cyan-300 border-cyan-500/30',
  constraints: 'bg-violet-500/15 text-violet-300 border-violet-500/30',
  intelligence: 'bg-indigo-500/15 text-indigo-300 border-indigo-500/30',
  workflows: 'bg-rose-500/15 text-rose-300 border-rose-500/30',
  animation: 'bg-orange-500/15 text-orange-300 border-orange-500/30',
}

const DEFAULT_BREAKDOWN_ACCENT = 'bg-cyan-500/15 text-cyan-300 border-cyan-500/30'

export function PlanTrace({ steps, goal, breakdown, assumptions, risks }: PlanTraceProps) {
  const [open, setOpen] = useState(true)
  if (!steps || steps.length === 0) return null

  const done = steps.filter((s) => s.status === 'done').length
  const failed = steps.filter((s) => s.status === 'failed').length
  const running = steps.some((s) => s.status === 'running')
  const total = steps.length

  const headline = goal && goal.trim().length > 0 ? goal.trim() : `${total} planned step${total === 1 ? '' : 's'}`

  // Per-sub-goal progress so each chip shows its mini done/total.
  const breakdownMeta = useMemo(() => {
    if (!breakdown || breakdown.length === 0) return null
    const stepStatuses = new Map(steps.map((s) => [s.id, s.status]))
    return breakdown.map((b) => {
      let bDone = 0
      let bFailed = 0
      let bRunning = false
      for (const sid of b.step_ids) {
        const st = stepStatuses.get(sid)
        if (st === 'done') bDone++
        else if (st === 'failed') bFailed++
        else if (st === 'running') bRunning = true
      }
      return {
        ...b,
        done: bDone,
        total: b.step_ids.length,
        failed: bFailed,
        running: bRunning,
      }
    })
  }, [breakdown, steps])

  return (
    <div className="rounded-md border border-accent-cyan/25 bg-accent-cyan/5 overflow-hidden">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-2 px-3 py-2 text-left"
      >
        <Route size={13} className="text-accent-cyan" />
        <span className="text-[11px] font-medium text-fg-secondary">
          Plan · <span className="text-fg-primary">{done}/{total}</span> done
          {failed > 0 && <span className="text-rose-400 ml-1">· {failed} failed</span>}
          <span className="text-fg-muted ml-1 truncate">{headline}</span>
        </span>
        {open ? (
          <ChevronDown size={12} className="ml-auto text-fg-muted" />
        ) : (
          <ChevronRight size={12} className="ml-auto text-fg-muted" />
        )}
      </button>
      {open && (
        <div className="px-3 pb-2 space-y-2">
          {breakdownMeta && breakdownMeta.length > 0 && (
            <div className="flex items-center flex-wrap gap-1.5 pt-0.5">
              {breakdownMeta.map((b, i) => (
                <div key={b.category + i} className="flex items-center gap-1">
                  {i > 0 && <ArrowRight size={10} className="text-fg-muted shrink-0" />}
                  <span
                    className={`inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[10px] font-medium ${
                      BREAKDOWN_ACCENT[b.category] ?? DEFAULT_BREAKDOWN_ACCENT
                    }`}
                  >
                    <span>{b.label}</span>
                    <span className="opacity-70">
                      {b.done}/{b.total}
                    </span>
                    {b.running && (
                      <Loader2 size={9} className="animate-spin opacity-80" />
                    )}
                    {b.failed > 0 && <X size={9} className="text-rose-400" />}
                  </span>
                </div>
              ))}
            </div>
          )}
          <div className="space-y-1">
            {steps.map((s, i) => {
              const meta = STATUS_META[s.status] ?? STATUS_META.pending
              const Icon = meta.icon
              return (
                <motion.div
                  key={s.id || i}
                  initial={{ opacity: 0.4 }}
                  animate={{ opacity: 1 }}
                  transition={{ duration: 0.15 }}
                  className="flex items-start gap-2 text-[11px] leading-relaxed"
                >
                  <Icon
                    size={12}
                    className={`mt-0.5 shrink-0 ${meta.color} ${meta.spin ? 'animate-spin' : ''}`}
                  />
                  <div className="min-w-0 flex-1">
                    <span className="font-mono text-fg-secondary">{s.tool}</span>
                    {s.description && s.description !== `Call ${s.tool}` && (
                      <span className="text-fg-muted"> — {s.description}</span>
                    )}
                    {s.status === 'failed' && s.message && (
                      <div className="text-rose-400/80 mt-0.5 break-words">{s.message}</div>
                    )}
                  </div>
                  {running && s.status === 'running' && (
                    <span className="text-[9px] text-accent-cyan/80 uppercase tracking-wide">live</span>
                  )}
                </motion.div>
              )
            })}
          </div>

          {/* Agent-stated assumptions and risks — the "why" behind the plan */}
          {((assumptions && assumptions.length > 0) || (risks && risks.length > 0)) && (
            <div className="pt-1.5 border-t border-border-subtle space-y-1.5">
              {assumptions && assumptions.length > 0 && (
                <div className="space-y-0.5">
                  <div className="text-[9px] uppercase tracking-wider text-fg-muted font-semibold">
                    Assumptions
                  </div>
                  {assumptions.map((a, i) => (
                    <div key={i} className="flex items-start gap-1.5 text-[10.5px] text-fg-secondary">
                      <span className="text-fg-muted">•</span>
                      <span className="leading-relaxed">{a}</span>
                    </div>
                  ))}
                </div>
              )}
              {risks && risks.length > 0 && (
                <div className="space-y-0.5">
                  <div className="text-[9px] uppercase tracking-wider text-amber-400/80 font-semibold">
                    Risks
                  </div>
                  {risks.map((r, i) => (
                    <div key={i} className="flex items-start gap-1.5 text-[10.5px] text-amber-200/80">
                      <span className="text-amber-400/80">⚠</span>
                      <span className="leading-relaxed">{r}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
