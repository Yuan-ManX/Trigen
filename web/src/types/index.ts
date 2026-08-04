// Trigen scene data model and API event type definitions
// Kept in sync with backend trigen/scene.py

/** 3D vector / Euler angles (radians) */
export type Vec3 = [number, number, number]

/** Supported geometry types */
export type GeometryType =
  | 'box'
  | 'sphere'
  | 'cylinder'
  | 'cone'
  | 'torus'
  | 'plane'
  | 'torusKnot'
  | 'dodecahedron'
  | 'icosahedron'
  | 'octahedron'
  | 'tetrahedron'
  | 'ring'
  | 'capsule'
  | 'tube'
  | 'lathe'
  | 'extrude'
  | 'text'
  | 'spline'

/** Geometry parameters (different types have different fields) */
export type GeometryParams = Record<string, number | number[] | number[][] | string | boolean>

export interface Geometry {
  type: GeometryType
  params: GeometryParams
}

/** PBR material */
export interface Material {
  color: string
  metalness: number
  roughness: number
  opacity: number
  wireframe: boolean
  emissive: string
  emissive_intensity: number
  flat_shading?: boolean
  side?: 'front' | 'back' | 'double'
  // Extended PBR (MeshPhysicalMaterial). All optional with zero defaults
  // so older scenes omit them without breaking the renderer.
  clearcoat?: number
  clearcoat_roughness?: number
  transmission?: number
  thickness?: number
  ior?: number
  iridescence?: number
  iridescence_ior?: number
  iridescence_thickness_min?: number
  iridescence_thickness_max?: number
  sheen?: number
  sheen_color?: string
  sheen_roughness?: number
  specular_intensity?: number
  specular_color?: string
  attenuation_color?: string
  attenuation_distance?: number
}

/** Object-space transform */
export interface Transform {
  position: Vec3
  rotation: Vec3
  scale: Vec3
}

/** Mesh object in the scene */
export interface SceneObject {
  id: string
  name: string
  type: 'mesh'
  geometry: Geometry
  material: Material
  transform: Transform
  visible: boolean
  locked: boolean
  group_id?: string | null
  tags?: string[]
  animation?: ObjectAnimation | null
}

/** Object animation descriptor (keyframe/orbit/wave/bounce) */
export interface ObjectAnimation {
  type: 'keyframe' | 'orbit' | 'wave' | 'bounce'
  duration: number
  loop: boolean
  // keyframe
  keyframes?: Array<{
    t: number
    position?: Vec3
    rotation?: Vec3
    scale?: Vec3
  }>
  easing?: 'linear' | 'easeIn' | 'easeOut' | 'easeInOut'
  // orbit
  center?: Vec3
  radius?: number
  height?: number
  axis?: 'x' | 'y' | 'z'
  face_center?: boolean
  // wave
  amplitude?: number
  frequency?: number
  // bounce
  bounces?: number
  squash?: boolean
  // internal captured state
  start_position?: Vec3
  start_scale?: Vec3
}

/** Light types */
export type LightType = 'ambient' | 'directional' | 'point' | 'spot' | 'hemisphere'

/** Light object */
export interface LightObject {
  id: string
  name: string
  type: LightType
  color: string
  intensity: number
  position: Vec3
  target: Vec3 | null
  cast_shadow: boolean
  angle?: number
  penumbra?: number
  distance?: number
  decay?: number
}

/** Camera animation descriptor (orbit/flythrough) */
export interface CameraAnimation {
  type: 'orbit' | 'flythrough'
  duration: number
  loop: boolean
  target?: Vec3
  radius?: number
  height?: number
  points?: Vec3[]
}

/** Camera object */
export interface CameraObject {
  id: string
  name: string
  type: 'perspective' | 'orthographic'
  position: Vec3
  target: Vec3
  fov: number
  near: number
  far: number
  animation?: CameraAnimation | null
}

/** Group object */
export interface GroupObject {
  id: string
  name: string
  child_ids: string[]
  visible: boolean
  locked: boolean
}

/** Fog configuration */
export interface FogConfig {
  color: string
  near: number
  far: number
}

/** On-canvas annotation. Anchored either to a world position or to a
 *  specific object id (in which case the renderer tracks the object
 *  transform every frame). */
export interface Annotation {
  /** Stable identifier; matches backend Annotation.id. */
  id: string
  /** Optional anchor object id. When set, the label follows the object's
   *  world-space position (its transform.position plus an offset). */
  object_id?: string | null
  /** World-space anchor position. Used directly when object_id is null. */
  position: Vec3
  /** Text body shown in the viewport bubble. */
  text: string
  /** Optional short title rendered as a header above the body. */
  title?: string
  /** Accent color for the bubble border + leader line. */
  color?: string
  /** Whether the annotation is currently visible. */
  visible?: boolean
}

/** Complete scene */
export interface SceneData {
  objects: SceneObject[]
  lights: LightObject[]
  cameras: CameraObject[]
  groups: GroupObject[]
  background: string
  environment: string | null
  fog: FogConfig | null
  grid_visible: boolean
  grid_size: number
  /** On-canvas annotations (text labels anchored to objects or world points). */
  annotations?: Annotation[]
}

/** Empty scene default value */
export const EMPTY_SCENE: SceneData = {
  objects: [],
  lights: [],
  cameras: [],
  groups: [],
  background: '#0a0a0f',
  environment: null,
  fog: null,
  grid_visible: true,
  grid_size: 40,
  annotations: [],
}

/* ============ WebSocket event types ============ */

/** Thinking event (Agent reasoning trace) */
export interface ThinkingEvent {
  type: 'thinking'
  data: {
    phase: 'understanding' | 'planning' | 'complete' | string
    content: string
    tools?: string[]
    scene_summary?: string
    elapsed?: number
    iterations?: number
  }
}

/** Tool call start event */
export interface ToolCallEvent {
  type: 'tool_call'
  data: {
    id: string
    name: string
    arguments: Record<string, unknown>
  }
}

/** Tool execution result event */
export interface ToolResultEvent {
  type: 'tool_result'
  data: {
    id?: string
    name?: string
    success: boolean
    message: string
    data?: unknown
  }
}

/** Scene update event */
export interface SceneUpdateEvent {
  type: 'scene_update'
  data: {
    deltas?: Array<{
      action: string
      target_id?: string
      payload?: Record<string, unknown>
    }>
    scene: SceneData
  }
}

/** Streaming text delta event */
export interface TextDeltaEvent {
  type: 'text_delta'
  data: {
    content: string
  }
}

/** Turn finished event */
export interface DoneEvent {
  type: 'done'
  data: {
    content: string
    scene?: SceneData
    elapsed?: number
    /** Proactive next-action suggestions produced by the Agent for the
     *  current scene; optional because some turns (errors, editor-only)
     *  may not generate them. */
    suggestions?: unknown[]
    /** Optional turn statistics payload from the orchestrator. */
    stats?: {
      iterations?: number
      tool_calls?: number
      elapsed?: number
      token_budget_used?: number
      token_budget_limit?: number
      token_usage?: {
        prompt_tokens?: number
        completion_tokens?: number
        total_tokens?: number
      }
    }
    /** Token usage for the turn (also mirrored on stats.token_usage). */
    token_usage?: {
      prompt_tokens?: number
      completion_tokens?: number
      total_tokens?: number
    }
    session_id?: string
    /** Cross-turn project headline inferred from the latest plan. */
    project_goal?: string
  }
}

/** Error event */
export interface ErrorEvent {
  type: 'error'
  data: {
    message: string
  }
}

/** A single step in the agent's execution plan roadmap. */
export interface PlanStep {
  id: string
  tool: string
  description?: string
  arguments?: Record<string, unknown>
  status: 'pending' | 'running' | 'done' | 'failed'
  message?: string
}

/** Plan roadmap event — emitted at the planning phase with the full step list. */
export interface PlanEvent {
  type: 'plan'
  data: {
    goal?: string
    assumptions?: string[]
    risks?: string[]
    iteration?: number
    steps: Array<{
      id: string
      tool: string
      description?: string
      arguments?: Record<string, unknown>
      status: string
    }>
  }
}

/** Per-step status transition emitted as each tool call runs / completes. */
export interface PlanUpdateEvent {
  type: 'plan_update'
  data: {
    id: string
    tool?: string
    status: 'running' | 'done' | 'failed' | string
    message?: string
  }
}

/** Mid-turn plan refinement notice — emitted when the agent revises its
 *  plan (alternative-tool proposal after a failure, budget-driven pruning).
 *  Advisory only; the LLM still decides whether to follow the hint. */
export interface PlanRefineEvent {
  type: 'plan_refine'
  data: {
    reason: 'tool_failure_alternative_suggestion' | 'budget_prune' | string
    iteration?: number
    proposals?: { failed: string; alternative: string }[]
    active_categories?: string[]
    tool_subset_size?: number
    budget_remaining?: number
  }
}

/** Message sent by the client */
export interface ClientMessage {
  type: 'message'
  data: {
    message: string
    session_id: string
    model?: string
  }
}

/** Union type of all server-pushed events */
export type ServerEvent =
  | ThinkingEvent
  | TextDeltaEvent
  | ToolCallEvent
  | ToolResultEvent
  | SceneUpdateEvent
  | PlanEvent
  | PlanUpdateEvent
  | PlanRefineEvent
  | DoneEvent
  | ErrorEvent

/* ============ REST API types ============ */

/** Health check response */
export interface HealthResponse {
  status: string
  version: string
  llm_configured: boolean
  sessions?: number
  tools?: number
}

/** Tool schema */
export interface ToolSchema {
  name: string
  description: string
  parameters: Record<string, unknown>
  category?: string
  requires_approval?: boolean
}

/** Tools listing response */
export interface ToolsResponse {
  tools: ToolSchema[]
  count: number
}

/** Single category entry in the /api/tools/categories summary. */
export interface ToolCategorySummaryEntry {
  category: string
  count: number
}

/** Tools grouped by category, returned by /api/tools/categories. */
export interface ToolCategoriesResponse {
  categories: Record<string, ToolSchema[]>
  summary: ToolCategorySummaryEntry[]
  total_categories: number
  total_tools: number
}

/** Per-category capabilities block in /api/agent/status. */
export interface AgentStatusCategory {
  category: string
  count: number
}

/** Capabilities block returned by /api/agent/status. */
export interface AgentStatusCapabilities {
  tools: number
  skills: number
  categories: AgentStatusCategory[]
  total_categories: number
}

/** Runtime config block returned by /api/agent/status. */
export interface AgentStatusConfig {
  max_iterations: number
  memory_window: number
  max_tokens_per_turn: number
}

/** Response of GET /api/agent/status — used to drive an online/offline
 *  indicator and disable LLM-dependent UI when the agent is offline. */
export interface AgentStatusResponse {
  online: boolean
  mode: 'online' | 'offline'
  llm_configured: boolean
  primary_model: string | null
  available_chat_models: string[]
  fallback_chain: string[]
  usable_fallback_chain: string[]
  capabilities: AgentStatusCapabilities
  config: AgentStatusConfig
}

/** Result of POST /api/skills/invoke — direct skill execution payload. */
export interface InvokeSkillResponse {
  skill: string
  success: boolean
  message: string
  data: Record<string, unknown>
  deltas: Array<Record<string, unknown>>
  scene: SceneData
}

/** Presets listing response */
export interface PresetsResponse {
  geometry_types: string[]
  material_presets: string[]
  light_types: string[]
}

/* ============ Pipeline node graph types ============ */

/** Type label for a pipeline port: 'str' | 'int' | 'bool' | 'dict' | 'any'. */
export type PipelinePortType = 'str' | 'int' | 'bool' | 'dict' | 'any' | string

/** Schema for a single pipeline node type — input/output port declarations. */
export interface PipelineNodeType {
  /** Type identifier used in pipeline JSON (e.g. 'llm_complete'). */
  type: string
  /** Human-readable label rendered in the palette. */
  label: string
  /** Short description shown under the label. */
  description: string
  /** Functional grouping used to colour-code palette entries. */
  category: 'llm' | 'image' | 'three_d' | 'video' | 'audio' | 'utility'
  /** Input port name -> type label. */
  inputs: Record<string, PipelinePortType>
  /** Output port name -> type label. */
  outputs: Record<string, PipelinePortType>
}

/** Response of GET /api/models/pipeline/node_types. */
export interface PipelineNodeTypesResponse {
  node_types: Record<string, { inputs: Record<string, PipelinePortType>; outputs: Record<string, PipelinePortType> }>
  count: number
}

/** A node instance placed on the graph canvas. */
export interface PipelineGraphNode {
  /** Stable instance id (unique within the graph). */
  id: string
  /** Node type from the registry. */
  type: string
  /** Resolved input values — either literals or refs to upstream outputs. */
  inputs: Record<string, unknown>
  /** Canvas position in graph-space pixels. */
  position: { x: number; y: number }
}

/** An edge between an upstream output port and a downstream input port. */
export interface PipelineGraphEdge {
  /** Source node id. */
  from: string
  /** Source output port name. */
  output: string
  /** Target node id. */
  to: string
  /** Target input port name. */
  input: string
}

/** Per-node execution status surfaced by the SSE stream. */
export type PipelineNodeStatus = 'pending' | 'running' | 'success' | 'failed' | 'skipped'
