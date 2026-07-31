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

/** Geometry parameters (different types have different fields) */
export interface Geometry {
  type: GeometryType
  params: Record<string, number | number[]>
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
  }
}

/** Error event */
export interface ErrorEvent {
  type: 'error'
  data: {
    message: string
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
}

/** Tools listing response */
export interface ToolsResponse {
  tools: ToolSchema[]
  count: number
}

/** Presets listing response */
export interface PresetsResponse {
  geometry_types: string[]
  material_presets: string[]
  light_types: string[]
}
