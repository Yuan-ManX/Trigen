// Skills tab: catalogs creative skills (multi-tool recipes) fetched from
// /api/skills, grouped by category. Clicking a skill sends a deterministic
// "use the <skill> skill" prompt via the chat store so the Agent invokes
// invoke_skill with no ambiguity.
import {
  Boxes,
  Lightbulb,
  Loader2,
  Package,
  Sparkles,
  Spline,
  Trees,
  Triangle,
  Wand2,
  X,
} from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { fetchSkills, type SkillDescriptor } from '../../api/client'
import { useChat } from '../../store/useChat'

/** Category metadata: icon + accent color + label. */
const CATEGORY_META: Record<
  string,
  { icon: typeof Boxes; color: string; label: string }
> = {
  architecture: { icon: Boxes, color: 'text-amber-300', label: 'Architecture' },
  nature: { icon: Trees, color: 'text-emerald-400', label: 'Nature' },
  abstract: { icon: Spline, color: 'text-fuchsia-400', label: 'Abstract' },
  lighting: { icon: Lightbulb, color: 'text-yellow-300', label: 'Lighting' },
  layout: { icon: Package, color: 'text-cyan-300', label: 'Layout' },
  effects: { icon: Sparkles, color: 'text-rose-300', label: 'Effects' },
  terrain: { icon: Triangle, color: 'text-emerald-300', label: 'Terrain' },
  sci_fi: { icon: Wand2, color: 'text-violet-400', label: 'Sci-Fi' },
}

const DEFAULT_CATEGORY = {
  icon: Sparkles,
  color: 'text-accent-cyan',
  label: 'Creative',
}

function categoryMeta(category: string) {
  return CATEGORY_META[category] ?? DEFAULT_CATEGORY
}

export function SkillsTab() {
  const [skills, setSkills] = useState<SkillDescriptor[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const send = useChat((s) => s.send)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    fetchSkills()
      .then((list) => {
        if (cancelled) return
        setSkills(list)
        setError(null)
      })
      .catch((err: unknown) => {
        if (cancelled) return
        setError(err instanceof Error ? err.message : 'Failed to load skills')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  // Group skills by category preserving first-seen order.
  const grouped = useMemo(() => {
    const groups: Array<{ category: string; skills: SkillDescriptor[] }> = []
    const index: Record<string, number> = {}
    for (const s of skills) {
      if (!(s.category in index)) {
        index[s.category] = groups.length
        groups.push({ category: s.category, skills: [] })
      }
      groups[index[s.category]].skills.push(s)
    }
    return groups
  }, [skills])

  /** Click handler: send a deterministic skill-invocation prompt. */
  const invoke = (skill: SkillDescriptor) => {
    send(`Use the ${skill.name} skill to create a ${skill.name.replace(/_/g, ' ')}`)
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full text-fg-muted text-[11px] gap-2">
        <Loader2 size={13} className="animate-spin" />
        Loading skills…
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-fg-muted text-[11px] gap-2 p-4 text-center">
        <X size={16} className="text-rose-400" />
        <p>{error}</p>
      </div>
    )
  }

  if (skills.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-fg-muted text-[11px] gap-2 p-4 text-center">
        <Wand2 size={16} />
        <p>No skills registered yet.</p>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="px-3 py-2.5 border-b border-border-subtle">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1.5">
            <Wand2 size={12} className="text-accent-cyan" />
            <span className="text-[11px] font-semibold text-fg-primary">
              Creative Skills
            </span>
          </div>
          <span className="text-[9px] text-fg-muted font-mono">
            {skills.length} available
          </span>
        </div>
        <p className="text-[9.5px] text-fg-muted mt-1 leading-relaxed">
          Click a skill to run its multi-step recipe through the Agent.
        </p>
      </div>

      {/* Skills grouped by category */}
      <div className="flex-1 overflow-y-auto p-2 space-y-3">
        {grouped.map((group) => {
          const meta = categoryMeta(group.category)
          const GroupIcon = meta.icon
          return (
            <div key={group.category} className="space-y-1.5">
              <div className="flex items-center gap-1.5 px-1">
                <GroupIcon size={11} className={meta.color} />
                <span className="text-[9.5px] uppercase tracking-wider font-semibold text-fg-muted">
                  {meta.label}
                </span>
                <span className="text-[9px] text-fg-muted/60 font-mono ml-auto">
                  {group.skills.length}
                </span>
              </div>
              <div className="space-y-1">
                {group.skills.map((skill) => (
                  <SkillRow key={skill.name} skill={skill} onInvoke={invoke} />
                ))}
              </div>
            </div>
          )
        })}
      </div>

      {/* Footer hint */}
      <div className="px-3 py-2 border-t border-border-subtle text-[9px] text-fg-muted/70 flex items-center gap-1.5">
        <Triangle size={9} className="text-fg-muted/50" />
        Skills compose with the full toolset — every step stays editable.
      </div>
    </div>
  )
}

interface SkillRowProps {
  skill: SkillDescriptor
  onInvoke: (skill: SkillDescriptor) => void
}

function SkillRow({ skill, onInvoke }: SkillRowProps) {
  // Read the declared parameter count so users see how tweakable a skill is.
  const paramCount = useMemo(() => {
    const props = (skill.parameters as { properties?: Record<string, unknown> })?.properties
    return props ? Object.keys(props).length : 0
  }, [skill.parameters])

  return (
    <button
      onClick={() => onInvoke(skill)}
      className="w-full group flex flex-col gap-0.5 rounded-md border border-border bg-bg-elevated/30 hover:bg-bg-hover hover:border-accent-cyan/40 transition-colors px-2.5 py-1.5 text-left"
    >
      <div className="flex items-center justify-between gap-2">
        <span className="text-[11px] font-medium text-fg-primary group-hover:text-accent-cyan transition-colors">
          {skill.name.replace(/_/g, ' ')}
        </span>
        {paramCount > 0 && (
          <span
            title={`${paramCount} parameter${paramCount === 1 ? '' : 's'}`}
            className="shrink-0 text-[8.5px] font-mono text-fg-muted/70 border border-border rounded px-1 py-px"
          >
            {paramCount}p
          </span>
        )}
      </div>
      <p className="text-[9.5px] text-fg-muted leading-relaxed line-clamp-2">
        {skill.description}
      </p>
    </button>
  )
}
