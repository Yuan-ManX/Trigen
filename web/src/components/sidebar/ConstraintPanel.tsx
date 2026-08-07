// Constraint panel: declarative spatial-relationship authoring + solver.
// Lets the user pin relationships between scene objects (above / below /
// above_floor / faces / centered / min_distance / aligned), list them with
// live pass/fail evaluation, run the greedy solver to enforce them, and
// clear the set. Mirrors the visual style of CritiquePanel.
// Bilingual labels: English / 中文.
import {
  AlertTriangle,
  CheckCircle2,
  Eraser,
  Link2,
  Loader2,
  Plus,
  RefreshCw,
  Wand2,
  X,
  XCircle,
} from 'lucide-react'
import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react'
import {
  addConstraint,
  clearConstraints,
  listConstraints,
  solveConstraints,
  type AddConstraintArgs,
} from '../../api/client'
import { useChat } from '../../store/useChat'
import { useEditor } from '../../store/useEditor'
import { useScene } from '../../store/useScene'
import type {
  ConstraintEvalRow,
  ConstraintKind,
  SolveConstraintsData,
} from '../../types'

/** All supported constraint kinds, in display order. */
const KIND_OPTIONS: ConstraintKind[] = [
  'above',
  'below',
  'above_floor',
  'faces',
  'centered',
  'min_distance',
  'aligned',
]

/** Short human-readable hint for each kind, shown in the add form. */
const KIND_HINT: Record<ConstraintKind, string> = {
  above: "subject's base sits above anchor's top (offset gap)",
  below: "subject's top sits below anchor's base",
  above_floor: "subject rests on y=0 (or target_point.y / offset)",
  faces: "subject's +Z axis points at anchor",
  centered: "subject's center matches anchor's center on axis (or all)",
  min_distance: 'centers kept >= distance apart',
  aligned: 'centers aligned on axis within tolerance',
}

/** Kinds that require an anchor object. */
const KIND_NEEDS_ANCHOR: Record<ConstraintKind, boolean> = {
  above: true,
  below: true,
  above_floor: false,
  faces: false,
  centered: true,
  min_distance: true,
  aligned: true,
}

/** Kinds that use the axis field. */
const KIND_USES_AXIS: Record<ConstraintKind, boolean> = {
  above: false,
  below: false,
  above_floor: false,
  faces: false,
  centered: true,
  min_distance: false,
  aligned: true,
}

/** Kinds that use the distance field. */
const KIND_USES_DISTANCE: Record<ConstraintKind, boolean> = {
  above: false,
  below: false,
  above_floor: false,
  faces: false,
  centered: false,
  min_distance: true,
  aligned: false,
}

/** Kinds that use the offset field. */
const KIND_USES_OFFSET: Record<ConstraintKind, boolean> = {
  above: true,
  below: true,
  above_floor: true,
  faces: false,
  centered: false,
  min_distance: false,
  aligned: false,
}

export function ConstraintPanel() {
  const [rows, setRows] = useState<ConstraintEvalRow[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showAdd, setShowAdd] = useState(false)
  const [adding, setAdding] = useState(false)
  const [solving, setSolving] = useState(false)
  const [clearing, setClearing] = useState(false)
  const [solveReport, setSolveReport] = useState<SolveConstraintsData | null>(null)

  const sessionId = useChat((s) => s.sessionId)
  const activePanel = useEditor((s) => s.activePanel)
  const setScene = useScene((s) => s.setScene)
  const objects = useScene((s) => s.scene.objects)

  /** Build a list of "name (id)" options for the subject/anchor datalists. */
  const objectOptions = useMemo(
    () => objects.map((o) => ({ id: o.id, label: `${o.name} (${o.id})` })),
    [objects],
  )

  /** Refresh the constraint list from the backend. Read-only. */
  const refresh = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const resp = await listConstraints(sessionId)
      setRows(resp.result.data.constraints ?? [])
      setSolveReport(null)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to list constraints')
    } finally {
      setLoading(false)
    }
  }, [sessionId])

  // Auto-load once when the panel first becomes active.
  const [didAutoRun, setDidAutoRun] = useState(false)
  useEffect(() => {
    if (activePanel === 'constraints' && !didAutoRun) {
      setDidAutoRun(true)
      void refresh()
    }
  }, [activePanel, didAutoRun, refresh])

  /** Submit a new constraint from the add form. */
  const handleAdd = async (args: AddConstraintArgs) => {
    setAdding(true)
    setError(null)
    try {
      const resp = await addConstraint(args, sessionId)
      setScene(resp.scene)
      setShowAdd(false)
      await refresh()
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to add constraint')
    } finally {
      setAdding(false)
    }
  }

  /** Run the greedy solver and refresh the list afterwards. */
  const handleSolve = async () => {
    setSolving(true)
    setError(null)
    try {
      const resp = await solveConstraints(sessionId)
      setScene(resp.scene)
      setSolveReport(resp.result.data)
      await refresh()
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to solve constraints')
    } finally {
      setSolving(false)
    }
  }

  /** Clear every constraint. */
  const handleClear = async () => {
    setClearing(true)
    setError(null)
    try {
      const resp = await clearConstraints(sessionId)
      setScene(resp.scene)
      setSolveReport(null)
      await refresh()
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to clear constraints')
    } finally {
      setClearing(false)
    }
  }

  const passed = rows.filter((r) => r.passed).length
  const failed = rows.length - passed
  const allPass = rows.length > 0 && failed === 0

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="px-3 py-2.5 border-b border-border-subtle">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1.5">
            <Link2 size={12} className="text-accent-cyan" />
            <span className="text-[11px] font-semibold text-fg-primary">Constraints / 约束</span>
          </div>
          {rows.length > 0 && (
            <span className="text-[9px] text-fg-muted font-mono">
              {rows.length} rule{rows.length === 1 ? '' : 's'} · {passed} pass · {failed} fail
            </span>
          )}
        </div>
        <p className="text-[9.5px] text-fg-muted mt-1 leading-relaxed">
          Declare spatial relationships between objects, then run the solver to
          enforce them in one pass. Distinct from critique — constraints pin the
          relationships you want, the solver re-derives transforms from them.
        </p>
      </div>

      {/* Action bar: refresh / add / solve / clear */}
      <div className="px-3 py-2 border-b border-border-subtle bg-bg-base/40 flex items-center gap-1.5 flex-wrap">
        <button
          onClick={refresh}
          disabled={loading}
          title="Re-evaluate constraints"
          className="flex items-center gap-1 text-[10px] font-medium px-2 py-1.5 rounded border border-border text-fg-secondary hover:text-fg-primary hover:border-fg-muted/40 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          {loading ? <Loader2 size={11} className="animate-spin" /> : <RefreshCw size={11} />}
          Refresh
        </button>
        <button
          onClick={() => setShowAdd((v) => !v)}
          title="Add a new constraint"
          className={`flex items-center gap-1 text-[10px] font-medium px-2 py-1.5 rounded border transition-colors ${
            showAdd
              ? 'border-accent-cyan/40 bg-accent-cyan/10 text-accent-cyan'
              : 'border-border text-fg-secondary hover:text-fg-primary hover:border-fg-muted/40'
          }`}
        >
          <Plus size={11} />
          Add
        </button>
        <button
          onClick={handleSolve}
          disabled={solving || rows.length === 0}
          title="Run the solver to enforce all constraints"
          className="flex items-center gap-1 text-[10px] font-medium px-2 py-1.5 rounded border border-accent-emerald/30 bg-accent-emerald/10 text-accent-emerald hover:bg-accent-emerald/20 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          {solving ? <Loader2 size={11} className="animate-spin" /> : <Wand2 size={11} />}
          Solve
        </button>
        <button
          onClick={handleClear}
          disabled={clearing || rows.length === 0}
          title="Remove every constraint"
          className="flex items-center gap-1 text-[10px] font-medium px-2 py-1.5 rounded border border-border text-fg-muted hover:text-rose-300 hover:border-rose-400/40 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          {clearing ? <Loader2 size={11} className="animate-spin" /> : <Eraser size={11} />}
          Clear
        </button>
        {rows.length > 0 && (
          <span
            className={`ml-auto flex items-center gap-1 px-1.5 py-0.5 rounded text-[9px] font-semibold border ${
              allPass
                ? 'text-emerald-200 border-emerald-400/40 bg-emerald-400/10'
                : 'text-amber-200 border-amber-400/40 bg-amber-400/10'
            }`}
          >
            {allPass ? <CheckCircle2 size={9} /> : <AlertTriangle size={9} />}
            {allPass ? 'all satisfied' : `${failed} violated`}
          </span>
        )}
      </div>

      {/* Add constraint form (collapsible) */}
      {showAdd && (
        <AddConstraintForm
          objectOptions={objectOptions}
          onSubmit={handleAdd}
          onCancel={() => setShowAdd(false)}
          submitting={adding}
        />
      )}

      {/* Error banner */}
      {error && (
        <div className="mx-3 my-2 px-2 py-1.5 rounded border border-rose-400/30 bg-rose-400/10 text-[10px] text-rose-200 flex items-start gap-1.5">
          <X size={11} className="mt-0.5 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Constraint list / empty / loading states */}
      <div className="flex-1 overflow-y-auto p-2 space-y-1.5">
        {loading && rows.length === 0 && (
          <div className="flex items-center justify-center h-full text-fg-muted text-[11px] gap-2">
            <Loader2 size={13} className="animate-spin" />
            Evaluating constraints…
          </div>
        )}

        {!loading && rows.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full text-fg-muted text-[11px] gap-2 p-4 text-center">
            <Link2 size={18} className="opacity-50" />
            <p>No constraints yet.</p>
            <p className="text-[9.5px] text-fg-muted/70">
              Click <span className="text-fg-secondary">Add</span> to pin a relationship like
              “lamp above table” or “chair faces desk”, then <span className="text-fg-secondary">Solve</span> to enforce it.
            </p>
          </div>
        )}

        {rows.map((r) => (
          <ConstraintRow key={r.id} row={r} />
        ))}

        {/* Solve report */}
        {solveReport && <SolveReport report={solveReport} />}
      </div>

      {/* Footer hint */}
      <div className="px-3 py-2 border-t border-border-subtle text-[9px] text-fg-muted/70 flex items-center gap-1.5">
        <Link2 size={9} className="text-fg-muted/50" />
        Solve moves subjects only — anchors stay put. Clear does not revert transforms.
      </div>
    </div>
  )
}

interface AddConstraintFormProps {
  objectOptions: Array<{ id: string; label: string }>
  onSubmit: (args: AddConstraintArgs) => void
  onCancel: () => void
  submitting: boolean
}

/** Inline form for authoring a single constraint. Fields adapt to the
 *  selected kind (anchor / axis / distance / offset shown conditionally). */
function AddConstraintForm({ objectOptions, onSubmit, onCancel, submitting }: AddConstraintFormProps) {
  const [kind, setKind] = useState<ConstraintKind>('above')
  const [subject, setSubject] = useState('')
  const [anchor, setAnchor] = useState('')
  const [axis, setAxis] = useState<'x' | 'y' | 'z'>('y')
  const [distance, setDistance] = useState('')
  const [offset, setOffset] = useState('')
  const [tolerance, setTolerance] = useState('0.05')
  const [description, setDescription] = useState('')

  const needsAnchor = KIND_NEEDS_ANCHOR[kind]
  const usesAxis = KIND_USES_AXIS[kind]
  const usesDistance = KIND_USES_DISTANCE[kind]
  const usesOffset = KIND_USES_OFFSET[kind]

  const datalistId = 'constraint-object-options'
  const datalistIdAnchor = 'constraint-anchor-options'

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    if (!subject.trim()) return
    if (needsAnchor && !anchor.trim()) return
    const args: AddConstraintArgs = {
      kind,
      subject: subject.trim(),
    }
    if (needsAnchor) args.anchor = anchor.trim()
    if (usesAxis) args.axis = axis
    if (usesDistance && distance.trim()) args.distance = Number(distance)
    if (usesOffset && offset.trim()) args.offset = Number(offset)
    if (tolerance.trim()) args.tolerance = Number(tolerance)
    if (description.trim()) args.description = description.trim()
    onSubmit(args)
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="mx-2 my-2 rounded-md border border-border bg-bg-elevated/40 p-2.5 space-y-2"
    >
      <div className="flex items-center gap-1.5">
        <Plus size={11} className="text-accent-cyan" />
        <span className="text-[10.5px] font-semibold text-fg-primary">New constraint</span>
        <button
          type="button"
          onClick={onCancel}
          aria-label="Cancel"
          className="ml-auto text-fg-muted hover:text-fg-primary transition-colors"
        >
          <X size={12} />
        </button>
      </div>

      {/* Kind selector */}
      <label className="block">
        <span className="text-[9px] text-fg-muted uppercase tracking-wider">Kind</span>
        <select
          value={kind}
          onChange={(e) => setKind(e.target.value as ConstraintKind)}
          className="mt-0.5 w-full bg-bg-base border border-border rounded px-1.5 py-1 text-[10.5px] text-fg-primary focus:outline-none focus:border-accent-cyan/50"
        >
          {KIND_OPTIONS.map((k) => (
            <option key={k} value={k}>
              {k}
            </option>
          ))}
        </select>
        <span className="block text-[9px] text-fg-muted/70 mt-0.5 leading-snug">
          {KIND_HINT[kind]}
        </span>
      </label>

      {/* Subject + anchor */}
      <div className="grid grid-cols-2 gap-1.5">
        <label className="block">
          <span className="text-[9px] text-fg-muted uppercase tracking-wider">Subject</span>
          <input
            list={datalistId}
            value={subject}
            onChange={(e) => setSubject(e.target.value)}
            placeholder="id or name"
            required
            className="mt-0.5 w-full bg-bg-base border border-border rounded px-1.5 py-1 text-[10.5px] text-fg-primary focus:outline-none focus:border-accent-cyan/50"
          />
        </label>
        <label className="block">
          <span className="text-[9px] text-fg-muted uppercase tracking-wider">
            Anchor{needsAnchor ? '' : ' (opt)'}
          </span>
          <input
            list={datalistIdAnchor}
            value={anchor}
            onChange={(e) => setAnchor(e.target.value)}
            placeholder={needsAnchor ? 'id or name' : '—'}
            required={needsAnchor}
            disabled={!needsAnchor}
            className="mt-0.5 w-full bg-bg-base border border-border rounded px-1.5 py-1 text-[10.5px] text-fg-primary focus:outline-none focus:border-accent-cyan/50 disabled:opacity-40"
          />
        </label>
      </div>

      {/* Axis / distance / offset / tolerance — conditional */}
      <div className="grid grid-cols-2 gap-1.5">
        {usesAxis && (
          <label className="block">
            <span className="text-[9px] text-fg-muted uppercase tracking-wider">Axis</span>
            <select
              value={axis}
              onChange={(e) => setAxis(e.target.value as 'x' | 'y' | 'z')}
              className="mt-0.5 w-full bg-bg-base border border-border rounded px-1.5 py-1 text-[10.5px] text-fg-primary focus:outline-none focus:border-accent-cyan/50"
            >
              <option value="x">x</option>
              <option value="y">y</option>
              <option value="z">z</option>
            </select>
          </label>
        )}
        {usesDistance && (
          <label className="block">
            <span className="text-[9px] text-fg-muted uppercase tracking-wider">Distance</span>
            <input
              type="number"
              step="0.1"
              value={distance}
              onChange={(e) => setDistance(e.target.value)}
              placeholder="0.0"
              className="mt-0.5 w-full bg-bg-base border border-border rounded px-1.5 py-1 text-[10.5px] text-fg-primary focus:outline-none focus:border-accent-cyan/50"
            />
          </label>
        )}
        {usesOffset && (
          <label className="block">
            <span className="text-[9px] text-fg-muted uppercase tracking-wider">Offset / gap</span>
            <input
              type="number"
              step="0.1"
              value={offset}
              onChange={(e) => setOffset(e.target.value)}
              placeholder="0.0"
              className="mt-0.5 w-full bg-bg-base border border-border rounded px-1.5 py-1 text-[10.5px] text-fg-primary focus:outline-none focus:border-accent-cyan/50"
            />
          </label>
        )}
        <label className="block">
          <span className="text-[9px] text-fg-muted uppercase tracking-wider">Tolerance</span>
          <input
            type="number"
            step="0.01"
            value={tolerance}
            onChange={(e) => setTolerance(e.target.value)}
            className="mt-0.5 w-full bg-bg-base border border-border rounded px-1.5 py-1 text-[10.5px] text-fg-primary focus:outline-none focus:border-accent-cyan/50"
          />
        </label>
      </div>

      {/* Description */}
      <label className="block">
        <span className="text-[9px] text-fg-muted uppercase tracking-wider">Note (opt)</span>
        <input
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="human-readable description"
          className="mt-0.5 w-full bg-bg-base border border-border rounded px-1.5 py-1 text-[10.5px] text-fg-primary focus:outline-none focus:border-accent-cyan/50"
        />
      </label>

      {/* Submit / cancel */}
      <div className="flex items-center justify-end gap-1.5 pt-1">
        <button
          type="button"
          onClick={onCancel}
          className="text-[10px] px-2 py-1 rounded border border-border text-fg-muted hover:text-fg-primary transition-colors"
        >
          Cancel
        </button>
        <button
          type="submit"
          disabled={submitting}
          className="flex items-center gap-1 text-[10px] px-2 py-1 rounded border border-accent-cyan/30 bg-accent-cyan/10 text-accent-cyan hover:bg-accent-cyan/20 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          {submitting ? <Loader2 size={10} className="animate-spin" /> : <Plus size={10} />}
          Add
        </button>
      </div>

      {/* Shared datalists for object id/name autocompletion */}
      <datalist id={datalistId}>
        {objectOptions.map((o) => (
          <option key={o.id} value={o.id}>
            {o.label}
          </option>
        ))}
      </datalist>
      <datalist id={datalistIdAnchor}>
        {objectOptions.map((o) => (
          <option key={o.id} value={o.id}>
            {o.label}
          </option>
        ))}
      </datalist>
    </form>
  )
}

interface ConstraintRowProps {
  row: ConstraintEvalRow
}

/** A single constraint row with a pass/fail badge, kind, subject→anchor,
 *  and the evaluator's diagnostic message. */
function ConstraintRow({ row }: ConstraintRowProps) {
  return (
    <div
      className={`rounded-md border px-2 py-1.5 transition-colors ${
        row.passed
          ? 'border-emerald-400/20 bg-emerald-400/5'
          : 'border-rose-400/20 bg-rose-400/5'
      }`}
    >
      <div className="flex items-center gap-1.5">
        <span
          className={`flex items-center gap-0.5 px-1.5 py-px rounded text-[9px] font-mono font-semibold border ${
            row.passed
              ? 'text-emerald-200 border-emerald-400/40 bg-emerald-400/10'
              : 'text-rose-200 border-rose-400/40 bg-rose-400/10'
          }`}
        >
          {row.passed ? <CheckCircle2 size={9} /> : <XCircle size={9} />}
          {row.passed ? 'pass' : 'fail'}
        </span>
        <span className="text-[10.5px] text-fg-primary font-medium font-mono">
          {row.kind}
        </span>
        <span className="text-[9.5px] text-fg-muted font-mono truncate">
          {row.subject}
          {row.anchor ? ` → ${row.anchor}` : ''}
          {row.axis ? ` · ${row.axis}` : ''}
          {row.distance != null ? ` · d=${row.distance}` : ''}
          {row.offset != null ? ` · off=${row.offset}` : ''}
        </span>
      </div>
      {row.message && (
        <p className="text-[9px] text-fg-muted mt-0.5 leading-snug break-words font-mono">
          {row.message}
        </p>
      )}
      {row.description && (
        <p className="text-[9px] text-fg-muted/70 mt-0.5 leading-snug italic">
          {row.description}
        </p>
      )}
    </div>
  )
}

/** Compact summary of the last solve_constraints run: solved / moved / still
 *  violated. Mirrors the AutoFixReport in CritiquePanel. */
function SolveReport({ report }: { report: SolveConstraintsData }) {
  return (
    <div className="rounded-md border border-accent-cyan/30 bg-accent-cyan/5 px-2 py-1.5 space-y-1">
      <div className="flex items-center gap-1.5">
        <Wand2 size={11} className="text-accent-cyan" />
        <span className="text-[10.5px] font-semibold text-fg-primary">Solve report</span>
        <span className="text-[9px] text-fg-muted/70 ml-auto font-mono">
          {report.passes} pass{report.passes === 1 ? '' : 'es'}
        </span>
      </div>
      <div className="flex items-center gap-2 text-[9.5px] font-mono">
        <span className="text-emerald-300">
          {report.solved}/{report.total} solved
        </span>
        <span className="text-accent-cyan">~{report.moved.length} moved</span>
        <span className="text-rose-300">{report.still_violated.length} violated</span>
      </div>
      {report.moved.length > 0 && (
        <ul className="text-[9.5px] text-fg-secondary space-y-0.5">
          {report.moved.slice(0, 4).map((m, i) => (
            <li key={`${m.id}-${i}`} className="truncate font-mono">
              <span className="text-accent-cyan">·</span> {m.name}: [
              {m.from.map((v) => v.toFixed(2)).join(', ')}] → [
              {m.to.map((v) => v.toFixed(2)).join(', ')}]
            </li>
          ))}
          {report.moved.length > 4 && (
            <li className="text-fg-muted/70">+ {report.moved.length - 4} more</li>
          )}
        </ul>
      )}
      {report.still_violated.length > 0 && (
        <ul className="text-[9.5px] text-fg-muted space-y-0.5">
          {report.still_violated.slice(0, 3).map((s, i) => (
            <li key={`${s.id}-${i}`} className="truncate">
              <span className="text-rose-300">·</span> {s.kind}('{s.subject}'
              {s.anchor ? `, '${s.anchor}'` : ''}): {s.message}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
