// Tool call card: inline display of tool name, parameters and execution result
import { motion } from 'framer-motion'
import {
  Activity,
  AlignHorizontalDistributeCenter,
  Box,
  Camera,
  CheckCircle2,
  CircleDot,
  CopyPlus,
  Download,
  Eraser,
  Eye,
  Film,
  Flame,
  Flower2,
  Folders,
  GitBranch,
  Globe,
  Grid3x3,
  HeartPulse,
  Hexagon,
  Image as ImageIcon,
  Info,
  Layers,
  Lightbulb,
  Link2,
  List,
  Loader2,
  type LucideIcon,
  Move,
  Orbit,
  Palette,
  Play,
  RotateCcw,
  RotateCw,
  Ruler,
  Save,
  Sparkles,
  Sun,
  Sparkle,
  Terminal,
  Timer,
  Trash2,
  Type,
  Users,
  Video,
  Wand2,
  Waves,
  XCircle,
  Zap,
} from 'lucide-react'
import { useChat, type ToolCallRecord } from '../../store/useChat'
import { MultimodalResult, hasMultimediaResult } from './MultimodalResult'

interface ToolCallCardProps {
  call: ToolCallRecord
}

/** Category taxonomy mirrors the orchestrator's _TOOL_CATEGORIES map. Each
 *  entry gets a colored chip (bg + text + border) so the user can scan the
 *  conversation at a glance. */
interface ToolCategoryMeta {
  label: string
  icon: LucideIcon
  chipClass: string
  textClass: string
}
const CATEGORY_META: Record<string, ToolCategoryMeta> = {
  geometry: {
    label: 'Geometry',
    icon: Box,
    chipClass: 'bg-indigo-500/12 border-indigo-400/25',
    textClass: 'text-indigo-300',
  },
  material: {
    label: 'Material',
    icon: Palette,
    chipClass: 'bg-pink-500/12 border-pink-400/25',
    textClass: 'text-pink-300',
  },
  lighting: {
    label: 'Lighting',
    icon: Lightbulb,
    chipClass: 'bg-yellow-500/12 border-yellow-400/25',
    textClass: 'text-yellow-300',
  },
  camera: {
    label: 'Camera',
    icon: Camera,
    chipClass: 'bg-sky-500/12 border-sky-400/25',
    textClass: 'text-sky-300',
  },
  transform: {
    label: 'Transform',
    icon: Move,
    chipClass: 'bg-blue-500/12 border-blue-400/25',
    textClass: 'text-blue-300',
  },
  animation: {
    label: 'Animation',
    icon: Film,
    chipClass: 'bg-cyan-500/12 border-cyan-400/25',
    textClass: 'text-cyan-300',
  },
  physics: {
    label: 'Physics',
    icon: Zap,
    chipClass: 'bg-amber-500/12 border-amber-400/25',
    textClass: 'text-amber-300',
  },
  particles: {
    label: 'Particles',
    icon: Flame,
    chipClass: 'bg-orange-500/12 border-orange-400/25',
    textClass: 'text-orange-300',
  },
  procedural: {
    label: 'Procedural',
    icon: Flower2,
    chipClass: 'bg-violet-500/12 border-violet-400/25',
    textClass: 'text-violet-300',
  },
  deformation: {
    label: 'Deform',
    icon: Sparkle,
    chipClass: 'bg-fuchsia-500/12 border-fuchsia-400/25',
    textClass: 'text-fuchsia-300',
  },
  postfx: {
    label: 'PostFX',
    icon: Sparkles,
    chipClass: 'bg-emerald-500/12 border-emerald-400/25',
    textClass: 'text-emerald-300',
  },
  patterns: {
    label: 'Pattern',
    icon: Hexagon,
    chipClass: 'bg-teal-500/12 border-teal-400/25',
    textClass: 'text-teal-300',
  },
  snapshots: {
    label: 'Version',
    icon: Save,
    chipClass: 'bg-lime-500/12 border-lime-400/25',
    textClass: 'text-lime-300',
  },
  layout: {
    label: 'Layout',
    icon: AlignHorizontalDistributeCenter,
    chipClass: 'bg-indigo-500/12 border-indigo-400/25',
    textClass: 'text-indigo-300',
  },
  utility: {
    label: 'Utility',
    icon: List,
    chipClass: 'bg-slate-500/12 border-slate-400/25',
    textClass: 'text-slate-300',
  },
  generative: {
    label: 'Generative',
    icon: Sparkles,
    chipClass: 'bg-purple-500/12 border-purple-400/25',
    textClass: 'text-purple-300',
  },
  editor: {
    label: 'Editor',
    icon: Layers,
    chipClass: 'bg-accent-cyan/12 border-accent-cyan/30',
    textClass: 'text-accent-cyan',
  },
  export: {
    label: 'Export',
    icon: Download,
    chipClass: 'bg-rose-500/12 border-rose-400/25',
    textClass: 'text-rose-300',
  },
  io: {
    label: 'I/O',
    icon: Folders,
    chipClass: 'bg-emerald-500/12 border-emerald-400/25',
    textClass: 'text-emerald-300',
  },
  analysis: {
    label: 'Analysis',
    icon: Info,
    chipClass: 'bg-blue-500/12 border-blue-400/25',
    textClass: 'text-blue-300',
  },
  planning: {
    label: 'Planning',
    icon: Wand2,
    chipClass: 'bg-accent-gold/12 border-accent-gold/30',
    textClass: 'text-accent-gold',
  },
  ai: {
    label: 'AI',
    icon: Wand2,
    chipClass: 'bg-accent-gold/12 border-accent-gold/30',
    textClass: 'text-accent-gold',
  },
  nodes: {
    label: 'Nodes',
    icon: GitBranch,
    chipClass: 'bg-violet-500/12 border-violet-400/25',
    textClass: 'text-violet-300',
  },
  voxel: {
    label: 'Voxel',
    icon: Grid3x3,
    chipClass: 'bg-indigo-500/12 border-indigo-400/25',
    textClass: 'text-indigo-300',
  },
  text: {
    label: 'Text',
    icon: Type,
    chipClass: 'bg-sky-500/12 border-sky-400/25',
    textClass: 'text-sky-300',
  },
  layers: {
    label: 'Layers',
    icon: Layers,
    chipClass: 'bg-teal-500/12 border-teal-400/25',
    textClass: 'text-teal-300',
  },
  scenes: {
    label: 'Scenes',
    icon: Sun,
    chipClass: 'bg-purple-500/12 border-purple-400/25',
    textClass: 'text-purple-300',
  },
}

/** Default category meta fallback (editor utility) */
const UNKNOWN_META: ToolCategoryMeta = CATEGORY_META.editor

/** Mirror of the orchestrator's _TOOL_CATEGORIES map so the client can
 *  resolve a category name from any registered tool name without an
 *  extra round-trip to the backend. Keep in sync with orchestrator.py. */
const TOOL_CATEGORY_LOOKUP: Record<string, string> = {
  // --- procedural & deformation
  noise_deform: 'deformation', bend_object: 'deformation', twist_object: 'deformation',
  taper_object: 'deformation', wave_deform: 'deformation', clear_modifiers: 'deformation',
  // --- postfx
  set_bloom: 'postfx', set_tone_mapping: 'postfx', set_color_grading: 'postfx',
  set_vignette: 'postfx', set_film_grain: 'postfx', set_depth_of_field: 'postfx',
  set_chromatic_aberration: 'postfx', reset_postfx: 'postfx', set_exposure: 'lighting',
  // --- patterns
  hex_grid_pattern: 'patterns', fibonacci_lattice: 'patterns', generate_maze: 'patterns',
  honeycomb_truss: 'patterns', knotwork_lattice: 'patterns',
  // --- snapshots / versioning
  snapshot_scene: 'snapshots', list_snapshots: 'snapshots', restore_snapshot: 'snapshots',
  snapshot_diff: 'snapshots', delete_snapshot: 'snapshots',
  // --- geometry
  create_object: 'geometry', duplicate_object: 'geometry', modify_geometry: 'geometry',
  convert_geometry: 'geometry', subdivide_mesh: 'geometry', delete_object: 'utility',
  // --- material
  apply_material: 'material', apply_material_preset: 'material', paint_vertex_colors: 'material',
  // --- lighting
  add_light: 'lighting', modify_light: 'lighting', delete_light: 'lighting',
  set_ambient_level: 'lighting', create_lighting_rig: 'lighting', set_environment: 'lighting',
  // --- camera
  add_camera: 'camera', modify_camera: 'camera', set_view: 'camera',
  snapshot_view: 'camera', animate_camera: 'camera', orbit_viewport: 'camera',
  fit_camera_to_selection: 'camera',
  // --- transform
  transform_object: 'transform', arrange_layout: 'layout', align_objects: 'layout',
  distribute_objects: 'layout', apply_physics: 'physics', clear_physics: 'physics',
  list_physics: 'physics',
  // --- animation
  set_keyframe: 'animation', create_animation_clip: 'animation', keyframe_animation: 'animation',
  orbit_animation: 'animation', wave_animation: 'animation', bounce_animation: 'animation',
  pulse_animation: 'animation', sway_animation: 'animation', spin_animation: 'animation',
  create_scene_transition: 'animation', play_scene_transition: 'animation',
  list_scene_transitions: 'animation', remove_scene_transition: 'animation',
  // --- procedural helpers (already covered above; kept explicit)
  radial_symmetry: 'procedural', clone_with_jitter: 'procedural',
  // --- particles
  create_particle_system: 'particles', delete_particle_system: 'particles',
  modify_particle_system: 'particles', list_particle_systems: 'particles',
  // --- group / layer
  group_objects: 'utility', ungroup_objects: 'utility',
  set_layer_visibility: 'layers', create_layer: 'layers', delete_layer: 'layers',
  set_layer_color: 'layers',
  // --- scene-level
  set_background: 'scenes', set_fog: 'scenes', toggle_grid: 'utility',
  set_grid_size: 'utility', apply_scene_preset: 'scenes',
  // --- utility & info
  list_objects: 'analysis', measure_distance: 'analysis', scene_info: 'analysis',
  analyze_scene: 'analysis', scene_statistics: 'analysis', self_evaluate: 'ai',
  list_constraints: 'planning', add_constraint: 'planning', clear_constraints: 'planning',
  solve_constraints: 'planning', refine_scene: 'ai',
  // --- nodes
  configure_node_graph: 'nodes', execute_node_graph: 'nodes',
  list_node_graphs: 'nodes', delete_node_graph: 'nodes',
  // --- text
  create_text: 'text',
  // --- voxel
  voxel_sculpt: 'voxel',
  // --- io/export
  export_scene: 'export', generate_3d_asset: 'generative',
  generate_image: 'generative', generate_video: 'generative',
  import_scene: 'io',
  // --- select/editor-state
  select_object: 'editor', focus_object: 'editor', toggle_editor_panel: 'editor',
  deselect_all: 'editor', set_animation_looping: 'animation',
  list_scene_templates: 'editor', list_skills: 'ai',
  // --- multi-agent
  dispatch_subagent: 'ai', ensemble_brainstorm: 'ai', consensus_vote: 'ai',
}

/** Resolve a category meta object from a tool name. */
function categoryForTool(name: string): ToolCategoryMeta {
  const key = TOOL_CATEGORY_LOOKUP[name]
  if (key && CATEGORY_META[key]) return CATEGORY_META[key]
  // Heuristic fallback — prefix-based partial matches for forward compatibility.
  for (const [t, key2] of Object.entries(TOOL_CATEGORY_LOOKUP)) {
    if (name.startsWith(t.split('_')[0]) && CATEGORY_META[key2]) return CATEGORY_META[key2]
  }
  return UNKNOWN_META
}

/** Map a tool name to a representative icon */
const TOOL_ICONS: Record<string, LucideIcon> = {
  create_object: Box,
  duplicate_object: Box,
  transform_object: Move,
  modify_geometry: Box,
  delete_object: Trash2,
  list_objects: Layers,
  apply_material: Palette,
  apply_material_preset: Palette,
  add_light: Lightbulb,
  modify_light: Lightbulb,
  delete_light: Lightbulb,
  add_camera: Camera,
  modify_camera: Camera,
  set_view: Camera,
  snapshot_view: Camera,
  animate_camera: Film,
  group_objects: Layers,
  ungroup_objects: Layers,
  set_background: Palette,
  set_fog: Globe,
  set_environment: Sun,
  arrange_layout: AlignHorizontalDistributeCenter,
  align_objects: AlignHorizontalDistributeCenter,
  distribute_objects: AlignHorizontalDistributeCenter,
  measure_distance: Ruler,
  scene_info: Info,
  analyze_scene: Info,
  toggle_grid: Layers,
  set_grid_size: Layers,
  select_object: Eye,
  focus_object: Eye,
  export_scene: Download,
  generate_image: ImageIcon,
  generate_3d_asset: Box,
  generate_video: Video,
  generate_animation: Film,
  list_scene_templates: Sparkles,
  orbit_viewport: Orbit,
  set_layer_visibility: Layers,
  list_skills: Sparkles,
  add_constraint: Link2,
  list_constraints: List,
  clear_constraints: Eraser,
  solve_constraints: Wand2,
  refine_scene: Sparkles,
  radial_symmetry: CircleDot,
  clone_with_jitter: CopyPlus,
  convert_geometry: Box,
  subdivide_mesh: Grid3x3,
  create_lighting_rig: Sun,
  set_ambient_level: Lightbulb,
  set_exposure: Sun,
  apply_scene_preset: Layers,
  set_keyframe: Film,
  create_animation_clip: Film,
  fit_camera_to_selection: Camera,
  keyframe_animation: Film,
  orbit_animation: Orbit,
  wave_animation: Waves,
  bounce_animation: Activity,
  pulse_animation: HeartPulse,
  sway_animation: Waves,
  spin_animation: RotateCw,
  create_layer: Layers,
  delete_layer: Trash2,
  set_layer_color: Palette,
  paint_vertex_colors: Palette,
  configure_node_graph: Link2,
  execute_node_graph: Loader2,
  list_node_graphs: List,
  delete_node_graph: Trash2,
  apply_physics: Move,
  clear_physics: Eraser,
  list_physics: List,
  create_text: Type,
  create_scene_transition: Move,
  play_scene_transition: Play,
  list_scene_transitions: List,
  remove_scene_transition: Trash2,
  dispatch_subagent: Users,
  ensemble_brainstorm: Users,
  // --- Deformation modifier tools
  noise_deform: Sparkle,
  bend_object: Sparkle,
  twist_object: Sparkle,
  taper_object: Sparkle,
  wave_deform: Sparkle,
  clear_modifiers: Eraser,
  // --- PostFX tools
  set_bloom: Sparkles,
  set_tone_mapping: Sparkles,
  set_color_grading: Palette,
  set_vignette: Sparkles,
  set_film_grain: Film,
  set_depth_of_field: Camera,
  set_chromatic_aberration: Sparkles,
  reset_postfx: Eraser,
  // --- Spatial pattern generators
  hex_grid_pattern: Hexagon,
  fibonacci_lattice: Flower2,
  generate_maze: Grid3x3,
  honeycomb_truss: Hexagon,
  knotwork_lattice: CircleDot,
  // --- Scene snapshot / versioning
  snapshot_scene: Save,
  list_snapshots: List,
  restore_snapshot: Save,
  snapshot_diff: GitBranch,
  delete_snapshot: Trash2,
  scene_statistics: Info,
  consensus_vote: Users,
}

/** Resolve the icon for a tool, falling back to Terminal */
function iconForTool(name: string): LucideIcon {
  return TOOL_ICONS[name] ?? Terminal
}

/** Friendly display of the tool name */
function friendlyName(name: string): string {
  return name.replace(/_/g, ' ')
}

/** Extract an execution duration (in milliseconds) from a tool result's
 *  data payload. Different tools report timing under different keys, so we
 *  probe the common ones and normalize seconds → milliseconds. Returns null
 *  when no timing info is present. */
function extractDurationMs(data: Record<string, unknown> | undefined): number | null {
  if (!data) return null
  const keys = ['duration_ms', 'elapsed_ms', 'time_ms', 'ms', 'duration', 'elapsed', 'execution_time', 'time']
  for (const k of keys) {
    const v = data[k]
    if (typeof v === 'number' && isFinite(v) && v > 0) {
      // Heuristic: keys with a "_ms" suffix or named "ms" are milliseconds;
      // the rest (duration/elapsed/time) are conventionally seconds.
      return k.endsWith('_ms') || k === 'ms' ? v : Math.round(v * 1000)
    }
  }
  return null
}

/** Format a millisecond duration as a compact human string. */
function formatDuration(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

/**
 * Render tool arguments as a compact, human-readable sentence for the common
 * editor tools, falling back to pretty JSON for unusual ones. This turns raw
 * argument maps into the "why/what" a user can actually read at a glance.
 */
function summarizeArgs(name: string, args: Record<string, unknown>): string {
  const esc = (v: unknown): string =>
    typeof v === 'string' ? v : JSON.stringify(v)
  const fmtVec = (v: unknown): string => {
    if (Array.isArray(v)) return `(${(v as unknown[]).map((n) => Number(n).toFixed(2)).join(', ')})`
    return String(v ?? 0)
  }
  switch (name) {
    case 'create_object':
      return `${esc(args.geometry_type ?? 'box')} "${esc(args.name ?? '')}"${args.color ? `, color ${esc(args.color)}` : ''} at ${fmtVec(args.position)}`
    case 'transform_object':
      return `move "${esc(args.target ?? '')}" to ${fmtVec(args.position)}${args.rotation ? `, rotate ${fmtVec(args.rotation)}` : ''}`
    case 'apply_material':
      return `apply ${esc(args.color ?? args.preset ?? 'material')} to "${esc(args.target ?? '')}"`
    case 'add_light':
      return `${esc(args.light_type ?? 'light')} "${esc(args.name ?? '')}" at ${fmtVec(args.position)}, intensity ${esc(args.intensity ?? 1)}`
    case 'create_particle_system':
      return `${esc(args.effect_type ?? 'fire')} particle system at ${fmtVec(args.position)}, intensity ${esc(args.intensity ?? 1)}`
    case 'voxel_sculpt':
      return `${esc(args.operation ?? 'add')} voxel${args.radius ? ` (radius ${esc(args.radius)})` : ''} at ${fmtVec(args.position)}`
    case 'generate_lod_chain':
      return `LOD chain for "${esc(args.target ?? '')}" with ${esc(args.levels ?? 3)} levels`
    case 'repair_mesh':
      return `repair "${esc(args.target ?? '')}" (${esc(args.fixes ?? ['all']).replace(/"/g, '')})`
    case 'self_evaluate':
      return `evaluate scene: "${esc(args.goal ?? '')}"${args.auto_fix ? ' (with auto-fix)' : ''}`
    case 'consensus_vote':
      return `multi-model vote (${esc(args.strategy ?? 'majority')}) on "${esc(args.prompt ?? '')}"`
    case 'orbit_animation':
      return `orbit "${esc(args.target ?? '')}" radius ${esc(args.radius ?? 3)}`
    default:
      return ''
  }
}

export function ToolCallCard({ call }: ToolCallCardProps) {
  const send = useChat((s) => s.send)
  const isResponding = useChat((s) => s.isResponding)
  const humanArgs = summarizeArgs(call.name, call.arguments)
  const argString = (() => {
    try {
      return JSON.stringify(call.arguments, null, 2)
    } catch {
      return '{}'
    }
  })()

  const hasMedia = call.result?.data && hasMultimediaResult(call.name)
  const Icon = iconForTool(call.name)
  const failed = !call.pending && call.result && !call.result.success
  const category = categoryForTool(call.name)
  const CatIcon = category.icon
  // Execution duration surfaced from the tool result's data payload. May be
  // absent when the backend did not report timing for this tool.
  const durationMs = extractDurationMs(call.result?.data)

  const handleRetry = () => {
    if (isResponding) return
    send(`Retry the ${friendlyName(call.name)} tool call with the same parameters`)
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2 }}
      className={`relative rounded-md border bg-bg-base/60 overflow-hidden ${
        failed ? 'border-rose-500/30' : 'border-border'
      }`}
    >
      {/* Pulsing left accent — animates while the tool is executing so the
          user can see at a glance which call is in flight. */}
      {call.pending && (
        <div className="absolute left-0 top-0 bottom-0 w-0.5 bg-accent-cyan animate-pulse" />
      )}

      <div className="flex items-center gap-2 px-3 py-2 bg-bg-elevated/70 border-b border-border-subtle">
        <Icon size={13} className={failed ? 'text-rose-400' : 'text-accent-cyan'} />
        <span className="text-xs font-mono text-fg-primary font-medium tracking-wide">
          {friendlyName(call.name)}
        </span>
        <span
          title={`Category: ${category.label}`}
          className={`inline-flex items-center gap-1 rounded-full border px-1.5 py-[1px] text-[9px] font-semibold uppercase tracking-wider ${category.chipClass} ${category.textClass}`}
        >
          <CatIcon size={8.5} />
          {category.label}
        </span>
        <span className="ml-auto flex items-center gap-1.5 text-[10px]">
          {/* Execution duration badge — shown when the tool reported timing. */}
          {durationMs !== null && !call.pending && (
            <span
              title="Execution duration"
              className="flex items-center gap-1 text-fg-muted font-mono"
            >
              <Timer size={9} className="text-fg-muted/70" />
              {formatDuration(durationMs)}
            </span>
          )}
          {call.pending ? (
            <span className="flex items-center gap-1 text-fg-secondary">
              <Loader2 size={11} className="animate-spin" />
              Running…
            </span>
          ) : call.result?.success ? (
            <span className="flex items-center gap-1 text-emerald-400">
              <CheckCircle2 size={11} />
              Success
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
        <div className="px-3 py-2">
          {humanArgs ? (
            <p className="text-[11.5px] text-fg-secondary leading-relaxed">{humanArgs}</p>
          ) : null}
          <details className="mt-1">
            <summary className="cursor-pointer text-[10px] text-fg-muted hover:text-fg-secondary select-none">
              Raw arguments
            </summary>
            <pre className="mt-1 text-[11px] font-mono text-fg-secondary overflow-x-auto max-h-40 leading-relaxed">
              {argString}
            </pre>
          </details>
        </div>
      )}

      {call.result && (
        <div className="px-3 py-1.5 text-[11px] text-fg-secondary border-t border-border-subtle bg-bg-base/40">
          <div className="flex items-start gap-2">
            <span className="flex-1">{call.result.message}</span>
            {/* Retry button — re-sends the same tool call as a natural
                language instruction so the Agent can re-run it. */}
            {failed && (
              <button
                onClick={handleRetry}
                disabled={isResponding}
                title="Retry this tool call"
                className="shrink-0 inline-flex items-center gap-1 text-[10px] font-medium text-rose-300 hover:text-rose-200 border border-rose-500/30 hover:border-rose-500/50 rounded px-1.5 py-0.5 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              >
                <RotateCcw size={9} />
                Retry
              </button>
            )}
          </div>
        </div>
      )}

      {/* Rich media rendering for multimodal generation tools */}
      {hasMedia && call.result?.data && (
        <div className="px-3 pb-2">
          <MultimodalResult toolName={call.name} data={call.result.data} />
        </div>
      )}
    </motion.div>
  )
}
