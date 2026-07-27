// Status bar: displays scene statistics, mode, selection info, and FPS counter
import { Box, Eye, Lightbulb, MousePointer2, Zap } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
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

      {/* Right: mode and FPS */}
      <div className="flex items-center gap-3">
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
