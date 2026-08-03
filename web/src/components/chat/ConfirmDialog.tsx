// Destructive-action confirmation modal. Opens when useChat.pendingDestructive
// is non-null — i.e. the plan preview flagged requires_approval tool calls.
// Follows the SceneTemplates modal pattern (AnimatePresence + motion.div).
import { AnimatePresence, motion } from 'framer-motion'
import { AlertTriangle, ShieldAlert, X } from 'lucide-react'

interface PendingDestructive {
  text: string
  reasoning?: string
  steps: Array<{ name: string; arguments: Record<string, unknown> }>
}

interface ConfirmDialogProps {
  open: boolean
  pending: PendingDestructive | null
  onConfirm: () => void
  onCancel: () => void
}

export function ConfirmDialog({ open, pending, onConfirm, onCancel }: ConfirmDialogProps) {
  return (
    <AnimatePresence>
      {open && pending && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.15 }}
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
          onClick={onCancel}
        >
          <motion.div
            initial={{ scale: 0.95, opacity: 0, y: 10 }}
            animate={{ scale: 1, opacity: 1, y: 0 }}
            exit={{ scale: 0.95, opacity: 0, y: 10 }}
            transition={{ duration: 0.2 }}
            onClick={(e) => e.stopPropagation()}
            className="relative w-[520px] max-w-[90vw] max-h-[80vh] overflow-hidden rounded-xl border border-rose-500/40 bg-bg-panel shadow-2xl"
          >
            {/* Header */}
            <header className="flex items-center justify-between h-12 px-5 border-b border-border">
              <div className="flex items-center gap-2">
                <ShieldAlert size={16} className="text-rose-400" />
                <h2 className="text-sm font-semibold text-fg-primary">
                  Confirm Destructive Action
                </h2>
              </div>
              <button
                onClick={onCancel}
                aria-label="Cancel"
                className="flex items-center justify-center w-7 h-7 rounded text-fg-muted hover:text-fg-primary hover:bg-bg-hover transition-colors"
              >
                <X size={15} />
              </button>
            </header>

            {/* Body */}
            <div className="p-5 overflow-y-auto max-h-[calc(80vh-48px)] space-y-4">
              {/* The user message that triggered the plan */}
              <div>
                <div className="text-[10px] uppercase tracking-wider text-fg-muted mb-1">
                  Your request
                </div>
                <div className="rounded-md border border-border bg-bg-elevated/40 px-3 py-2 text-[12px] text-fg-secondary">
                  {pending.text}
                </div>
              </div>

              {/* Optional reasoning from the planner */}
              {pending.reasoning && (
                <div>
                  <div className="text-[10px] uppercase tracking-wider text-fg-muted mb-1">
                    Planner reasoning
                  </div>
                  <p className="text-[11px] text-fg-secondary leading-relaxed">
                    {pending.reasoning}
                  </p>
                </div>
              )}

              {/* Destructive tool calls */}
              <div>
                <div className="flex items-center gap-1.5 mb-1.5">
                  <AlertTriangle size={11} className="text-rose-400" />
                  <span className="text-[10px] uppercase tracking-wider text-rose-400">
                    Destructive steps ({pending.steps.length})
                  </span>
                </div>
                <div className="space-y-2">
                  {pending.steps.map((step, i) => (
                    <div
                      key={`${step.name}-${i}`}
                      className="rounded-md border border-rose-500/30 bg-rose-500/5 px-3 py-2"
                    >
                      <div className="flex items-center gap-2">
                        <span className="text-[10px] font-mono text-fg-muted">
                          {i + 1}.
                        </span>
                        <span className="text-[12px] font-semibold text-fg-primary font-mono">
                          {step.name}
                        </span>
                      </div>
                      <pre className="mt-1 ml-5 text-[10px] text-fg-muted font-mono whitespace-pre-wrap break-all">
                        {JSON.stringify(step.arguments, null, 2)}
                      </pre>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {/* Footer: actions */}
            <footer className="flex items-center justify-end gap-2 px-5 py-3 border-t border-border bg-bg-elevated/30">
              <button
                onClick={onCancel}
                className="px-3 h-8 rounded-md text-[11px] font-medium text-fg-secondary hover:text-fg-primary hover:bg-bg-hover transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={onConfirm}
                className="flex items-center gap-1.5 px-3 h-8 rounded-md bg-rose-500 text-white text-[11px] font-medium hover:bg-rose-600 transition-colors"
              >
                <ShieldAlert size={12} />
                <span>Confirm &amp; Run</span>
              </button>
            </footer>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
