// Timeline: animation management + playback control panel.
// Lists every object carrying an animation descriptor, exposes global
// play / pause / stop / scrub controls, and lets the user remove an
// animation, toggle its loop flag, edit its duration, or (for keyframe
// animations) pick an easing curve and scrub to a specific keyframe.
// Per-keyframe tick marks are rendered on the scrubber so the user can
// see at a glance where each keyframe sits in time. The shared
// usePlayback store drives the clock; SceneMesh consumes it to apply
// per-frame transforms.
import { Circle, Clock, Pause, Play, Repeat, Square, Trash2, Zap } from 'lucide-react'
import { useEffect, useMemo } from 'react'
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

const EASING_OPTIONS: NonNullable<ObjectAnimation['easing']>[] = [
  'linear',
  'easeIn',
  'easeOut',
  'easeInOut',
]

function AnimIcon({ type }: { type: ObjectAnimation['type'] }) {
  if (type === 'orbit') return <Circle size={12} className="shrink-0" />
  if (type === 'bounce') return <Zap size={12} className="shrink-0" />
  return <Clock size={12} className="shrink-0" />
}

function AnimRow({ object }: { object: SceneObject }) {
  const select = useScene((s) => s.select)
  const selectedId = useScene((s) => s.selectedId)
  const updateAnimation = useScene((s) => s.updateAnimation)
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

  // Toggle the loop flag without rebuilding the whole animation descriptor.
  const toggleLoop = () => {
    updateAnimation(object.id, { ...anim, loop: !anim.loop })
  }

  // Inline-edit the duration. Clamp to a 0.1s minimum so the math in
  // solveAnimation never divides by zero.
  const setDuration = (v: number) => {
    const dur = Math.max(0.1, Number.isFinite(v) ? v : 0.1)
    updateAnimation(object.id, { ...anim, duration: dur })
  }

  // Switch the easing curve for keyframe animations.
  const setEasing = (e: NonNullable<ObjectAnimation['easing']>) => {
    updateAnimation(object.id, { ...anim, easing: e })
  }

  return (
    <div
      onClick={() => select(object.id)}
      className={`group flex flex-col gap-1.5 px-3 py-2 cursor-pointer border-l-2 transition-colors ${
        isPrimary
          ? 'bg-accent-gold/10 border-accent-gold'
          : 'border-transparent hover:bg-bg-hover'
      }`}
    >
      <div className="flex items-center gap-2">
        <AnimIcon type={anim.type} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5">
            <span className={`text-[10px] uppercase font-mono ${animColor(anim.type)}`}>
              {anim.type}
            </span>
            <button
              onClick={(e) => {
                e.stopPropagation()
                toggleLoop()
              }}
              title={anim.loop ? 'Loop ON — click to disable' : 'Loop OFF — click to enable'}
              className={`shrink-0 transition-opacity ${
                anim.loop
                  ? 'text-accent-cyan opacity-100'
                  : 'text-fg-muted opacity-50 hover:opacity-100'
              }`}
              aria-label="Toggle loop"
            >
              <Repeat size={10} />
            </button>
          </div>
          <span className={`block text-xs truncate ${isPrimary ? 'text-fg-primary' : 'text-fg-secondary'}`}>
            {object.name}
          </span>
        </div>
        {/* Inline duration editor — click to focus, Enter/blur to commit */}
        <label
          className="shrink-0 flex items-center gap-0.5 text-[10px] font-mono text-fg-muted"
          onClick={(e) => e.stopPropagation()}
        >
          <input
            type="number"
            min={0.1}
            step={0.1}
            defaultValue={anim.duration.toFixed(1)}
            onBlur={(e) => setDuration(parseFloat(e.target.value))}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault()
                ;(e.target as HTMLInputElement).blur()
              }
            }}
            className="w-8 bg-transparent border border-border-subtle rounded px-1 py-0.5 text-right text-fg-secondary focus:outline-none focus:border-accent-cyan/50"
            aria-label="Duration in seconds"
          />
          <span>s</span>
        </label>
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
      {/* Easing picker — only relevant for keyframe animations */}
      {anim.type === 'keyframe' && (
        <div
          className="flex items-center gap-1 pl-5"
          onClick={(e) => e.stopPropagation()}
        >
          <span className="text-[9px] uppercase tracking-wider text-fg-muted">ease</span>
          <div className="flex gap-0.5">
            {EASING_OPTIONS.map((e) => {
              const active = (anim.easing ?? 'linear') === e
              return (
                <button
                  key={e}
                  onClick={() => setEasing(e)}
                  className={`px-1.5 py-0.5 rounded text-[9px] font-mono transition-colors ${
                    active
                      ? 'bg-accent-gold/20 text-accent-gold'
                      : 'text-fg-muted hover:text-fg-secondary hover:bg-bg-hover'
                  }`}
                  title={`Easing: ${e}`}
                >
                  {e}
                </button>
              )
            })}
          </div>
          {anim.keyframes && anim.keyframes.length > 0 && (
            <span className="ml-auto text-[9px] text-fg-muted font-mono">
              {anim.keyframes.length} kf
            </span>
          )}
        </div>
      )}
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

  // Collect keyframe ticks across all keyframe-type animations so the
  // scrubber can render per-keyframe markers in absolute time. Each tick
  // is the keyframe's normalized time (0..1) multiplied by the animation's
  // own duration (since the global clock uses the longest animation).
  const keyframeTicks = useMemo(() => {
    const ticks: number[] = []
    for (const o of animatedObjects) {
      const a = o.animation
      if (!a || a.type !== 'keyframe' || !a.keyframes) continue
      for (const kf of a.keyframes) {
        if (typeof kf.t !== 'number') continue
        // kf.t is 0..1 within the animation; convert to absolute seconds.
        ticks.push(kf.t * a.duration)
      }
    }
    return ticks
  }, [animatedObjects])

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
        <span className="ml-auto text-[9px] uppercase tracking-wider text-fg-muted">
          {keyframeTicks.length > 0 ? `${keyframeTicks.length} kf` : ''}
        </span>
      </div>

      {/* Scrubber with per-keyframe tick marks */}
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
          {/* Per-keyframe tick marks rendered on top of the track */}
          {duration > 0 &&
            keyframeTicks.map((t, i) => {
              const left = (t / duration) * 100
              return (
                <div
                  key={i}
                  title={`Keyframe @ ${t.toFixed(2)}s`}
                  className="absolute w-0.5 h-3 rounded-full bg-accent-gold/80 -translate-x-1/2 pointer-events-none"
                  style={{ left: `${left}%` }}
                />
              )
            })}
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
