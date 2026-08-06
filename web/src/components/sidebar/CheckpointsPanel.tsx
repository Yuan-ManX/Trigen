// Checkpoints panel: the scene's revisioned version history.
// Each checkpoint is an immutable revision (1, 2, 3, …) captured from the
// live scene with an auto-generated semantic summary. The user can create a
// new revision, restore any earlier one, and diff two revisions to see what
// changed (added / removed / modified objects). Fetched from the
// /api/agent/checkpoints endpoints. Bilingual labels: English / 中文.
import { GitCommitVertical, GitCompare, Loader2, Plus, RotateCcw, X } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  createCheckpoint,
  diffCheckpoints,
  fetchCheckpoints,
  restoreCheckpoint,
} from '../../api/client'
import type { CheckpointDiff, CheckpointEntry } from '../../types'
import { useChat } from '../../store/useChat'
import { useEditor } from '../../store/useEditor'
import { useScene } from '../../store/useScene'

/** Format a unix timestamp as a compact local string. */
function fmtTime(ts: number): string {
  try {
    return new Date(ts * 1000).toLocaleString(undefined, {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return ''
  }
}

export function CheckpointsPanel() {
  const [entries, setEntries] = useState<CheckpointEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  // New-checkpoint form state
  const [draft, setDraft] = useState('')
  const [creating, setCreating] = useState(false)
  // Diff-selection state
  const [diffA, setDiffA] = useState<number | null>(null)
  const [diffB, setDiffB] = useState<number | null>(null)
  const [diff, setDiff] = useState<CheckpointDiff | null>(null)
  const [diffing, setDiffing] = useState(false)
  // Restore state (loading spinner on the restoring revision)
  const [restoring, setRestoring] = useState<number | null>(null)

  const sessionId = useChat((s) => s.sessionId)
  const activePanel = useEditor((s) => s.activePanel)
  const setScene = useScene((s) => s.setScene)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = await fetchCheckpoints()
      setEntries(data.checkpoints)
      setError(null)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load checkpoints')
    } finally {
      setLoading(false)
    }
  }, [])

  // Load on mount and whenever the panel becomes active.
  useEffect(() => {
    if (activePanel === 'checkpoints') {
      void load()
    }
  }, [activePanel, load])

  /** Capture the current scene as a new revision. */
  const handleCreate = async () => {
    setCreating(true)
    try {
      await createCheckpoint(draft.trim(), sessionId)
      setDraft('')
      // Clear the diff selection since the history changed.
      setDiff(null)
      setDiffA(null)
      setDiffB(null)
      void load()
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to create checkpoint')
    } finally {
      setCreating(false)
    }
  }

  /** Restore the live scene to a revision. */
  const handleRestore = async (entry: CheckpointEntry) => {
    setRestoring(entry.revision)
    try {
      const result = await restoreCheckpoint(entry.revision, sessionId)
      // Swap the live scene into the editor so the restore is instantly visible.
      setScene(result.scene)
      setError(null)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : `Failed to restore revision ${entry.revision}`)
    } finally {
      setRestoring(null)
    }
  }

  /** Compute and show the diff between the two selected revisions. */
  const handleDiff = async () => {
    if (diffA === null || diffB === null) return
    setDiffing(true)
    try {
      setDiff(await diffCheckpoints(diffA, diffB))
      setError(null)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to compute diff')
    } finally {
      setDiffing(false)
    }
  }

  const maxRevision = useMemo(
    () => (entries.length ? Math.max(...entries.map((e) => e.revision)) : 0),
    [entries],
  )

  if (loading && entries.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-fg-muted text-[11px] gap-2">
        <Loader2 size={13} className="animate-spin" />
        Loading checkpoints…
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="px-3 py-2.5 border-b border-border-subtle">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1.5">
            <GitCommitVertical size={12} className="text-accent-purple" />
            <span className="text-[11px] font-semibold text-fg-primary">Checkpoints / 版本</span>
          </div>
          <span className="text-[9px] text-fg-muted font-mono">
            {entries.length} rev{entries.length === 1 ? '' : 's'}
          </span>
        </div>
        <p className="text-[9.5px] text-fg-muted mt-1 leading-relaxed">
          Immutable scene revisions with semantic summaries. Capture, restore, and diff any point in the scene's evolution.
        </p>
      </div>

      {/* Create-a-checkpoint form */}
      <div className="px-3 py-2 border-b border-border-subtle bg-bg-base/40">
        <div className="flex items-center gap-1.5">
          <input
            type="text"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !creating) {
                e.preventDefault()
                void handleCreate()
              }
            }}
            placeholder="Label this revision, e.g. 'Forest + three-point light'"
            className="flex-1 text-[11px] bg-bg-elevated/60 border border-border rounded px-2 py-1.5 text-fg-primary placeholder:text-fg-muted/60 focus:outline-none focus:border-accent-purple/50"
          />
          <button
            onClick={handleCreate}
            disabled={creating}
            title="Capture current scene as a new revision"
            className="flex items-center gap-1 text-[10px] font-medium px-2 py-1.5 rounded border border-accent-purple/30 bg-accent-purple/10 text-accent-purple hover:bg-accent-purple/20 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            {creating ? <Loader2 size={11} className="animate-spin" /> : <Plus size={11} />}
            Rev {maxRevision + 1}
          </button>
        </div>
      </div>

      {/* Error banner */}
      {error && (
        <div className="mx-3 my-2 px-2 py-1.5 rounded border border-rose-400/30 bg-rose-400/10 text-[10px] text-rose-200 flex items-start gap-1.5">
          <X size={11} className="mt-0.5 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Diff selector */}
      {entries.length >= 2 && (
        <div className="px-3 py-2 border-b border-border-subtle bg-bg-base/20">
          <div className="flex items-center gap-1.5">
            <GitCompare size={11} className="text-fg-muted shrink-0" />
            <select
              value={diffA ?? ''}
              onChange={(e) => {
                setDiffA(e.target.value === '' ? null : Number(e.target.value))
                setDiff(null)
              }}
              className="text-[10px] bg-bg-elevated/60 border border-border rounded px-1 py-1 text-fg-secondary focus:outline-none focus:border-accent-purple/50"
            >
              <option value="">—</option>
              {entries.map((e) => (
                <option key={e.revision} value={e.revision}>
                  Rev {e.revision}
                </option>
              ))}
            </select>
            <span className="text-[9px] text-fg-muted">→</span>
            <select
              value={diffB ?? ''}
              onChange={(e) => {
                setDiffB(e.target.value === '' ? null : Number(e.target.value))
                setDiff(null)
              }}
              className="text-[10px] bg-bg-elevated/60 border border-border rounded px-1 py-1 text-fg-secondary focus:outline-none focus:border-accent-purple/50"
            >
              <option value="">—</option>
              {entries.map((e) => (
                <option key={e.revision} value={e.revision}>
                  Rev {e.revision}
                </option>
              ))}
            </select>
            <button
              onClick={handleDiff}
              disabled={diffA === null || diffB === null || diffA === diffB || diffing}
              className="ml-auto flex items-center gap-1 text-[10px] px-1.5 py-1 rounded border border-border text-fg-secondary hover:text-accent-cyan disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              {diffing ? <Loader2 size={10} className="animate-spin" /> : 'Diff'}
            </button>
          </div>
          {diff && (
            <div className="mt-1.5 space-y-0.5 text-[9.5px]">
              <div className="flex items-center gap-2 text-fg-muted">
                <span className="text-emerald-300">+{diff.added_count}</span>
                <span className="text-rose-300">-{diff.removed_count}</span>
                <span className="text-amber-300">~{diff.changed_count}</span>
                <span className="text-fg-muted/60">kept {diff.kept_count}</span>
              </div>
              {diff.added.length > 0 && (
                <div className="text-emerald-300/90 truncate">
                  + {diff.added.slice(0, 4).map((o) => o.name).join(', ')}
                  {diff.added.length > 4 ? ` +${diff.added.length - 4} more` : ''}
                </div>
              )}
              {diff.removed.length > 0 && (
                <div className="text-rose-300/90 truncate">
                  - {diff.removed.slice(0, 4).map((o) => o.name).join(', ')}
                  {diff.removed.length > 4 ? ` +${diff.removed.length - 4} more` : ''}
                </div>
              )}
              {diff.changed.length > 0 && (
                <div className="text-amber-300/90 truncate">
                  ~ {diff.changed.slice(0, 4).map((o) => o.name).join(', ')}
                  {diff.changed.length > 4 ? ` +${diff.changed.length - 4} more` : ''}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Checkpoint history list */}
      <div className="flex-1 overflow-y-auto p-2 space-y-1.5">
        {entries.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-fg-muted text-[11px] gap-2 p-4 text-center">
            <GitCommitVertical size={18} className="opacity-50" />
            <p>No checkpoints yet.</p>
            <p className="text-[9.5px] text-fg-muted/70">
              Capture the current scene as revision 1 above, or ask the Agent: “checkpoint this scene”.
            </p>
          </div>
        ) : (
          entries.map((entry) => (
            <CheckpointRow
              key={entry.revision}
              entry={entry}
              latest={entry.revision === maxRevision}
              restoring={restoring === entry.revision}
              onRestore={handleRestore}
            />
          ))
        )}
      </div>

      {/* Footer hint */}
      <div className="px-3 py-2 border-t border-border-subtle text-[9px] text-fg-muted/70 flex items-center gap-1.5">
        <GitCommitVertical size={9} className="text-fg-muted/50" />
        Checkpoints are immutable — restoring never deletes later revisions.
      </div>
    </div>
  )
}

interface CheckpointRowProps {
  entry: CheckpointEntry
  latest: boolean
  restoring: boolean
  onRestore: (entry: CheckpointEntry) => void
}

function CheckpointRow({ entry, latest, restoring, onRestore }: CheckpointRowProps) {
  const gc = entry.summary?.geometry_counts ?? {}
  const parts = Object.entries(gc).map(([k, v]) => `${v} ${k}`)
  return (
    <div
      className={`group rounded-md border px-2 py-1.5 transition-colors ${
        latest
          ? 'border-accent-purple/30 bg-accent-purple/5'
          : 'border-border bg-bg-elevated/30'
      }`}
    >
      <div className="flex items-center gap-1.5">
        <span
          className={`px-1.5 py-px rounded text-[9.5px] font-mono font-semibold border ${
            latest
              ? 'text-accent-purple border-accent-purple/40 bg-accent-purple/10'
              : 'text-fg-secondary border-border bg-bg-elevated/60'
          }`}
        >
          R{entry.revision}
        </span>
        <span className="text-[9px] text-fg-muted/60 font-mono">{fmtTime(entry.created_at)}</span>
        <button
          onClick={() => onRestore(entry)}
          disabled={restoring}
          title="Restore this revision"
          className="ml-auto flex items-center gap-1 text-[9.5px] px-1.5 py-0.5 rounded border border-border text-fg-muted hover:text-accent-cyan hover:border-accent-cyan/40 disabled:opacity-40 disabled:cursor-not-allowed transition-colors opacity-0 group-hover:opacity-100"
        >
          {restoring ? <Loader2 size={9} className="animate-spin" /> : <RotateCcw size={9} />}
          Restore
        </button>
      </div>
      {entry.description && (
        <p className="text-[10.5px] text-fg-primary leading-snug mt-1 break-words">
          {entry.description}
        </p>
      )}
      <p className="text-[9px] text-fg-muted mt-0.5 leading-snug">
        {entry.summary?.prose ?? `${entry.summary?.object_count ?? 0} objects`}
        {parts.length > 0 && (
          <span className="text-fg-muted/60"> · {parts.slice(0, 3).join(', ')}</span>
        )}
      </p>
    </div>
  )
}