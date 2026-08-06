// Storyboard panel: the scene's cinematic camera sequence.
// A storyboard is an ordered set of camera shots (position + look-at +
// fov + duration + easing) that plays as a scripted camera tour. The panel
// lists the shots, lets the user play / pause / stop the sequence, jump to a
// specific shot, clear the whole storyboard, and compose a fresh one from
// the current viewport camera. Driven by the /api/agent/story endpoints.
// Bilingual labels: English / 中文.
import {
  Clapperboard,
  Loader2,
  Pause,
  Play,
  Plus,
  Repeat,
  Square,
  Trash2,
  X,
} from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  clearStoryboard,
  composeStoryboard,
  controlStoryboard,
  fetchStoryboard,
  type StoryboardShotInput,
} from '../../api/client'
import { useChat } from '../../store/useChat'
import { useEditor } from '../../store/useEditor'
import { useScene } from '../../store/useScene'
import type { SceneData, Storyboard, StoryboardShot } from '../../types'

/** Format a shot duration as a compact label. */
function fmtDuration(sec: number): string {
  return `${sec.toFixed(1)}s`
}

export function StoryboardPanel() {
  const [storyboard, setStoryboard] = useState<Storyboard | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  // Compose-form state
  const [composing, setComposing] = useState(false)
  const [draftTitle, setDraftTitle] = useState('')
  const [draftShots, setDraftShots] = useState<StoryboardShotInput[]>([])
  // Playback busy state (disables buttons while a command is in flight)
  const [busy, setBusy] = useState(false)

  const sessionId = useChat((s) => s.sessionId)
  const activePanel = useEditor((s) => s.activePanel)
  const setScene = useScene((s) => s.setScene)
  const scene = useScene((s) => s.scene)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = await fetchStoryboard(sessionId)
      setStoryboard(data.storyboard)
      setError(null)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load storyboard')
    } finally {
      setLoading(false)
    }
  }, [sessionId])

  // Load on mount and whenever the panel becomes active.
  useEffect(() => {
    if (activePanel === 'storyboard') {
      void load()
    }
  }, [activePanel, load])

  const shots = useMemo(() => storyboard?.shots ?? [], [storyboard])
  const totalDuration = useMemo(
    () => shots.reduce((sum, s) => sum + (s.duration ?? 0), 0),
    [shots],
  )

  /** Swap the live scene into the editor after a compose so the new
   *  storyboard is immediately visible to the camera rig. */
  const applyScene = useCallback(
    (scenePayload: SceneData) => setScene(scenePayload),
    [setScene],
  )

  /** Run a playback command and refresh the local storyboard state. */
  const runPlayback = async (mode: 'play' | 'pause' | 'stop', index?: number) => {
    setBusy(true)
    try {
      const data = await controlStoryboard(mode, { sessionId, index })
      setStoryboard(data.storyboard)
      setError(null)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : `Failed to ${mode} storyboard`)
    } finally {
      setBusy(false)
    }
  }

  /** Add the current viewport camera as a new shot in the draft sequence. */
  const captureCameraShot = () => {
    const vc = scene.cameras.find((c) => c.name === 'ViewportCamera')
    setDraftShots((prev) => [
      ...prev,
      {
        name: `Shot ${prev.length + 1}`,
        position: vc ? [vc.position[0], vc.position[1], vc.position[2]] : [5, 4, 7],
        target: vc ? [vc.target[0], vc.target[1], vc.target[2]] : [0, 0.5, 0],
        fov: vc?.fov ?? 45,
        duration: 3,
        easing: 'easeInOut',
      },
    ])
  }

  /** Remove a shot from the draft sequence. */
  const removeDraftShot = (idx: number) => {
    setDraftShots((prev) => prev.filter((_, i) => i !== idx))
  }

  /** Submit the draft sequence as the new storyboard. */
  const handleCompose = async () => {
    if (draftShots.length === 0) return
    setComposing(true)
    try {
      const data = await composeStoryboard(
        draftTitle.trim() || 'Untitled scene',
        draftShots,
        { sessionId },
      )
      setStoryboard(data.storyboard)
      if (data.scene) applyScene(data.scene)
      setDraftTitle('')
      setDraftShots([])
      setError(null)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to compose storyboard')
    } finally {
      setComposing(false)
    }
  }

  /** Remove the whole storyboard from the scene. */
  const handleClear = async () => {
    setBusy(true)
    try {
      const data = await clearStoryboard(sessionId)
      setStoryboard(null)
      setError(data.cleared ? null : 'No storyboard to clear')
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to clear storyboard')
    } finally {
      setBusy(false)
    }
  }

  if (loading && shots.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-fg-muted text-[11px] gap-2">
        <Loader2 size={13} className="animate-spin" />
        Loading storyboard…
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="px-3 py-2.5 border-b border-border-subtle">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1.5">
            <Clapperboard size={12} className="text-accent-cyan" />
            <span className="text-[11px] font-semibold text-fg-primary">Storyboard / 分镜</span>
          </div>
          <ShoardMeta storyboard={storyboard} totalDuration={totalDuration} />
        </div>
        <p className="text-[9.5px] text-fg-muted mt-1 leading-relaxed">
          A sequence of camera shots that plays as a cinematic tour. Compose
          shots, then play the cut to narrate the scene.
        </p>
      </div>

      {/* Error banner */}
      {error && (
        <div className="mx-3 my-2 px-2 py-1.5 rounded border border-rose-400/30 bg-rose-400/10 text-[10px] text-rose-200 flex items-start gap-1.5">
          <X size={11} className="mt-0.5 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Playback controls */}
      {shots.length > 0 && (
        <div className="px-3 py-2 border-b border-border-subtle bg-bg-base/30 flex items-center gap-1.5">
          <button
            onClick={() => runPlayback('play')}
            disabled={busy || storyboard?.playing}
            title="Play sequence"
            className="flex items-center gap-1 text-[10px] font-medium px-2 py-1 rounded border border-accent-cyan/30 bg-accent-cyan/10 text-accent-cyan hover:bg-accent-cyan/20 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            {busy ? <Loader2 size={11} className="animate-spin" /> : <Play size={11} />}
            Play
          </button>
          <button
            onClick={() => runPlayback('pause')}
            disabled={busy || !storyboard?.playing}
            title="Pause sequence"
            className="flex items-center gap-1 text-[10px] px-2 py-1 rounded border border-border text-fg-secondary hover:text-fg-primary disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            <Pause size={11} />
          </button>
          <button
            onClick={() => runPlayback('stop')}
            disabled={busy}
            title="Stop sequence"
            className="flex items-center gap-1 text-[10px] px-2 py-1 rounded border border-border text-fg-secondary hover:text-fg-primary disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            <Square size={11} />
          </button>
          <div className="ml-auto flex items-center gap-1.5">
            {storyboard?.loop && (
              <span title="Looping" className="flex items-center">
                <Repeat size={11} className="text-accent-cyan/70" />
              </span>
            )}
            <button
              onClick={handleClear}
              disabled={busy}
              title="Clear storyboard"
              className="flex items-center gap-1 text-[10px] px-1.5 py-1 rounded border border-border text-fg-muted hover:text-rose-300 hover:border-rose-400/40 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              <Trash2 size={11} />
            </button>
          </div>
        </div>
      )}

      {/* Shot list */}
      <div className="flex-1 overflow-y-auto p-2 space-y-1.5">
        {shots.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-fg-muted text-[11px] gap-2 p-4 text-center">
            <Clapperboard size={18} className="opacity-50" />
            <p>No shots yet.</p>
            <p className="text-[9.5px] text-fg-muted/70">
              Compose a sequence below, or ask the Agent: “compose a storyboard panning around the scene”.
            </p>
          </div>
        ) : (
          shots.map((shot, i) => (
            <ShotRow
              key={shot.id}
              shot={shot}
              index={i}
              active={!!storyboard?.playing && storyboard.index === i}
              onJump={() => runPlayback('play', i)}
            />
          ))
        )}
      </div>

      {/* Compose form */}
      <div className="px-3 py-2 border-t border-border-subtle bg-bg-base/40 space-y-1.5">
        <div className="flex items-center gap-1.5">
          <input
            type="text"
            value={draftTitle}
            onChange={(e) => setDraftTitle(e.target.value)}
            placeholder="Sequence title"
            className="flex-1 text-[11px] bg-bg-elevated/60 border border-border rounded px-2 py-1.5 text-fg-primary placeholder:text-fg-muted/60 focus:outline-none focus:border-accent-cyan/50"
          />
          <button
            onClick={captureCameraShot}
            title="Add current viewport camera as a shot"
            className="flex items-center gap-1 text-[10px] px-2 py-1.5 rounded border border-border text-fg-secondary hover:text-accent-cyan hover:border-accent-cyan/40 transition-colors"
          >
            <Plus size={11} />
            Shot
          </button>
        </div>

        {draftShots.length > 0 && (
          <>
            <div className="flex flex-wrap gap-1">
              {draftShots.map((s, i) => (
                <span
                  key={i}
                  className="flex items-center gap-1 px-1.5 py-0.5 rounded border border-border bg-bg-elevated/40 text-[9.5px] text-fg-secondary"
                >
                  {i + 1}. {s.name ?? `Shot ${i + 1}`}
                  <button
                    onClick={() => removeDraftShot(i)}
                    className="text-fg-muted hover:text-rose-300"
                    aria-label={`Remove shot ${i + 1}`}
                  >
                    <X size={9} />
                  </button>
                </span>
              ))}
            </div>
            <button
              onClick={handleCompose}
              disabled={composing || draftShots.length === 0}
              className="w-full flex items-center justify-center gap-1 text-[10px] font-medium px-2 py-1.5 rounded border border-accent-cyan/30 bg-accent-cyan/10 text-accent-cyan hover:bg-accent-cyan/20 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              {composing ? <Loader2 size={11} className="animate-spin" /> : <Play size={11} />}
              Compose {draftShots.length === 1 ? 'shot' : `${draftShots.length} shots`}
            </button>
          </>
        )}
      </div>
    </div>
  )
}

/** Compact header meta showing shot count + total duration. */
function ShoardMeta({
  storyboard,
  totalDuration,
}: {
  storyboard: Storyboard | null
  totalDuration: number
}) {
  const count = storyboard?.shots?.length ?? 0
  return (
    <span className="text-[9px] text-fg-muted font-mono">
      {count} shot{count === 1 ? '' : 's'} · {fmtDuration(totalDuration)}
    </span>
  )
}

interface ShotRowProps {
  shot: StoryboardShot
  index: number
  active: boolean
  onJump: () => void
}

/** A single storyboard shot row with a jump-to-play button. */
function ShotRow({ shot, index, active, onJump }: ShotRowProps) {
  return (
    <div
      className={`group rounded-md border px-2 py-1.5 transition-colors ${
        active ? 'border-accent-cyan/40 bg-accent-cyan/5' : 'border-border bg-bg-elevated/30'
      }`}
    >
      <div className="flex items-center gap-1.5">
        <span
          className={`px-1.5 py-px rounded text-[9.5px] font-mono font-semibold border ${
            active
              ? 'text-accent-cyan border-accent-cyan/40 bg-accent-cyan/10'
              : 'text-fg-secondary border-border bg-bg-elevated/60'
          }`}
        >
          S{index + 1}
        </span>
        <span className="text-[10.5px] text-fg-primary font-medium truncate">{shot.name}</span>
        <span className="text-[9px] text-fg-muted/60 font-mono ml-auto">
          {fmtDuration(shot.duration ?? 3)}
        </span>
        <button
          onClick={onJump}
          title={`Play from shot ${index + 1}`}
          className="flex items-center gap-1 text-[9.5px] px-1.5 py-0.5 rounded border border-border text-fg-muted hover:text-accent-cyan hover:border-accent-cyan/40 transition-colors opacity-0 group-hover:opacity-100"
        >
          <Play size={9} />
        </button>
      </div>
      <p className="text-[9px] text-fg-muted mt-0.5 truncate font-mono">
        pos {shot.position.map((v) => v.toFixed(1)).join(', ')} · fov {Math.round(shot.fov)}
        {shot.description && <span className="text-fg-muted/60"> — {shot.description}</span>}
      </p>
    </div>
  )
}