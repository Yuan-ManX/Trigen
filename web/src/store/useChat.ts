// 对话状态管理：消息列表、流式渲染、WebSocket 连接
// Chat state management: message list, streaming rendering, WebSocket connection
import { create } from 'zustand'
import {
  ChatSocket,
  getOrCreateSessionId,
  type SocketStatus,
} from '../api/client'
import type { ServerEvent } from '../types'
import { useScene } from './useScene'

/** 工具调用记录（内联在助手消息中） */
/** Tool call record (inlined within an assistant message) */
export interface ToolCallRecord {
  id: string
  name: string
  arguments: Record<string, unknown>
  pending: boolean
  result?: { success: boolean; message: string }
}

/** 对话消息 */
/** Chat message */
export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  streaming?: boolean
  error?: string
  toolCalls?: ToolCallRecord[]
}

interface ChatState {
  messages: ChatMessage[]
  status: SocketStatus
  sessionId: string
  isResponding: boolean

  connect: () => void
  disconnect: () => void
  send: (text: string) => void
  clearMessages: () => void
}

/** 模块级单例 socket，由 store 持有 */
/** Module-level singleton socket, owned by the store */
let socket: ChatSocket | null = null

function genId(): string {
  return `m_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 7)}`
}

/** 创建并绑定 socket 事件处理 */
/** Create and bind socket event handlers */
function ensureSocket(handlers: {
  onStatus: (s: SocketStatus) => void
  onEvent: (ev: ServerEvent) => void
}): ChatSocket {
  if (socket) return socket
  socket = new ChatSocket({
    onOpen: () => handlers.onStatus('connected'),
    onClose: () => handlers.onStatus('disconnected'),
    onError: () => handlers.onStatus('error'),
    onEvent: (ev) => handlers.onEvent(ev),
  })
  return socket
}

export const useChat = create<ChatState>((set, get) => {
  // 状态变更回调
  // Status change callback
  const onStatus = (s: SocketStatus) => set({ status: s })

  // 服务端事件分发
  // Server event dispatch
  const onEvent = (ev: ServerEvent) => {
    switch (ev.type) {
      case 'text_delta': {
        // 追加到最近一条流式助手消息；若不存在则创建
        // Append to the latest streaming assistant message; create one if none exists
        set((state) => {
          const msgs = [...state.messages]
          for (let i = msgs.length - 1; i >= 0; i--) {
            if (msgs[i].role === 'assistant' && msgs[i].streaming) {
              msgs[i] = {
                ...msgs[i],
                content: msgs[i].content + ev.data.content,
              }
              return { messages: msgs }
            }
          }
          // 没有流式消息则新建一条
          // No streaming message, create a new one
          msgs.push({
            id: genId(),
            role: 'assistant',
            content: ev.data.content,
            streaming: true,
          })
          return { messages: msgs }
        })
        break
      }
      case 'tool_call': {
        const call: ToolCallRecord = {
          id: ev.data.id,
          name: ev.data.name,
          arguments: ev.data.arguments,
          pending: true,
        }
        set((state) => {
          const msgs = [...state.messages]
          // 附加到最近的流式助手消息
          // Attach to the latest streaming assistant message
          for (let i = msgs.length - 1; i >= 0; i--) {
            if (msgs[i].role === 'assistant' && msgs[i].streaming) {
              msgs[i] = {
                ...msgs[i],
                toolCalls: [...(msgs[i].toolCalls ?? []), call],
              }
              return { messages: msgs }
            }
          }
          // 没有流式消息则新建一条承载工具调用
          // No streaming message, create a new one to carry the tool call
          msgs.push({
            id: genId(),
            role: 'assistant',
            content: '',
            streaming: true,
            toolCalls: [call],
          })
          return { messages: msgs }
        })
        break
      }
      case 'tool_result': {
        set((state) => {
          const msgs = [...state.messages]
          // tool_result 不携带工具 id，匹配最近一条仍 pending 的工具调用
          // tool_result does not carry a tool id, match the latest still-pending tool call
          for (let i = msgs.length - 1; i >= 0; i--) {
            const m = msgs[i]
            if (m.role !== 'assistant' || !m.toolCalls) continue
            const idx = m.toolCalls.findIndex((c) => c.pending)
            if (idx >= 0) {
              const newCalls = [...m.toolCalls]
              newCalls[idx] = {
                ...newCalls[idx],
                pending: false,
                result: {
                  success: ev.data.success,
                  message: ev.data.message,
                },
              }
              msgs[i] = { ...m, toolCalls: newCalls }
              return { messages: msgs }
            }
          }
          return { messages: msgs }
        })
        break
      }
      case 'scene_update': {
        if (ev.data.scene) {
          useScene.getState().applyScene(ev.data.scene)
        }
        break
      }
      case 'done': {
        // 完成最近一条流式助手消息
        // Finalize the latest streaming assistant message
        set((state) => {
          const msgs = [...state.messages]
          for (let i = msgs.length - 1; i >= 0; i--) {
            if (msgs[i].role === 'assistant' && msgs[i].streaming) {
              msgs[i] = {
                ...msgs[i],
                streaming: false,
                content: ev.data.content || msgs[i].content,
              }
              break
            }
          }
          return { messages: msgs, isResponding: false }
        })
        if (ev.data.scene) {
          useScene.getState().applyScene(ev.data.scene)
        }
        break
      }
      case 'error': {
        set((state) => {
          const msgs = [...state.messages]
          // 将错误挂到最近一条流式助手消息，否则新建一条
          // Attach the error to the latest streaming assistant message, otherwise create a new one
          let attached = false
          for (let i = msgs.length - 1; i >= 0; i--) {
            if (msgs[i].role === 'assistant' && msgs[i].streaming) {
              msgs[i] = {
                ...msgs[i],
                streaming: false,
                error: ev.data.message,
              }
              attached = true
              break
            }
          }
          if (!attached) {
            msgs.push({
              id: genId(),
              role: 'assistant',
              content: '',
              streaming: false,
              error: ev.data.message,
            })
          }
          return { messages: msgs, isResponding: false }
        })
        break
      }
      default:
        break
    }
  }

  return {
    messages: [],
    status: 'idle',
    sessionId: getOrCreateSessionId(),
    isResponding: false,

    connect: () => {
      const s = ensureSocket({ onStatus, onEvent })
      if (s.status !== 'connected' && s.status !== 'connecting') {
        s.connect()
      }
      set({ status: s.status })
    },

    disconnect: () => {
      socket?.disconnect()
      set({ status: 'disconnected' })
    },

    send: (text) => {
      const trimmed = text.trim()
      if (!trimmed) return
      const sessionId = get().sessionId

      // 先建立连接（若未连接）
      // Establish connection first (if not connected)
      const s = ensureSocket({ onStatus, onEvent })
      if (s.status !== 'connected') {
        s.connect()
      }

      // 推送用户消息 + 预占一条流式助手消息
      // Push the user message + reserve a streaming assistant message
      set((state) => ({
        messages: [
          ...state.messages,
          { id: genId(), role: 'user', content: trimmed },
          {
            id: genId(),
            role: 'assistant',
            content: '',
            streaming: true,
            toolCalls: [],
          },
        ],
        isResponding: true,
      }))

      s.send({ type: 'message', data: { message: trimmed, session_id: sessionId } })
    },

    clearMessages: () => set({ messages: [] }),
  }
})
