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
  Globe,
  Grid3x3,
  HeartPulse,
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
  RotateCw,
  Ruler,
  Sparkles,
  Sun,
  Terminal,
  Trash2,
  Type,
  Users,
  Video,
  Wand2,
  Waves,
  XCircle,
} from 'lucide-react'
import type { ToolCallRecord } from '../../store/useChat'
import { MultimodalResult, hasMultimediaResult } from './MultimodalResult'

interface ToolCallCardProps {
  call: ToolCallRecord
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
  // Frontend-editor coverage gap tools
  list_scene_templates: Sparkles,
  orbit_viewport: Orbit,
  set_layer_visibility: Layers,
  list_skills: Sparkles,
  // Constraint authoring + goal-driven refinement
  add_constraint: Link2,
  list_constraints: List,
  clear_constraints: Eraser,
  solve_constraints: Wand2,
  refine_scene: Sparkles,
  // Generative geometry — radial symmetry rings + jittered clones
  radial_symmetry: CircleDot,
  clone_with_jitter: CopyPlus,
  // Mesh detail editing — in-place type conversion + segment subdivision
  convert_geometry: Box,
  subdivide_mesh: Grid3x3,
  // Lighting rigs + scene presets + exposure
  create_lighting_rig: Sun,
  set_ambient_level: Lightbulb,
  set_exposure: Sun,
  apply_scene_preset: Layers,
  // Keyframing + camera framing
  set_keyframe: Film,
  create_animation_clip: Film,
  fit_camera_to_selection: Camera,
  // Object motion primitives — keyframe / orbit / wave / bounce + pulse / sway / spin
  keyframe_animation: Film,
  orbit_animation: Orbit,
  wave_animation: Waves,
  bounce_animation: Activity,
  pulse_animation: HeartPulse,
  sway_animation: Waves,
  spin_animation: RotateCw,
  // Layer management + vertex paint
  create_layer: Layers,
  delete_layer: Trash2,
  set_layer_color: Palette,
  paint_vertex_colors: Palette,
  // Node graph authoring
  configure_node_graph: Link2,
  execute_node_graph: Loader2,
  list_node_graphs: List,
  delete_node_graph: Trash2,
  // Rigid-body physics + text authoring
  apply_physics: Move,
  clear_physics: Eraser,
  list_physics: List,
  create_text: Type,
  // Scene transitions — AI-native motion choreography
  create_scene_transition: Move,
  play_scene_transition: Play,
  list_scene_transitions: List,
  remove_scene_transition: Trash2,
  // Multi-agent orchestration — sub-agent dispatch + parallel specialist ensemble
  dispatch_subagent: Users,
  ensemble_brainstorm: Users,
}

/** Resolve the icon for a tool, falling back to Terminal */
function iconForTool(name: string): LucideIcon {
  return TOOL_ICONS[name] ?? Terminal
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

  const hasMedia = call.result?.data && hasMultimediaResult(call.name)
  const Icon = iconForTool(call.name)
  const failed = !call.pending && call.result && !call.result.success

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2 }}
      className={`rounded-md border bg-bg-base/60 overflow-hidden ${
        failed ? 'border-rose-500/30' : 'border-border'
      }`}
    >
      <div className="flex items-center gap-2 px-3 py-2 bg-bg-elevated/70 border-b border-border-subtle">
        <Icon size={13} className={failed ? 'text-rose-400' : 'text-accent-cyan'} />
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

      {/* Rich media rendering for multimodal generation tools */}
      {hasMedia && call.result?.data && (
        <div className="px-3 pb-2">
          <MultimodalResult toolName={call.name} data={call.result.data} />
        </div>
      )}
    </motion.div>
  )
}
