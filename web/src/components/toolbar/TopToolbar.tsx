// Top toolbar: Logo + tagline, with mode toggle / undo-redo / export / reset
import { motion } from 'framer-motion'
import {
  Download,
  Loader2,
  Pause,
  Play,
  Redo2,
  RotateCcw,
  Triangle,
  Undo2,
} from 'lucide-react'
import { useState } from 'react'
import { resetScene } from '../../api/client'
import { useChat } from '../../store/useChat'
import { useScene } from '../../store/useScene'

interface TopToolbarProps {
  mode: 'edit' | 'run'
  onToggleMode: () => void
}

export function TopToolbar({ mode, onToggleMode }: TopToolbarProps) {
  const sessionId = useChat((s) => s.sessionId)
  const scene = useScene((s) => s.scene)
  const clearScene = useScene((s) => s.clear)
  const undo = useScene((s) => s.undo)
  const redo = useScene((s) => s.redo)
  const canUndo = useScene((s) => s.past.length > 0)
  const canRedo = useScene((s) => s.future.length > 0)

  const [resetting, setResetting] = useState(false)
  const isRun = mode === 'run'

  /** Export the current scene as a JSON file (client-side download) */
  const handleExport = () => {
    const blob = new Blob([JSON.stringify(scene, null, 2)], {
      type: 'application/json',
    })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `trigen-scene-${sessionId}.json`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }

  /** Reset the scene: call the backend and clear the local state */
  const handleReset = async () => {
    if (resetting) return
    const ok = window.confirm('Reset the current scene? All objects will be cleared.')
    if (!ok) return
    setResetting(true)
    try {
      const fresh = await resetScene(sessionId)
      clearScene()
      useScene.getState().setScene(fresh)
    } catch {
      // Still clear the local scene when the backend is unavailable
      clearScene()
    } finally {
      setResetting(false)
    }
  }

  return (
    <header className="flex items-center justify-between h-12 px-4 border-b border-border bg-bg-panel/90 backdrop-blur z-10">
      {/* Left: logo + tagline */}
      <div className="flex items-center gap-2.5">
        <motion.div
          initial={{ rotate: -20, opacity: 0 }}
          animate={{ rotate: 0, opacity: 1 }}
          transition={{ duration: 0.4 }}
          className="w-7 h-7 rounded-md bg-gradient-to-br from-accent-cyan to-accent-gold flex items-center justify-center shadow-glow"
        >
          <Triangle size={14} className="text-bg-base" fill="currentColor" />
        </motion.div>
        <div className="flex items-baseline gap-2">
          <span className="font-sans font-bold text-fg-primary text-base tracking-tight">
            Trigen
          </span>
          <span className="text-[11px] text-fg-muted hidden sm:inline">
            AI-Native 3D Creation Agent Platform
          </span>
        </div>
      </div>

      {/* Center: mode toggle */}
      <div className="flex items-center gap-1 rounded-md border border-border bg-bg-elevated p-0.5">
        <button
          onClick={onToggleMode}
          className={`flex items-center gap-1.5 px-3 py-1 rounded text-[11px] font-medium transition-colors ${
            !isRun
              ? 'bg-accent-cyan/15 text-accent-cyan'
              : 'text-fg-muted hover:text-fg-secondary'
          }`}
        >
          Edit
        </button>
        <button
          onClick={onToggleMode}
          className={`flex items-center gap-1.5 px-3 py-1 rounded text-[11px] font-medium transition-colors ${
            isRun
              ? 'bg-accent-gold/15 text-accent-gold'
              : 'text-fg-muted hover:text-fg-secondary'
          }`}
        >
          {isRun ? <Pause size={12} /> : <Play size={12} />}
          Run
        </button>
      </div>

      {/* Right actions */}
      <div className="flex items-center gap-2">
        {/* Undo / Redo */}
        <div className="flex items-center gap-0.5 rounded-md border border-border bg-bg-elevated p-0.5">
          <button
            onClick={undo}
            disabled={!canUndo || isRun}
            className="flex items-center justify-center w-7 h-7 rounded text-fg-secondary hover:text-fg-primary hover:bg-bg-hover transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
            title="Undo (Ctrl+Z)"
          >
            <Undo2 size={13} />
          </button>
          <button
            onClick={redo}
            disabled={!canRedo || isRun}
            className="flex items-center justify-center w-7 h-7 rounded text-fg-secondary hover:text-fg-primary hover:bg-bg-hover transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
            title="Redo (Ctrl+Shift+Z)"
          >
            <Redo2 size={13} />
          </button>
        </div>

        <button
          onClick={handleExport}
          disabled={isRun}
          className="flex items-center gap-1.5 text-xs text-fg-secondary hover:text-fg-primary px-2.5 py-1.5 rounded-md border border-border hover:border-accent-cyan/40 hover:bg-bg-hover transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          title="Export scene as JSON"
        >
          <Download size={13} />
          <span className="hidden sm:inline">Export</span>
        </button>

        <button
          onClick={handleReset}
          disabled={resetting || isRun}
          className="flex items-center gap-1.5 text-xs text-fg-secondary hover:text-fg-primary px-2.5 py-1.5 rounded-md border border-border hover:border-rose-400/40 hover:bg-bg-hover transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          title="Reset scene"
        >
          {resetting ? (
            <Loader2 size={13} className="animate-spin" />
          ) : (
            <RotateCcw size={13} />
          )}
          <span className="hidden sm:inline">Reset</span>
        </button>
      </div>
    </header>
  )
}
