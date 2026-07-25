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
