// SceneContextPanel: analyzes the live scene state and recommends
// scene-aware starting points for the Agent. The panel is shown above the
// prompt gallery whenever the user has not yet started typing — it reacts
// to the current scene and points out the next most useful action.
//
// The analysis is deterministic (no LLM call): it counts objects, lights,
// cameras and layers, then picks up to four suggestion chips from a lookup
// table. Suggestions are curated by intent and translated into a concrete
// prompt the user can insert or send.
import { Flame, Info, Lightbulb, Plus, Sparkles, Sun, type LucideIcon } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { fetchSkills, type SkillDescriptor } from '../../api/client'
import { useScene } from '../../store/useScene'

interface SceneContextPanelProps {
  /** Insert a suggested prompt into the input bar without sending it. */
  onInsert: (prompt: string) => void
  disabled: boolean
}

/** A single contextual suggestion chip. */
interface Suggestion {
  id: string
  label: string
  prompt: string
  icon: LucideIcon
  accent: string
}

/** A scene-aware context summary used to drive suggestion selection. */
interface SceneContext {
  objectCount: number
  lightCount: number
  cameraCount: number
  layerCount: number
  hasBackground: boolean
  hasEnvironment: boolean
  hasFog: boolean
  hasGrid: boolean
  tagSet: Set<string>
}

/** Derive a scene context summary from the live scene store. */
function deriveContext(scene: ReturnType<typeof useScene.getState>['scene']): SceneContext {
  const tagSet = new Set<string>()
  for (const o of scene.objects) {
    for (const t of o.tags ?? []) tagSet.add(t)
  }
  return {
    objectCount: scene.objects.length,
    lightCount: scene.lights.length,
    cameraCount: scene.cameras.length,
    layerCount: Object.keys(scene.layers ?? {}).length,
    hasBackground: Boolean(scene.background && scene.background !== '#050505'),
    hasEnvironment: Boolean(scene.environment),
    hasFog: Boolean(scene.fog),
    hasGrid: scene.grid_visible !== false,
    tagSet,
  }
}

/** Curated suggestion library — keyed by scene-state fingerprints. The
 *  first matching entry wins; entries are tried in priority order from
 *  top to bottom so the most urgent gap surfaces first. */
function pickSuggestions(ctx: SceneContext): Suggestion[] {
  const out: Suggestion[] = []
  const seenIds = new Set<string>()
  const add = (s: Suggestion) => {
    if (seenIds.has(s.id)) return
    seenIds.add(s.id)
    out.push(s)
  }

  // 1. Empty scene → show the fastest on-ramp first
  if (ctx.objectCount === 0 && ctx.lightCount === 0) {
    add({
      id: 'empty-hero',
      label: 'Shape a hero',
      prompt: 'Create a centered low-poly hero object — a stylized sphere — on a soft ground plane with simple studio lighting.',
      icon: Sparkles,
      accent: 'text-accent-cyan',
    })
    add({
      id: 'empty-room',
      label: 'Build a room',
      prompt: 'Compose a small stylized room with walls, floor, a window and a simple lamp.',
      icon: Plus,
      accent: 'text-accent-cyan',
    })
    add({
      id: 'empty-product',
      label: 'Product showcase',
      prompt: 'Set up a minimal product showcase: a glossy sphere on a white pedestal with soft three-point studio lighting.',
      icon: Sparkles,
      accent: 'text-accent-gold',
    })
    add({
      id: 'empty-landscape',
      label: 'Landscape',
      prompt: 'Compose a wide stylized landscape: rolling ground, a few hills, and a warm sun.',
      icon: Sparkles,
      accent: 'text-emerald-400',
    })
    return out
  }

  // 2. Objects exist but no lights
  if (ctx.objectCount > 0 && ctx.lightCount === 0) {
    add({
      id: 'add-light',
      label: 'Add lighting',
      prompt: 'Set up a three-point lighting rig around the main object: warm key, cool fill, and a cyan rim.',
      icon: Lightbulb,
      accent: 'text-accent-gold',
    })
    add({
      id: 'scene-preset-studio',
      label: 'Studio preset',
      prompt: 'Apply the studio scene preset with balanced exposure and soft studio lights.',
      icon: Sun,
      accent: 'text-accent-gold',
    })
  }

  // 3. Objects and lights but no environment/background
  if (ctx.objectCount > 0 && !ctx.hasBackground && !ctx.hasEnvironment) {
    add({
      id: 'set-background',
      label: 'Set background',
      prompt: 'Set the background to a soft gradient and add a subtle fog for depth.',
      icon: Sparkles,
      accent: 'text-accent-cyan',
    })
    add({
      id: 'add-fog',
      label: 'Add atmospheric fog',
      prompt: 'Enable a light amber fog with a small density to add atmospheric depth.',
      icon: Flame,
      accent: 'text-rose-300',
    })
  }

  // 4. No camera yet
  if (ctx.objectCount > 0 && ctx.cameraCount === 0) {
    add({
      id: 'fit-camera',
      label: 'Frame the subject',
      prompt: 'Fit the main camera to the scene subject and add a second side camera.',
      icon: Sparkles,
      accent: 'text-accent-cyan',
    })
  }

  // 5. More than 5 objects — suggest grouping / layering
  if (ctx.objectCount >= 5) {
    add({
      id: 'organize-layers',
      label: 'Organize with layers',
      prompt: 'Group the hero object and its lights into a new layer called "Hero" and lock it.',
      icon: Plus,
      accent: 'text-accent-purple',
    })
  }

  // 6. Scene has no animation
  if (ctx.objectCount > 0) {
    add({
      id: 'animate',
      label: 'Add motion',
      prompt: 'Animate the hero object with a gentle orbit and a slow bounce on the ground.',
      icon: Sparkles,
      accent: 'text-emerald-400',
    })
  }

  // Always append a few evergreen creative prompts
  add({
    id: 'evergreen-orbit',
    label: 'Orbit camera tour',
    prompt: 'Animate the camera in a slow orbit around the main object at height 2, radius 6, looping smoothly.',
    icon: Sparkles,
    accent: 'text-accent-cyan',
  })
  add({
    id: 'evergreen-cinematic',
    label: 'Cinematic reveal',
    prompt: 'Compose a cinematic storyboard: wide establishing shot, close-up on the hero, slow orbit back out.',
    icon: Sparkles,
    accent: 'text-rose-300',
  })

  return out.slice(0, 6)
}

/** Hard-coded fallback list of templates used before the skills API
 *  resolves — mirrors the backend invoke_skill catalog so the panel is
 *  useful in offline mode too. */
const FALLBACK_TEMPLATES: SkillDescriptor[] = [
  { name: 'spiral_staircase', description: 'A spiral staircase composition', category: 'architecture', parameters: {} },
  { name: 'colonnade', description: 'Classical colonnade row', category: 'architecture', parameters: {} },
  { name: 'forest', description: 'Stylized low-poly forest', category: 'nature', parameters: {} },
  { name: 'crystal_garden', description: 'Glowing crystal garden', category: 'procedural', parameters: {} },
  { name: 'dna_helix', description: 'Abstract DNA helix', category: 'abstract', parameters: {} },
  { name: 'spiral_galaxy', description: 'Spiral galaxy', category: 'cosmos', parameters: {} },
  { name: 'studio_lighting', description: 'Studio three-point rig', category: 'lighting', parameters: {} },
  { name: 'atom', description: 'Atomic orbits', category: 'abstract', parameters: {} },
  { name: 'gear_assembly', description: 'Mechanical gear cluster', category: 'abstract', parameters: {} },
  { name: 'molecule', description: 'Stylized molecule', category: 'abstract', parameters: {} },
  { name: 'snowman', description: 'Low-poly snowman', category: 'character', parameters: {} },
  { name: 'bridge', description: 'Stylized bridge', category: 'architecture', parameters: {} },
  { name: 'zen_garden', description: 'Zen rock garden', category: 'nature', parameters: {} },
]

/** Renders scene-aware suggestions and a compact template strip. */
export function SceneContextPanel({ onInsert, disabled }: SceneContextPanelProps) {
  const scene = useScene((s) => s.scene)

  // Fetch skills (scene templates) once on mount; fall back to a static
  // list if the network is unavailable so the panel still has content
  // when Trigen runs fully offline.
  const [skills, setSkills] = useState<SkillDescriptor[]>(FALLBACK_TEMPLATES)
  useEffect(() => {
    let cancelled = false
    fetchSkills()
      .then((list) => {
        if (!cancelled && list.length > 0) setSkills(list)
      })
      .catch(() => {
        /* keep fallback list */
      })
    return () => {
      cancelled = true
    }
  }, [])

  const ctx = useMemo(() => deriveContext(scene), [scene])
  const suggestions = useMemo(() => pickSuggestions(ctx), [ctx])

  // Truncate template list to what the panel can show without crowding the
  // prompt gallery below; templates are ordered by category to surface the
  // most visual / structural ones first.
  const templateStrip = skills.slice(0, 6)

  if (disabled) return null

  const SceneStateChip = () => {
    const chips: Array<{ label: string; value: string; cls: string }> = []
    chips.push({ label: 'objects', value: String(ctx.objectCount), cls: 'text-accent-cyan' })
    chips.push({ label: 'lights', value: String(ctx.lightCount), cls: 'text-accent-gold' })
    if (ctx.cameraCount > 0) chips.push({ label: 'cameras', value: String(ctx.cameraCount), cls: 'text-fuchsia-300' })
    if (ctx.layerCount > 0) chips.push({ label: 'layers', value: String(ctx.layerCount), cls: 'text-emerald-300' })
    return (
      <div className="flex items-center gap-1.5 text-[10px] text-fg-muted mb-1.5 flex-wrap">
        <Info size={10} className="text-fg-muted/60" />
        <span className="text-fg-muted">Scene:</span>
        {chips.map((c) => (
          <span key={c.label} className="flex items-center gap-0.5">
            <span className={`${c.cls} font-medium`}>{c.value}</span>
            <span>{c.label}</span>
            <span className="text-fg-muted/40">·</span>
          </span>
        ))}
      </div>
    )
  }

  return (
    <div className="mb-2">
      <div className="flex items-center justify-between mb-1">
        <button
          className="flex items-center gap-1.5 text-[10px] font-medium text-accent-cyan hover:text-accent-cyan/80 transition-colors"
          onClick={() => onInsert('')}
          title="Insert a scene-aware suggestion"
        >
          <Sparkles size={10} />
          <span>Scene suggestions / 场景建议</span>
        </button>
        <span className="text-[9px] text-fg-muted/60">
          {suggestions.length} next-best actions
        </span>
      </div>

      <div className="rounded-lg border border-border-subtle bg-bg-base/50 p-2">
        <SceneStateChip />

        {/* Scene-state driven suggestion chips */}
        <div className="flex items-center gap-1 flex-wrap mb-2">
          {suggestions.map((s) => {
            const Icon = s.icon
            return (
              <button
                key={s.id}
                onClick={() => onInsert(s.prompt)}
                title={s.prompt}
                className="flex items-center gap-1 px-2 py-1 rounded text-[10px] border border-border-subtle bg-bg-elevated/60 hover:border-accent-cyan/50 hover:bg-accent-cyan/5 transition-colors"
              >
                <Icon size={10} className={s.accent} />
                <span className="text-fg-primary">{s.label}</span>
              </button>
            )
          })}
        </div>

        {/* Template quick-start strip */}
        {templateStrip.length > 0 && (
          <div className="pt-1.5 border-t border-border-subtle">
            <div className="flex items-center justify-between mb-1">
              <span className="text-[9px] uppercase tracking-wider text-fg-muted">
                Quick templates · 模板
              </span>
              <span className="text-[9px] text-fg-muted/60">
                click to load into Agent
              </span>
            </div>
            <div className="flex items-center gap-1 flex-wrap">
              {templateStrip.map((t) => (
                <button
                  key={t.name}
                  onClick={() =>
                    onInsert(
                      `Load the ${t.name} template. ${t.description}.`,
                    )
                  }
                  title={t.description}
                  className="flex items-center gap-1 px-1.5 py-0.5 rounded text-[9.5px] border border-border-subtle bg-bg-panel/70 hover:border-accent-gold/40 hover:bg-accent-gold/5 text-fg-secondary hover:text-fg-primary transition-colors"
                >
                  <Plus size={9} className="text-accent-gold" />
                  {t.name.replace(/_/g, ' ')}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
