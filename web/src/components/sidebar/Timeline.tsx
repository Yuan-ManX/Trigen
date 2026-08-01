// Timeline: animation management + playback control panel.
// Lists every object carrying an animation descriptor, exposes global
// play / pause / stop / scrub controls, and lets the user remove an
// animation. The shared usePlayback store drives the clock; SceneMesh
// consumes it to apply per-frame transforms.
import { Circle, Clock, Pause, Play, Repeat, Square, Trash2, Zap } from 'lucide-react'
import { useEffect } from 'react'
import { usePlayback } from '../../store/usePlayback'
import { useScene } from '../../store/useScene'
import type { ObjectAnimation, SceneObject } from '../../types'

/** Format seconds as M:SS */
function fmt(t: number): string {
  const m = Math.floor(t / 60)
  const s = Math.floor(t % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}

/** Badge color per animation kind for quick visual parsing */
function animColor(type: ObjectAnimation['type']): string {
  switch (type) {
    case 'orbit':
      return 'text-accent-cyan'
    case 'wave':
      return 'text-sky-400'
    case 'bounce':
      return 'text-amber-400'
    case 'keyframe':
      return 'text-accent-gold'
    default:
      return 'text-fg-secondary'
  }
}

function AnimIcon({ type }: { type: ObjectAnimation['type'] }) {
  if (type === 'orbit') return <Circle size={12} className="shrink-0" />
  if (type === 'bounce') return <Zap size={12} className="shrink-0" />
  return <Clock size={12} className="shrink-0" />
}

function AnimRow({ object }: { object: SceneObject }) {
  const select = useScene((s) => s.select)
  const selectedId = useScene((s) => s.selectedId)
  const anim = object.animation!
  const isPrimary = selectedId === object.id

  // Clear the animation descriptor via a lightweight scene patch that records
  // history for undo, reusing the store's commitScene path.
  const removeAnim = () => {
    const store = useScene.getState()
    const prev = store.scene
    const next = {
      ...prev,
      objects: prev.objects.map((o) =>
        o.id === object.id ? { ...o, animation: null } : o,
      ),
    }
    store.commitScene(next, prev)
  }

  return (
    <div
      onClick={() => select(object.id)}
      className={`group flex items-center gap-2 px-3 py-2 cursor-pointer border-l-2 transition-colors ${
        isPrimary
          ? 'bg-accent-gold/10 border-accent-gold'
          : 'border-transparent hover:bg-bg-hover'
      }`}
    >
      <AnimIcon type={anim.type} />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1.5">
          <span className={`text-[10px] uppercase font-mono ${animColor(anim.type)}`}>
            {anim.type}
          </span>
          {anim.loop && <Repeat size={9} className="text-fg-muted" />}
        </div>
        <span className={`block text-xs truncate ${isPrimary ? 'text-fg-primary' : 'text-fg-secondary'}`}>
          {object.name}
        </span>
      </div>
      <span className="text-[10px] font-mono text-fg-muted shrink-0">
        {anim.duration.toFixed(1)}s
      </span>
      <button
        onClick={(e) => {
          e.stopPropagation()
          removeAnim()
        }}
        className="shrink-0 text-fg-muted hover:text-rose-400 opacity-0 group-hover:opacity-100 transition-opacity"
        aria-label="Remove animation"
      >
        <Trash2 size={12} />
      </button>
    </div>
  )
}

export function Timeline() {
  const objects = useScene((s) => s.scene.objects)
  const isPlaying = usePlayback((s) => s.isPlaying)
  const currentTime = usePlayback((s) => s.currentTime)
  const duration = usePlayback((s) => s.duration)
  const play = usePlayback((s) => s.play)
  const pause = usePlayback((s) => s.pause)
  const stop = usePlayback((s) => s.stop)
  const seek = usePlayback((s) => s.seek)
  const setDuration = usePlayback((s) => s.setDuration)

  const animatedObjects = objects.filter((o) => o.animation)

  // Derive total duration from the longest animation; recompute when the
  // set of animated objects or their durations change.
  useEffect(() => {
    const maxDur = animatedObjects.reduce(
      (m, o) => Math.max(m, o.animation?.duration ?? 0),
      0,
    )
    setDuration(maxDur)
  }, [animatedObjects, setDuration])

  if (animatedObjects.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-center px-6 py-10">
        <Clock size={20} className="text-fg-muted mb-2" />
        <p className="text-xs text-fg-secondary">No animations yet</p>
        <p className="text-[11px] text-fg-muted mt-1">
          Ask the AI to add orbit, wave, bounce, or keyframe animation to objects
        </p>
      </div>
    )
  }

  const progress = duration > 0 ? (currentTime / duration) * 100 : 0

  return (
    <div className="flex flex-col h-full">
      {/* Transport controls */}
      <div className="flex items-center gap-2 px-3 py-2.5 border-b border-border-subtle">
        <button
          onClick={isPlaying ? pause : play}
          className="flex items-center justify-center w-7 h-7 rounded bg-accent-cyan/10 text-accent-cyan hover:bg-accent-cyan/20 transition-colors"
          aria-label={isPlaying ? 'Pause' : 'Play'}
        >
          {isPlaying ? <Pause size={13} /> : <Play size={13} />}
        </button>
        <button
          onClick={stop}
          className="flex items-center justify-center w-7 h-7 rounded text-fg-secondary hover:bg-bg-hover transition-colors"
          aria-label="Stop"
        >
          <Square size={11} />
        </button>
        <span className="text-[11px] font-mono text-fg-secondary tabular-nums">
          {fmt(currentTime)} <span className="text-fg-muted">/</span> {fmt(duration)}
        </span>
      </div>

      {/* Scrubber */}
      <div className="px-3 py-2 border-b border-border-subtle">
        <div
          className="relative h-4 flex items-center cursor-pointer group"
          onClick={(e) => {
            const rect = e.currentTarget.getBoundingClientRect()
            const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width))
            seek(ratio * duration)
          }}
        >
          <div className="absolute inset-x-0 h-1 rounded-full bg-bg-hover" />
          <div
            className="absolute h-1 rounded-full bg-accent-cyan"
            style={{ width: `${progress}%` }}
          />
          <div
            className="absolute w-3 h-3 rounded-full bg-fg-primary shadow-md opacity-0 group-hover:opacity-100 transition-opacity -translate-x-1/2"
            style={{ left: `${progress}%` }}
          />
        </div>
      </div>

      {/* Animated object list */}
      <div className="px-3 py-1.5 text-[10px] uppercase tracking-wider text-fg-muted border-b border-border-subtle">
        Animations · {animatedObjects.length}
      </div>
      <div className="flex-1 overflow-y-auto">
        {animatedObjects.map((o) => (
          <AnimRow key={o.id} object={o} />
        ))}
      </div>
    </div>
  )
}
