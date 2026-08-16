// Message bubble: user messages on the right, assistant messages on the left, supports streaming cursor and tool calls
import { motion } from 'framer-motion'
import { AlertTriangle, Brain, Check, ChevronDown, ChevronRight, Copy, GitBranch, Lightbulb, RefreshCw, Sparkles, Wand2 } from 'lucide-react'
import { useState } from 'react'
import { useChat } from '../../store/useChat'
import type { ChatMessage, Suggestion, ThinkingTrace } from '../../store/useChat'
import { NodeGraphView } from '../toolbar/NodeGraphView'
import { PlanTrace } from './PlanTrace'
import { ToolCallCard } from './ToolCallCard'

/** Format a Unix epoch (ms) as a compact HH:MM timestamp for display
 *  next to the message header. Returns empty string for invalid values. */
function formatTimestamp(ms: number | undefined): string {
  if (!ms) return ''
  const d = new Date(ms)
  const h = d.getHours().toString().padStart(2, '0')
  const m = d.getMinutes().toString().padStart(2, '0')
  return `${h}:${m}`
}

/** Copy-to-clipboard button — appears on hover over assistant messages
 *  that have text content. Shows a brief check-mark confirmation after
 *  copying so the user knows it worked. */
function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false)
  const handleCopy = () => {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    })
  }
  return (
    <button
      onClick={handleCopy}
      aria-label="Copy message"
      title={copied ? 'Copied!' : 'Copy to clipboard'}
      className="flex items-center justify-center w-5 h-5 rounded text-fg-muted hover:text-accent-cyan hover:bg-bg-hover transition-colors"
    >
      {copied ? <Check size={11} className="text-emerald-400" /> : <Copy size={11} />}
    </button>
  )
}

interface MessageBubbleProps {
  message: ChatMessage
}

/** Collapsible reasoning trace card */
function ThinkingCard({ traces }: { traces: ThinkingTrace[] }) {
  const [open, setOpen] = useState(false)
  const lastPhase = traces[traces.length - 1]?.phase ?? ''
  const reflectionCount = traces.filter((t) => t.phase === 'reflection').length
  const isReflecting = lastPhase === 'reflection'
  const isCritique = lastPhase === 'critique'
  const isPerception = lastPhase === 'perception'
  const isSceneIntelligence = lastPhase === 'scene_intelligence'
  const isSuggestions = lastPhase === 'suggestions'

  // Header accent by active phase:
  //   reflection          → rose (recovery from failure)
  //   perception          → cyan (multimodal 3D scene sanity check)
  //   scene_intelligence  → cyan (Agent "seeing" the scene semantically)
  //   critique            → gold (plan-quality gate before execution)
  //   suggestions         → gold (proactive next-action proposals)
  //   default             → gold (thinking)
  const headerAccent = isReflecting
    ? 'border-rose-400/30 bg-rose-500/5'
    : (isPerception || isSceneIntelligence)
      ? 'border-accent-cyan/30 bg-accent-cyan/5'
      : (isCritique || isSuggestions)
        ? 'border-accent-gold/50 bg-accent-gold/10'
        : 'border-accent-gold/25 bg-accent-gold/5'
  const headerIconColor = isReflecting
    ? 'text-rose-400'
    : (isPerception || isSceneIntelligence)
      ? 'text-accent-cyan'
      : 'text-accent-gold'

  return (
    <div className={`rounded-md border overflow-hidden ${headerAccent}`}>
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-2 px-3 py-2 text-left"
      >
        <Brain size={13} className={headerIconColor} />
        <span className="text-[11px] font-medium text-fg-secondary">
          Reasoning · {lastPhase || 'thinking'}
          {traces.length > 1 && (
            <span className="text-fg-muted ml-1">({traces.length} steps)</span>
          )}
          {reflectionCount > 0 && (
            <span className="text-rose-400 ml-1">· {reflectionCount} reflection{reflectionCount > 1 ? 's' : ''}</span>
          )}
        </span>
        {open ? (
          <ChevronDown size={12} className="ml-auto text-fg-muted" />
        ) : (
          <ChevronRight size={12} className="ml-auto text-fg-muted" />
        )}
      </button>
      {open && (
        <div className="px-3 pb-2 space-y-1.5">
          {traces.map((t, i) => {
            // Per-trace phase color coding:
            //   reflection          → rose (recovery from failure)
            //   perception          → cyan (multimodal 3D scene sanity check)
            //   scene_intelligence  → cyan (Agent "seeing" the scene)
            //   critique            → gold (plan-quality gate)
            //   suggestions         → gold (proactive next-action proposals)
            //   assessment/verification/other → default muted
            const isRefl = t.phase === 'reflection'
            const isPerc = t.phase === 'perception'
            const isCrit = t.phase === 'critique'
            const isSceneIntel = t.phase === 'scene_intelligence'
            const isSugg = t.phase === 'suggestions'
            const labelColor = isRefl
              ? 'text-rose-400'
              : (isPerc || isSceneIntel)
                ? 'text-accent-cyan'
                : (isCrit || isSugg)
                  ? 'text-accent-gold'
                  : 'text-accent-gold/80'
            const bodyColor = isRefl
              ? 'text-rose-300'
              : (isPerc || isSceneIntel)
                ? 'text-accent-cyan/90'
                : (isCrit || isSugg)
                  ? 'text-accent-gold/90'
                  : 'text-fg-secondary'
            return (
              <div key={i} className={`text-[11px] leading-relaxed ${bodyColor}`}>
                <span className={`font-mono ${labelColor}`}>[{t.phase}]</span>{' '}
                {t.content}
                {t.tools && t.tools.length > 0 && (
                  <span className="text-fg-muted"> → {t.tools.join(', ')}</span>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

/** Convert a structured Suggestion into a concise natural-language prompt the
 *  user can send back to the Agent. Prefers the suggested arguments; falls
 *  back to the suggestion name so the click always produces an actionable
 *  message. Mirrors the helper in MessageList.tsx so chip clicks and the
 *  legacy "Next steps" strip produce identical prompts. */
function buildSuggestionPrompt(s: Suggestion): string {
  const argValues = Object.values(s.arguments ?? {}).filter(Boolean)
  if (argValues.length === 0) return s.name
  const parts = argValues
    .filter((v) => typeof v === 'string' || typeof v === 'number' || typeof v === 'boolean')
    .map((v) => String(v))
  if (parts.length === 0) return s.name
  return `${s.name}: ${parts.join(', ')}`
}

/** Compact "Quick Actions" chip strip rendered below an assistant message
 *  when the turn produced proactive suggestions. Each chip sends the
 *  suggestion as a new user message with one click. */
function QuickActionsStrip({ suggestions }: { suggestions: Suggestion[] }) {
  const send = useChat((s) => s.send)
  const isResponding = useChat((s) => s.isResponding)
  return (
    <div className="pt-0.5">
      <div className="flex items-center gap-1.5 mb-1 px-0.5">
        <Wand2 size={10} className="text-accent-gold" />
        <span className="text-[9px] uppercase tracking-wider font-semibold text-fg-muted">
          Quick actions
        </span>
      </div>
      <div className="flex flex-wrap gap-1">
        {suggestions.map((s, i) => {
          const prompt = buildSuggestionPrompt(s)
          return (
            <motion.button
              key={`${s.name}-${i}`}
              initial={{ opacity: 0, scale: 0.96 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ duration: 0.18, delay: 0.03 * i }}
              onClick={() => send(prompt)}
              disabled={isResponding}
              title={s.rationale || s.description}
              className="group inline-flex items-center gap-1 rounded-full border border-accent-gold/30 bg-accent-gold/5 hover:bg-accent-gold/15 hover:border-accent-gold/50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors px-2 py-1 text-[10px] font-medium text-fg-secondary hover:text-accent-gold"
            >
              <Lightbulb size={9} className="text-accent-gold/70 group-hover:text-accent-gold shrink-0" />
              <span className="truncate max-w-[180px]">{s.name}</span>
            </motion.button>
          )
        })}
      </div>
    </div>
  )
}

/** Subtle pulsing-dots "thinking" indicator shown while an assistant
 *  message is streaming but has not yet received any text content (e.g.
 *  during the reasoning / tool-call phase before the first token arrives).
 *  Three dots pulse with staggered delays to convey active processing. */
function TypingDots() {
  return (
    <span className="inline-flex items-center gap-1 py-0.5" aria-label="Assistant is thinking">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="w-1.5 h-1.5 rounded-full bg-accent-cyan/70 animate-pulse"
          style={{ animationDelay: `${i * 200}ms` }}
        />
      ))}
    </span>
  )
}

export function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === 'user'
  const retry = useChat((s) => s.retry)
  const isResponding = useChat((s) => s.isResponding)
  // Local modal state for the plan-DAG viewer. Only rendered when the
  // message carries a planGraph payload (set by the plan_graph event).
  const [showPlanGraph, setShowPlanGraph] = useState(false)

  if (isUser) {
    const ts = formatTimestamp(message.createdAt)
    return (
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.18 }}
        className="flex justify-end"
      >
        <div className="flex flex-col items-end gap-0.5 max-w-[88%]">
          <div className="rounded-md rounded-tr-sm bg-accent-cyan/15 border border-accent-cyan/30 px-3 py-2 text-sm text-fg-primary whitespace-pre-wrap break-words">
            {message.content}
          </div>
          {ts && (
            <span className="text-[9px] text-fg-muted/50 font-mono px-1">{ts}</span>
          )}
        </div>
      </motion.div>
    )
  }

  const ts = formatTimestamp(message.createdAt)
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.18 }}
      className="flex justify-start"
    >
      <div className="max-w-[92%] w-full space-y-2">
        <div className="flex items-center gap-1.5 text-[11px] text-fg-muted">
          <Sparkles size={12} className="text-accent-gold" />
          <span>Trigen AI</span>
          {ts && (
            <span className="text-[9px] text-fg-muted/50 font-mono">{ts}</span>
          )}
          {/* Copy button — only on completed (non-streaming) assistant
              messages with text content. Hidden during streaming so it
              doesn't flicker as the text grows. */}
          {!message.streaming && message.content && (
            <CopyButton text={message.content} />
          )}
        </div>

        {/* Reasoning trace */}
        {message.thinking && message.thinking.length > 0 && (
          <ThinkingCard traces={message.thinking} />
        )}

        {/* Live execution-plan checklist */}
        {message.planSteps && message.planSteps.length > 0 && (
          <PlanTrace
            steps={message.planSteps}
            goal={message.planGoal}
            breakdown={message.planBreakdown}
            assumptions={message.planAssumptions}
            risks={message.planRisks}
          />
        )}

        {/* Plan DAG viewer trigger — only when the orchestrator emitted a
            plan_graph event for this turn. Opens the NodeGraphView modal
            in read-only plan-DAG mode. */}
        {message.planGraph && message.planGraph.nodes.length > 0 && (
          <>
            <button
              onClick={() => setShowPlanGraph(true)}
              className="flex items-center gap-1.5 px-2 py-1 rounded-md border border-accent-gold/30 bg-accent-gold/5 text-[11px] text-accent-gold hover:bg-accent-gold/15 hover:border-accent-gold/50 transition-colors"
              title="View the plan dependency graph"
            >
              <GitBranch size={11} />
              View plan graph
              <span className="text-fg-muted ml-0.5">
                ({message.planGraph.nodes.length} steps · {message.planGraph.edges.length} deps)
              </span>
            </button>
            <NodeGraphView
              open={showPlanGraph}
              onClose={() => setShowPlanGraph(false)}
              planGraph={message.planGraph}
            />
          </>
        )}

        {/* Tool calls */}
        {message.toolCalls && message.toolCalls.length > 0 && (
          <div className="space-y-1.5">
            {message.toolCalls.map((c) => (
              <ToolCallCard key={c.id} call={c} />
            ))}
          </div>
        )}

        {/* Text content */}
        {(message.content || message.streaming) && (
          <div className="rounded-md rounded-tl-sm bg-bg-elevated border border-border px-3 py-2 text-sm text-fg-primary whitespace-pre-wrap break-words">
            {message.streaming && !message.content ? (
              <TypingDots />
            ) : (
              <>
                {message.content}
                {message.streaming && (
                  <span className="inline-block w-1.5 h-3.5 ml-0.5 bg-accent-cyan align-middle animate-pulse" />
                )}
              </>
            )}
          </div>
        )}

        {/* Quick Actions chip strip — proactive suggestions attached to this
            assistant turn. Hidden while streaming so they don't compete with
            the in-flight response. Each chip sends the suggestion as a new
            user message. */}
        {!message.streaming &&
          message.suggestions &&
          message.suggestions.length > 0 && (
            <QuickActionsStrip suggestions={message.suggestions} />
          )}

        {/* Error */}
        {message.error && (
          <div className="rounded-md border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-xs text-rose-300">
            <div className="flex items-start gap-2">
              <AlertTriangle size={13} className="mt-0.5 shrink-0" />
              <span className="break-words flex-1">{message.error}</span>
            </div>
            <button
              onClick={() => retry()}
              disabled={isResponding}
              className="mt-2 flex items-center gap-1.5 px-2 py-1 rounded text-[10px] font-medium bg-rose-500/20 text-rose-200 hover:bg-rose-500/30 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              <RefreshCw size={10} className={isResponding ? 'animate-spin' : ''} />
              {isResponding ? 'Retrying…' : 'Retry'}
            </button>
          </div>
        )}
      </div>
    </motion.div>
  )
}
