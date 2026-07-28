// REST + WebSocket client
// In development, proxied to backend http://localhost:7100 via Vite proxy

import type {
  ClientMessage,
  HealthResponse,
  PresetsResponse,
  SceneData,
  ServerEvent,
  ToolsResponse,
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

/** Fetch the preset catalog (geometry / material / light) */
export async function fetchPresets(): Promise<PresetsResponse> {
  const res = await fetch('/api/presets')
  if (!res.ok) throw new Error(`Failed to fetch preset list: ${res.status}`)
  return res.json() as Promise<PresetsResponse>
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
