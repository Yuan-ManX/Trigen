// PlanTrace: live execution-plan checklist rendered inline in an assistant
// message. Each step flips status (pending -> running -> done/failed) as the
// orchestrator emits plan / plan_update events.
import { motion } from 'framer-motion'
import { Check, ChevronDown, ChevronRight, CircleDashed, Loader2, Route, X } from 'lucide-react'
import { useState } from 'react'
import type { PlanStep } from '../../types'

interface PlanTraceProps {
  steps: PlanStep[]
  goal?: string
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

export function PlanTrace({ steps, goal }: PlanTraceProps) {
  const [open, setOpen] = useState(true)
  if (!steps || steps.length === 0) return null

  const done = steps.filter((s) => s.status === 'done').length
  const failed = steps.filter((s) => s.status === 'failed').length
  const running = steps.some((s) => s.status === 'running')
  const total = steps.length

  const headline = goal && goal.trim().length > 0 ? goal.trim() : `${total} planned step${total === 1 ? '' : 's'}`

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
        <div className="px-3 pb-2 space-y-1">
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
      )}
    </div>
  )
}
