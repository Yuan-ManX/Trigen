// Tool call card: inline display of tool name, parameters and execution result
import { motion } from 'framer-motion'
import { CheckCircle2, Loader2, Terminal, XCircle } from 'lucide-react'
import type { ToolCallRecord } from '../../store/useChat'

interface ToolCallCardProps {
  call: ToolCallRecord
}

/** Friendly display of the tool name */
function friendlyName(name: string): string {
  return name.replace(/_/g, ' ')
}

export function ToolCallCard({ call }: ToolCallCardProps) {
  const argString = (() => {
    try {
      return JSON.stringify(call.arguments, null, 2)
    } catch {
      return '{}'
    }
  })()

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2 }}
      className="rounded-md border border-border bg-bg-base/60 overflow-hidden"
    >
      <div className="flex items-center gap-2 px-3 py-2 bg-bg-elevated/70 border-b border-border-subtle">
        <Terminal size={13} className="text-accent-cyan" />
        <span className="text-xs font-mono text-fg-primary font-medium tracking-wide">
          {friendlyName(call.name)}
        </span>
        <span className="ml-auto flex items-center gap-1 text-[10px]">
          {call.pending ? (
            <span className="flex items-center gap-1 text-fg-secondary">
              <Loader2 size={11} className="animate-spin" />
              Running
            </span>
          ) : call.result?.success ? (
            <span className="flex items-center gap-1 text-emerald-400">
              <CheckCircle2 size={11} />
              Done
            </span>
          ) : (
            <span className="flex items-center gap-1 text-rose-400">
              <XCircle size={11} />
              Failed
            </span>
          )}
        </span>
      </div>

      {Object.keys(call.arguments).length > 0 && (
        <pre className="px-3 py-2 text-[11px] font-mono text-fg-secondary overflow-x-auto max-h-40 leading-relaxed">
          {argString}
        </pre>
      )}

      {call.result && (
        <div className="px-3 py-1.5 text-[11px] text-fg-secondary border-t border-border-subtle bg-bg-base/40">
          {call.result.message}
        </div>
      )}
    </motion.div>
  )
}
