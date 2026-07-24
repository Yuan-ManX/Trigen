// Trigen scene data model and API event type definitions
// Trigen 场景数据模型与 API 事件类型定义
// Kept in sync with backend trigen/scene.py

/** 3D vector / Euler angles (radians) */
/** 三维向量 / 欧拉角（弧度） */
export type Vec3 = [number, number, number]

/** Supported geometry types */
/** 支持的几何体类型 */
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
/** 几何体参数（不同类型字段不同） */
export interface Geometry {
  type: GeometryType
  params: Record<string, number | number[]>
}

/** PBR material */
/** PBR 材质 */
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
/** 对象空间变换 */
export interface Transform {
  position: Vec3
  rotation: Vec3
  scale: Vec3
}

/** Mesh object in the scene */
/** 场景中的网格对象 */
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
/** 光源类型 */
export type LightType = 'ambient' | 'directional' | 'point' | 'spot' | 'hemisphere'

/** Light object */
/** 光源对象 */
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

/** Camera object */
/** 相机对象 */
export interface CameraObject {
  id: string
  name: string
  type: 'perspective' | 'orthographic'
  position: Vec3
  target: Vec3
  fov: number
  near: number
  far: number
}

/** Group object */
/** 分组对象 */
export interface GroupObject {
  id: string
  name: string
  child_ids: string[]
  visible: boolean
  locked: boolean
}

/** Fog configuration */
/** 雾效配置 */
export interface FogConfig {
  color: string
  near: number
  far: number
}

/** Complete scene */
/** 完整场景 */
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
/** 空场景默认值 */
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
/* ===================== WebSocket 事件类型 ===================== */

/** Thinking event (Agent reasoning trace) */
/** 思考事件（Agent 推理轨迹） */
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
/** 工具调用开始事件 */
export interface ToolCallEvent {
  type: 'tool_call'
  data: {
    id: string
    name: string
    arguments: Record<string, unknown>
  }
}

/** Tool execution result event */
/** 工具执行结果事件 */
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
/** 场景变更事件 */
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
/** 流式文本片段事件 */
export interface TextDeltaEvent {
  type: 'text_delta'
  data: {
    content: string
  }
}

/** Turn finished event */
/** 本轮结束事件 */
export interface DoneEvent {
  type: 'done'
  data: {
    content: string
    scene?: SceneData
    elapsed?: number
  }
}

/** Error event */
/** 错误事件 */
export interface ErrorEvent {
  type: 'error'
  data: {
    message: string
  }
}

/** Message sent by the client */
/** 客户端发送的消息 */
export interface ClientMessage {
  type: 'message'
  data: {
    message: string
    session_id: string
  }
}

/** Union type of all server-pushed events */
/** 服务端推送的所有事件联合类型 */
export type ServerEvent =
  | ThinkingEvent
  | TextDeltaEvent
  | ToolCallEvent
  | ToolResultEvent
  | SceneUpdateEvent
  | DoneEvent
  | ErrorEvent

/* ============ REST API types ============ */
/* ===================== REST 接口类型 ===================== */

/** Health check response */
/** 健康检查响应 */
export interface HealthResponse {
  status: string
  version: string
  llm_configured: boolean
  sessions?: number
  tools?: number
}

/** Tool schema */
/** 工具 schema */
export interface ToolSchema {
  name: string
  description: string
  parameters: Record<string, unknown>
}

/** Tools listing response */
/** 工具列表响应 */
export interface ToolsResponse {
  tools: ToolSchema[]
  count: number
}

/** Presets listing response */
/** 预设列表响应 */
export interface PresetsResponse {
  geometry_types: string[]
  material_presets: string[]
  light_types: string[]
}
