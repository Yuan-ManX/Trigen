// Activity timeline: a vertical trace of the current/last turn's plan/think/act phases.
// Renders entries from the latest assistant message's thinking + tool_calls + plan.
import {
  Brain,
  CheckCircle,
  Route,
  Sparkles,
  Wrench,
  XCircle,
  type LucideIcon,
} from 'lucide-react'
import { useMemo } from 'react'
import { useChat, type ChatMessage, type ToolCallRecord } from '../../store/useChat'

/** Bilingual labels for the timeline header and entry phases. */
const LABELS = {
  title: 'Activity / 活动',
  empty: 'No activity yet. Send a message to see the agent trace. / 暂无活动，发送消息后可查看代理轨迹。',
  phase: {
    understanding: 'Understanding / 理解意图',
    planning: 'Planning / 规划',
    critique: 'Critique / 评审',
    execution: 'Executing / 执行',
    perception: 'Perception / 感知',
    verification: 'Verification / 校验',
    reflection: 'Reflection / 反思',
    assessment: 'Assessment / 评估',
    complete: 'Complete / 完成',
    interrupted: 'Interrupted / 中断',
    budget: 'Budget / 预算',
    memory_recall: 'Memory recall / 记忆回溯',
    model_routing: 'Model routing / 模型路由',
    self_correction: 'Self-correction / 自我修正',
    other: 'Thinking / 思考',
  } as Record<string, string>,
  plan: 'Plan / 计划',
  toolCall: 'Tool call / 工具调用',
  toolResultSuccess: 'Tool result (success) / 工具结果（成功）',
  toolResultFailure: 'Tool result (failed) / 工具结果（失败）',
} as const

/** A single timeline entry. */
interface TimelineEntry {
  /** Stable sort key (mono-increasing within a turn). */
  seq: number
  /** Lucide icon component to render for this entry. */
  Icon: LucideIcon
  /** Human-readable label (bilingual). */
  label: string
  /** Optional sub-label, e.g. the tool name or phase headline. */
  sub?: string
  /** Optional duration/iteration text shown on the right. */
  duration?: string
  /** Color class for the icon. */
  tone: 'cyan' | 'gold' | 'muted' | 'green' | 'red' | 'purple'
}

/** Tone → icon color class lookup so the timeline reads at a glance. */
const TONE_CLASS: Record<TimelineEntry['tone'], string> = {
  cyan: 'text-accent-cyan',
  gold: 'text-accent-gold',
  muted: 'text-fg-muted',
  green: 'text-emerald-400',
  red: 'text-rose-400',
  purple: 'text-violet-400',
}

/** Pick the latest assistant message that has any traceable activity. */
function pickLatestActivityMessage(messages: ChatMessage[]): ChatMessage | null {
  for (let i = messages.length - 1; i >= 0; i--) {
    const m = messages[i]
    if (m.role !== 'assistant') continue
    if ((m.thinking && m.thinking.length > 0) || (m.toolCalls && m.toolCalls.length > 0) || m.planGoal) {
      return m
    }
  }
  return null
}

/** Build a merged, ordered timeline from a message's thinking + tool_calls. */
function buildTimeline(msg: ChatMessage | null): TimelineEntry[] {
  if (!msg) return []
  const entries: TimelineEntry[] = []
  let seq = 0

  // Plan headline (if present).
  if (msg.planGoal) {
    entries.push({
      seq: seq++,
      Icon: Route,
      label: LABELS.plan,
      sub: msg.planGoal,
      tone: 'gold',
    })
  }

  // Thinking traces.
  if (msg.thinking) {
    for (const t of msg.thinking) {
      const phase = String(t.phase ?? 'other')
      const isSelfCorrection = phase === 'self_correction'
      const label = LABELS.phase[phase] ?? LABELS.phase.other
      const sub = t.content ? String(t.content).slice(0, 140) : undefined
      const durParts: string[] = []
      if (typeof t.elapsed === 'number') durParts.push(`${t.elapsed}s`)
      if (typeof t.iterations === 'number') durParts.push(`it${t.iterations}`)
      entries.push({
        seq: seq++,
        Icon: isSelfCorrection ? Sparkles : Brain,
        label,
        sub,
        duration: durParts.length > 0 ? durParts.join(' · ') : undefined,
        tone: isSelfCorrection ? 'purple' : 'cyan',
      })
    }
  }

  // Tool calls + their results, interleaved in call→result order.
  if (msg.toolCalls) {
    for (const tc of msg.toolCalls) {
      entries.push({
        seq: seq++,
        Icon: Wrench,
        label: LABELS.toolCall,
        sub: `${tc.name}`,
        tone: 'muted',
      })
      if (tc.result) {
        const ok = tc.result.success
        entries.push({
          seq: seq++,
          Icon: ok ? CheckCircle : XCircle,
          label: ok ? LABELS.toolResultSuccess : LABELS.toolResultFailure,
          sub: tc.result.message ? String(tc.result.message).slice(0, 140) : undefined,
          tone: ok ? 'green' : 'red',
        })
      }
    }
  }

  return entries
}

/** ToolCallRecord is exported from useChat; re-assert for type-safety in helpers. */
export type { ToolCallRecord }

export function ActivityTimeline() {
  const messages = useChat((s) => s.messages)
  const isResponding = useChat((s) => s.isResponding)

  const latest = useMemo(() => pickLatestActivityMessage(messages), [messages])
  const entries = useMemo(() => buildTimeline(latest), [latest])

  return (
    <section
      aria-label="Agent activity timeline"
      className="flex flex-col h-full min-h-0 border-b border-border bg-bg-panel/60"
    >
      <div className="flex items-center justify-between px-3 py-1.5 border-b border-border-subtle">
        <span className="text-[11px] font-semibold tracking-wide text-fg-primary">
          {LABELS.title}
        </span>
        {isResponding && (
          <span className="text-[10px] text-accent-gold animate-pulse">live</span>
        )}
      </div>
      <div className="flex-1 min-h-0 overflow-y-auto px-3 py-2">
        {entries.length === 0 ? (
          <p className="text-[11px] text-fg-muted leading-relaxed">{LABELS.empty}</p>
        ) : (
          <ol className="relative space-y-2.5">
            {/* Vertical spine */}
            <span
              aria-hidden
              className="absolute left-[7px] top-1 bottom-1 w-px bg-border-subtle"
            />
            {entries.map((e) => {
              const Icon = e.Icon
              return (
                <li key={e.seq} className="relative flex items-start gap-2.5 pl-0">
                  <span className={`relative z-10 flex items-center justify-center w-3.5 h-3.5 rounded-full bg-bg-panel ${TONE_CLASS[e.tone]}`}>
                    <Icon size={11} />
                  </span>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-baseline justify-between gap-2">
                      <span className="text-[11px] font-medium text-fg-primary truncate">
                        {e.label}
                      </span>
                      {e.duration && (
                        <span className="text-[10px] font-mono text-fg-muted shrink-0">
                          {e.duration}
                        </span>
                      )}
                    </div>
                    {e.sub && (
                      <p className="text-[10px] text-fg-muted leading-snug mt-0.5 break-words">
                        {e.sub}
                      </p>
                    )}
                  </div>
                </li>
              )
            })}
          </ol>
        )}
      </div>
    </section>
  )
}
