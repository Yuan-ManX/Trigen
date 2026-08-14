// Top toolbar: Logo + tagline, with mode toggle / undo-redo / actions menu
import { motion, AnimatePresence } from 'framer-motion'
import {
  ChevronDown,
  Download,
  GitCommitVertical,
  LayoutGrid,
  Loader2,
  Paintbrush,
  Pause,
  Play,
  Redo2,
  RotateCcw,
  Settings2,
  Sparkles,
  Triangle,
  Undo2,
  Workflow,
} from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { executeTool, fetchCheckpoints, resetScene, restoreCheckpoint } from '../../api/client'
import type { CheckpointEntry } from '../../types'
import { useChat } from '../../store/useChat'
import { useScene } from '../../store/useScene'
import { MaterialLibrary } from './MaterialLibrary'
import { NodeGraphView } from './NodeGraphView'
import { SceneTemplates } from './SceneTemplates'
import { SmartLayout } from './SmartLayout'

interface TopToolbarProps {
  mode: 'edit' | 'run'
  onToggleMode: () => void
}

/** Dropdown menu item */
interface MenuItem {
  id: string
  label: string
  description: string
  icon: typeof Download
  action: () => void
  disabled?: boolean
  danger?: boolean
  loading?: boolean
}

/** Post-FX quick-toggle cycle. Each click advances to the next preset and
 *  applies it directly to the scene's post_processing config via the backend
 *  apply_post_fx / reset_postfx tools. Order matches the product spec:
 *  no effects → bloom → cinematic → noir → reset (then loops to no effects). */
interface PostFxPreset {
  id: string
  label: string
  tool: string
  args: Record<string, unknown>
}

const POSTFX_CYCLE: PostFxPreset[] = [
  { id: 'off', label: 'Post-FX: Off', tool: 'reset_postfx', args: {} },
  { id: 'bloom', label: 'Post-FX: Bloom', tool: 'apply_post_fx', args: { bloom: true } },
  {
    id: 'cinematic',
    label: 'Post-FX: Cinematic',
    tool: 'apply_post_fx',
    args: { bloom: true, color_grading: 'cinematic', tone_mapping: 'aces_filmic' },
  },
  {
    id: 'noir',
    label: 'Post-FX: Noir',
    tool: 'apply_post_fx',
    args: { color_grading: 'noir', vignette: true, grain: 0.4, tone_mapping: 'filmic' },
  },
  { id: 'reset', label: 'Post-FX: Reset', tool: 'reset_postfx', args: {} },
]

/** Format a unix timestamp (seconds) as a compact local string for snapshots. */
function fmtSnapshotTime(ts: number): string {
  try {
    return new Date(ts * 1000).toLocaleString(undefined, {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return ''
  }
}

export function TopToolbar({ mode, onToggleMode }: TopToolbarProps) {
  const sessionId = useChat((s) => s.sessionId)
  const send = useChat((s) => s.send)
  const scene = useScene((s) => s.scene)
  const clearScene = useScene((s) => s.clear)
  const undo = useScene((s) => s.undo)
  const redo = useScene((s) => s.redo)
  const canUndo = useScene((s) => s.past.length > 0)
  const canRedo = useScene((s) => s.future.length > 0)

  const [resetting, setResetting] = useState(false)
  const [showTemplates, setShowTemplates] = useState(false)
  const [showMaterialLibrary, setShowMaterialLibrary] = useState(false)
  const [showNodeGraph, setShowNodeGraph] = useState(false)
  const [showSmartLayout, setShowSmartLayout] = useState(false)
  const [menuOpen, setMenuOpen] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)
  // Snapshots quick-access dropdown state (last 3 revisions, one-tap restore)
  const [showSnapshots, setShowSnapshots] = useState(false)
  const [snapshots, setSnapshots] = useState<CheckpointEntry[]>([])
  const [snapshotsLoading, setSnapshotsLoading] = useState(false)
  const [restoringRev, setRestoringRev] = useState<number | null>(null)
  const snapshotsRef = useRef<HTMLDivElement>(null)
  // Post-FX quick-toggle cycle state (off → bloom → cinematic → noir → reset)
  const [postfxIndex, setPostfxIndex] = useState(0)
  const [postfxBusy, setPostfxBusy] = useState(false)
  const isRun = mode === 'run'

  // Close menu when clicking outside
  useEffect(() => {
    if (!menuOpen) return
    const handler = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [menuOpen])

  // Close snapshots dropdown when clicking outside
  useEffect(() => {
    if (!showSnapshots) return
    const handler = (e: MouseEvent) => {
      if (snapshotsRef.current && !snapshotsRef.current.contains(e.target as Node)) {
        setShowSnapshots(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [showSnapshots])

  /** Export the current scene as a JSON file (client-side download) */
  const handleExport = () => {
    setMenuOpen(false)
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
    setMenuOpen(false)
    const ok = window.confirm('Reset the current scene? All objects will be cleared.')
    if (!ok) return
    setResetting(true)
    try {
      const fresh = await resetScene(sessionId)
      clearScene()
      useScene.getState().setScene(fresh)
    } catch {
      clearScene()
    } finally {
      setResetting(false)
    }
  }

  /** Fetch the three most recent snapshots for the quick-access dropdown. */
  const loadSnapshots = useCallback(async () => {
    setSnapshotsLoading(true)
    try {
      const data = await fetchCheckpoints(3)
      setSnapshots(data.checkpoints ?? [])
    } catch {
      setSnapshots([])
    } finally {
      setSnapshotsLoading(false)
    }
  }, [])

  /** Toggle the snapshots dropdown, refreshing the list when opening. */
  const toggleSnapshots = () => {
    if (isRun) return
    setShowSnapshots((v) => {
      if (!v) void loadSnapshots()
      return !v
    })
  }

  /** Restore a snapshot revision into the live scene. */
  const handleRestoreSnapshot = async (entry: CheckpointEntry) => {
    if (restoringRev !== null) return
    setRestoringRev(entry.revision)
    try {
      const result = await restoreCheckpoint(entry.revision, sessionId)
      useScene.getState().setScene(result.scene)
      setShowSnapshots(false)
    } catch {
      /* keep the dropdown open so the user can retry */
    } finally {
      setRestoringRev(null)
    }
  }

  /** Advance the Post-FX cycle by one step and apply the preset to the scene. */
  const cyclePostFx = async () => {
    if (postfxBusy || isRun) return
    setPostfxBusy(true)
    const nextIndex = (postfxIndex + 1) % POSTFX_CYCLE.length
    const preset = POSTFX_CYCLE[nextIndex]
    try {
      const prev = useScene.getState().scene
      const res = await executeTool(preset.tool, preset.args, sessionId)
      if (res.scene) useScene.getState().commitScene(res.scene, prev)
      setPostfxIndex(nextIndex)
    } catch {
      /* leave the current look untouched on failure */
    } finally {
      setPostfxBusy(false)
    }
  }

  // Menu items
  const menuItems: MenuItem[] = [
    {
      id: 'templates',
      label: 'Scene Templates',
      description: 'Browse pre-built scene templates',
      icon: LayoutGrid,
      action: () => {
        setMenuOpen(false)
        setShowTemplates(true)
      },
      disabled: isRun,
    },
    {
      id: 'materials',
      label: 'Material Library',
      description: 'Apply material presets to objects',
      icon: Paintbrush,
      action: () => {
        setMenuOpen(false)
        setShowMaterialLibrary(true)
      },
      disabled: isRun,
    },
    {
      id: 'pipeline',
      label: 'Pipeline Node Graph',
      description: 'Visually compose and run multi-step pipelines',
      icon: Workflow,
      action: () => {
        setMenuOpen(false)
        setShowNodeGraph(true)
      },
      disabled: isRun,
    },
    {
      id: 'smart-layout',
      label: 'Smart Layout',
      description: 'Auto-arrange objects into a grid, ring, or scatter',
      icon: Sparkles,
      action: () => {
        setMenuOpen(false)
        setShowSmartLayout(true)
      },
      disabled: isRun,
    },
    {
      id: 'export',
      label: 'Export Scene',
      description: 'Download scene as JSON file',
      icon: Download,
      action: handleExport,
      disabled: isRun,
    },
    {
      id: 'reset',
      label: 'Reset Scene',
      description: 'Clear all objects and start fresh',
      icon: RotateCcw,
      action: handleReset,
      disabled: resetting || isRun,
      danger: true,
      loading: resetting,
    },
  ]

  return (
    <>
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

          {/* Quick-access: Snapshots + Post-FX */}
          <div className="flex items-center gap-0.5 rounded-md border border-border bg-bg-elevated p-0.5">
            {/* Snapshots dropdown — last 3 revisions with one-tap restore */}
            <div ref={snapshotsRef} className="relative">
              <button
                onClick={toggleSnapshots}
                disabled={isRun}
                className="flex items-center justify-center w-7 h-7 rounded text-fg-secondary hover:text-fg-primary hover:bg-bg-hover transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
                title="Snapshots — save & restore revisions"
              >
                <GitCommitVertical size={13} />
              </button>
              <AnimatePresence>
                {showSnapshots && (
                  <motion.div
                    initial={{ opacity: 0, y: -8, scale: 0.96 }}
                    animate={{ opacity: 1, y: 0, scale: 1 }}
                    exit={{ opacity: 0, y: -8, scale: 0.96 }}
                    transition={{ duration: 0.15 }}
                    className="absolute top-full right-0 mt-1.5 w-60 rounded-md border border-border bg-bg-elevated shadow-lg overflow-hidden z-50"
                  >
                    <div className="px-3 py-1.5 text-[10px] uppercase tracking-wider text-fg-muted border-b border-border-subtle flex items-center justify-between">
                      <span>Snapshots</span>
                      <span className="text-fg-muted/60 normal-case tracking-normal">
                        {snapshots.length} rev{snapshots.length === 1 ? '' : 's'}
                      </span>
                    </div>
                    <div className="py-1 max-h-64 overflow-y-auto">
                      {snapshotsLoading ? (
                        <div className="flex items-center justify-center gap-1.5 px-3 py-3 text-[10px] text-fg-muted">
                          <Loader2 size={11} className="animate-spin" />
                          Loading…
                        </div>
                      ) : snapshots.length === 0 ? (
                        <div className="px-3 py-3 text-[10px] text-fg-muted leading-relaxed">
                          No snapshots yet. Say “save a snapshot” to the Agent, or use the Checkpoints panel.
                        </div>
                      ) : (
                        snapshots.map((entry) => (
                          <div
                            key={entry.revision}
                            className="group flex items-start gap-2 px-3 py-1.5 hover:bg-bg-hover transition-colors"
                          >
                            <span className="mt-px px-1.5 py-px rounded text-[9.5px] font-mono font-semibold border text-accent-purple border-accent-purple/40 bg-accent-purple/10">
                              R{entry.revision}
                            </span>
                            <div className="flex-1 min-w-0">
                              <div className="text-[10.5px] text-fg-primary leading-snug truncate">
                                {entry.description || `Revision ${entry.revision}`}
                              </div>
                              <div className="text-[9px] text-fg-muted font-mono">
                                {fmtSnapshotTime(entry.created_at)}
                                {' · '}
                                {entry.summary?.object_count ?? 0} obj
                              </div>
                            </div>
                            <button
                              onClick={() => handleRestoreSnapshot(entry)}
                              disabled={restoringRev !== null}
                              title="Restore this revision"
                              className="flex items-center gap-1 text-[9.5px] px-1.5 py-0.5 rounded border border-border text-fg-muted hover:text-accent-cyan hover:border-accent-cyan/40 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                            >
                              {restoringRev === entry.revision ? (
                                <Loader2 size={9} className="animate-spin" />
                              ) : (
                                <RotateCcw size={9} />
                              )}
                              Restore
                            </button>
                          </div>
                        ))
                      )}
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>

            {/* Post-FX cycle toggle — off → bloom → cinematic → noir → reset */}
            <button
              onClick={cyclePostFx}
              disabled={isRun || postfxBusy}
              className={`flex items-center justify-center w-7 h-7 rounded transition-colors disabled:opacity-30 disabled:cursor-not-allowed ${
                postfxIndex > 0 && postfxIndex < POSTFX_CYCLE.length - 1
                  ? 'text-rose-300 bg-rose-500/10 hover:bg-rose-500/20'
                  : 'text-fg-secondary hover:text-fg-primary hover:bg-bg-hover'
              }`}
              title={POSTFX_CYCLE[postfxIndex].label}
            >
              {postfxBusy ? <Loader2 size={13} className="animate-spin" /> : <Sparkles size={13} />}
            </button>
          </div>

          {/* Consolidated actions menu */}
          <div ref={menuRef} className="relative">
            <button
              onClick={() => setMenuOpen((v) => !v)}
              disabled={isRun}
              className="flex items-center gap-1.5 text-xs text-fg-secondary hover:text-fg-primary px-2.5 py-1.5 rounded-md border border-border hover:border-accent-cyan/40 hover:bg-bg-hover transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              title="Settings"
            >
              <Settings2 size={13} />
              <span className="hidden sm:inline">Settings</span>
              <ChevronDown size={10} className={`transition-transform ${menuOpen ? 'rotate-180' : ''}`} />
            </button>

            <AnimatePresence>
              {menuOpen && (
                <motion.div
                  initial={{ opacity: 0, y: -8, scale: 0.96 }}
                  animate={{ opacity: 1, y: 0, scale: 1 }}
                  exit={{ opacity: 0, y: -8, scale: 0.96 }}
                  transition={{ duration: 0.15 }}
                  className="absolute top-full right-0 mt-1.5 w-64 rounded-md border border-border bg-bg-elevated shadow-lg overflow-hidden z-50"
                >
                  <div className="px-3 py-1.5 text-[10px] uppercase tracking-wider text-fg-muted border-b border-border-subtle">
                    Actions
                  </div>
                  <div className="py-1">
                    {menuItems.map((item) => {
                      const Icon = item.icon
                      return (
                        <button
                          key={item.id}
                          onClick={item.action}
                          disabled={item.disabled}
                          className={`w-full flex items-start gap-2.5 px-3 py-2 text-left transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${
                            item.danger
                              ? 'hover:bg-rose-500/10'
                              : 'hover:bg-bg-hover'
                          }`}
                        >
                          <div className={`shrink-0 mt-0.5 ${item.danger ? 'text-rose-400' : 'text-accent-cyan'}`}>
                            {item.loading ? (
                              <Loader2 size={14} className="animate-spin" />
                            ) : (
                              <Icon size={14} />
                            )}
                          </div>
                          <div className="flex-1 min-w-0">
                            <div className={`text-xs font-medium ${item.danger ? 'text-rose-400' : 'text-fg-primary'}`}>
                              {item.label}
                            </div>
                            <div className="text-[10px] text-fg-muted">{item.description}</div>
                          </div>
                        </button>
                      )
                    })}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </div>
      </header>

      {/* Scene templates dialog */}
      <SceneTemplates
        open={showTemplates}
        onClose={() => setShowTemplates(false)}
        onSelect={(prompt) => send(prompt)}
      />

      {/* Material library dialog */}
      <MaterialLibrary
        open={showMaterialLibrary}
        onClose={() => setShowMaterialLibrary(false)}
      />

      {/* Pipeline node graph editor */}
      <NodeGraphView
        open={showNodeGraph}
        onClose={() => setShowNodeGraph(false)}
      />

      {/* Smart Layout dialog */}
      <SmartLayout
        open={showSmartLayout}
        onClose={() => setShowSmartLayout(false)}
      />
    </>
  )
}
