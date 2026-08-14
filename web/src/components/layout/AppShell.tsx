// Overall layout container: top bar + left chat + center canvas + right panel + status bar
// Includes keyboard shortcuts: Space=toggle mode, Delete=remove, Ctrl+D=duplicate, ?=shortcuts
import { AnimatePresence, motion } from 'framer-motion'
import { PanelLeftOpen, PanelRightOpen } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { fetchScene } from '../../api/client'
import { useScene } from '../../store/useScene'
import { useEditor } from '../../store/useEditor'
import { usePlayback } from '../../store/usePlayback'
import { useWebSocket } from '../../hooks/useWebSocket'
import { ChatPanel } from '../chat/ChatPanel'
import { EditorCanvas } from '../canvas/EditorCanvas'
import { SceneStateMachine } from '../canvas/SceneStateMachine'
import { StatusBar } from '../canvas/StatusBar'
import { RightPanel } from '../sidebar/RightPanel'
import { TopToolbar } from '../toolbar/TopToolbar'
import { KeyboardShortcuts } from '../toolbar/KeyboardShortcuts'
import { CommandPalette } from '../toolbar/CommandPalette'
import { OnboardingHints, useReopenOnboarding } from '../OnboardingHints'

export function AppShell() {
  // Automatically establish WebSocket connection
  const { sessionId } = useWebSocket()
  const setScene = useScene((s) => s.setScene)

  const [chatOpen, setChatOpen] = useState(true)
  const [rightOpen, setRightOpen] = useState(true)
  // Editor mode (edit/run) is owned by the useEditor store so the Agent
  // can toggle it via the editor_set_mode delta. Local UI buttons call
  // setEditorMode; the store is the single source of truth.
  const mode = useEditor((s) => s.editorMode)
  const setEditorMode = useEditor((s) => s.setEditorMode)
  // Panel visibility is also reflected in the editor store so the Agent
  // can drive it through editor_toggle_panel deltas. The local state
  // remains the source of truth for the layout; this effect syncs the
  // store's requested visibility back into the local state whenever the
  // panelToggleToken changes (i.e. the Agent issued a toggle request).
  const chatPanelVisible = useEditor((s) => s.chatPanelVisible)
  const rightPanelVisible = useEditor((s) => s.rightPanelVisible)
  const panelToggleToken = useEditor((s) => s.panelToggleToken)
  const [lastPanelToken, setLastPanelToken] = useState(0)
  useEffect(() => {
    if (panelToggleToken === lastPanelToken) return
    setLastPanelToken(panelToggleToken)
    setChatOpen(chatPanelVisible)
    setRightOpen(rightPanelVisible)
  }, [panelToggleToken, chatPanelVisible, rightPanelVisible, lastPanelToken])
  const [showShortcuts, setShowShortcuts] = useState(false)
  const [showCommandPalette, setShowCommandPalette] = useState(false)
  const { forceOpen: onboardingForceOpen, reopen: reopenOnboarding, handleClose: handleOnboardingClose } =
    useReopenOnboarding()

  const selectedId = useScene((s) => s.selectedId)
  const selectedIds = useScene((s) => s.selectedIds)
  const removeObject = useScene((s) => s.removeObject)
  const duplicateObject = useScene((s) => s.duplicateObject)
  const undo = useScene((s) => s.undo)
  const redo = useScene((s) => s.redo)
  const selectAll = useScene((s) => s.selectAll)
  const clearSelection = useScene((s) => s.clearSelection)
  const groupObjects = useScene((s) => s.groupObjects)
  const sceneObjects = useScene((s) => s.scene.objects)

  // Editor store hooks for the new quick-action shortcuts
  const setTransformMode = useEditor((s) => s.setTransformMode)
  const setViewportCamera = useEditor((s) => s.setViewportCamera)
  const setGrid = useScene((s) => s.setGrid)
  const gridVisible = useScene((s) => s.scene.grid_visible)
  const minimapEnabled = useEditor((s) => s.minimapEnabled)
  const setMinimapEnabled = useEditor((s) => s.setMinimapEnabled)
  const gridSnapEnabled = useEditor((s) => s.gridSnapEnabled)
  const snapIncrement = useEditor((s) => s.snapIncrement)
  const setGridSnap = useEditor((s) => s.setGridSnap)
  const renderQuality = useEditor((s) => s.renderQuality)
  const setRenderQuality = useEditor((s) => s.setRenderQuality)
  const viewportShading = useEditor((s) => s.viewportShading)
  const setViewportShading = useEditor((s) => s.setViewportShading)
  const requestCapture = useEditor((s) => s.requestCapture)

  // Playback store hooks for the playback shortcuts
  const isPlaying = usePlayback((s) => s.isPlaying)
  const play = usePlayback((s) => s.play)
  const pause = usePlayback((s) => s.pause)
  const stop = usePlayback((s) => s.stop)

  // Load the existing scene of the current session on startup
  useEffect(() => {
    fetchScene(sessionId)
      .then((s) => setScene(s))
      .catch(() => {
        /* Stay silent when the backend is not ready, wait for WS push */
      })
  }, [sessionId, setScene])

  const toggleMode = useCallback(() => {
    setEditorMode(mode === 'edit' ? 'run' : 'edit')
  }, [mode, setEditorMode])

  // Keyboard shortcuts
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      // Cmd/Ctrl+K: open the command palette (works even from input/textarea)
      if ((e.metaKey || e.ctrlKey) && (e.key === 'k' || e.key === 'K')) {
        e.preventDefault()
        setShowCommandPalette((v) => !v)
        return
      }

      // Ignore when typing in input/textarea
      const target = e.target as HTMLElement
      if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA') return

      // ? or Shift+/: toggle shortcuts overlay
      if (e.key === '?' || (e.shiftKey && e.key === '/')) {
        e.preventDefault()
        setShowShortcuts((v) => !v)
        return
      }

      // Escape: close shortcuts overlay
      if (e.key === 'Escape' && showShortcuts) {
        setShowShortcuts(false)
        return
      }

      // Ctrl/Cmd+E: toggle edit/run mode
      if ((e.ctrlKey || e.metaKey) && e.key === 'e') {
        e.preventDefault()
        toggleMode()
        return
      }

      // Ctrl/Cmd+B: toggle left chat panel; Ctrl/Cmd+Shift+B: toggle right panel
      if ((e.ctrlKey || e.metaKey) && (e.key === 'b' || e.key === 'B')) {
        e.preventDefault()
        if (e.shiftKey) {
          setRightOpen((v) => !v)
          useEditor.getState().setPanelVisibility('right')
        } else {
          setChatOpen((v) => !v)
          useEditor.getState().setPanelVisibility('chat')
        }
        return
      }

      // Ctrl/Cmd+G: group selected objects
      if ((e.ctrlKey || e.metaKey) && (e.key === 'g' || e.key === 'G')) {
        e.preventDefault()
        if (selectedIds.length >= 2) groupObjects(selectedIds)
        return
      }

      // Ctrl/Cmd+A: select all; Ctrl/Cmd+Shift+A: deselect all
      if ((e.ctrlKey || e.metaKey) && (e.key === 'a' || e.key === 'A')) {
        e.preventDefault()
        if (e.shiftKey) clearSelection()
        else selectAll()
        return
      }

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

      // Single-letter shortcuts that don't conflict with input editing.
      // Avoid intercepting when a meta/ctrl modifier is held so we don't
      // shadow browser commands.
      if (e.metaKey || e.ctrlKey || e.altKey) return

      // 1/2/3: transform mode
      if (e.key === '1') {
        e.preventDefault()
        setTransformMode('translate')
        return
      }
      if (e.key === '2') {
        e.preventDefault()
        setTransformMode('rotate')
        return
      }
      if (e.key === '3') {
        e.preventDefault()
        setTransformMode('scale')
        return
      }
      // F: focus camera on selected object
      if (e.key === 'f' || e.key === 'F') {
        const o = sceneObjects.find((x) => x.id === selectedId)
        if (o) {
          const [x, y, z] = o.transform.position
          setViewportCamera([x, y + 2, z + 4], [x, y, z], true)
        }
        return
      }
      // A: frame all objects (no selectedId check — frame all works regardless)
      if (e.key === 'a' || e.key === 'A') {
        if (sceneObjects.length === 0) return
        const cx = sceneObjects.reduce((s, o) => s + o.transform.position[0], 0) / sceneObjects.length
        const cy = sceneObjects.reduce((s, o) => s + o.transform.position[1], 0) / sceneObjects.length
        const cz = sceneObjects.reduce((s, o) => s + o.transform.position[2], 0) / sceneObjects.length
        const span = Math.max(
          4,
          ...sceneObjects.map((o) => {
            const dx = o.transform.position[0] - cx
            const dy = o.transform.position[1] - cy
            const dz = o.transform.position[2] - cz
            return Math.sqrt(dx * dx + dy * dy + dz * dz)
          }),
        )
        setViewportCamera([cx, cy + span * 0.8, cz + span * 1.4], [cx, cy, cz], true)
        return
      }
      // G: toggle grid visibility
      if (e.key === 'g' || e.key === 'G') {
        e.preventDefault()
        setGrid(!gridVisible)
        return
      }
      // M: toggle minimap
      if (e.key === 'm' || e.key === 'M') {
        e.preventDefault()
        setMinimapEnabled(!minimapEnabled)
        return
      }
      // Shift+S: toggle grid snap
      if (e.shiftKey && (e.key === 'S' || e.key === 's')) {
        e.preventDefault()
        setGridSnap(!gridSnapEnabled, snapIncrement)
        return
      }
      // R: cycle render quality
      if (e.key === 'r' || e.key === 'R') {
        e.preventDefault()
        const order = ['low', 'medium', 'high'] as const
        const idx = order.indexOf(renderQuality)
        setRenderQuality(order[(idx + 1) % order.length])
        return
      }
      // W: cycle viewport shading (wireframe / solid / material / rendered)
      if (e.key === 'w' || e.key === 'W') {
        e.preventDefault()
        const modes = ['wireframe', 'solid', 'material', 'rendered'] as const
        const idx = modes.indexOf(viewportShading)
        setViewportShading(modes[(idx + 1) % modes.length])
        return
      }
      // C: capture viewport
      if (e.key === 'c' || e.key === 'C') {
        e.preventDefault()
        requestCapture(`viewport_${Date.now()}`)
        return
      }
      // P: play/pause; Shift+P: stop
      if (e.shiftKey && (e.key === 'P' || e.key === 'p')) {
        e.preventDefault()
        stop()
        return
      }
      if (e.key === 'p' || e.key === 'P') {
        e.preventDefault()
        if (isPlaying) pause()
        else play()
        return
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [
    mode,
    selectedId,
    selectedIds,
    removeObject,
    duplicateObject,
    undo,
    redo,
    toggleMode,
    showShortcuts,
    selectAll,
    clearSelection,
    groupObjects,
    setTransformMode,
    setViewportCamera,
    setGrid,
    gridVisible,
    minimapEnabled,
    setMinimapEnabled,
    gridSnapEnabled,
    snapIncrement,
    setGridSnap,
    renderQuality,
    setRenderQuality,
    viewportShading,
    setViewportShading,
    requestCapture,
    isPlaying,
    play,
    pause,
    stop,
    sceneObjects,
  ])

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
              animate={{ width: 400, opacity: 1 }}
              exit={{ width: 0, opacity: 0 }}
              transition={{ duration: 0.22, ease: 'easeInOut' }}
              className="overflow-hidden h-full shrink-0"
            >
              <ChatPanel onCollapse={() => {
                setChatOpen(false)
                useEditor.getState().setPanelVisibility('chat', false)
              }} />
            </motion.div>
          ) : (
            <motion.button
              key="chat-rail"
              initial={{ width: 0, opacity: 0 }}
              animate={{ width: 44, opacity: 1 }}
              exit={{ width: 0, opacity: 0 }}
              transition={{ duration: 0.22, ease: 'easeInOut' }}
              onClick={() => {
                setChatOpen(true)
                useEditor.getState().setPanelVisibility('chat', true)
              }}
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
          {/* Floating scene-state indicator (bottom-right, collapsed by default) */}
          <SceneStateMachine mode={mode} />
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
              className="overflow-hidden shrink-0"
            >
              <RightPanel onCollapse={() => {
                setRightOpen(false)
                useEditor.getState().setPanelVisibility('right', false)
              }} />
            </motion.div>
          ) : mode === 'run' ? null : (
            <motion.button
              key="right-rail"
              initial={{ width: 0, opacity: 0 }}
              animate={{ width: 44, opacity: 1 }}
              exit={{ width: 0, opacity: 0 }}
              transition={{ duration: 0.22, ease: 'easeInOut' }}
              onClick={() => {
                setRightOpen(true)
                useEditor.getState().setPanelVisibility('right', true)
              }}
              aria-label="Expand right panel"
              className="shrink-0 flex flex-col items-center gap-2 w-11 border-l border-border bg-bg-panel text-fg-muted hover:text-fg-primary pt-3"
            >
              <PanelRightOpen size={16} />
              <span className="text-[10px]">Panel</span>
            </motion.button>
          )}
        </AnimatePresence>
      </div>

      {/* Bottom status bar */}
      <StatusBar mode={mode} />

      {/* Keyboard shortcuts overlay */}
      <KeyboardShortcuts open={showShortcuts} onClose={() => setShowShortcuts(false)} />

      {/* Command palette (Cmd/Ctrl+K) */}
      <CommandPalette
        open={showCommandPalette}
        onClose={() => setShowCommandPalette(false)}
        onReopenOnboarding={reopenOnboarding}
      />

      {/* First-visit coachmark tour (auto-shows once, can be reopened from toolbar) */}
      <OnboardingHints forceOpen={onboardingForceOpen} onClose={handleOnboardingClose} />
    </div>
  )
}
