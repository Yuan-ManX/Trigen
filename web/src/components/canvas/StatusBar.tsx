// Status bar: displays scene statistics, mode, selection info, agent status,
// and FPS counter. Polls /api/agent/status for online/offline mode so the
// user always knows whether the LLM is powering the chat or the offline
// rule engine is handling turns.
import { Box, Cpu, Eye, Layers, Lightbulb, MousePointer2, Zap } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { fetchAgentStatus } from '../../api/client'
import type { AgentStatusResponse } from '../../types'
import { useScene } from '../../store/useScene'

interface StatusBarProps {
  mode: 'edit' | 'run'
}

/** Estimate polygon count from scene objects */
function estimatePolygons(objects: { type: string; geometry: { type: string } }[]): number {
  let total = 0
  for (const obj of objects) {
    switch (obj.geometry.type) {
      case 'box':
        total += 12
        break
      case 'sphere':
        total += 960
        break
      case 'cylinder':
        total += 96
        break
      case 'cone':
        total += 96
        break
      case 'torus':
        total += 2048
        break
      case 'torusKnot':
        total += 4096
        break
      case 'plane':
        total += 2
        break
      case 'ring':
        total += 64
        break
      case 'capsule':
        total += 256
        break
      case 'tube':
        total += 512
        break
      default:
        total += 100
    }
  }
  return total
}

export function StatusBar({ mode }: StatusBarProps) {
  const scene = useScene((s) => s.scene)
  const selected = useScene((s) => s.selected())

  // FPS counter using requestAnimationFrame
  const [fps, setFps] = useState(60)
  const frameCount = useRef(0)
  const lastTime = useRef(performance.now())

  // Agent online/offline status — polled on mount and every 30s so the
  // indicator stays accurate without a websocket push. The endpoint is
  // cheap (no LLM calls); 30s is a good balance between responsiveness
  // and avoiding unnecessary requests when the tab is left open.
  const [agentStatus, setAgentStatus] = useState<AgentStatusResponse | null>(null)

  useEffect(() => {
    let cancelled = false
    const poll = () => {
      fetchAgentStatus()
        .then((status) => {
          if (!cancelled) setAgentStatus(status)
        })
        .catch(() => {
          // Leave the previous status in place on transient errors so the
          // indicator doesn't flicker when the backend briefly hiccups.
        })
    }
    poll()
    const id = window.setInterval(poll, 30000)
    return () => {
      cancelled = true
      window.clearInterval(id)
    }
  }, [])

  useEffect(() => {
    let rafId: number
    const loop = () => {
      frameCount.current++
      const now = performance.now()
      const elapsed = now - lastTime.current
      if (elapsed >= 500) {
        setFps(Math.round((frameCount.current * 1000) / elapsed))
        frameCount.current = 0
        lastTime.current = now
      }
      rafId = requestAnimationFrame(loop)
    }
    rafId = requestAnimationFrame(loop)
    return () => cancelAnimationFrame(rafId)
  }, [])

  const objectCount = scene.objects.length
  const lightCount = scene.lights.length
  const visibleCount = scene.objects.filter((o) => o.visible).length
  const polyCount = estimatePolygons(scene.objects)
  const polyLabel = polyCount >= 1000 ? `${(polyCount / 1000).toFixed(1)}k` : `${polyCount}`
  // Draw call estimate: each visible mesh and each light contributes one
  // draw call. Lights may add shadow passes, so this is a lower bound.
  const drawCalls = visibleCount + lightCount

  const online = agentStatus?.online ?? false
  const primaryModel = agentStatus?.primary_model
  // Build a concise tooltip summarizing what's powering the agent right now.
  const agentTooltip = agentStatus
    ? online
      ? `Online · ${primaryModel ?? 'LLM'} · ${agentStatus.capabilities.tools} tools / ${agentStatus.capabilities.skills} skills`
      : `Offline · rule engine · ${agentStatus.capabilities.tools} tools / ${agentStatus.capabilities.skills} skills`
    : 'Agent status unavailable'

  return (
    <footer className="flex items-center justify-between h-6 px-3 border-t border-border bg-bg-panel text-[10px] text-fg-muted select-none">
      {/* Left: scene stats */}
      <div className="flex items-center gap-3">
        <span className="flex items-center gap-1">
          <Box size={10} className="text-accent-cyan/70" />
          <span>{objectCount} objects</span>
        </span>
        <span className="flex items-center gap-1">
          <Eye size={10} className="text-accent-cyan/70" />
          <span>{visibleCount} visible</span>
        </span>
        <span className="flex items-center gap-1">
          <Lightbulb size={10} className="text-accent-gold/70" />
          <span>{lightCount} lights</span>
        </span>
        <span className="flex items-center gap-1">
          <Zap size={10} className="text-accent-cyan/70" />
          <span>{polyLabel} polys</span>
        </span>
        <span className="flex items-center gap-1" title="Estimated draw calls (visible objects + lights)">
          <Layers size={10} className="text-accent-cyan/70" />
          <span>{drawCalls} draws</span>
        </span>
      </div>

      {/* Center: selection info */}
      <div className="flex items-center gap-2">
        {selected ? (
          <span className="flex items-center gap-1 text-fg-secondary">
            <MousePointer2 size={10} className="text-accent-cyan" />
            <span className="text-accent-cyan font-medium">{selected.name}</span>
            <span className="text-fg-muted">·</span>
            <span>{selected.type}</span>
          </span>
        ) : (
          <span className="text-fg-muted">No selection</span>
        )}
      </div>

      {/* Right: agent mode + edit/run mode + FPS */}
      <div className="flex items-center gap-3">
        <span
          title={agentTooltip}
          className="flex items-center gap-1 font-medium"
        >
          <Cpu size={10} className={online ? 'text-emerald-400' : 'text-fg-muted'} />
          <span className={online ? 'text-emerald-400' : 'text-fg-muted'}>
            {online ? 'ONLINE' : 'OFFLINE'}
          </span>
          {online && primaryModel && (
            <span className="text-fg-muted/70 font-mono ml-0.5 hidden sm:inline">
              · {primaryModel}
            </span>
          )}
        </span>
        <span className="text-fg-muted">·</span>
        <span
          className={`font-medium ${
            mode === 'edit' ? 'text-accent-cyan' : 'text-accent-gold'
          }`}
        >
          {mode === 'edit' ? 'EDIT' : 'RUN'}
        </span>
        <span className="text-fg-muted">·</span>
        <span
          className={`font-mono ${
            fps >= 50
              ? 'text-emerald-400'
              : fps >= 30
                ? 'text-accent-gold'
                : 'text-rose-400'
          }`}
        >
          {fps} FPS
        </span>
      </div>
    </footer>
  )
}
