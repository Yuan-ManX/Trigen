// Chat state management: message list, streaming rendering, WebSocket connection
// Includes conversation history persistence via localStorage
import { create } from 'zustand'
import {
  ChatSocket,
  fetchAgentPlan,
  getOrCreateSessionId,
  type SocketStatus,
  type TokenUsage,
} from '../api/client'
import type { PlanGraphPayload, PlanStep, SceneData, ServerEvent, Vec3 } from '../types'
import { useEditor, type PanelTab, type RenderQuality, type TransformMode } from './useEditor'
import { usePlayback } from './usePlayback'
import { useScene } from './useScene'

/** Tool call record (inlined within an assistant message) */
export interface ToolCallRecord {
  id: string
  name: string
  arguments: Record<string, unknown>
  pending: boolean
  result?: {
    success: boolean
    message: string
    data?: Record<string, unknown>
  }
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
  /** Live execution-plan roadmap (sub-task checklist). Populated by the
   *  `plan` event and updated in place by subsequent `plan_update` events. */
  planSteps?: PlanStep[]
  /** Agent-stated goal for the current turn, surfaced from the `plan`
   *  event's `goal` field and rendered as the PlanTrace headline. */
  planGoal?: string
  /** Mid-turn plan refinements emitted when the agent revises its plan
   *  (alternative-tool proposals after a failure, budget-driven pruning).
   *  Advisory only — the LLM still decides whether to follow the hint. */
  planRefinements?: PlanRefinement[]
  /** Plan dependency DAG emitted by the `plan_graph` event. Optional —
   *  only present when the orchestrator derived at least one edge. The
   *  chat UI may surface a "view graph" affordance when this is set. */
  planGraph?: PlanGraphPayload
  /** Proactive next-action suggestions attached to this assistant message
   *  by the `done` event. Rendered as a compact "Quick Actions" chip strip
   *  below the message body so the user can re-send a suggestion as a new
   *  message with one click. */
  suggestions?: Suggestion[]
}

/** An advisory plan-refinement notice. Rendered as a subtle annotation on
 *  the plan checklist so the user can see the agent considered switching
 *  tools or pruning its toolset mid-turn. */
export interface PlanRefinement {
  reason: 'tool_failure_alternative_suggestion' | 'budget_prune' | string
  iteration?: number
  proposals?: { failed: string; alternative: string }[]
  active_categories?: string[]
  tool_subset_size?: number
  budget_remaining?: number
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

/** A proactive next-action suggestion produced by the Agent after a turn.
 *  Scene-aware: derived from the current scene state on the backend. */
export interface Suggestion {
  name: string
  description: string
  skill_or_tool: string
  arguments: Record<string, unknown>
  rationale: string
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
  /** Proactive next-action suggestions produced by the Agent at the end of
   *  the most recent turn. Cleared when the user sends a new message. */
  suggestions: Suggestion[]
  /** When true, the next send() goes through POST /api/agent/plan first and
   *  surfaces a confirmation modal if any destructive step is detected. */
  confirmDestructive: boolean
  /** True while a /api/agent/plan preview is in-flight for the current send. */
  planning: boolean
  /** Pending destructive turn awaiting user confirmation. The modal is open
   *  whenever this is non-null. */
  pendingDestructive: {
    text: string
    reasoning?: string
    steps: Array<{ name: string; arguments: Record<string, unknown> }>
  } | null
  /** Token usage reported by the most recent DONE event (cumulative per turn). */
  lastTokenUsage: TokenUsage | null

  connect: () => void
  disconnect: () => void
  send: (text: string) => void
  retry: () => void
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
  setConfirmDestructive: (enabled: boolean) => void
  confirmPendingDestructive: () => void
  cancelPendingDestructive: () => void
}

/** Module-level singleton socket, owned by the store */
let socket: ChatSocket | null = null

/** Snapshot of the scene captured when the user sends a message, used for undo history */
let sceneBeforeResponse: SceneData | null = null

/** Whether the current turn produced any scene-mutating delta. When false
 *  (editor-only turns such as undo/redo/play/pause), the ``done`` event's
 *  scene snapshot is skipped so it does not override local frontend state. */
let turnHadSceneMutation = false

/** Dispatch editor-control deltas to the matching local store. These deltas
 *  do not mutate the backend Scene; they request a frontend-side action. */
function dispatchEditorDelta(action: string, targetId: string | undefined, payload: Record<string, unknown>): void {
  const editor = useEditor.getState()
  const playback = usePlayback.getState()
  const scene = useScene.getState()
  switch (action) {
    case 'editor_select': {
      if (targetId) scene.select(targetId, !payload.clear)
      break
    }
    case 'editor_set_selection': {
      const ids = Array.isArray(payload.ids) ? (payload.ids as string[]) : []
      const clear = payload.clear !== false
      if (clear) scene.clearSelection()
      ids.forEach((id) => scene.select(id, true))
      break
    }
    case 'editor_reorder_layer': {
      const ordered = Array.isArray(payload.ordered_ids) ? (payload.ordered_ids as string[]) : []
      if (ordered.length) scene.reorderObjectsById(ordered)
      break
    }
    case 'editor_focus':
    case 'editor_viewport_camera': {
      const pos = (payload.position ?? payload.camera_position) as Vec3 | undefined
      const tgt = (payload.target ?? [0, 0.5, 0]) as Vec3
      if (pos) editor.setViewportCamera(pos, tgt, payload.smooth !== false)
      break
    }
    case 'editor_transform_mode': {
      editor.setTransformMode(payload.mode as TransformMode)
      break
    }
    case 'editor_play': {
      if (payload.from_start) playback.seek(0)
      playback.play()
      break
    }
    case 'editor_pause': {
      playback.pause()
      break
    }
    case 'editor_seek': {
      playback.seek(Number(payload.time ?? 0))
      break
    }
    case 'editor_set_playback_speed': {
      playback.setSpeed(Number(payload.speed ?? 1))
      break
    }
    case 'editor_toggle_grid_snapping': {
      editor.setGridSnap(Boolean(payload.enabled), Number(payload.increment ?? 0.5))
      break
    }
    case 'editor_focus_panel': {
      editor.setActivePanel(payload.panel as PanelTab)
      break
    }
    case 'editor_undo': {
      scene.undo()
      break
    }
    case 'editor_redo': {
      scene.redo()
      break
    }
    case 'editor_capture_viewport': {
      editor.requestCapture(payload.filename as string | undefined)
      break
    }
    case 'editor_set_render_quality': {
      editor.setRenderQuality(payload.quality as RenderQuality)
      break
    }
    case 'editor_set_clipping_plane': {
      editor.setClippingPlane({
        enabled: Boolean(payload.enabled),
        axis: (payload.axis as 'x' | 'y' | 'z') ?? 'y',
        position: Number(payload.position ?? 0),
        invert: Boolean(payload.invert ?? false),
      })
      break
    }
    case 'editor_set_minimap': {
      editor.setMinimapEnabled(Boolean(payload.enabled))
      break
    }
    case 'editor_set_shadows': {
      editor.setShadowsEnabled(Boolean(payload.enabled))
      break
    }
    case 'editor_set_projection': {
      const mode = payload.mode as 'perspective' | 'orthographic'
      if (mode === 'perspective' || mode === 'orthographic') {
        editor.setProjectionMode(mode)
      }
      break
    }
    case 'editor_set_mode': {
      const mode = payload.mode as 'edit' | 'run'
      if (mode === 'edit' || mode === 'run') {
        editor.setEditorMode(mode)
      }
      break
    }
    case 'editor_save_scene_slot':
    case 'editor_load_scene_slot': {
      // Slot persistence happens backend-side; no frontend store mutation
      // needed beyond reflecting the action in the chat surface. The
      // backend already returns a scene snapshot via the SCENE_UPDATE
      // deltas when load_scene_slot replaces the scene.
      break
    }
    case 'editor_camera_flythrough': {
      const waypoints = Array.isArray(payload.waypoints)
        ? (payload.waypoints as Array<Record<string, unknown>>).map((w) => ({
            position: (w.position as Vec3) ?? [0, 0, 0],
            target: (w.target as Vec3) ?? [0, 0.5, 0],
            dwell: Number(w.dwell ?? 0),
            speed: Number(w.speed ?? 2),
          }))
        : []
      if (waypoints.length >= 2) {
        editor.setCameraFlythrough({
          waypoints,
          loop: Boolean(payload.loop ?? false),
          smooth: Boolean(payload.smooth ?? true),
          speed: Number(payload.speed ?? 2),
          duration: Number(payload.duration ?? 0),
          distance: Number(payload.distance ?? 0),
        })
      }
      break
    }
    case 'editor_measure': {
      const aPosition = (payload.a_position ?? [0, 0, 0]) as Vec3
      const bPosition = (payload.b_position ?? [0, 0, 0]) as Vec3
      const distance = Number(payload.distance ?? 0)
      const aName = String(payload.a_name ?? 'A')
      const bName = String(payload.b_name ?? 'B')
      editor.setMeasurement({
        aPosition,
        bPosition,
        distance,
        label: `${aName} ↔ ${bName}: ${distance.toFixed(3)}`,
      })
      break
    }
    case 'editor_clear_measurement': {
      editor.clearMeasurement()
      break
    }
    case 'editor_stop_camera_flythrough': {
      editor.clearCameraFlythrough()
      break
    }
    case 'editor_radial_menu': {
      if (payload.show === false) {
        editor.clearRadialMenu()
      } else {
        // Anchor the radial menu at the supplied viewport pixel position,
        // falling back to the screen center if the agent did not specify one.
        const target = String(payload.target ?? '')
        const pos = Array.isArray(payload.position) ? (payload.position as number[]) : null
        const x = pos && pos.length >= 2 ? Number(pos[0]) : (window.innerWidth / 2)
        const y = pos && pos.length >= 2 ? Number(pos[1]) : (window.innerHeight / 2)
        editor.setRadialMenu({ objectId: target, x, y })
      }
      break
    }
    default:
      break
  }
}

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
      case 'plan': {
        // Store the roadmap on the streaming message so the checklist can
        // render immediately and later plan_update events can mutate it.
        const steps: PlanStep[] = ev.data.steps.map((s) => ({
          id: s.id,
          tool: s.tool,
          description: s.description,
          arguments: s.arguments,
          status: (s.status as PlanStep['status']) ?? 'pending',
        }))
        const goal = typeof ev.data.goal === 'string' ? ev.data.goal : ''
        set((state) => {
          const msgs = [...state.messages]
          for (let i = msgs.length - 1; i >= 0; i--) {
            if (msgs[i].role === 'assistant' && msgs[i].streaming) {
              msgs[i] = { ...msgs[i], planSteps: steps, planGoal: goal }
              return { messages: msgs }
            }
          }
          msgs.push({
            id: genId(),
            role: 'assistant',
            content: '',
            streaming: true,
            planSteps: steps,
            planGoal: goal,
          })
          return { messages: msgs }
        })
        break
      }
      case 'plan_update': {
        const stepId = ev.data.id
        const status = ev.data.status as PlanStep['status']
        const message = ev.data.message
        set((state) => {
          const msgs = [...state.messages]
          for (let i = msgs.length - 1; i >= 0; i--) {
            const m = msgs[i]
            if (m.role !== 'assistant' || !m.planSteps) continue
            const idx = m.planSteps.findIndex((s) => s.id === stepId)
            if (idx >= 0) {
              const newSteps = [...m.planSteps]
              newSteps[idx] = {
                ...newSteps[idx],
                status,
                message: message ?? newSteps[idx].message,
              }
              msgs[i] = { ...m, planSteps: newSteps }
              return { messages: msgs }
            }
          }
          return { messages: msgs }
        })
        break
      }
      case 'plan_refine': {
        // Advisory refinement notice — append to the streaming message's
        // planRefinements list so the UI can surface the agent's mid-turn
        // reasoning (alternative-tool proposals, budget pruning).
        const refinement: PlanRefinement = {
          reason: ev.data.reason,
          iteration: ev.data.iteration,
          proposals: ev.data.proposals,
          active_categories: ev.data.active_categories,
          tool_subset_size: ev.data.tool_subset_size,
          budget_remaining: ev.data.budget_remaining,
        }
        set((state) => {
          const msgs = [...state.messages]
          for (let i = msgs.length - 1; i >= 0; i--) {
            if (msgs[i].role === 'assistant' && msgs[i].streaming) {
              const prev = msgs[i].planRefinements ?? []
              msgs[i] = { ...msgs[i], planRefinements: [...prev, refinement] }
              return { messages: msgs }
            }
          }
          msgs.push({
            id: genId(),
            role: 'assistant',
            content: '',
            streaming: true,
            planRefinements: [refinement],
          })
          return { messages: msgs }
        })
        break
      }
      case 'plan_graph': {
        // Plan dependency DAG — store on the streaming message so a
        // "view graph" affordance can render the topology alongside the
        // linear PlanTrace checklist.
        const graph: PlanGraphPayload = ev.data.graph
        set((state) => {
          const msgs = [...state.messages]
          for (let i = msgs.length - 1; i >= 0; i--) {
            if (msgs[i].role === 'assistant' && msgs[i].streaming) {
              msgs[i] = { ...msgs[i], planGraph: graph }
              return { messages: msgs }
            }
          }
          msgs.push({
            id: genId(),
            role: 'assistant',
            content: '',
            streaming: true,
            planGraph: graph,
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
                  data: ev.data.data as Record<string, unknown> | undefined,
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
        // Dispatch editor-control deltas (select/focus/playback/undo/etc.)
        // to their matching local stores, and track whether the turn produced
        // any scene mutation so the `done` handler knows whether to commit.
        const deltas = ev.data.deltas
        if (deltas && deltas.length > 0) {
          for (const d of deltas) {
            const act = String(d.action ?? '')
            if (act.startsWith('editor_')) {
              dispatchEditorDelta(act, d.target_id, (d.payload ?? {}) as Record<string, unknown>)
            } else {
              turnHadSceneMutation = true
            }
          }
        }
        // Apply the full scene snapshot for scene-mutating deltas. For
        // editor-only turns the snapshot equals the current scene, so skip
        // the replace to avoid clobbering local state (e.g. after undo).
        if (ev.data.scene && turnHadSceneMutation) {
          useScene.getState().replaceScene(ev.data.scene)
        }
        break
      }
      case 'done': {
        // Finalize the latest streaming assistant message
        const doneSuggestions = Array.isArray(ev.data.suggestions)
          ? (ev.data.suggestions as Suggestion[])
          : []
        // Capture token usage (top-level field with stats.token_usage fallback)
        const tokenUsage = ev.data.token_usage ?? ev.data.stats?.token_usage ?? null
        set((state) => {
          const msgs = [...state.messages]
          for (let i = msgs.length - 1; i >= 0; i--) {
            if (msgs[i].role === 'assistant' && msgs[i].streaming) {
              msgs[i] = {
                ...msgs[i],
                streaming: false,
                content: ev.data.content || msgs[i].content,
                // Attach suggestions to the message so the "Quick Actions"
                // chip strip renders inline below this assistant turn. The
                // top-level suggestions state is also kept for any consumer
                // that reads it directly.
                suggestions: doneSuggestions,
              }
              break
            }
          }
          return {
            messages: msgs,
            isResponding: false,
            suggestions: doneSuggestions,
            lastTokenUsage: tokenUsage,
          }
        })
        // Commit the final scene only when the turn mutated the backend scene.
        // Editor-only turns (undo/redo/play/pause/viewport) leave the backend
        // scene unchanged, so committing would clobber local frontend state.
        if (ev.data.scene && turnHadSceneMutation) {
          const before = sceneBeforeResponse
          if (before) {
            useScene.getState().commitScene(ev.data.scene, before)
          } else {
            useScene.getState().applyScene(ev.data.scene)
          }
        }
        sceneBeforeResponse = null
        turnHadSceneMutation = false
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

  /** Push the user message + reserve a streaming assistant slot and ship the
   *  WebSocket message. This is the "actual send" that the plan-aware wrapper
   *  and the confirmation modal both eventually call. Defined as a closure so
   *  it is not exposed on the public store API. */
  const _sendNow = (text: string) => {
    const trimmed = text.trim()
    if (!trimmed) return
    const sessionId = get().sessionId

    // Establish connection first (if not connected)
    const s = ensureSocket({ onStatus, onEvent })
    if (s.status !== 'connected') {
      s.connect()
    }

    // Push the user message + reserve a streaming assistant message.
    // Clear stale suggestions so they don't outlive the previous turn.
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
      suggestions: [],
      pendingDestructive: null,
    }))

    // Capture the scene snapshot before the Agent responds, for undo history
    sceneBeforeResponse = JSON.parse(JSON.stringify(useScene.getState().scene))
    turnHadSceneMutation = false

    s.send({ type: 'message', data: { message: trimmed, session_id: sessionId, model: get().model } })
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
    suggestions: [],
    confirmDestructive: true,
    planning: false,
    pendingDestructive: null,
    lastTokenUsage: null,

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
      // When confirmation is disabled, just send.
      if (!get().confirmDestructive) {
        _sendNow(trimmed)
        return
      }
      // Otherwise preview via POST /api/agent/plan first. If the plan flags
      // any destructive step, surface a confirmation modal instead of sending.
      set({ planning: true })
      fetchAgentPlan(trimmed, get().sessionId, get().model)
        .then((plan) => {
          set({ planning: false })
          const destructive = Array.isArray(plan.destructive_steps) ? plan.destructive_steps : []
          if (plan.has_destructive_steps && destructive.length > 0) {
            set({
              pendingDestructive: {
                text: trimmed,
                reasoning: plan.reasoning,
                steps: destructive.map((s) => ({
                  name: s.name,
                  arguments: s.arguments ?? {},
                })),
              },
            })
          } else {
            _sendNow(trimmed)
          }
        })
        .catch(() => {
          set({ planning: false })
          // On plan failure, proceed with the message (don't block the user).
          _sendNow(trimmed)
        })
    },

    setConfirmDestructive: (enabled) => set({ confirmDestructive: enabled }),

    confirmPendingDestructive: () => {
      const pending = get().pendingDestructive
      if (!pending) return
      _sendNow(pending.text)
    },

    cancelPendingDestructive: () => set({ pendingDestructive: null }),

    retry: () => {
      const state = get()
      if (state.isResponding) return
      const msgs = [...state.messages]
      // Find the last user message (skipping any trailing errored assistant message)
      let lastUserText = ''
      for (let i = msgs.length - 1; i >= 0; i--) {
        if (msgs[i].role === 'user') {
          lastUserText = msgs[i].content
          break
        }
      }
      if (!lastUserText) return
      // Drop trailing errored assistant messages so the retry produces a fresh response
      const cleaned: ChatMessage[] = []
      for (let i = 0; i < msgs.length; i++) {
        const m = msgs[i]
        // Keep everything up to and including the last user message;
        // drop any trailing assistant error/empty messages after it
        if (m.role === 'user') {
          cleaned.push(m)
          continue
        }
        // Only keep assistant messages that appear before the last user message
        const hasLaterUser = msgs.slice(i + 1).some((x) => x.role === 'user')
        if (hasLaterUser) {
          cleaned.push(m)
        }
      }
      set({ messages: cleaned })
      // Re-send the last user message
      get().send(lastUserText)
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
