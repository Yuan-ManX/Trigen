// Memory panel: shows the Agent's explicit (pinned) memory — durable facts
// the Agent chose to remember across turns and sessions. Fetched from
// /api/agent/memory. Each fact renders as a chip with a category color and
// a remove button. A small form at the top lets the user pin a new fact
// (text + optional category). Bilingual labels: English / 中文.
import { Brain, ChevronDown, ChevronRight, Loader2, Plus, Trash2, X } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  fetchAgentMemory,
  fetchReflections,
  forgetAgentFact,
  pinAgentFact,
  type PinnedFact,
  type TurnReflection,
} from '../../api/client'
import { useChat } from '../../store/useChat'
import { useEditor } from '../../store/useEditor'

/** Category visual metadata — color + label. Matches the backend's
 *  suggested category buckets ('project', 'preference', 'constraint',
 *  'style', 'audience', 'general'). Unknown categories fall back to
 *  the neutral default. */
const CATEGORY_META: Record<string, { color: string; label: string }> = {
  project: { color: 'text-cyan-300 border-cyan-400/30 bg-cyan-400/10', label: 'Project' },
  preference: { color: 'text-fuchsia-300 border-fuchsia-400/30 bg-fuchsia-400/10', label: 'Preference' },
  constraint: { color: 'text-amber-300 border-amber-400/30 bg-amber-400/10', label: 'Constraint' },
  style: { color: 'text-emerald-300 border-emerald-400/30 bg-emerald-400/10', label: 'Style' },
  audience: { color: 'text-violet-300 border-violet-400/30 bg-violet-400/10', label: 'Audience' },
  general: { color: 'text-fg-secondary border-border bg-bg-elevated/40', label: 'General' },
}

const DEFAULT_CATEGORY_META = {
  color: 'text-fg-secondary border-border bg-bg-elevated/40',
  label: 'General',
}

function categoryMeta(category: string) {
  return CATEGORY_META[category] ?? DEFAULT_CATEGORY_META
}

const CATEGORY_OPTIONS = ['general', 'project', 'preference', 'constraint', 'style', 'audience']

export function MemoryPanel() {
  const [facts, setFacts] = useState<PinnedFact[]>([])
  const [patternCount, setPatternCount] = useState(0)
  const [reflections, setReflections] = useState<TurnReflection[]>([])
  const [reflOpen, setReflOpen] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  // New-fact form state
  const [draftText, setDraftText] = useState('')
  const [draftCategory, setDraftCategory] = useState('general')
  const [submitting, setSubmitting] = useState(false)
  const activePanel = useEditor((s) => s.activePanel)
  const sessionId = useChat((s) => s.sessionId)
  const send = useChat((s) => s.send)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [mem, reflRes] = await Promise.all([
        fetchAgentMemory(),
        fetchReflections(sessionId || 'default', 6).catch(() => ({ reflections: [] })),
      ])
      // Backend stores facts in pinned_at order; sort newest-first client-side.
      const sorted = [...mem.pinned_facts].sort((a, b) => b.pinned_at - a.pinned_at)
      setFacts(sorted)
      setPatternCount(mem.summary?.pattern_count ?? 0)
      setReflections(reflRes.reflections ?? [])
      setError(null)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load memory')
    } finally {
      setLoading(false)
    }
  }, [sessionId])

  // Load on mount and whenever the memory tab becomes active.
  useEffect(() => {
    if (activePanel === 'memory') {
      void load()
    }
  }, [activePanel, load])

  /** Pin a new fact from the form. */
  const handlePin = async () => {
    const text = draftText.trim()
    if (!text) return
    setSubmitting(true)
    try {
      const result = await pinAgentFact(text, draftCategory)
      // Optimistic refresh: prepend the new fact for instant feedback,
      // then re-fetch to guarantee consistency with the backend.
      setFacts((prev) => [result.fact, ...prev])
      setDraftText('')
      void load()
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to pin fact')
    } finally {
      setSubmitting(false)
    }
  }

  /** Remove a single fact by text. */
  const handleForget = async (fact: PinnedFact) => {
    try {
      await forgetAgentFact({ text: fact.text })
      setFacts((prev) => prev.filter((f) => f.text !== fact.text))
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to forget fact')
    }
  }

  /** Ask the Agent (via chat) to recall facts — useful when the user wants
   *  the Agent to ground its next reply in long-lived context. */
  const askRecall = () => {
    send('Recall my pinned facts and use them as context for this scene.')
  }

  // Group facts by category for display, preserving first-seen order.
  const grouped = useMemo(() => {
    const groups: Array<{ category: string; facts: PinnedFact[] }> = []
    const index: Record<string, number> = {}
    for (const f of facts) {
      if (!(f.category in index)) {
        index[f.category] = groups.length
        groups.push({ category: f.category, facts: [] })
      }
      groups[index[f.category]].facts.push(f)
    }
    // Sort groups by a stable preferred order, then alphabetical.
    const order = ['project', 'preference', 'constraint', 'style', 'audience', 'general']
    groups.sort((a, b) => {
      const ai = order.indexOf(a.category)
      const bi = order.indexOf(b.category)
      if (ai !== -1 && bi !== -1) return ai - bi
      if (ai !== -1) return -1
      if (bi !== -1) return 1
      return a.category.localeCompare(b.category)
    })
    return groups
  }, [facts])

  if (loading && facts.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-fg-muted text-[11px] gap-2">
        <Loader2 size={13} className="animate-spin" />
        Loading memory…
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="px-3 py-2.5 border-b border-border-subtle">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1.5">
            <Brain size={12} className="text-accent-cyan" />
            <span className="text-[11px] font-semibold text-fg-primary">Memory / 记忆</span>
          </div>
          <span className="text-[9px] text-fg-muted font-mono">
            {facts.length} fact{facts.length === 1 ? '' : 's'}
          </span>
        </div>
        <p className="text-[9.5px] text-fg-muted mt-1 leading-relaxed">
          Durable facts the Agent remembers across turns and sessions. Pinned facts are injected into every prompt so you don't repeat yourself.
        </p>
      </div>

      {/* Pin-a-fact form */}
      <div className="px-3 py-2 border-b border-border-subtle bg-bg-base/40">
        <div className="flex flex-col gap-1.5">
          <input
            type="text"
            value={draftText}
            onChange={(e) => setDraftText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !submitting && draftText.trim()) {
                e.preventDefault()
                void handlePin()
              }
            }}
            placeholder="Pin a fact, e.g. 'Target platform is mobile WebGL'"
            className="w-full text-[11px] bg-bg-elevated/60 border border-border rounded px-2 py-1.5 text-fg-primary placeholder:text-fg-muted/60 focus:outline-none focus:border-accent-cyan/50"
          />
          <div className="flex items-center gap-1.5">
            <select
              value={draftCategory}
              onChange={(e) => setDraftCategory(e.target.value)}
              className="text-[10px] bg-bg-elevated/60 border border-border rounded px-1.5 py-1 text-fg-secondary focus:outline-none focus:border-accent-cyan/50 capitalize"
            >
              {CATEGORY_OPTIONS.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
            <button
              onClick={handlePin}
              disabled={!draftText.trim() || submitting}
              className="ml-auto flex items-center gap-1 text-[10px] font-medium px-2 py-1 rounded border border-accent-cyan/30 bg-accent-cyan/10 text-accent-cyan hover:bg-accent-cyan/20 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              {submitting ? <Loader2 size={11} className="animate-spin" /> : <Plus size={11} />}
              Pin
            </button>
          </div>
        </div>
      </div>

      {/* Error banner */}
      {error && (
        <div className="mx-3 my-2 px-2 py-1.5 rounded border border-rose-400/30 bg-rose-400/10 text-[10px] text-rose-200 flex items-start gap-1.5">
          <X size={11} className="mt-0.5 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Facts list, grouped by category */}
      <div className="flex-1 overflow-y-auto p-2 space-y-3">
        {facts.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-fg-muted text-[11px] gap-2 p-4 text-center">
            <Brain size={18} className="opacity-50" />
            <p>No pinned facts yet.</p>
            <p className="text-[9.5px] text-fg-muted/70">
              Pin a fact above, or ask the Agent: <button onClick={askRecall} className="text-accent-cyan hover:underline">“remember that I prefer low-poly aesthetics”</button>.
            </p>
          </div>
        ) : (
          grouped.map((group) => {
            const meta = categoryMeta(group.category)
            return (
              <div key={group.category} className="space-y-1.5">
                <div className="flex items-center gap-1.5 px-1">
                  <span className={`text-[9.5px] uppercase tracking-wider font-semibold px-1.5 py-px rounded border ${meta.color}`}>
                    {meta.label}
                  </span>
                  <span className="text-[9px] text-fg-muted/60 font-mono ml-auto">
                    {group.facts.length}
                  </span>
                </div>
                <div className="space-y-1">
                  {group.facts.map((fact) => (
                    <FactChip
                      key={`${fact.text}-${fact.pinned_at}`}
                      fact={fact}
                      onForget={handleForget}
                    />
                  ))}
                </div>
              </div>
            )
          })
        )}
      </div>

      {/* Session reflections — the Agent's own per-turn self-assessments */}
      {reflections.length > 0 && (
        <div className="px-3 py-2 border-t border-border-subtle">
          <button
            onClick={() => setReflOpen((v) => !v)}
            className="w-full flex items-center gap-1.5 text-left"
          >
            {reflOpen ? (
              <ChevronDown size={11} className="text-fg-muted" />
            ) : (
              <ChevronRight size={11} className="text-fg-muted" />
            )}
            <span className="text-[9px] uppercase tracking-wider text-fg-muted font-semibold">
              Session reflections
            </span>
            <span className="text-[9px] text-fg-muted/60 font-mono ml-auto">
              {reflections.length}
            </span>
          </button>
          {reflOpen && (
            <div className="mt-1.5 space-y-1.5">
              {reflections.map((r) => {
                const rating = r.quality?.rating
                return (
                  <div
                    key={r.turn}
                    className="rounded-md border border-border bg-bg-base/40 px-2 py-1.5"
                  >
                    <div className="flex items-center gap-1.5">
                      <span className="text-[9px] font-mono text-fg-muted">#{r.turn}</span>
                      {typeof rating === 'string' && (
                        <span
                          className={`text-[8.5px] uppercase tracking-wide font-semibold px-1 py-px rounded ${
                            rating === 'excellent'
                              ? 'text-emerald-300 bg-emerald-400/10 border border-emerald-400/20'
                              : rating === 'good'
                                ? 'text-accent-cyan bg-accent-cyan/10 border border-accent-cyan/20'
                                : 'text-amber-300 bg-amber-400/10 border border-amber-400/20'
                          }`}
                        >
                          {rating}
                        </span>
                      )}
                    </div>
                    {r.goal && <p className="text-[10px] text-fg-secondary mt-0.5 truncate">{r.goal}</p>}
                    {r.outcome && (
                      <p className="text-[9.5px] text-fg-muted leading-relaxed mt-0.5 line-clamp-2">
                        {r.outcome}
                      </p>
                    )}
                    {r.tool_calls.length > 0 && (
                      <p className="text-[8.5px] font-mono text-fg-muted/60 mt-0.5 truncate">
                        {r.tool_calls.join(' · ')}
                      </p>
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}

      {/* Footer hint */}
      <div className="px-3 py-2 border-t border-border-subtle text-[9px] text-fg-muted/70 flex items-center justify-between gap-1.5">
        <span className="flex items-center gap-1.5">
          <Trash2 size={9} className="text-fg-muted/50" />
          {patternCount} cached pattern{patternCount === 1 ? '' : 's'} learned
        </span>
        <button
          onClick={askRecall}
          className="text-accent-cyan/80 hover:text-accent-cyan hover:underline"
        >
          Ask Agent to recall
        </button>
      </div>
    </div>
  )
}

interface FactChipProps {
  fact: PinnedFact
  onForget: (fact: PinnedFact) => void
}

function FactChip({ fact, onForget }: FactChipProps) {
  const meta = categoryMeta(fact.category)
  return (
    <div
      className={`group flex items-start gap-1.5 rounded-md border ${meta.color} px-2 py-1.5`}
      title={`Pinned ${new Date(fact.pinned_at * 1000).toLocaleString()}`}
    >
      <p className="flex-1 text-[10.5px] leading-relaxed text-fg-primary break-words">
        {fact.text}
      </p>
      <button
        onClick={() => onForget(fact)}
        aria-label="Forget fact"
        className="shrink-0 mt-0.5 text-fg-muted/60 hover:text-rose-300 opacity-0 group-hover:opacity-100 transition-opacity"
      >
        <X size={11} />
      </button>
    </div>
  )
}
