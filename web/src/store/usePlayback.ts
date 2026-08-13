// Animation playback state: drives object animations across the canvas.
// The Timeline panel controls this store; SceneMesh consumes it to apply
// per-frame transforms (orbit / wave / bounce / keyframe) when playing.
import { create } from 'zustand'

interface PlaybackState {
  /** Whether the timeline is currently playing */
  isPlaying: boolean
  /** Current playhead position in seconds */
  currentTime: number
  /** Total timeline duration in seconds (max across all animations) */
  duration: number
  /** Playback speed multiplier (applied during tick) */
  speed: number
  /** Whether playback loops back to start when reaching the end */
  loop: boolean
  /** Last RAF timestamp for delta computation */
  lastTick: number | null

  /** Start or resume playback */
  play: () => void
  /** Pause playback (keeps currentTime) */
  pause: () => void
  /** Stop and reset playhead to 0 */
  stop: () => void
  /** Seek to a specific time */
  seek: (t: number) => void
  /** Recompute duration from the max animation duration in the scene */
  setDuration: (d: number) => void
  /** Set the playback speed multiplier (0.25 - 4.0) */
  setSpeed: (s: number) => void
  /** Toggle or set the animation loop mode. When false, playback stops at
   *  the end of the timeline instead of wrapping back to zero. */
  setLoop: (enabled: boolean) => void
  /** Advance the clock by one frame (called by the canvas RAF loop) */
  tick: (now: number) => void
}

export const usePlayback = create<PlaybackState>((set, get) => ({
  isPlaying: false,
  currentTime: 0,
  duration: 0,
  speed: 1,
  loop: true,
  lastTick: null,

  play: () => set({ isPlaying: true, lastTick: null }),
  pause: () => set({ isPlaying: false, lastTick: null }),
  stop: () => set({ isPlaying: false, currentTime: 0, lastTick: null }),
  seek: (t) =>
    set((state) => ({
      currentTime: Math.max(0, Math.min(state.duration, t)),
      lastTick: null,
    })),
  setDuration: (d) => set({ duration: Math.max(0, d) }),
  setSpeed: (s) => set({ speed: Math.max(0.25, Math.min(4, s)) }),
  setLoop: (enabled) => set({ loop: Boolean(enabled) }),

  tick: (now) => {
    const { isPlaying, lastTick, duration, speed, loop } = get()
    if (!isPlaying) return
    if (lastTick === null) {
      set({ lastTick: now })
      return
    }
    const delta = ((now - lastTick) / 1000) * speed
    let next = get().currentTime + delta
    if (duration > 0 && next >= duration) {
      if (loop) {
        // Loop back to start when exceeding duration
        next = next % duration
      } else {
        // Stop at the end when loop is disabled
        next = duration
        set({ isPlaying: false, currentTime: next, lastTick: null })
        return
      }
    }
    set({ currentTime: next, lastTick: now })
  },
}))
