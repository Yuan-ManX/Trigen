// Top toolbar: Logo + tagline, with mode toggle / undo-redo / actions menu
import { motion, AnimatePresence } from 'framer-motion'
import {
  ChevronDown,
  Download,
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
import { useEffect, useRef, useState } from 'react'
import { resetScene } from '../../api/client'
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
