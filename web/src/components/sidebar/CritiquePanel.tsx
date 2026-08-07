// Critique panel: a prescriptive "fresh eyes" design review of the scene.
// Runs the deterministic critique_scene engine (via POST /api/agent/run) and
// lists each finding ranked by severity — empty scene, missing/dim/harsh
// lighting, floating objects, overlapping objects, composition drift, palette
// monotony, poor background contrast. Every finding carries a concrete
// proposed corrective tool call, so the user can apply a single fix in one
// tap, or hit "Auto-fix all" to apply the top-severity fixes in one shot.
// Mirrors the visual style of CheckpointsPanel / StoryboardPanel.
// Bilingual labels: English / 中文.
import {
  AlertTriangle,
  CheckCircle2,
  ClipboardCheck,
  Loader2,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  Wand2,
  X,
} from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import {
  applyProposedFix,
  autoFixScene,
  critiqueScene,
} from '../../api/client'
import { useChat } from '../../store/useChat'
import { useEditor } from '../../store/useEditor'
import { useScene } from '../../store/useScene'
import type {
  AutoFixData,
  CritiqueData,
  CritiqueFinding,
  CritiqueSeverity,
} from '../../types'

/** Severity badge styling: red for high, amber for medium, blue for low. */
const SEVERITY_STYLE: Record<
  CritiqueSeverity,
  { label: string; cls: string }
> = {
  high: {
    label: 'HIGH',
    cls: 'text-rose-200 border-rose-400/40 bg-rose-400/10',
  },
  medium: {
    label: 'MED',
    cls: 'text-amber-200 border-amber-400/40 bg-amber-400/10',
  },
  low: {
    label: 'LOW',
    cls: 'text-sky-200 border-sky-400/40 bg-sky-400/10',
  },
}

export function CritiquePanel() {
  const [review, setReview] = useState<CritiqueData | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // Per-finding "applying" busy state keyed by finding id.
  const [applyingId, setApplyingId] = useState<string | null>(null)
  // Last auto-fix report (applied / skipped / remaining) — shown inline.
  const [fixReport, setFixReport] = useState<AutoFixData | null>(null)
  const [autoFixing, setAutoFixing] = useState(false)

  const sessionId = useChat((s) => s.sessionId)
  const activePanel = useEditor((s) => s.activePanel)
  const setScene = useScene((s) => s.setScene)

  /** Run the read-only design review and update the findings list. */
  const runReview = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const resp = await critiqueScene(sessionId)
      setReview(resp.result.data)
      // Clear any stale auto-fix report when the user re-runs the review.
      setFixReport(null)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to run review')
    } finally {
      setLoading(false)
    }
  }, [sessionId])

  // Auto-run the review once when the panel first becomes active so the user
  // sees findings without an extra click. Skip on subsequent tab switches to
  // avoid clobbering a manually-edited state.
  const [didAutoRun, setDidAutoRun] = useState(false)
  useEffect(() => {
    if (activePanel === 'critique' && !didAutoRun) {
      setDidAutoRun(true)
      void runReview()
    }
  }, [activePanel, didAutoRun, runReview])

  /** Apply a single finding's proposed fix, then re-run the review so the
   *  user sees the new state of the scene. */
  const handleApplyFix = async (finding: CritiqueFinding) => {
    setApplyingId(finding.id)
    setError(null)
    try {
      const fix = finding.proposed_fix
      const resp = await applyProposedFix(fix.tool, fix.arguments, sessionId)
      // Swap the mutated scene into the editor so the change is visible.
      setScene(resp.scene)
      // Re-run the review to show what's left after the fix.
      await runReview()
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : `Failed to apply fix: ${finding.title}`)
    } finally {
      setApplyingId(null)
    }
  }

  /** Apply the top-severity fixes in one shot via auto_fix_scene, then
   *  refresh the review and show the structured before/after report. */
  const handleAutoFixAll = async () => {
    setAutoFixing(true)
    setError(null)
    try {
      const resp = await autoFixScene(sessionId)
      setScene(resp.scene)
      setFixReport(resp.result.data)
      // Refresh the review so the findings list reflects the post-fix state.
      await runReview()
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to auto-fix scene')
    } finally {
      setAutoFixing(false)
    }
  }

  const findings = review?.findings ?? []
  const verdict = review?.verdict
  const isClean = verdict === 'clean'

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="px-3 py-2.5 border-b border-border-subtle">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1.5">
            <ClipboardCheck size={12} className="text-accent-emerald" />
            <span className="text-[11px] font-semibold text-fg-primary">Critique / 审查</span>
          </div>
          {review && (
            <span className="text-[9px] text-fg-muted font-mono">
              {review.object_count} obj · {review.light_count} light
              {review.light_count === 1 ? '' : 's'}
            </span>
          )}
        </div>
        <p className="text-[9.5px] text-fg-muted mt-1 leading-relaxed">
          A prescriptive design review of the current scene — finds empty scenes,
          dim lighting, floating objects, overlap, composition drift, and palette
          issues, with a one-tap fix for each.
        </p>
      </div>

      {/* Action bar: re-run review + auto-fix all */}
      <div className="px-3 py-2 border-b border-border-subtle bg-bg-base/40 flex items-center gap-1.5">
        <button
          onClick={runReview}
          disabled={loading}
          title="Re-run the design review"
          className="flex items-center gap-1 text-[10px] font-medium px-2 py-1.5 rounded border border-border text-fg-secondary hover:text-fg-primary hover:border-fg-muted/40 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          {loading ? <Loader2 size={11} className="animate-spin" /> : <RefreshCw size={11} />}
          Review
        </button>
        <button
          onClick={handleAutoFixAll}
          disabled={autoFixing || loading || isClean || findings.length === 0}
          title="Apply the top-severity fixes in one shot"
          className="flex items-center gap-1 text-[10px] font-medium px-2 py-1.5 rounded border border-accent-emerald/30 bg-accent-emerald/10 text-accent-emerald hover:bg-accent-emerald/20 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          {autoFixing ? <Loader2 size={11} className="animate-spin" /> : <Wand2 size={11} />}
          Auto-fix all
        </button>
        {verdict && (
          <span
            className={`ml-auto flex items-center gap-1 px-1.5 py-0.5 rounded text-[9px] font-semibold border ${
              isClean
                ? 'text-emerald-200 border-emerald-400/40 bg-emerald-400/10'
                : 'text-amber-200 border-amber-400/40 bg-amber-400/10'
            }`}
          >
            {isClean ? <CheckCircle2 size={9} /> : <AlertTriangle size={9} />}
            {isClean ? 'clean' : 'needs attention'}
          </span>
        )}
      </div>

      {/* Error banner */}
      {error && (
        <div className="mx-3 my-2 px-2 py-1.5 rounded border border-rose-400/30 bg-rose-400/10 text-[10px] text-rose-200 flex items-start gap-1.5">
          <X size={11} className="mt-0.5 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Findings list / clean state / loading state */}
      <div className="flex-1 overflow-y-auto p-2 space-y-1.5">
        {loading && findings.length === 0 && !fixReport && (
          <div className="flex items-center justify-center h-full text-fg-muted text-[11px] gap-2">
            <Loader2 size={13} className="animate-spin" />
            Reviewing scene…
          </div>
        )}

        {!loading && !review && (
          <div className="flex flex-col items-center justify-center h-full text-fg-muted text-[11px] gap-2 p-4 text-center">
            <ClipboardCheck size={18} className="opacity-50" />
            <p>No review yet.</p>
            <p className="text-[9.5px] text-fg-muted/70">
              Click <span className="text-fg-secondary">Review</span> above to inspect the scene for
              design problems, or ask the Agent: “how does this scene look?”.
            </p>
          </div>
        )}

        {review && isClean && !fixReport && (
          <div className="flex flex-col items-center justify-center h-full text-fg-muted text-[11px] gap-2 p-4 text-center">
            <CheckCircle2 size={18} className="text-emerald-300" />
            <p className="text-emerald-200">Scene looks well-formed.</p>
            <p className="text-[9.5px] text-fg-muted/70">
              No design problems found. The review checks lighting, floating objects, overlap,
              composition, palette, and contrast.
            </p>
          </div>
        )}

        {findings.length > 0 &&
          findings.map((f) => (
            <FindingRow
              key={f.id}
              finding={f}
              applying={applyingId === f.id}
              onApply={() => void handleApplyFix(f)}
            />
          ))}

        {/* Auto-fix summary report */}
        {fixReport && (
          <AutoFixReport report={fixReport} />
        )}
      </div>

      {/* Footer hint */}
      <div className="px-3 py-2 border-t border-border-subtle text-[9px] text-fg-muted/70 flex items-center gap-1.5">
        <ShieldCheck size={9} className="text-fg-muted/50" />
        Critique is read-only — applying a fix runs the proposed tool directly.
      </div>
    </div>
  )
}

interface FindingRowProps {
  finding: CritiqueFinding
  applying: boolean
  onApply: () => void
}

/** A single finding row with a severity badge, title, detail, and an
 *  "Apply fix" button that runs the finding's proposed corrective tool call. */
function FindingRow({ finding, applying, onApply }: FindingRowProps) {
  const sev = SEVERITY_STYLE[finding.severity] ?? SEVERITY_STYLE.low
  const fix = finding.proposed_fix
  return (
    <div className="group rounded-md border border-border bg-bg-elevated/30 px-2 py-1.5 transition-colors">
      <div className="flex items-center gap-1.5">
        <span
          className={`px-1.5 py-px rounded text-[9px] font-mono font-semibold border ${sev.cls}`}
        >
          {sev.label}
        </span>
        <span className="text-[10.5px] text-fg-primary font-medium leading-snug truncate">
          {finding.title}
        </span>
        <button
          onClick={onApply}
          disabled={applying}
          title={`Apply proposed fix: ${fix?.tool ?? ''}`}
          className="ml-auto flex items-center gap-1 text-[9.5px] px-1.5 py-0.5 rounded border border-border text-fg-muted hover:text-accent-emerald hover:border-accent-emerald/40 disabled:opacity-40 disabled:cursor-not-allowed transition-colors opacity-0 group-hover:opacity-100"
        >
          {applying ? <Loader2 size={9} className="animate-spin" /> : <Sparkles size={9} />}
          Fix
        </button>
      </div>
      {finding.detail && (
        <p className="text-[9.5px] text-fg-muted mt-0.5 leading-snug break-words">
          {finding.detail}
        </p>
      )}
      {fix && (
        <p className="text-[9px] text-fg-muted/70 mt-0.5 font-mono truncate">
          → {fix.tool}
        </p>
      )}
    </div>
  )
}

/** Compact summary of the last auto_fix_scene run: applied / skipped / remaining. */
function AutoFixReport({ report }: { report: AutoFixData }) {
  return (
    <div className="rounded-md border border-accent-emerald/30 bg-accent-emerald/5 px-2 py-1.5 space-y-1">
      <div className="flex items-center gap-1.5">
        <Wand2 size={11} className="text-accent-emerald" />
        <span className="text-[10.5px] font-semibold text-fg-primary">Auto-fix report</span>
        <span className="text-[9px] text-fg-muted/70 ml-auto font-mono">
          {report.changed ? 'scene changed' : 'no change'}
        </span>
      </div>
      <div className="flex items-center gap-2 text-[9.5px] font-mono">
        <span className="text-emerald-300">+{report.applied.length} applied</span>
        <span className="text-amber-300">~{report.skipped.length} skipped</span>
        <span className="text-fg-muted">{report.remaining.length} left</span>
      </div>
      {report.applied.length > 0 && (
        <ul className="text-[9.5px] text-fg-secondary space-y-0.5">
          {report.applied.slice(0, 4).map((a, i) => (
            <li key={`${a.id}-${i}`} className="truncate">
              <span className="text-accent-emerald">·</span> {a.tool} → {a.title ?? a.id}
            </li>
          ))}
          {report.applied.length > 4 && (
            <li className="text-fg-muted/70">+ {report.applied.length - 4} more</li>
          )}
        </ul>
      )}
      {report.skipped.length > 0 && (
        <ul className="text-[9.5px] text-fg-muted space-y-0.5">
          {report.skipped.slice(0, 3).map((s, i) => (
            <li key={`${s.id}-${i}`} className="truncate">
              <span className="text-amber-300">·</span> {s.tool ?? s.id}: {s.reason}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
