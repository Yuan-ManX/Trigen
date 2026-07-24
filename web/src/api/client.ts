// REST + WebSocket 客户端
// REST + WebSocket client
// 开发环境下通过 Vite proxy 代理到后端 http://localhost:7100
// In development, proxied to backend http://localhost:7100 via Vite proxy

import type {
  ClientMessage,
  HealthResponse,
  SceneData,
  ServerEvent,
} from '../types'

/* ===================== REST 接口 ===================== */
/* ============ REST API ============ */

/** 健康检查 */
/** Health check */
export async function fetchHealth(): Promise<HealthResponse> {
  const res = await fetch('/api/health')
  if (!res.ok) throw new Error(`健康检查失败: ${res.status}`)
  return res.json() as Promise<HealthResponse>
}

/** 获取完整场景 */
/** Fetch the complete scene */
export async function fetchScene(sessionId: string): Promise<SceneData> {
  const res = await fetch(`/api/scene/${encodeURIComponent(sessionId)}`)
  if (!res.ok) throw new Error(`获取场景失败: ${res.status}`)
  return res.json() as Promise<SceneData>
}

/** 重置场景 */
/** Reset scene */
export async function resetScene(sessionId: string): Promise<SceneData> {
  const res = await fetch(`/api/scene/${encodeURIComponent(sessionId)}/reset`, {
    method: 'POST',
  })
  if (!res.ok) throw new Error(`重置场景失败: ${res.status}`)
  return res.json() as Promise<SceneData>
}

/** 构造导出文件下载 URL */
/** Build the export file download URL */
export function exportUrl(filename: string): string {
  return `/api/exports/${encodeURIComponent(filename)}`
}

/* ===================== WebSocket 客户端 ===================== */
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

/** 根据 window.location 推导 WebSocket 地址（开发期由 Vite 代理转发） */
/** Derive WebSocket URL from window.location (forwarded by Vite proxy during development) */
function buildWsUrl(): string {
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${proto}//${window.location.host}/api/chat/ws`
}

/**
 * 轻量 WebSocket 客户端封装：
 * - 自动重连（指数退避，最多 5 次）
 * - 只在 active 时发送，未连接时缓存最近一条消息并在连接后补发
 * - 解析服务端 JSON 事件并回调
 *
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
      // 连接成功后补发缓存消息
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
        /* ignore / 忽略 */
      }
      this.ws = null
    }
    this.setStatus('disconnected')
  }

  /** 发送消息；未连接时缓存并触发连接 */
  /** Send a message; cache it and trigger connection when not connected */
  send(message: ClientMessage) {
    if (this.status === 'connected' && this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.rawSend(message)
    } else {
      // 缓存最近一条，连接后补发
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

/** 生成或读取本地持久化的 session id */
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
