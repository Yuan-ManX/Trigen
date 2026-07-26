// Overall layout container: top bar + left chat + center canvas + right panel, panels are collapsible
// Includes keyboard shortcuts: Space=toggle mode, Delete=remove, Ctrl+D=duplicate
import { AnimatePresence, motion } from 'framer-motion'
import { PanelLeftOpen, PanelRightOpen } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { fetchScene } from '../../api/client'
import { useScene } from '../../store/useScene'
import { useWebSocket } from '../../hooks/useWebSocket'
import { ChatPanel } from '../chat/ChatPanel'
import { EditorCanvas } from '../canvas/EditorCanvas'
import { RightPanel } from '../sidebar/RightPanel'
import { TopToolbar } from '../toolbar/TopToolbar'

type EditorMode = 'edit' | 'run'

export function AppShell() {
  // Automatically establish WebSocket connection
  const { sessionId } = useWebSocket()
  const setScene = useScene((s) => s.setScene)

  const [chatOpen, setChatOpen] = useState(true)
  const [rightOpen, setRightOpen] = useState(true)
  const [mode, setMode] = useState<EditorMode>('edit')

  const selectedId = useScene((s) => s.selectedId)
  const removeObject = useScene((s) => s.removeObject)
  const duplicateObject = useScene((s) => s.duplicateObject)
  const undo = useScene((s) => s.undo)
  const redo = useScene((s) => s.redo)

  // Load the existing scene of the current session on startup
  useEffect(() => {
    fetchScene(sessionId)
      .then((s) => setScene(s))
      .catch(() => {
        /* Stay silent when the backend is not ready, wait for WS push */
      })
  }, [sessionId, setScene])

  const toggleMode = useCallback(() => {
    setMode((m) => (m === 'edit' ? 'run' : 'edit'))
  }, [])

  // Keyboard shortcuts
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      // Ignore when typing in input/textarea
      const target = e.target as HTMLElement
      if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA') return

      // Space: toggle edit/run mode
      if (e.code === 'Space') {
        e.preventDefault()
        toggleMode()
        return
      }

      // Only process the following in edit mode
      if (mode !== 'edit') return

      // Ctrl/Cmd+Z: undo, Ctrl/Cmd+Shift+Z: redo
      if ((e.ctrlKey || e.metaKey) && e.key === 'z') {
        e.preventDefault()
        if (e.shiftKey) {
          redo()
        } else {
          undo()
        }
        return
      }

      // Ctrl/Cmd+Y: redo (alternative)
      if ((e.ctrlKey || e.metaKey) && e.key === 'y') {
        e.preventDefault()
        redo()
        return
      }

      // Delete/Backspace: remove selected object
      if ((e.key === 'Delete' || e.key === 'Backspace') && selectedId) {
        e.preventDefault()
        removeObject(selectedId)
        return
      }

      // Ctrl/Cmd+D: duplicate selected object
      if ((e.ctrlKey || e.metaKey) && e.key === 'd' && selectedId) {
        e.preventDefault()
        duplicateObject(selectedId)
        return
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [mode, selectedId, removeObject, duplicateObject, undo, redo, toggleMode])

  return (
    <div className="flex flex-col h-screen w-screen overflow-hidden bg-bg-base text-fg-primary">
      <TopToolbar mode={mode} onToggleMode={toggleMode} />

      <div className="flex flex-1 min-h-0">
        {/* Left chat panel */}
        <AnimatePresence initial={false}>
          {chatOpen ? (
            <motion.div
              key="chat"
              initial={{ width: 0, opacity: 0 }}
              animate={{ width: 440, opacity: 1 }}
              exit={{ width: 0, opacity: 0 }}
              transition={{ duration: 0.22, ease: 'easeInOut' }}
              className="overflow-hidden"
            >
              <ChatPanel onCollapse={() => setChatOpen(false)} />
            </motion.div>
          ) : (
            <motion.button
              key="chat-rail"
              initial={{ width: 0, opacity: 0 }}
              animate={{ width: 44, opacity: 1 }}
              exit={{ width: 0, opacity: 0 }}
              transition={{ duration: 0.22, ease: 'easeInOut' }}
              onClick={() => setChatOpen(true)}
              aria-label="Expand chat panel"
              className="shrink-0 flex flex-col items-center gap-2 w-11 border-r border-border bg-bg-panel text-fg-muted hover:text-fg-primary pt-3"
            >
              <PanelLeftOpen size={16} />
              <span className="text-[10px] [writing-mode:vertical-rl]">Chat</span>
            </motion.button>
          )}
        </AnimatePresence>

        {/* Center 3D canvas */}
        <main className="relative flex-1 min-w-0 bg-bg-base">
          <EditorCanvas mode={mode} />
          {/* Watermark at the bottom-left of the canvas */}
          <div className="pointer-events-none absolute bottom-3 left-3 text-[10px] font-mono text-fg-muted/60">
            {mode === 'edit'
              ? 'Trigen Editor · Drag to orbit · Scroll to zoom · Click to select'
              : 'Trigen Player · Auto-rotating · Press Edit to modify'}
          </div>
        </main>

        {/* Right panel */}
        <AnimatePresence initial={false}>
          {rightOpen && mode === 'edit' ? (
            <motion.div
              key="right"
              initial={{ width: 0, opacity: 0 }}
              animate={{ width: 280, opacity: 1 }}
              exit={{ width: 0, opacity: 0 }}
              transition={{ duration: 0.22, ease: 'easeInOut' }}
              className="overflow-hidden"
            >
              <RightPanel onCollapse={() => setRightOpen(false)} />
            </motion.div>
          ) : mode === 'run' ? null : (
            <motion.button
              key="right-rail"
              initial={{ width: 0, opacity: 0 }}
              animate={{ width: 44, opacity: 1 }}
              exit={{ width: 0, opacity: 0 }}
              transition={{ duration: 0.22, ease: 'easeInOut' }}
              onClick={() => setRightOpen(true)}
              aria-label="Expand right panel"
              className="shrink-0 flex flex-col items-center gap-2 w-11 border-l border-border bg-bg-panel text-fg-muted hover:text-fg-primary pt-3"
            >
              <PanelRightOpen size={16} />
              <span className="text-[10px]">Panel</span>
            </motion.button>
          )}
        </AnimatePresence>
      </div>
    </div>
  )
}
