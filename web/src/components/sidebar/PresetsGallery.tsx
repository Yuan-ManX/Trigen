import { AnimatePresence, motion } from 'framer-motion'
import {
  Boxes,
  Building2,
  Castle,
  ChevronDown,
  ChevronRight,
  Clock,
  CloudRain,
  Columns,
  Dna,
  Flame,
  Flower2,
  Gem,
  Loader2,
  Mountain,
  Orbit,
  RefreshCw,
  Search,
  Snowflake,
  Sparkles,
  Spline,
  Sun,
  SunDim,
  Trees,
  Waves,
  X,
} from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { useChat } from '../../store/useChat'

interface SceneTemplateDescriptor {
  id: string
  name: string
  description: string
  category: string
  prompt: string
  icon?: string
  accent_color?: string
  thumbnail_url?: string
}

const CATEGORY_META: Record<
  string,
  { icon: typeof Boxes; color: string; label: string; chipBg: string }
> = {
  architecture: {
    icon: Boxes,
    color: 'text-amber-300',
    label: 'Architecture',
    chipBg: 'bg-amber-500/15 border-amber-400/30',
  },
  nature: {
    icon: Trees,
    color: 'text-emerald-400',
    label: 'Nature',
    chipBg: 'bg-emerald-500/15 border-emerald-400/30',
  },
  abstract: {
    icon: Spline,
    color: 'text-fuchsia-400',
    label: 'Abstract',
    chipBg: 'bg-fuchsia-500/15 border-fuchsia-400/30',
  },
  lighting: {
    icon: Sun,
    color: 'text-yellow-300',
    label: 'Lighting',
    chipBg: 'bg-yellow-500/15 border-yellow-400/30',
  },
  interiors: {
    icon: Building2,
    color: 'text-rose-300',
    label: 'Interiors',
    chipBg: 'bg-rose-500/15 border-rose-400/30',
  },
  patterns: {
    icon: Boxes,
    color: 'text-teal-300',
    label: 'Patterns',
    chipBg: 'bg-teal-500/15 border-teal-400/30',
  },
}

const DEFAULT_CATEGORY = {
  icon: Sparkles,
  color: 'text-accent-cyan',
  label: 'Creative',
  chipBg: 'bg-accent-cyan/15 border-accent-cyan/30',
}

const PRESET_ICONS: Record<string, typeof Boxes> = {
  colonnade: Columns,
  spiral_staircase: Building2,
  tower_castle: Castle,
  campfire_ring: Flame,
  swimming_pool: Waves,
  rainbow_arch: Spline,
  city_skyline: Building2,
  forest: Trees,
  ocean: Waves,
  beach: Sun,
  cave: Mountain,
  winter_scene: Snowflake,
  garden_of_crystals: Flower2,
  living_room: Building2,
  bedroom_scene: Building2,
  office_space: Building2,
  dna_helix: Dna,
  spiral_galaxy: Orbit,
  fractal_maze: Spline,
  solar_system: Gem,
  hex_grid_tiles: Boxes,
  fibonacci_spiral: Flower2,
  knotwork_patio: Boxes,
  sunset_studio: SunDim,
  rainy_moody: CloudRain,
  clean_white_studio: Sparkles,
}

function categoryMeta(category: string) {
  return CATEGORY_META[category] ?? DEFAULT_CATEGORY
}

function presetIcon(id: string, category: string) {
  if (PRESET_ICONS[id]) return PRESET_ICONS[id]
  return categoryMeta(category).icon
}

const FALLBACK_PRESETS: SceneTemplateDescriptor[] = [
  {
    id: 'colonnade',
    name: 'Colonnade',
    description: 'Row of marble columns on a classical plinth',
    category: 'architecture',
    prompt: 'Create a colonnade with 8 marble columns arranged in a straight row on a stone plinth',
    accent_color: 'text-amber-300',
  },
  {
    id: 'spiral_staircase',
    name: 'Spiral Staircase',
    description: 'Central pillar with stone steps spiraling upward',
    category: 'architecture',
    prompt: 'Create a spiral staircase with a central pillar and 16 stone steps spiraling upward',
    accent_color: 'text-amber-300',
  },
  {
    id: 'tower_castle',
    name: 'Tower Castle',
    description: 'Fortified tower with crenellations and corner turrets',
    category: 'architecture',
    prompt: 'Create a medieval tower castle with four corner turrets, crenellated battlements, and a stone keep',
    accent_color: 'text-amber-300',
  },
  {
    id: 'forest',
    name: 'Forest',
    description: 'Scattered trees with trunks and leafy crowns',
    category: 'nature',
    prompt: 'Create a forest scene with 12 scattered trees featuring thick trunks and leafy crowns on a grassy ground plane',
    accent_color: 'text-emerald-400',
  },
  {
    id: 'ocean',
    name: 'Ocean',
    description: 'Rolling water plane with horizon and atmospheric fog',
    category: 'nature',
    prompt: 'Create an ocean scene with a large wavy water plane, distant horizon line, and soft atmospheric fog',
    accent_color: 'text-emerald-400',
  },
  {
    id: 'beach',
    name: 'Beach',
    description: 'Sandy shoreline meeting calm water with warm sun',
    category: 'nature',
    prompt: 'Create a beach scene with a curved sandy shoreline meeting calm blue water and a warm low sun',
    accent_color: 'text-emerald-400',
  },
  {
    id: 'cave',
    name: 'Cave',
    description: 'Cavern interior with stalactites and glowing crystals',
    category: 'nature',
    prompt: 'Create a cave interior with stalactites hanging from the ceiling, stalagmites rising from the floor, and scattered glowing crystals',
    accent_color: 'text-emerald-400',
  },
  {
    id: 'garden_of_crystals',
    name: 'Garden of Crystals',
    description: 'Cluster of glowing polyhedra on a reflective floor',
    category: 'nature',
    prompt: 'Create a garden of crystals featuring 10 glowing polyhedra of various sizes scattered on a dark reflective floor',
    accent_color: 'text-emerald-400',
  },
  {
    id: 'dna_helix',
    name: 'DNA Helix',
    description: 'Double helix of spheres connected by molecular rungs',
    category: 'abstract',
    prompt: 'Create a DNA double helix with 24 base pairs featuring two spiraling backbones of spheres connected by colored rung cylinders',
    accent_color: 'text-fuchsia-400',
  },
  {
    id: 'spiral_galaxy',
    name: 'Spiral Galaxy',
    description: 'Central bulge with two spiral arms of glowing stars',
    category: 'abstract',
    prompt: 'Create a spiral galaxy with a bright central bulge and two sweeping spiral arms populated by 120 glowing star spheres against a dark sky',
    accent_color: 'text-fuchsia-400',
  },
  {
    id: 'fractal_maze',
    name: 'Fractal Maze',
    description: 'Recursive geometric passages branching infinitely',
    category: 'abstract',
    prompt: 'Create a fractal maze featuring recursive box-like passages branching at right angles with subtle depth-based color grading',
    accent_color: 'text-fuchsia-400',
  },
  {
    id: 'solar_system',
    name: 'Solar System',
    description: 'Glowing sun with 8 orbiting planets and rings',
    category: 'abstract',
    prompt: 'Create a solar system with a glowing central sun and 8 orbiting planets at varying distances and sizes, Saturn featuring a ring system',
    accent_color: 'text-fuchsia-400',
  },
  {
    id: 'sunset_studio',
    name: 'Sunset Studio',
    description: 'Warm golden-hour key light with long soft shadows',
    category: 'lighting',
    prompt: 'Create a sunset studio lighting setup with a warm golden directional key light positioned low, casting long soft shadows across the scene',
    accent_color: 'text-yellow-300',
  },
  {
    id: 'rainy_moody',
    name: 'Rainy Moody',
    description: 'Cool diffused light with fog and desaturated palette',
    category: 'lighting',
    prompt: 'Create a rainy moody scene with cool blue diffused ambient light, dense atmospheric fog, and a desaturated color palette',
    accent_color: 'text-yellow-300',
  },
  {
    id: 'clean_white_studio',
    name: 'Clean White Studio',
    description: 'Even soft three-point lighting on pure white cyc',
    category: 'lighting',
    prompt: 'Create a clean white studio with even soft three-point lighting, a seamless pure white cyclorama backdrop, and minimal shadows',
    accent_color: 'text-yellow-300',
  },
  {
    id: 'campfire_ring',
    name: 'Campfire Ring',
    description: 'Glowing fire with log benches encircling a stone ring',
    category: 'nature',
    prompt: 'Create a campfire ring with a glowing central fire, surrounded by a circle of log seating benches and a low stone ring',
    accent_color: 'text-emerald-400',
  },
  {
    id: 'swimming_pool',
    name: 'Swimming Pool',
    description: 'Blue water basin with tiled deck and lounge chairs',
    category: 'nature',
    prompt: 'Create a rectangular swimming pool filled with clear blue water, a tiled white deck, and two reclining lounge chairs at the side',
    accent_color: 'text-emerald-400',
  },
  {
    id: 'winter_scene',
    name: 'Winter Scene',
    description: 'Snowy ground with pine trees and a gentle snowfall',
    category: 'nature',
    prompt: 'Create a winter scene with a white snow-covered ground plane, scattered pine trees with snow, and a snowfall particle effect',
    accent_color: 'text-emerald-400',
  },
  {
    id: 'rainbow_arch',
    name: 'Rainbow Arch',
    description: 'Colorful seven-band rainbow curving over the horizon',
    category: 'nature',
    prompt: 'Create a rainbow arch with seven horizontal colored bands spanning the horizon over a soft green ground',
    accent_color: 'text-emerald-400',
  },
  {
    id: 'city_skyline',
    name: 'City Skyline',
    description: 'Dense row of mixed-height skyscrapers with lit windows',
    category: 'architecture',
    prompt: 'Create a city skyline with 20 skyscrapers of varying heights, dark facades dotted with warm window lights, and a deep twilight sky',
    accent_color: 'text-amber-300',
  },
  {
    id: 'living_room',
    name: 'Living Room',
    description: 'Sofa, coffee table and floor lamp in a cozy interior',
    category: 'interiors',
    prompt: 'Create a living room with a three-seat fabric sofa, a wooden coffee table, a tall floor lamp, and a textured neutral carpet',
    accent_color: 'text-rose-300',
  },
  {
    id: 'bedroom_scene',
    name: 'Bedroom',
    description: 'Queen bed with nightstands, lamps, and a dresser',
    category: 'interiors',
    prompt: 'Create a bedroom with a queen-size bed with upholstered headboard, two matching nightstands with lamps, and a tall dresser',
    accent_color: 'text-rose-300',
  },
  {
    id: 'office_space',
    name: 'Home Office',
    description: 'Desk with ergonomic chair, monitor and bookshelves',
    category: 'interiors',
    prompt: 'Create a home office with a rectangular desk, ergonomic office chair, a raised monitor, and floor-to-ceiling bookshelves',
    accent_color: 'text-rose-300',
  },
  {
    id: 'hex_grid_tiles',
    name: 'Hex Grid Tiles',
    description: 'A staggered field of alternating-color hex tiles',
    category: 'patterns',
    prompt: 'Create a hex grid pattern with 60 alternating-color hex tiles arranged as a honeycomb ground plane',
    accent_color: 'text-teal-300',
  },
  {
    id: 'fibonacci_spiral',
    name: 'Fibonacci Spiral',
    description: 'Prisms placed along a golden-angle sunflower spiral',
    category: 'patterns',
    prompt: 'Create a fibonacci lattice pattern with 120 small colored prisms arranged in a sunflower golden-angle spiral',
    accent_color: 'text-teal-300',
  },
  {
    id: 'knotwork_patio',
    name: 'Knotwork Patio',
    description: 'Celtic-style interwoven truss pattern on a floor',
    category: 'patterns',
    prompt: 'Create a knotwork lattice pattern with interwoven curved rails forming a decorative patio floor',
    accent_color: 'text-teal-300',
  },
]

async function fetchSceneTemplates(): Promise<SceneTemplateDescriptor[]> {
  const res = await fetch('/api/scene-templates')
  if (!res.ok) throw new Error(`Failed to fetch scene templates: ${res.status}`)
  const data = await res.json()
  if (Array.isArray(data)) return data
  if (data && Array.isArray(data.templates)) return data.templates
  if (data && Array.isArray(data.presets)) return data.presets
  throw new Error('Unexpected scene-templates response format')
}

/* ============ Recently-used presets (localStorage) ============ */

const RECENT_KEY = 'trigen_recent_presets'
const MAX_RECENT = 3

/** Read the list of recently-applied preset ids (most-recent-first). */
function loadRecentIds(): string[] {
  try {
    const raw = localStorage.getItem(RECENT_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed.filter((x) => typeof x === 'string') : []
  } catch {
    return []
  }
}

/** Persist a new recent-id list, deduped and capped at MAX_RECENT. */
function saveRecentIds(ids: string[]): void {
  try {
    localStorage.setItem(RECENT_KEY, JSON.stringify(ids.slice(0, MAX_RECENT)))
  } catch {
    // Ignore quota errors
  }
}

/** Record a preset id as just-used: dedupe, move to front, cap at MAX_RECENT. */
function recordRecent(id: string): string[] {
  const next = [id, ...loadRecentIds().filter((x) => x !== id)].slice(0, MAX_RECENT)
  saveRecentIds(next)
  return next
}

function ShimmerKeyframes() {
  return (
    <style>{`
      @keyframes presets-shimmer {
        0% { background-position: -400px 0; }
        100% { background-position: 400px 0; }
      }
      .presets-shimmer {
        background: linear-gradient(
          90deg,
          rgba(255,255,255,0.02) 0%,
          rgba(255,255,255,0.07) 50%,
          rgba(255,255,255,0.02) 100%
        );
        background-size: 800px 100%;
        animation: presets-shimmer 1.4s ease-in-out infinite;
      }
    `}</style>
  )
}

function SkeletonCard() {
  return (
    <div className="rounded-lg border border-border bg-bg-elevated/30 p-3 h-[138px] flex flex-col gap-2 overflow-hidden">
      <div className="flex items-start gap-2">
        <div className="w-8 h-8 rounded-md bg-fg-muted/10 presets-shimmer" />
        <div className="flex-1 pt-1 space-y-1.5">
          <div className="h-3 w-2/3 rounded presets-shimmer" />
          <div className="h-2 w-1/2 rounded presets-shimmer" />
        </div>
      </div>
      <div className="mt-auto space-y-1.5">
        <div className="h-2 w-full rounded presets-shimmer" />
        <div className="h-2 w-5/6 rounded presets-shimmer" />
        <div className="h-6 w-16 rounded-full mt-2 presets-shimmer" />
      </div>
    </div>
  )
}

interface PresetCardProps {
  preset: SceneTemplateDescriptor
  index?: number
  /** Called before sending — used by the gallery to record recently-used presets. */
  onApply?: (preset: SceneTemplateDescriptor) => void
}

function PresetCard({ preset, index = 0, onApply }: PresetCardProps) {
  const meta = categoryMeta(preset.category)
  const Icon = presetIcon(preset.id, preset.category)
  const send = useChat((s) => s.send)
  const accent = preset.accent_color ?? meta.color

  const handleApply = () => {
    onApply?.(preset)
    send(preset.prompt)
  }

  return (
    <motion.button
      onClick={handleApply}
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2, delay: index * 0.03 }}
      whileHover={{ scale: 1.02 }}
      whileTap={{ scale: 0.985 }}
      className="group relative w-full text-left rounded-lg border border-border bg-bg-elevated/30 p-3 flex flex-col gap-2 h-[138px] overflow-hidden hover:bg-bg-hover hover:shadow-lg hover:shadow-black/20 transition-shadow"
    >
      <AnimatePresence>
        <motion.div
          initial={false}
          animate={{ opacity: 0 }}
          whileHover={{ opacity: 1 }}
          transition={{ duration: 0.15 }}
          className={`pointer-events-none absolute inset-0 rounded-lg ${meta.chipBg} border-opacity-0 group-hover:border-opacity-100`}
          style={{ borderWidth: 1 }}
          aria-hidden
        />
      </AnimatePresence>

      <div className="relative z-10 flex items-start gap-2">
        <div
          className={`shrink-0 w-8 h-8 rounded-md border flex items-center justify-center ${meta.chipBg}`}
        >
          <Icon size={14} className={accent} />
        </div>
        <div className="flex-1 min-w-0 pt-0.5">
          <h3 className="text-[13px] font-bold text-fg-primary leading-tight truncate">
            {preset.name}
          </h3>
        </div>
      </div>

      <p className="relative z-10 text-[11px] text-fg-muted leading-relaxed line-clamp-2">
        {preset.description}
      </p>

      <div className="relative z-10 mt-auto flex items-center justify-between">
        <span className="text-[9px] uppercase tracking-wider font-semibold text-fg-muted/60">
          {meta.label}
        </span>
        <span
          onClick={(e) => {
            e.stopPropagation()
            handleApply()
          }}
          className="inline-flex items-center gap-1 text-[11px] font-semibold text-white rounded-full bg-accent-cyan px-3 py-1 hover:bg-accent-cyan/90 active:scale-95 transition-all cursor-pointer shadow-sm shadow-accent-cyan/20"
        >
          Apply
        </span>
      </div>
    </motion.button>
  )
}

function CategorySection({
  category,
  presets,
  collapsed,
  onToggle,
  onApply,
}: {
  category: string
  presets: SceneTemplateDescriptor[]
  collapsed: boolean
  onToggle: () => void
  onApply?: (preset: SceneTemplateDescriptor) => void
}) {
  const meta = categoryMeta(category)
  const GroupIcon = meta.icon

  return (
    <div className="space-y-2">
      <button
        onClick={onToggle}
        className="flex items-center gap-1.5 px-1 w-full text-left hover:opacity-80 transition-opacity"
      >
        {collapsed ? (
          <ChevronRight size={11} className="text-fg-muted/60" />
        ) : (
          <ChevronDown size={11} className="text-fg-muted/60" />
        )}
        <GroupIcon size={11} className={meta.color} />
        <span className="text-[9.5px] uppercase tracking-wider font-semibold text-fg-muted">
          {meta.label}
        </span>
        <span className="text-[9px] text-fg-muted/60 font-mono ml-auto">
          {presets.length}
        </span>
      </button>
      <AnimatePresence initial={false}>
        {!collapsed && (
          <motion.div
            key="content"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div className="grid grid-cols-2 gap-2">
              {presets.map((p, i) => (
                <PresetCard key={p.id} preset={p} index={i} onApply={onApply} />
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

export default function PresetsGallery() {
  const [presets, setPresets] = useState<SceneTemplateDescriptor[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [collapsedCategories, setCollapsedCategories] = useState<Record<string, boolean>>({})
  // Search query filters presets by name/description across all categories.
  const [searchQuery, setSearchQuery] = useState('')
  // Recently-applied preset ids (most-recent-first), persisted in localStorage.
  const [recentIds, setRecentIds] = useState<string[]>(() => loadRecentIds())

  const loadPresets = () => {
    let cancelled = false
    setLoading(true)
    setError(null)
    fetchSceneTemplates()
      .then((list) => {
        if (cancelled) return
        setPresets(list)
      })
      .catch(() => {
        if (cancelled) return
        setPresets(FALLBACK_PRESETS)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }

  useEffect(loadPresets, [])

  const toggleCategory = (category: string) => {
    setCollapsedCategories((prev) => ({ ...prev, [category]: !prev[category] }))
  }

  // Record a preset as recently used and update local state so the Recent
  // section re-renders immediately. The PresetCard still sends the prompt.
  const handleApply = (preset: SceneTemplateDescriptor) => {
    setRecentIds(recordRecent(preset.id))
  }

  // Presets filtered by the search query (matches name or description).
  const filteredPresets = useMemo(() => {
    const q = searchQuery.trim().toLowerCase()
    if (!q) return presets
    return presets.filter(
      (p) =>
        p.name.toLowerCase().includes(q) ||
        p.description.toLowerCase().includes(q) ||
        p.category.toLowerCase().includes(q),
    )
  }, [presets, searchQuery])

  const isSearching = searchQuery.trim().length > 0

  // Resolve the full descriptors for the recently-used preset ids. Presets
  // that no longer exist in the catalog are silently dropped.
  const recentPresets = useMemo(() => {
    if (isSearching) return []
    return recentIds
      .map((id) => presets.find((p) => p.id === id))
      .filter((p): p is SceneTemplateDescriptor => Boolean(p))
  }, [recentIds, presets, isSearching])

  const grouped = useMemo(() => {
    const groups: Array<{ category: string; presets: SceneTemplateDescriptor[] }> = []
    const index: Record<string, number> = {}
    for (const p of filteredPresets) {
      if (!(p.category in index)) {
        index[p.category] = groups.length
        groups.push({ category: p.category, presets: [] })
      }
      groups[index[p.category]].presets.push(p)
    }
    return groups
  }, [filteredPresets])

  if (loading) {
    return (
      <div className="flex flex-col h-full">
        <ShimmerKeyframes />
        <div className="px-3 py-2.5 border-b border-border-subtle">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1.5">
              <Sparkles size={12} className="text-accent-cyan" />
              <span className="text-[11px] font-semibold text-fg-primary">
                Scene Presets
              </span>
            </div>
            <span className="text-[9px] text-fg-muted font-mono">
              <Loader2 size={10} className="animate-spin inline" />
            </span>
          </div>
          <p className="text-[9.5px] text-fg-muted mt-1 leading-relaxed">
            Loading preset gallery…
          </p>
        </div>
        <div className="flex-1 overflow-y-auto p-2 space-y-4">
          {['architecture', 'nature'].map((cat) => {
            const meta = categoryMeta(cat)
            const CatIcon = meta.icon
            return (
              <div key={cat} className="space-y-2">
                <div className="flex items-center gap-1.5 px-1">
                  <ChevronDown size={11} className="text-fg-muted/60" />
                  <CatIcon size={11} className={meta.color} />
                  <span className="text-[9.5px] uppercase tracking-wider font-semibold text-fg-muted">
                    {meta.label}
                  </span>
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <SkeletonCard />
                  <SkeletonCard />
                  <SkeletonCard />
                  <SkeletonCard />
                </div>
              </div>
            )
          })}
        </div>
      </div>
    )
  }

  if (error && presets.length === 0) {
    return (
      <div className="flex flex-col h-full">
        <div className="px-3 py-2.5 border-b border-border-subtle">
          <div className="flex items-center gap-1.5">
            <Sparkles size={12} className="text-accent-cyan" />
            <span className="text-[11px] font-semibold text-fg-primary">
              Scene Presets
            </span>
          </div>
        </div>
        <div className="flex flex-col items-center justify-center flex-1 text-fg-muted text-[11px] gap-3 p-4 text-center">
          <X size={18} className="text-rose-400" />
          <div className="space-y-1">
            <p className="font-medium text-fg-primary">Failed to load presets</p>
            <p className="text-[10px] text-fg-muted/80">{error}</p>
          </div>
          <button
            onClick={loadPresets}
            className="inline-flex items-center gap-1.5 text-[10px] font-semibold text-white rounded-full bg-accent-cyan px-3 py-1.5 hover:bg-accent-cyan/90 active:scale-95 transition-all"
          >
            <RefreshCw size={11} />
            Retry
          </button>
        </div>
      </div>
    )
  }

  if (presets.length === 0) {
    return (
      <div className="flex flex-col h-full">
        <div className="px-3 py-2.5 border-b border-border-subtle">
          <div className="flex items-center gap-1.5">
            <Sparkles size={12} className="text-accent-cyan" />
            <span className="text-[11px] font-semibold text-fg-primary">
              Scene Presets
            </span>
          </div>
        </div>
        <div className="flex flex-col items-center justify-center flex-1 text-fg-muted text-[11px] gap-2 p-4 text-center">
          <Sparkles size={18} />
          <p>No presets available yet.</p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full">
      <div className="px-3 py-2.5 border-b border-border-subtle">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1.5">
            <Sparkles size={12} className="text-accent-cyan" />
            <span className="text-[11px] font-semibold text-fg-primary">
              Scene Presets
            </span>
          </div>
          <span className="text-[9px] text-fg-muted font-mono">
            {isSearching ? `${filteredPresets.length} / ${presets.length}` : `${presets.length} presets`}
          </span>
        </div>
        <p className="text-[9.5px] text-fg-muted mt-1 leading-relaxed">
          Click Apply on any preset to generate the scene through the Agent.
        </p>
        {/* Search input — filters presets by name, description, or category. */}
        <div className="relative mt-2">
          <Search size={11} className="absolute left-2 top-1/2 -translate-y-1/2 text-fg-muted" />
          <input
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search presets..."
            className="w-full pl-6 pr-6 py-1.5 text-[11px] bg-bg-base border border-border-subtle rounded text-fg-primary placeholder:text-fg-muted outline-none focus:border-accent-cyan/50 transition-colors"
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery('')}
              aria-label="Clear search"
              className="absolute right-1.5 top-1/2 -translate-y-1/2 text-fg-muted hover:text-fg-primary transition-colors"
            >
              <X size={11} />
            </button>
          )}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-2 space-y-3">
        {/* Recent section — last 3 used presets, hidden while searching. */}
        {!isSearching && recentPresets.length > 0 && (
          <div className="space-y-2">
            <div className="flex items-center gap-1.5 px-1">
              <Clock size={11} className="text-accent-gold/80" />
              <span className="text-[9.5px] uppercase tracking-wider font-semibold text-fg-muted">
                Recent
              </span>
              <span className="text-[9px] text-fg-muted/60 font-mono ml-auto">
                {recentPresets.length}
              </span>
            </div>
            <div className="grid grid-cols-2 gap-2">
              {recentPresets.map((p, i) => (
                <PresetCard key={p.id} preset={p} index={i} onApply={handleApply} />
              ))}
            </div>
          </div>
        )}

        {grouped.length === 0 && isSearching ? (
          <div className="flex flex-col items-center justify-center py-10 text-fg-muted text-[11px] gap-2 text-center">
            <Search size={18} className="text-fg-muted/50" />
            <p>No presets match &ldquo;{searchQuery}&rdquo;</p>
            <button
              onClick={() => setSearchQuery('')}
              className="text-[10px] font-semibold text-accent-cyan hover:text-accent-cyan/80 transition-colors"
            >
              Clear search
            </button>
          </div>
        ) : (
          grouped.map((group) => (
            <CategorySection
              key={group.category}
              category={group.category}
              presets={group.presets}
              collapsed={collapsedCategories[group.category] ?? false}
              onToggle={() => toggleCategory(group.category)}
              onApply={handleApply}
            />
          ))
        )}
      </div>

      <div className="px-3 py-2 border-t border-border-subtle text-[9px] text-fg-muted/70 flex items-center gap-1.5">
        <Sparkles size={9} className="text-fg-muted/50" />
        Each preset sends a crafted prompt — you can refine it after generation.
      </div>
    </div>
  )
}
