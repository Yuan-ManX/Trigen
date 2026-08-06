// Smart Layout dialog: auto-arranges scene objects into a tidy formation.
// Three modes are offered — grid, ring, and organic scatter — and the
// arrangement can target either every object or just the current
// selection. The whole operation is committed as a single history entry
// so a single undo reverts it.
import { AnimatePresence, motion } from 'framer-motion'
import {
  Grid3x3,
  CircleDot,
  Shuffle,
  Sparkles,
  X,
} from 'lucide-react'
import { useMemo, useState } from 'react'
import { useScene } from '../../store/useScene'
import type { SceneData, SceneObject, Vec3 } from '../../types'

type LayoutMode = 'grid' | 'ring' | 'scatter'

interface ModeMeta {
  id: LayoutMode
  label: string
  description: string
  icon: typeof Grid3x3
  /** Primary parameter label, e.g. "Spacing" or "Radius". */
  paramLabel: string
  paramMin: number
  paramMax: number
  paramStep: number
  paramDefault: number
}

const MODES: ModeMeta[] = [
  {
    id: 'grid',
    label: 'Grid',
    description: 'Snap objects onto an evenly-spaced square grid.',
    icon: Grid3x3,
    paramLabel: 'Spacing',
    paramMin: 1,
    paramMax: 10,
    paramStep: 0.5,
    paramDefault: 3,
  },
  {
    id: 'ring',
    label: 'Ring',
    description: 'Distribute objects evenly around a circle in the XZ plane.',
    icon: CircleDot,
    paramLabel: 'Radius',
    paramMin: 2,
    paramMax: 20,
    paramStep: 0.5,
    paramDefault: 6,
  },
  {
    id: 'scatter',
    label: 'Scatter',
    description: 'Jitter objects into an organic, natural-looking spread.',
    icon: Shuffle,
    paramLabel: 'Spread',
    paramMin: 4,
    paramMax: 30,
    paramStep: 1,
    paramDefault: 12,
  },
]

/** Mulberry32 seeded PRNG — deterministic so the same scatter parameters
 *  produce the same layout every time (no surprises on re-apply). */
function makeRng(seed: number): () => number {
  let a = seed >>> 0
  return () => {
    a = (a + 0x6d2b79f5) >>> 0
    let t = a
    t = Math.imul(t ^ (t >>> 15), t | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

/** Compute target positions for every object under the chosen layout.
 *  Returns a map of id → position. Objects keep their Y unless "ground"
 *  is true, in which case Y is flattened to 0. */
function computeLayout(
  objects: SceneObject[],
  mode: LayoutMode,
  param: number,
  ground: boolean,
): Map<string, Vec3> {
  const out = new Map<string, Vec3>()
  if (objects.length === 0) return out
  const n = objects.length

  if (mode === 'grid') {
    // Squarest grid that fits n items: cols = ceil(sqrt(n)).
    const cols = Math.max(1, Math.ceil(Math.sqrt(n)))
    const rows = Math.ceil(n / cols)
    const spacing = param
    // Center the grid on the origin so the arrangement feels balanced.
    const offsetX = -((cols - 1) * spacing) / 2
    const offsetZ = -((rows - 1) * spacing) / 2
    objects.forEach((obj, i) => {
      const col = i % cols
      const row = Math.floor(i / cols)
      out.set(obj.id, [
        offsetX + col * spacing,
        ground ? 0 : obj.transform.position[1],
        offsetZ + row * spacing,
      ])
    })
    return out
  }

  if (mode === 'ring') {
    // Even angular distribution; first object starts at angle 0 (east).
    const radius = param
    objects.forEach((obj, i) => {
      const angle = (i / n) * Math.PI * 2
      out.set(obj.id, [
        Math.cos(angle) * radius,
        ground ? 0 : obj.transform.position[1],
        Math.sin(angle) * radius,
      ])
    })
    return out
  }

  // scatter — seeded jitter inside a square of side `spread` centered on
  // origin. Seed is fixed so re-applying is idempotent.
  const rng = makeRng(0x57a13e)
  const spread = param
  const half = spread / 2
  objects.forEach((obj) => {
    out.set(obj.id, [
      (rng() * 2 - 1) * half,
      ground ? 0 : obj.transform.position[1],
      (rng() * 2 - 1) * half,
    ])
  })
  return out
}

interface SmartLayoutProps {
  open: boolean
  onClose: () => void
}

export function SmartLayout({ open, onClose }: SmartLayoutProps) {
  const scene = useScene((s) => s.scene)
  const selectedIds = useScene((s) => s.selectedIds)
  const commitScene = useScene((s) => s.commitScene)
  const [mode, setMode] = useState<LayoutMode>('grid')
  const [scope, setScope] = useState<'all' | 'selected'>('all')
  const [ground, setGround] = useState(false)
  const modeMeta = useMemo(() => MODES.find((m) => m.id === mode)!, [mode])
  const [param, setParam] = useState(modeMeta.paramDefault)

  // Reset the slider when switching modes so it always lands on a sane
  // default for the new mode's parameter range.
  const switchMode = (next: LayoutMode) => {
    setMode(next)
    const meta = MODES.find((m) => m.id === next)!
    setParam(meta.paramDefault)
  }

  /** Objects the layout will act on. Falls back to "all" if "selected"
   *  is chosen but nothing is selected. */
  const targets = useMemo<SceneObject[]>(() => {
    if (scope === 'selected' && selectedIds.length > 0) {
      const idSet = new Set(selectedIds)
      return scene.objects.filter((o) => idSet.has(o.id))
    }
    return scene.objects
  }, [scene.objects, scope, selectedIds])

  // Live preview positions used by the inline mini-map (not the scene).
  const preview = useMemo(
    () => computeLayout(targets, mode, param, ground),
    [targets, mode, param, ground],
  )

  /** Apply the layout: build a new scene with updated positions and commit
   *  it as a single history entry. */
  const handleApply = () => {
    if (targets.length === 0) return
    const next: SceneData = {
      ...scene,
      objects: scene.objects.map((o) => {
        const p = preview.get(o.id)
        return p ? { ...o, transform: { ...o.transform, position: p } } : o
      }),
    }
    commitScene(next, scene)
    onClose()
  }

  // Bounding box of the preview, used to scale the mini-map. Falls back to
  // a small default range when there's nothing to show.
  const bounds = useMemo(() => {
    let minX = Infinity, maxX = -Infinity, minZ = Infinity, maxZ = -Infinity
    preview.forEach((p) => {
      minX = Math.min(minX, p[0])
      maxX = Math.max(maxX, p[0])
      minZ = Math.min(minZ, p[2])
      maxZ = Math.max(maxZ, p[2])
    })
    if (!isFinite(minX)) {
      minX = -1; maxX = 1; minZ = -1; maxZ = 1
    }
    return { minX, maxX, minZ, maxZ }
  }, [preview])

  // Mini-map transform: map [minX..maxX] → [0..1] in the 200x140 SVG.
  const W = 200, H = 140
  const pad = 12
  const rangeX = Math.max(0.001, bounds.maxX - bounds.minX)
  const rangeZ = Math.max(0.001, bounds.maxZ - bounds.minZ)
  const toX = (x: number) => pad + ((x - bounds.minX) / rangeX) * (W - pad * 2)
  const toY = (z: number) => pad + ((z - bounds.minZ) / rangeZ) * (H - pad * 2)

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.15 }}
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
          onClick={onClose}
        >
          <motion.div
            initial={{ scale: 0.95, opacity: 0, y: 10 }}
            animate={{ scale: 1, opacity: 1, y: 0 }}
            exit={{ scale: 0.95, opacity: 0, y: 10 }}
            transition={{ duration: 0.2 }}
            onClick={(e) => e.stopPropagation()}
            className="relative w-[560px] max-w-[90vw] max-h-[80vh] overflow-hidden rounded-xl border border-border bg-bg-panel shadow-2xl"
          >
            {/* Header */}
            <div className="flex items-center justify-between px-4 py-3 border-b border-border-subtle">
              <div className="flex items-center gap-2">
                <Sparkles size={14} className="text-accent-gold" />
                <div>
                  <div className="text-[12px] font-semibold text-fg-primary">Smart Layout</div>
                  <div className="text-[10px] text-fg-muted">
                    Auto-arrange {targets.length} object{targets.length === 1 ? '' : 's'} into a tidy formation.
                  </div>
                </div>
              </div>
              <button
                onClick={onClose}
                aria-label="Close"
                className="w-7 h-7 rounded flex items-center justify-center text-fg-muted hover:text-fg-primary hover:bg-bg-hover"
              >
                <X size={14} />
              </button>
            </div>

            <div className="grid grid-cols-2 gap-4 p-4">
              {/* Left: mode + options */}
              <div className="space-y-3">
                <div>
                  <div className="text-[10px] uppercase tracking-wider text-fg-muted mb-1.5">Mode</div>
                  <div className="grid grid-cols-3 gap-1.5">
                    {MODES.map((m) => {
                      const Icon = m.icon
                      const active = m.id === mode
                      return (
                        <button
                          key={m.id}
                          onClick={() => switchMode(m.id)}
                          className={`flex flex-col items-center gap-1 px-1 py-2 rounded-md border text-[10px] transition-colors ${
                            active
                              ? 'border-accent-cyan/50 bg-accent-cyan/10 text-accent-cyan'
                              : 'border-border text-fg-secondary hover:bg-bg-hover hover:text-fg-primary'
                          }`}
                        >
                          <Icon size={14} />
                          <span>{m.label}</span>
                        </button>
                      )
                    })}
                  </div>
                  <p className="text-[9.5px] text-fg-muted mt-1.5 leading-snug">
                    {modeMeta.description}
                  </p>
                </div>

                <div>
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-[10px] uppercase tracking-wider text-fg-muted">
                      {modeMeta.paramLabel}
                    </span>
                    <span className="text-[10px] font-mono text-fg-secondary">
                      {param.toFixed(1)}
                    </span>
                  </div>
                  <input
                    type="range"
                    min={modeMeta.paramMin}
                    max={modeMeta.paramMax}
                    step={modeMeta.paramStep}
                    value={param}
                    onChange={(e) => setParam(parseFloat(e.target.value))}
                    className="w-full h-1 accent-accent-cyan cursor-pointer"
                  />
                </div>

                <div>
                  <div className="text-[10px] uppercase tracking-wider text-fg-muted mb-1.5">Scope</div>
                  <div className="grid grid-cols-2 gap-1.5">
                    {([
                      { id: 'all' as const, label: 'All objects', disabled: false },
                      { id: 'selected' as const, label: 'Selected only', disabled: selectedIds.length === 0 },
                    ]).map((opt) => (
                      <button
                        key={opt.id}
                        onClick={() => !opt.disabled && setScope(opt.id)}
                        disabled={opt.disabled}
                        className={`px-2 py-1.5 rounded-md border text-[10px] transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${
                          scope === opt.id
                            ? 'border-accent-cyan/50 bg-accent-cyan/10 text-accent-cyan'
                            : 'border-border text-fg-secondary hover:bg-bg-hover hover:text-fg-primary'
                        }`}
                      >
                        {opt.label}
                      </button>
                    ))}
                  </div>
                </div>

                <label className="flex items-center gap-2 text-[10.5px] text-fg-secondary cursor-pointer select-none">
                  <input
                    type="checkbox"
                    checked={ground}
                    onChange={(e) => setGround(e.target.checked)}
                    className="accent-accent-cyan"
                  />
                  <span>Flatten Y to ground (top-down arrangement)</span>
                </label>
              </div>

              {/* Right: live mini-map preview */}
              <div className="flex flex-col gap-2">
                <div className="text-[10px] uppercase tracking-wider text-fg-muted">Preview</div>
                <div className="flex-1 rounded-md border border-border-subtle bg-bg-base overflow-hidden">
                  <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-full">
                    {/* Origin crosshair */}
                    <line
                      x1={toX(0)} y1={pad - 2}
                      x2={toX(0)} y2={H - pad + 2}
                      stroke="rgba(148,163,184,0.15)" strokeWidth="0.5"
                    />
                    <line
                      x1={pad - 2} y1={toY(0)}
                      x2={W - pad + 2} y2={toY(0)}
                      stroke="rgba(148,163,184,0.15)" strokeWidth="0.5"
                    />
                    {Array.from(preview.entries()).map(([id, p]) => (
                      <circle
                        key={id}
                        cx={toX(p[0])}
                        cy={toY(p[2])}
                        r={2.5}
                        fill="rgb(34,211,238)"
                      />
                    ))}
                  </svg>
                </div>
                <div className="text-[9.5px] text-fg-muted leading-snug">
                  Top-down view. Each dot is an object's target position.
                </div>
              </div>
            </div>

            {/* Footer */}
            <div className="flex items-center justify-between px-4 py-3 border-t border-border-subtle bg-bg-elevated/40">
              <span className="text-[10px] text-fg-muted">
                Single undo step · {targets.length} object{targets.length === 1 ? '' : 's'} will move
              </span>
              <div className="flex items-center gap-2">
                <button
                  onClick={onClose}
                  className="px-3 h-8 rounded-md text-[11px] text-fg-secondary hover:text-fg-primary hover:bg-bg-hover transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={handleApply}
                  disabled={targets.length === 0}
                  className="flex items-center gap-1.5 px-3 h-8 rounded-md bg-accent-cyan text-bg-base disabled:bg-bg-hover disabled:text-fg-muted disabled:cursor-not-allowed hover:shadow-glow transition-all text-[11px] font-medium"
                >
                  <Sparkles size={12} />
                  <span>Apply Layout</span>
                </button>
              </div>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
