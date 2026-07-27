// Chat state management: message list, streaming rendering, WebSocket connection
// Includes conversation history persistence via localStorage
import { create } from 'zustand'
import {
  ChatSocket,
  getOrCreateSessionId,
  type SocketStatus,
} from '../api/client'
import type { SceneData, ServerEvent } from '../types'
import { useScene } from './useScene'

/** Tool call record (inlined within an assistant message) */
export interface ToolCallRecord {
  id: string
  name: string
  arguments: Record<string, unknown>
  pending: boolean
  result?: { success: boolean; message: string }
}

/** Agent reasoning trace entry */
export interface ThinkingTrace {
  phase: string
  content: string
  tools?: string[]
  scene_summary?: string
  elapsed?: number
  iterations?: number
}

/** Chat message */
export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  streaming?: boolean
  error?: string
  toolCalls?: ToolCallRecord[]
  thinking?: ThinkingTrace[]
}

/** A saved conversation in history */
export interface Conversation {
  id: string
  title: string
  messages: ChatMessage[]
  sessionId: string
  createdAt: number
  updatedAt: number
  pinned?: boolean
}

const HISTORY_KEY = 'trigen_chat_history'
const MAX_CONVERSATIONS = 30

interface ChatState {
  messages: ChatMessage[]
  status: SocketStatus
  sessionId: string
  isResponding: boolean
  model: string
  conversations: Conversation[]
  activeConversationId: string | null
  showHistory: boolean

  connect: () => void
  disconnect: () => void
  send: (text: string) => void
  setModel: (model: string) => void
  clearMessages: () => void
  toggleHistory: () => void
  setHistoryVisible: (visible: boolean) => void
  startNewConversation: () => void
  saveCurrentConversation: () => void
  loadConversation: (id: string) => void
  deleteConversation: (id: string) => void
  togglePin: (id: string) => void
  renameConversation: (id: string, title: string) => void
}

/** Module-level singleton socket, owned by the store */
let socket: ChatSocket | null = null

/** Snapshot of the scene captured when the user sends a message, used for undo history */
let sceneBeforeResponse: SceneData | null = null

function genId(): string {
  return `m_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 7)}`
}

function genConversationId(): string {
  return `c_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 7)}`
}

/** Load conversation history from localStorage */
function loadHistory(): Conversation[] {
  try {
    const raw = localStorage.getItem(HISTORY_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed
  } catch {
    return []
  }
}

/** Save conversation history to localStorage */
function persistHistory(conversations: Conversation[]): void {
  try {
    // Only persist non-streaming messages
    const clean = conversations.map((c) => ({
      ...c,
      messages: c.messages.filter((m) => !m.streaming && !m.error),
    }))
    localStorage.setItem(HISTORY_KEY, JSON.stringify(clean))
  } catch {
    // Ignore quota errors
  }
}

/** Generate a title from the first user message */
function titleFromMessages(messages: ChatMessage[]): string {
  const first = messages.find((m) => m.role === 'user')
  if (!first) return 'New Conversation'
  const text = first.content.trim()
  return text.length > 40 ? text.slice(0, 40) + '…' : text
}

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
  // Status change callback
  const onStatus = (s: SocketStatus) => set({ status: s })

  // Server event dispatch
  const onEvent = (ev: ServerEvent) => {
    switch (ev.type) {
      case 'thinking': {
        // Append the reasoning trace to the latest streaming assistant message
        const trace: ThinkingTrace = {
          phase: ev.data.phase,
          content: ev.data.content,
          tools: ev.data.tools,
          scene_summary: ev.data.scene_summary,
          elapsed: ev.data.elapsed,
          iterations: ev.data.iterations,
        }
        set((state) => {
          const msgs = [...state.messages]
          for (let i = msgs.length - 1; i >= 0; i--) {
            if (msgs[i].role === 'assistant' && msgs[i].streaming) {
              msgs[i] = {
                ...msgs[i],
                thinking: [...(msgs[i].thinking ?? []), trace],
              }
              return { messages: msgs }
            }
          }
          // No streaming message, create a new one to carry the thinking trace
          msgs.push({
            id: genId(),
            role: 'assistant',
            content: '',
            streaming: true,
            thinking: [trace],
          })
          return { messages: msgs }
        })
        break
      }
      case 'text_delta': {
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
        // Intermediate scene updates during Agent execution: replace without
        // recording history so that a single user action = a single undo step.
        // The final history entry is committed on the `done` event below.
        if (ev.data.scene) {
          useScene.getState().replaceScene(ev.data.scene)
        }
        break
      }
      case 'done': {
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
        // Commit the final scene with the before-response snapshot for undo history
        if (ev.data.scene) {
          const before = sceneBeforeResponse
          if (before) {
            useScene.getState().commitScene(ev.data.scene, before)
          } else {
            useScene.getState().applyScene(ev.data.scene)
          }
          sceneBeforeResponse = null
        }
        // Auto-save the conversation after a complete response
        setTimeout(() => get().saveCurrentConversation(), 100)
        break
      }
      case 'error': {
        set((state) => {
          const msgs = [...state.messages]
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
    model: 'trigen-default',
    isResponding: false,
    conversations: loadHistory(),
    activeConversationId: null,
    showHistory: false,

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

      // Establish connection first (if not connected)
      const s = ensureSocket({ onStatus, onEvent })
      if (s.status !== 'connected') {
        s.connect()
      }

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

      // Capture the scene snapshot before the Agent responds, for undo history
      sceneBeforeResponse = JSON.parse(JSON.stringify(useScene.getState().scene))

      s.send({ type: 'message', data: { message: trimmed, session_id: sessionId, model: get().model } })
    },

    setModel: (model) => set({ model }),

    clearMessages: () => {
      get().saveCurrentConversation()
      set({ messages: [], activeConversationId: null })
    },

    toggleHistory: () => set((state) => ({ showHistory: !state.showHistory })),

    setHistoryVisible: (visible) => set({ showHistory: visible }),

    startNewConversation: () => {
      // Save the current conversation if it has messages
      get().saveCurrentConversation()
      set({
        messages: [],
        activeConversationId: null,
        showHistory: false,
        sessionId: getOrCreateSessionId(),
      })
    },

    saveCurrentConversation: () => {
      const state = get()
      const msgs = state.messages.filter((m) => !m.streaming)
      if (msgs.length === 0) return

      const now = Date.now()
      const title = titleFromMessages(msgs)

      if (state.activeConversationId) {
        // Update existing conversation
        const updated = state.conversations.map((c) =>
          c.id === state.activeConversationId
            ? { ...c, title, messages: msgs, updatedAt: now }
            : c,
        )
        const sorted = [...updated].sort((a, b) => b.updatedAt - a.updatedAt)
        set({ conversations: sorted })
        persistHistory(sorted)
      } else {
        // Create a new conversation
        const conv: Conversation = {
          id: genConversationId(),
          title,
          messages: msgs,
          sessionId: state.sessionId,
          createdAt: now,
          updatedAt: now,
        }
        const next = [conv, ...state.conversations].slice(0, MAX_CONVERSATIONS)
        set({ conversations: next, activeConversationId: conv.id })
        persistHistory(next)
      }
    },

    loadConversation: (id) => {
      const state = get()
      // Save current conversation first
      if (state.messages.length > 0 && !state.activeConversationId) {
        get().saveCurrentConversation()
      }

      const conv = state.conversations.find((c) => c.id === id)
      if (!conv) return

      set({
        messages: conv.messages.map((m) => ({ ...m, streaming: false })),
        activeConversationId: conv.id,
        sessionId: conv.sessionId,
        showHistory: false,
      })
    },

    deleteConversation: (id) => {
      const state = get()
      const next = state.conversations.filter((c) => c.id !== id)
      set({ conversations: next })
      persistHistory(next)

      // If we deleted the active conversation, clear messages
      if (state.activeConversationId === id) {
        set({ messages: [], activeConversationId: null })
      }
    },

    togglePin: (id) => {
      const state = get()
      const next = state.conversations.map((c) =>
        c.id === id ? { ...c, pinned: !c.pinned } : c,
      )
      set({ conversations: next })
      persistHistory(next)
    },

    renameConversation: (id, title) => {
      const state = get()
      const trimmed = title.trim()
      if (!trimmed) return
      const next = state.conversations.map((c) =>
        c.id === id ? { ...c, title: trimmed } : c,
      )
      set({ conversations: next })
      persistHistory(next)
    },
  }
})
