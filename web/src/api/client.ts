// REST + WebSocket client
// In development, proxied to backend http://localhost:7100 via Vite proxy

import type {
  AddConstraintData,
  AgentRunResponse,
  AgentStatusResponse,
  AutoFixData,
  CheckpointDiff,
  CheckpointEntry,
  CheckpointListResponse,
  ClearConstraintsData,
  ClientMessage,
  ConstraintKind,
  CritiqueData,
  HealthResponse,
  InvokeSkillResponse,
  ListConstraintsData,
  PipelineNodeTypesResponse,
  PresetsResponse,
  RefineData,
  SceneData,
  ServerEvent,
  SolveConstraintsData,
  StoryboardResponse,
  ToolCategoriesResponse,
  ToolsResponse,
  WorkspaceResponse,
} from '../types'

/* ============ REST API ============ */

/** Health check */
export async function fetchHealth(): Promise<HealthResponse> {
  const res = await fetch('/api/health')
  if (!res.ok) throw new Error(`Health check failed: ${res.status}`)
  return res.json() as Promise<HealthResponse>
}

/** Fetch the complete scene */
export async function fetchScene(sessionId: string): Promise<SceneData> {
  const res = await fetch(`/api/scene/${encodeURIComponent(sessionId)}`)
  if (!res.ok) throw new Error(`Failed to fetch scene: ${res.status}`)
  return res.json() as Promise<SceneData>
}

/** Reset scene */
export async function resetScene(sessionId: string): Promise<SceneData> {
  const res = await fetch(`/api/scene/${encodeURIComponent(sessionId)}/reset`, {
    method: 'POST',
  })
  if (!res.ok) throw new Error(`Failed to reset scene: ${res.status}`)
  return res.json() as Promise<SceneData>
}

/** Build the export file download URL */
export function exportUrl(filename: string): string {
  return `/api/exports/${encodeURIComponent(filename)}`
}

/** Fetch the available tool catalog */
export async function fetchTools(): Promise<ToolsResponse> {
  const res = await fetch('/api/tools')
  if (!res.ok) throw new Error(`Failed to fetch tool list: ${res.status}`)
  return res.json() as Promise<ToolsResponse>
}

/** Fetch the tool catalog grouped by functional category. The response
 *  mirrors the backend taxonomy (creation / transform / material / etc.)
 *  so the frontend can render a browsable catalog without re-grouping. */
export async function fetchToolCategories(): Promise<ToolCategoriesResponse> {
  const res = await fetch('/api/tools/categories')
  if (!res.ok) throw new Error(`Failed to fetch tool categories: ${res.status}`)
  return res.json() as Promise<ToolCategoriesResponse>
}

/** Fetch agent online/offline status and capability summary. Used to drive
 *  a mode indicator in the status bar and to disable LLM-dependent UI
 *  when the agent is running on the offline rule engine. */
export async function fetchAgentStatus(): Promise<AgentStatusResponse> {
  const res = await fetch('/api/agent/status')
  if (!res.ok) throw new Error(`Failed to fetch agent status: ${res.status}`)
  return res.json() as Promise<AgentStatusResponse>
}

/** Fetch the unified workspace bootstrap bundle in one call. Returns the
 *  live scene, agent status, tool catalog grouped by category, creative
 *  skill list, recent per-turn reflections, and saved Agentic Workflow
 *  Templates so the frontend can render every right-panel tab from a
 *  single payload on initial load. */
export async function fetchWorkspace(
  sessionId: string = 'default',
  reflectionLimit: number = 10,
): Promise<WorkspaceResponse> {
  const qs = `?session_id=${encodeURIComponent(sessionId)}&reflection_limit=${reflectionLimit}`
  const res = await fetch(`/api/agent/workspace${qs}`)
  if (!res.ok) throw new Error(`Failed to fetch workspace: ${res.status}`)
  return res.json() as Promise<WorkspaceResponse>
}

/** Invoke a creative skill directly (bypasses the LLM chat flow). Returns
 *  the aggregated result plus the updated scene so the caller can swap it
 *  in immediately. */
export async function invokeSkill(
  skill: string,
  arguments_: Record<string, unknown> = {},
  sessionId: string = 'default',
): Promise<InvokeSkillResponse> {
  const res = await fetch('/api/skills/invoke', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ skill, arguments: arguments_, session_id: sessionId }),
  })
  if (!res.ok) throw new Error(`Skill invocation failed: ${res.status}`)
  return res.json() as Promise<InvokeSkillResponse>
}

/** Batch-execute multiple tools sequentially against the same scene. */
export interface BatchStepResult {
  index: number
  tool: string
  success: boolean
  message: string
  deltas: Record<string, unknown>[]
  data: Record<string, unknown> | null
}

export interface BatchToolResponse {
  session_id: string
  total_steps: number
  executed_steps: number
  succeeded: number
  failed: number
  aborted: boolean
  steps: BatchStepResult[]
  scene: SceneData
}

export async function batchExecuteTools(
  steps: Array<{ tool_name: string; arguments: Record<string, unknown> }>,
  sessionId: string = 'default',
  stopOnError: boolean = true,
): Promise<BatchToolResponse> {
  const res = await fetch('/api/tools/batch', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ steps, session_id: sessionId, stop_on_error: stopOnError }),
  })
  if (!res.ok) throw new Error(`Batch execution failed: ${res.status}`)
  return res.json() as Promise<BatchToolResponse>
}

/** Fetch the preset catalog (geometry / material / light) */
export async function fetchPresets(): Promise<PresetsResponse> {
  const res = await fetch('/api/presets')
  if (!res.ok) throw new Error(`Failed to fetch preset list: ${res.status}`)
  return res.json() as Promise<PresetsResponse>
}

/** Default parameter presets for the newer generative tool families. */
export interface ToolPresetDescriptor {
  label: string
  category: string
  operations?: string[]
  effects?: string[]
  fixes?: string[]
  criteria?: string[]
  strategies?: string[]
  defaults: Record<string, unknown>
}

export interface ToolPresetsResponse {
  tools: Record<string, ToolPresetDescriptor>
  count: number
}

/** Fetch default parameter presets for the newest tool families. */
export async function fetchToolPresets(): Promise<ToolPresetsResponse> {
  const res = await fetch('/api/presets/tools')
  if (!res.ok) throw new Error(`Failed to fetch tool presets: ${res.status}`)
  return res.json() as Promise<ToolPresetsResponse>
}

/** Creative skill descriptor returned by /api/skills */
export interface SkillDescriptor {
  name: string
  description: string
  category: string
  parameters: Record<string, unknown>
}

/** Fetch the creative skill catalog (multi-tool recipes) */
export async function fetchSkills(): Promise<SkillDescriptor[]> {
  const res = await fetch('/api/skills')
  if (!res.ok) throw new Error(`Failed to fetch skills: ${res.status}`)
  const data = await res.json() as { skills: SkillDescriptor[]; count: number }
  return data.skills
}

/** Model entry from the LLM catalog */
export interface ModelEntry {
  id: string
  label: string
  provider: string
  description: string
  modalities: string[]
  max_tokens: number
  context_window: number
  is_open_source: boolean
  is_local: boolean
  api_key_env: string
}

/** Fetch the full LLM model catalog */
export async function fetchModels(): Promise<ModelEntry[]> {
  const res = await fetch('/api/models')
  if (!res.ok) throw new Error(`Failed to fetch models: ${res.status}`)
  const data = await res.json() as { models: ModelEntry[]; count: number }
  return data.models
}

/** Result of a multimodal generation call */
export interface GenerationResult {
  success: boolean
  modality: string
  model: string
  url?: string
  base64_data?: string
  mime_type?: string
  text?: string
  error?: string
  raw?: Record<string, unknown>
}

/** Generation modalities that use dedicated endpoints (not chat-completions) */
export const GENERATION_MODALITIES = ['image_gen', '3d', 'video', 'animation', 'voice', 'audio']

/** Check if a model is a generation-only model (cannot power chat directly) */
export function isGenerationModel(model: ModelEntry): boolean {
  const hasGeneration = model.modalities.some((m) => GENERATION_MODALITIES.includes(m))
  const hasChat = model.modalities.some((m) => m === 'text' || m === 'vision')
  return hasGeneration && !hasChat
}

/** Generate an image from a text prompt */
export async function generateImage(
  model: string,
  prompt: string,
  size: string = '1024x1024',
  n: number = 1,
): Promise<GenerationResult> {
  const res = await fetch('/api/models/generate-image', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ model, prompt, size, n }),
  })
  if (!res.ok) throw new Error(`Image generation failed: ${res.status}`)
  return res.json() as Promise<GenerationResult>
}

/** Generate a 3D asset from a text prompt */
export async function generate3D(
  model: string,
  prompt: string,
  outputFormat: string = 'glb',
): Promise<GenerationResult> {
  const res = await fetch('/api/models/generate-3d', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ model, prompt, output_format: outputFormat }),
  })
  if (!res.ok) throw new Error(`3D generation failed: ${res.status}`)
  return res.json() as Promise<GenerationResult>
}

/** Synthesize speech from text */
export async function textToSpeech(
  model: string,
  text: string,
  voice: string = 'alloy',
): Promise<GenerationResult> {
  const res = await fetch('/api/models/tts', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ model, text, voice }),
  })
  if (!res.ok) throw new Error(`TTS failed: ${res.status}`)
  return res.json() as Promise<GenerationResult>
}

/** Transcribe audio to text */
export async function transcribeAudio(
  model: string,
  audioBase64: string,
  mimeType: string = 'audio/wav',
): Promise<GenerationResult> {
  const res = await fetch('/api/models/transcribe', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ model, audio_base64: audioBase64, mime_type: mimeType }),
  })
  if (!res.ok) throw new Error(`Transcription failed: ${res.status}`)
  return res.json() as Promise<GenerationResult>
}

/* ============ Model availability & testing ============ */

/** Availability status for a single model */
export interface ModelAvailability {
  id: string
  label: string
  provider: string
  available: boolean
  reason: string
  modalities: string[]
  is_local: boolean
  is_open_source: boolean
  is_generation: boolean
}

/** Fetch availability status for all models */
export async function fetchModelAvailability(): Promise<ModelAvailability[]> {
  const res = await fetch('/api/models/availability')
  if (!res.ok) throw new Error(`Failed to fetch availability: ${res.status}`)
  const data = await res.json() as { models: ModelAvailability[]; total: number; available: number }
  return data.models
}

/** Result of a model connection test */
export interface ModelTestResult {
  model: string
  success: boolean
  response?: string
  error?: string
  elapsed_ms: number
  provider?: string
}

/** Test whether a model can actually respond to a request */
export async function testModelConnection(model: string, prompt?: string): Promise<ModelTestResult> {
  const res = await fetch('/api/models/test', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ model, prompt: prompt ?? 'Hello, respond with one word.' }),
  })
  if (!res.ok) throw new Error(`Model test failed: ${res.status}`)
  return res.json() as Promise<ModelTestResult>
}

/* ============ Runtime API key management ============ */

/** Status of a single API key slot */
export interface APIKeyStatus {
  env_name: string
  configured: boolean
  preview: string
  source: string // "runtime" | "env" | ""
}

/** Fetch the status of all API key slots */
export async function fetchAPIKeys(): Promise<{ keys: APIKeyStatus[]; total: number; configured: number }> {
  const res = await fetch('/api/models/keys')
  if (!res.ok) throw new Error(`Failed to fetch API keys: ${res.status}`)
  return res.json()
}

/** Set or update a runtime API key */
export async function setAPIKey(envName: string, apiKey: string): Promise<APIKeyStatus> {
  const res = await fetch('/api/models/keys', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ env_name: envName, api_key: apiKey }),
  })
  if (!res.ok) throw new Error(`Failed to set API key: ${res.status}`)
  return res.json()
}

/** Remove a runtime API key (falls back to env var if present) */
export async function deleteAPIKey(envName: string): Promise<{
  env_name: string
  removed: boolean
  still_configured_via_env: boolean
  configured: boolean
  source: string
}> {
  const res = await fetch(`/api/models/keys/${encodeURIComponent(envName)}`, {
    method: 'DELETE',
  })
  if (!res.ok) throw new Error(`Failed to delete API key: ${res.status}`)
  return res.json()
}

/** Remove all runtime API keys */
export async function clearAllAPIKeys(): Promise<{ removed_count: number }> {
  const res = await fetch('/api/models/keys', { method: 'DELETE' })
  if (!res.ok) throw new Error(`Failed to clear API keys: ${res.status}`)
  return res.json()
}

/* ============ Direct tool execution ============ */

/** Result of a direct tool execution */
export interface ToolExecutionResult {
  tool: string
  success: boolean
  message: string
  deltas: Array<Record<string, unknown>>
  data: Record<string, unknown>
  scene: SceneData
}

/** Execute a tool directly without going through chat */
export async function executeTool(
  toolName: string,
  args: Record<string, unknown>,
  sessionId: string = 'default',
): Promise<ToolExecutionResult> {
  const res = await fetch('/api/tools/execute', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ tool_name: toolName, arguments: args, session_id: sessionId }),
  })
  if (!res.ok) throw new Error(`Tool execution failed: ${res.status}`)
  return res.json() as Promise<ToolExecutionResult>
}

/* ============ Agent-level operations ============ */

/** A single tool call in an agent plan, with an approval flag for destructive tools. */
export interface PlanToolCall {
  id: string
  name: string
  arguments: Record<string, unknown>
  requires_approval?: boolean
}

/** Optional token usage breakdown returned by the orchestrator. */
export interface TokenUsage {
  prompt_tokens?: number
  completion_tokens?: number
  total_tokens?: number
}

/** Result of POST /api/agent/plan — a preview of what the Agent would do. */
export interface AgentPlanResult {
  plan?: unknown
  reasoning?: string
  tool_calls?: PlanToolCall[]
  has_destructive_steps?: boolean
  destructive_steps?: PlanToolCall[]
  offline?: boolean
  token_usage?: TokenUsage
}

/** Preview what the Agent would do for ``message`` without executing any tools. */
export async function fetchAgentPlan(
  message: string,
  sessionId: string = 'default',
  model?: string,
): Promise<AgentPlanResult> {
  const res = await fetch('/api/agent/plan', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, session_id: sessionId, model }),
  })
  if (!res.ok) throw new Error(`Agent plan failed: ${res.status}`)
  return res.json() as Promise<AgentPlanResult>
}

/** Critique findings block returned by POST /api/agent/plan/graph. */
export interface AgentPlanCritique {
  summary: string
  findings: Array<{ kind: string; step_id?: string; tool?: string; target?: string; targets?: string[]; message: string }>
  pruned_step_ids: string[]
}

/** Perception findings block returned by POST /api/agent/plan/graph. */
export interface AgentPlanPerception {
  summary: string
  findings: Array<{ kind: string; severity?: string; message: string }>
  metrics: Record<string, unknown>
}

/** Result of POST /api/agent/plan/graph — plan preview + DAG + critique + perception. */
export interface AgentPlanGraphResult extends AgentPlanResult {
  /** Plan dependency DAG (``{nodes, edges, layers}``) for node-graph rendering. */
  graph?: import('../types').PlanGraphPayload
  /** Pre-execution critique findings (advisory). */
  critique?: AgentPlanCritique | null
  /** Heuristic scene-perception findings, or null for non-3D plans. */
  perception?: AgentPlanPerception | null
}

/** Preview the plan + dependency DAG + critique + perception for ``message``
 *  without executing any tools. Mirrors fetchAgentPlan with extra fields. */
export async function fetchAgentPlanGraph(
  message: string,
  sessionId: string = 'default',
  model?: string,
): Promise<AgentPlanGraphResult> {
  const res = await fetch('/api/agent/plan/graph', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, session_id: sessionId, model }),
  })
  if (!res.ok) throw new Error(`Agent plan/graph failed: ${res.status}`)
  return res.json() as Promise<AgentPlanGraphResult>
}

/** Tool / skill documentation returned by POST /api/agent/explain. */
export interface ExplainResult {
  kind: 'tool' | 'skill'
  name: string
  description: string
  parameters: Record<string, unknown>
  category?: string
  requires_approval?: boolean
}

/** Fetch inline documentation for a tool or skill. */
export async function explainAgentItem(kind: 'tool' | 'skill', name: string): Promise<ExplainResult> {
  const res = await fetch('/api/agent/explain', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ kind, name }),
  })
  if (!res.ok) throw new Error(`Explain failed: ${res.status}`)
  return res.json() as Promise<ExplainResult>
}

/** Uploaded image descriptor returned by POST /api/agent/upload/image. */
export interface UploadedImage {
  media_id: string
  filename: string
  mime_type: string
  size: number
  data_url: string
  path: string
}

/** Upload an image to the workspace and return a data URL the chat can preview. */
export async function uploadChatImage(file: File): Promise<UploadedImage> {
  const fd = new FormData()
  fd.append('file', file)
  const res = await fetch('/api/agent/upload/image', { method: 'POST', body: fd })
  if (!res.ok) throw new Error(`Image upload failed: ${res.status}`)
  return res.json() as Promise<UploadedImage>
}

/* ============ Agent memory (pinned facts) ============ */

/** A single pinned fact the Agent remembers across sessions. */
export interface PinnedFact {
  text: string
  category: string
  pinned_at: number
}

/** Response payload from GET /api/agent/memory. */
export interface AgentMemoryResponse {
  preferences: Record<string, Record<string, number>>
  patterns: Record<string, unknown>
  pinned_facts: PinnedFact[]
  last_updated: number
  summary: {
    total_facts: number
    categories: string[]
    pattern_count: number
  }
}

/** Fetch the Agent's explicit memory (pinned facts + preferences summary). */
export async function fetchAgentMemory(): Promise<AgentMemoryResponse> {
  const res = await fetch('/api/agent/memory')
  if (!res.ok) throw new Error(`Failed to fetch agent memory: ${res.status}`)
  return res.json() as Promise<AgentMemoryResponse>
}

/** Pin a durable fact. Returns the new fact plus the total fact count. */
export async function pinAgentFact(
  text: string,
  category?: string,
): Promise<{ fact: PinnedFact; total_facts: number }> {
  const res = await fetch('/api/agent/memory/pin', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text, category }),
  })
  if (!res.ok) throw new Error(`Failed to pin fact: ${res.status}`)
  return res.json()
}

/** Remove a pinned fact by text, or clear a whole category. */
export async function forgetAgentFact(body: {
  text?: string
  category?: string
}): Promise<{ removed: number | boolean; remaining?: number; text?: string; category?: string | null }> {
  const res = await fetch('/api/agent/memory', {
    method: 'DELETE',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(`Failed to forget fact: ${res.status}`)
  return res.json()
}

/** Supported scene-to-code export formats */
export type ExportCodeFormat = 'three_js' | 'react_r3f' | 'html'

/** Result returned by the /api/export/code endpoint */
export interface ExportCodeResult {
  tool: 'export_code'
  success: boolean
  message: string
  data: {
    format: ExportCodeFormat
    filename: string
    path: string
    code: string
    lines: number
    size_kb: number
  }
}

/** Export the current session scene as ready-to-run source code */
export async function exportSceneCode(
  format: ExportCodeFormat,
  sessionId: string = 'default',
  options: { filename?: string; includeAnimation?: boolean } = {},
): Promise<ExportCodeResult> {
  const body: Record<string, unknown> = { format, session_id: sessionId }
  if (options.filename) body.filename = options.filename
  if (options.includeAnimation !== undefined) body.include_animation = options.includeAnimation
  const res = await fetch('/api/export/code', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(`Code export failed: ${res.status}`)
  return res.json() as Promise<ExportCodeResult>
}

/* ============ Pipeline templates ============ */

/** A pre-built pipeline template */
export interface PipelineTemplate {
  id: string
  name: string
  description: string
  nodes: Array<Record<string, unknown>>
}

/** Fetch pre-built pipeline templates */
export async function fetchPipelineTemplates(): Promise<PipelineTemplate[]> {
  const res = await fetch('/api/models/pipeline/templates')
  if (!res.ok) throw new Error(`Failed to fetch pipeline templates: ${res.status}`)
  const data = await res.json() as { templates: PipelineTemplate[]; count: number }
  return data.templates
}

/** Fetch the registered pipeline node types and their I/O port schemas.
 *  Drives the node palette and connection-type validation in the
 *  node graph editor. */
export async function fetchPipelineNodeTypes(): Promise<PipelineNodeTypesResponse> {
  const res = await fetch('/api/models/pipeline/node_types')
  if (!res.ok) throw new Error(`Failed to fetch pipeline node types: ${res.status}`)
  return res.json() as Promise<PipelineNodeTypesResponse>
}

/** Execute a pipeline */
export async function runPipeline(
  name: string,
  nodes: Array<Record<string, unknown>>,
): Promise<{
  name: string
  node_count: number
  results: Array<{
    node_id: string
    status: string
    outputs: Record<string, unknown>
    error: string
    elapsed_ms: number
  }>
}> {
  const res = await fetch('/api/models/pipeline', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, nodes }),
  })
  if (!res.ok) throw new Error(`Pipeline execution failed: ${res.status}`)
  return res.json()
}

/** A single event from the pipeline SSE stream */
export interface PipelineStreamEvent {
  event: 'start' | 'result' | 'done'
  node_id?: string
  node_type?: string
  status?: string
  outputs?: Record<string, unknown>
  error?: string
  elapsed_ms?: number
  index?: number
  total?: number
  name?: string
  total_elapsed_ms?: number
  node_count?: number
  succeeded?: number
  failed?: number
}

/** Execute a pipeline and stream node-by-node progress via SSE */
export async function* runPipelineStream(
  name: string,
  nodes: Array<Record<string, unknown>>,
): AsyncGenerator<PipelineStreamEvent> {
  const res = await fetch('/api/models/pipeline/sse', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, nodes }),
  })
  if (!res.ok || !res.body) throw new Error(`Pipeline SSE failed: ${res.status}`)

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() ?? ''
    for (const line of lines) {
      const trimmed = line.trim()
      if (!trimmed.startsWith('data: ')) continue
      try {
        const data = JSON.parse(trimmed.slice(6)) as PipelineStreamEvent
        yield data
      } catch {
        // Skip malformed lines
      }
    }
  }
}

/* ============ Scene checkpoints (version history) ============ */

/** Fetch the scene's checkpoint history, newest-first. */
export async function fetchCheckpoints(limit?: number): Promise<CheckpointListResponse> {
  const qs = limit !== undefined && limit >= 0 ? `?limit=${limit}` : ''
  const res = await fetch(`/api/agent/checkpoints${qs}`)
  if (!res.ok) throw new Error(`Failed to fetch checkpoints: ${res.status}`)
  return res.json() as Promise<CheckpointListResponse>
}

/** Capture the current scene as a new immutable revision. */
export async function createCheckpoint(
  description: string,
  sessionId: string = 'default',
): Promise<{ revision: number; description: string; summary: CheckpointEntry['summary']; total: number }> {
  const res = await fetch('/api/agent/checkpoints', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ description, session_id: sessionId }),
  })
  if (!res.ok) throw new Error(`Failed to create checkpoint: ${res.status}`)
  return res.json()
}

/** Restore the live scene to a checkpoint revision. Returns the restored scene. */
export async function restoreCheckpoint(
  revision: number,
  sessionId: string = 'default',
): Promise<{ revision: number; description: string; summary: CheckpointEntry['summary']; scene: SceneData }> {
  const res = await fetch(`/api/agent/checkpoints/${revision}/restore?session_id=${encodeURIComponent(sessionId)}`, {
    method: 'POST',
  })
  if (!res.ok) throw new Error(`Failed to restore checkpoint: ${res.status}`)
  return res.json()
}

/** Diff two checkpoint revisions. */
export async function diffCheckpoints(
  revisionA: number,
  revisionB: number,
): Promise<CheckpointDiff> {
  const res = await fetch(`/api/agent/checkpoints/diff?revision_a=${revisionA}&revision_b=${revisionB}`)
  if (!res.ok) throw new Error(`Failed to diff checkpoints: ${res.status}`)
  return res.json() as Promise<CheckpointDiff>
}

/* ============ Cinematic storyboard ============ */

/** A raw (un-normalized) shot payload accepted by the compose endpoint. */
export interface StoryboardShotInput {
  name?: string
  position?: [number, number, number]
  target?: [number, number, number]
  fov?: number
  duration?: number
  easing?: string
  description?: string
}

/** Fetch the scene's cinematic storyboard. */
export async function fetchStoryboard(sessionId: string = 'default'): Promise<StoryboardResponse> {
  const res = await fetch(`/api/agent/story?session_id=${encodeURIComponent(sessionId)}`)
  if (!res.ok) throw new Error(`Failed to fetch storyboard: ${res.status}`)
  return res.json() as Promise<StoryboardResponse>
}

/** Compose or replace the scene's cinematic storyboard. Returns the full
 *  scene snapshot so the caller can swap it into the editor. */
export async function composeStoryboard(
  title: string,
  shots: StoryboardShotInput[],
  opts: { sessionId?: string; loop?: boolean } = {},
): Promise<StoryboardResponse> {
  const res = await fetch('/api/agent/story', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      session_id: opts.sessionId ?? 'default',
      title,
      shots,
      loop: opts.loop ?? true,
    }),
  })
  if (!res.ok) throw new Error(`Failed to compose storyboard: ${res.status}`)
  return res.json() as Promise<StoryboardResponse>
}

/** Remove the scene's cinematic storyboard. */
export async function clearStoryboard(sessionId: string = 'default'): Promise<StoryboardResponse> {
  const res = await fetch(`/api/agent/story?session_id=${encodeURIComponent(sessionId)}`, {
    method: 'DELETE',
  })
  if (!res.ok) throw new Error(`Failed to clear storyboard: ${res.status}`)
  return res.json() as Promise<StoryboardResponse>
}

/** Control storyboard playback (play / pause / stop). */
export async function controlStoryboard(
  mode: 'play' | 'pause' | 'stop',
  opts: { sessionId?: string; speed?: number; index?: number } = {},
): Promise<StoryboardResponse> {
  const res = await fetch('/api/agent/story/play', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      session_id: opts.sessionId ?? 'default',
      mode,
      speed: opts.speed,
      index: opts.index,
    }),
  })
  if (!res.ok) throw new Error(`Failed to control storyboard: ${res.status}`)
  return res.json() as Promise<StoryboardResponse>
}

/* ============ Scene critique + auto-fix (direct execution) ============ */

/** Run the prescriptive design review (critique_scene) directly against the
 *  session's scene via POST /api/agent/run. Read-only: never mutates the
 *  scene. Returns the verdict + ranked findings, each carrying a concrete
 *  proposed corrective tool call. */
export async function critiqueScene(
  sessionId: string = 'default',
  opts: { maxFindings?: number; focus?: string[] } = {},
): Promise<AgentRunResponse<CritiqueData>> {
  const args: Record<string, unknown> = {}
  if (opts.maxFindings !== undefined) args.max_findings = opts.maxFindings
  if (opts.focus !== undefined) args.focus = opts.focus
  const res = await fetch('/api/agent/run', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name: 'critique_scene', session_id: sessionId, arguments: args }),
  })
  if (!res.ok) throw new Error(`Critique failed: ${res.status}`)
  return res.json() as Promise<AgentRunResponse<CritiqueData>>
}

/** Run the self-healing auto-fix (auto_fix_scene) directly against the
 *  session's scene via POST /api/agent/run. Mutates the scene by applying
 *  the highest-severity proposed fixes in severity order, then returns a
 *  before/after report (applied / skipped / remaining). The updated scene
 *  snapshot is in the response so the caller can swap it in. */
export async function autoFixScene(
  sessionId: string = 'default',
  opts: { maxFixes?: number; focus?: string[] } = {},
): Promise<AgentRunResponse<AutoFixData>> {
  const args: Record<string, unknown> = {}
  if (opts.maxFixes !== undefined) args.max_fixes = opts.maxFixes
  if (opts.focus !== undefined) args.focus = opts.focus
  const res = await fetch('/api/agent/run', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name: 'auto_fix_scene', session_id: sessionId, arguments: args }),
  })
  if (!res.ok) throw new Error(`Auto-fix failed: ${res.status}`)
  return res.json() as Promise<AgentRunResponse<AutoFixData>>
}

/** Apply a single proposed corrective tool call (e.g. one finding's
 *  `proposed_fix.tool` + `proposed_fix.arguments`) directly against the
 *  session's scene via POST /api/agent/run. Used by the CritiquePanel's
 *  per-finding "Apply fix" button. */
export async function applyProposedFix(
  tool: string,
  args: Record<string, unknown>,
  sessionId: string = 'default',
): Promise<AgentRunResponse> {
  const res = await fetch('/api/agent/run', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name: tool, session_id: sessionId, arguments: args }),
  })
  if (!res.ok) throw new Error(`Apply fix (${tool}) failed: ${res.status}`)
  return res.json() as Promise<AgentRunResponse>
}

/* ============ Constraint authoring + goal-driven refinement ============ */

/** Arguments for add_constraint. Only `kind` and `subject` are required;
 *  the rest are kind-dependent. */
export interface AddConstraintArgs {
  kind: ConstraintKind
  subject: string
  anchor?: string
  target_point?: number[]
  axis?: 'x' | 'y' | 'z'
  distance?: number
  offset?: number
  tolerance?: number
  description?: string
}

/** Register a single spatial constraint on the current scene. Does not move
 *  objects — call solveConstraints to enforce. Returns the new constraint. */
export async function addConstraint(
  args: AddConstraintArgs,
  sessionId: string = 'default',
): Promise<AgentRunResponse<AddConstraintData>> {
  const res = await fetch('/api/agent/run', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name: 'add_constraint', session_id: sessionId, arguments: args }),
  })
  if (!res.ok) throw new Error(`Add constraint failed: ${res.status}`)
  return res.json() as Promise<AgentRunResponse<AddConstraintData>>
}

/** List every constraint attached to the scene with current pass/fail.
 *  Read-only. */
export async function listConstraints(
  sessionId: string = 'default',
): Promise<AgentRunResponse<ListConstraintsData>> {
  const res = await fetch('/api/agent/run', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name: 'list_constraints', session_id: sessionId, arguments: {} }),
  })
  if (!res.ok) throw new Error(`List constraints failed: ${res.status}`)
  return res.json() as Promise<AgentRunResponse<ListConstraintsData>>
}

/** Remove every constraint from the scene. Does not revert transforms. */
export async function clearConstraints(
  sessionId: string = 'default',
): Promise<AgentRunResponse<ClearConstraintsData>> {
  const res = await fetch('/api/agent/run', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name: 'clear_constraints', session_id: sessionId, arguments: {} }),
  })
  if (!res.ok) throw new Error(`Clear constraints failed: ${res.status}`)
  return res.json() as Promise<AgentRunResponse<ClearConstraintsData>>
}

/** Run the greedy iterative solver: mutates object transforms to satisfy
 *  the registered constraints, emits update deltas, and returns a report
 *  of what moved and what is still violated. */
export async function solveConstraints(
  sessionId: string = 'default',
  opts: { maxPasses?: number } = {},
): Promise<AgentRunResponse<SolveConstraintsData>> {
  const args: Record<string, unknown> = {}
  if (opts.maxPasses !== undefined) args.max_passes = opts.maxPasses
  const res = await fetch('/api/agent/run', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name: 'solve_constraints', session_id: sessionId, arguments: args }),
  })
  if (!res.ok) throw new Error(`Solve constraints failed: ${res.status}`)
  return res.json() as Promise<AgentRunResponse<SolveConstraintsData>>
}

/** Iteratively refine the scene toward a stated goal via a bounded
 *  critique + auto-fix loop. Returns a per-iteration trace. */
export async function refineScene(
  sessionId: string = 'default',
  opts: { goal?: string; maxIterations?: number; maxFixesPerIter?: number } = {},
): Promise<AgentRunResponse<RefineData>> {
  const args: Record<string, unknown> = {}
  if (opts.goal !== undefined) args.goal = opts.goal
  if (opts.maxIterations !== undefined) args.max_iterations = opts.maxIterations
  if (opts.maxFixesPerIter !== undefined) args.max_fixes_per_iter = opts.maxFixesPerIter
  const res = await fetch('/api/agent/run', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name: 'refine_scene', session_id: sessionId, arguments: args }),
  })
  if (!res.ok) throw new Error(`Refine scene failed: ${res.status}`)
  return res.json() as Promise<AgentRunResponse<RefineData>>
}

/* ============ WebSocket client ============ */

export type SocketStatus =
  | 'idle'
  | 'connecting'
  | 'connected'
  | 'disconnected'
  | 'error'

export interface ChatSocketHandlers {
  onOpen?: () => void
  onClose?: (ev: CloseEvent) => void
  onError?: (ev: Event) => void
  onEvent?: (ev: ServerEvent) => void
}

/** Derive WebSocket URL from window.location (forwarded by Vite proxy during development) */
function buildWsUrl(): string {
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${proto}//${window.location.host}/api/chat/ws`
}

/**
 * Lightweight WebSocket client wrapper:
 * - Auto reconnect (exponential backoff, up to 5 attempts)
 * - Sends only when active; caches the latest message when not connected and resends after connection
 * - Parses server JSON events and invokes callbacks
 */
export class ChatSocket {
  private url: string
  private ws: WebSocket | null = null
  private handlers: ChatSocketHandlers
  private reconnectAttempts = 0
  private maxReconnect = 5
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null
  private pending: ClientMessage | null = null
  private shouldReconnect = true
  status: SocketStatus = 'idle'

  constructor(handlers: ChatSocketHandlers = {}) {
    this.handlers = handlers
    this.url = buildWsUrl()
  }

  connect() {
    if (this.ws && (this.status === 'connected' || this.status === 'connecting')) {
      return
    }
    this.shouldReconnect = true
    this.setStatus('connecting')
    try {
      this.ws = new WebSocket(this.url)
    } catch (e) {
      this.setStatus('error')
      this.handlers.onError?.(e as Event)
      this.scheduleReconnect()
      return
    }

    this.ws.onopen = () => {
      this.reconnectAttempts = 0
      this.setStatus('connected')
      this.handlers.onOpen?.()
      // Resend cached message after successful connection
      if (this.pending) {
        this.rawSend(this.pending)
        this.pending = null
      }
    }

    this.ws.onmessage = (ev) => {
      this.handleMessage(ev.data)
    }

    this.ws.onerror = (ev) => {
      this.setStatus('error')
      this.handlers.onError?.(ev)
    }

    this.ws.onclose = (ev) => {
      this.setStatus('disconnected')
      this.handlers.onClose?.(ev)
      if (this.shouldReconnect) this.scheduleReconnect()
    }
  }

  disconnect() {
    this.shouldReconnect = false
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }
    if (this.ws) {
      this.ws.onclose = null
      this.ws.onerror = null
      this.ws.onopen = null
      this.ws.onmessage = null
      try {
        this.ws.close()
      } catch {
        /* ignore */
      }
      this.ws = null
    }
    this.setStatus('disconnected')
  }

  /** Send a message; cache it and trigger connection when not connected */
  send(message: ClientMessage) {
    if (this.status === 'connected' && this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.rawSend(message)
    } else {
      // Cache the latest message and resend after connection
      this.pending = message
      if (this.status !== 'connecting') this.connect()
    }
  }

  private rawSend(message: ClientMessage) {
    if (!this.ws) return
    this.ws.send(JSON.stringify(message))
  }

  private handleMessage(raw: unknown) {
    if (typeof raw !== 'string') return
    let parsed: ServerEvent
    try {
      parsed = JSON.parse(raw) as ServerEvent
    } catch {
      return
    }
    if (!parsed || typeof parsed.type !== 'string') return
    this.handlers.onEvent?.(parsed)
  }

  private scheduleReconnect() {
    if (this.reconnectAttempts >= this.maxReconnect) return
    const delay = Math.min(1000 * 2 ** this.reconnectAttempts, 8000)
    this.reconnectAttempts += 1
    this.reconnectTimer = setTimeout(() => {
      if (this.shouldReconnect) this.connect()
    }, delay)
  }

  private setStatus(s: SocketStatus) {
    this.status = s
  }
}

/** Generate or read a locally persisted session id */
export function getOrCreateSessionId(): string {
  const KEY = 'trigen_session_id'
  let id = localStorage.getItem(KEY)
  if (!id) {
    id = `sess_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 10)}`
    localStorage.setItem(KEY, id)
  }
  return id
}
