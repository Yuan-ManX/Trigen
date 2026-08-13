// Command Palette (Cmd/Ctrl+K): fuzzy-searchable launcher for tools, skills,
// scene templates, and quick editor actions. Sends a chat message for tools /
// skills / templates, and dispatches local editor actions for quick actions.
import { AnimatePresence, motion } from 'framer-motion'
import {
  Box,
  Camera,
  Command,
  CornerDownLeft,
  Frame,
  Gauge,
  Layers,
  Maximize2,
  PanelLeftOpen,
  PanelRightOpen,
  Play,
  RotateCcw,
  RotateCw,
  Search,
  Sparkles,
  Tag,
  Terminal,
  Wand2,
  HelpCircle,
  type LucideIcon,
} from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import {
  fetchSkills,
  fetchTools,
  type SkillDescriptor,
} from '../../api/client'
import { useChat } from '../../store/useChat'
import { useEditor } from '../../store/useEditor'
import { useScene } from '../../store/useScene'
import type { Annotation } from '../../types'
import { TEMPLATES } from './SceneTemplates'

/** A single searchable command entry. */
interface CommandItem {
  id: string
  title: string
  subtitle: string
  group: 'Templates' | 'Skills' | 'Tools' | 'Actions'
  icon: LucideIcon
  iconClass: string
  keywords: string
  /** Run the command. Receives a sender that posts a chat message. */
  run: (send: (text: string) => void) => void
}

/** Subsequence fuzzy match with word-boundary bonus. Returns 0 when no match. */
function fuzzyScore(query: string, target: string): number {
  if (!query) return 1
  const q = query.toLowerCase()
  const t = target.toLowerCase()
  if (t.includes(q)) {
    // Strong bonus for contiguous substring, extra when at a word boundary.
    const idx = t.indexOf(q)
    const boundaryBefore = idx === 0 || /[\s_-]/.test(t[idx - 1])
    return 100 + q.length - idx + (boundaryBefore ? 5 : 0)
  }
  // Subsequence match: each char of q must appear in t in order.
  let qi = 0
  let score = 0
  let lastIdx = -1
  for (let ti = 0; ti < t.length && qi < q.length; ti++) {
    if (t[ti] === q[qi]) {
      score += 1
      if (lastIdx === -1 || t[lastIdx] === ' ' || t[lastIdx] === '_' || t[lastIdx] === '-') {
        score += 2
      }
      lastIdx = ti
      qi++
    }
  }
  return qi === q.length ? score : 0
}

/** Pick the best score across an item's title + subtitle + keywords. */
function scoreItem(query: string, item: CommandItem): number {
  if (!query) return 1
  return Math.max(
    fuzzyScore(query, item.title) * 2,
    fuzzyScore(query, item.subtitle),
    fuzzyScore(query, item.keywords),
    fuzzyScore(query, item.group),
  )
}

interface CommandPaletteProps {
  open: boolean
  onClose: () => void
  /** Optional callback to re-open the first-visit onboarding tour. */
  onReopenOnboarding?: () => void
}

export function CommandPalette({ open, onClose, onReopenOnboarding }: CommandPaletteProps) {
  const send = useChat((s) => s.send)
  const [query, setQuery] = useState('')
  const [activeIndex, setActiveIndex] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)
  const listRef = useRef<HTMLDivElement>(null)

  // Catalog state
  const [tools, setTools] = useState<{ name: string; description: string }[]>([])
  const [skills, setSkills] = useState<SkillDescriptor[]>([])

  // Editor / scene actions for the "Actions" group
  const undo = useScene((s) => s.undo)
  const redo = useScene((s) => s.redo)
  const gridVisible = useScene((s) => s.scene.grid_visible)
  const setGrid = useScene((s) => s.setGrid)
  const focusSelected = useScene((s) => s.selected)
  const setViewportCamera = useEditor((s) => s.setViewportCamera)
  const setTransformMode = useEditor((s) => s.setTransformMode)
  // Phase 4: additional quick actions — annotation, capture, render quality,
  // editor mode, frame-all, onboarding tour.
  const scene = useScene((s) => s.scene)
  const selectedId = useScene((s) => s.selectedId)
  const addAnnotation = useScene((s) => s.addAnnotation)
  const requestCapture = useEditor((s) => s.requestCapture)
  const renderQuality = useEditor((s) => s.renderQuality)
  const setRenderQuality = useEditor((s) => s.setRenderQuality)
  const editorMode = useEditor((s) => s.editorMode)
  const setEditorMode = useEditor((s) => s.setEditorMode)
  const setMinimapEnabled = useEditor((s) => s.setMinimapEnabled)
  const minimapEnabled = useEditor((s) => s.minimapEnabled)
  const setPanelVisibility = useEditor((s) => s.setPanelVisibility)
  const chatPanelVisible = useEditor((s) => s.chatPanelVisible)
  const rightPanelVisible = useEditor((s) => s.rightPanelVisible)
  const clearSelection = useScene((s) => s.clearSelection)

  // Lazily fetch catalogs when the palette first opens
  useEffect(() => {
    if (!open) return
    if (tools.length === 0) {
      fetchTools()
        .then((res) => setTools(res.tools.map((t) => ({ name: t.name, description: t.description }))))
        .catch(() => {
          /* keep empty */
        })
    }
    if (skills.length === 0) {
      fetchSkills()
        .then(setSkills)
        .catch(() => {
          /* keep empty */
        })
    }
  }, [open, tools.length, skills.length])

  // Reset query + selection each time the palette opens
  useEffect(() => {
    if (open) {
      setQuery('')
      setActiveIndex(0)
      setTimeout(() => inputRef.current?.focus(), 30)
    }
  }, [open])

  // Build the full command list once per render (cheap; catalogs are small).
  const allItems = useMemo<CommandItem[]>(() => {
    const items: CommandItem[] = []

    // Templates
    for (const tpl of TEMPLATES) {
      const Icon = tpl.icon
      items.push({
        id: `tpl-${tpl.id}`,
        title: tpl.name,
        subtitle: tpl.description,
        group: 'Templates',
        icon: Icon,
        iconClass: tpl.color,
        keywords: `${tpl.id} ${tpl.skill ?? ''} template scene ${tpl.objects}`,
        run: (s) => s(tpl.prompt),
      })
    }

    // Skills
    for (const sk of skills) {
      items.push({
        id: `skill-${sk.name}`,
        title: sk.name.replace(/_/g, ' '),
        subtitle: sk.description,
        group: 'Skills',
        icon: Wand2,
        iconClass: 'text-accent-gold',
        keywords: `${sk.name} ${sk.category} skill`,
        run: (s) => s(`Use the ${sk.name} skill`),
      })
    }

    // Tools — chat-driven invocation (Agent decides arguments)
    for (const tool of tools) {
      items.push({
        id: `tool-${tool.name}`,
        title: tool.name.replace(/_/g, ' '),
        subtitle: tool.description,
        group: 'Tools',
        icon: Terminal,
        iconClass: 'text-accent-cyan',
        keywords: `${tool.name} tool`,
        run: (s) => s(`Use the ${tool.name} tool`),
      })
    }

    // Quick editor actions
    items.push({
      id: 'action-undo',
      title: 'Undo',
      subtitle: 'Revert the last scene change',
      group: 'Actions',
      icon: RotateCcw,
      iconClass: 'text-fg-secondary',
      keywords: 'undo revert',
      run: () => undo(),
    })
    items.push({
      id: 'action-redo',
      title: 'Redo',
      subtitle: 'Reapply the last undone change',
      group: 'Actions',
      icon: RotateCw,
      iconClass: 'text-fg-secondary',
      keywords: 'redo reapply',
      run: () => redo(),
    })
    items.push({
      id: 'action-toggle-grid',
      title: 'Toggle Grid',
      subtitle: 'Show or hide the viewport grid',
      group: 'Actions',
      icon: Layers,
      iconClass: 'text-fg-secondary',
      keywords: 'grid toggle visibility',
      run: () => setGrid(!gridVisible),
    })
    items.push({
      id: 'action-move-mode',
      title: 'Move Mode',
      subtitle: 'Switch the transform gizmo to translate',
      group: 'Actions',
      icon: Box,
      iconClass: 'text-fg-secondary',
      keywords: 'translate move gizmo transform',
      run: () => setTransformMode('translate'),
    })

    // Phase 4: extended quick actions.
    items.push({
      id: 'action-add-annotation',
      title: 'Add Annotation',
      subtitle: 'Pin a labeled annotation on the selected object',
      group: 'Actions',
      icon: Tag,
      iconClass: 'text-accent-emerald',
      keywords: 'annotation label note pin tag',
      run: () => {
        const target = scene.objects.find((o) => o.id === selectedId) ?? null
        const id = `note-${Date.now().toString(36)}`
        const position: [number, number, number] = target
          ? (target.transform.position as [number, number, number])
          : [0, 1, 0]
        const annotation: Annotation = {
          id,
          object_id: target ? target.id : null,
          position,
          text: 'New annotation — click to edit',
          title: target ? target.name : 'Scene note',
          color: '#22d3ee',
          visible: true,
        }
        addAnnotation(annotation)
      },
    })
    items.push({
      id: 'action-capture-viewport',
      title: 'Capture Viewport',
      subtitle: 'Save the current viewport as a PNG',
      group: 'Actions',
      icon: Camera,
      iconClass: 'text-accent-cyan',
      keywords: 'capture screenshot png snapshot viewport',
      run: () => requestCapture(`viewport_${Date.now()}`),
    })
    items.push({
      id: 'action-cycle-render-quality',
      title: 'Cycle Render Quality',
      subtitle: `Switch viewport quality (current: ${renderQuality})`,
      group: 'Actions',
      icon: Gauge,
      iconClass: 'text-amber-400',
      keywords: 'render quality low medium high performance',
      run: () => {
        const order: Array<'low' | 'medium' | 'high'> = ['low', 'medium', 'high']
        const idx = order.indexOf(renderQuality)
        setRenderQuality(order[(idx + 1) % order.length])
      },
    })
    items.push({
      id: 'action-toggle-editor-mode',
      title: 'Toggle Edit / Run Mode',
      subtitle: `Switch between authoring and playback (current: ${editorMode})`,
      group: 'Actions',
      icon: Play,
      iconClass: 'text-accent-purple',
      keywords: 'edit run mode play playback preview',
      run: () => setEditorMode(editorMode === 'edit' ? 'run' : 'edit'),
    })
    items.push({
      id: 'action-frame-all',
      title: 'Frame All',
      subtitle: 'Fit the entire scene in the viewport',
      group: 'Actions',
      icon: Maximize2,
      iconClass: 'text-fg-secondary',
      keywords: 'frame fit all scene camera viewport',
      run: () => {
        const objs = scene.objects
        if (objs.length === 0) return
        let minX = Infinity, minY = Infinity, minZ = Infinity
        let maxX = -Infinity, maxY = -Infinity, maxZ = -Infinity
        for (const o of objs) {
          const [x, y, z] = o.transform.position
          if (x < minX) minX = x; if (x > maxX) maxX = x
          if (y < minY) minY = y; if (y > maxY) maxY = y
          if (z < minZ) minZ = z; if (z > maxZ) maxZ = z
        }
        const cx = (minX + maxX) / 2
        const cy = (minY + maxY) / 2
        const cz = (minZ + maxZ) / 2
        const span = Math.max(maxX - minX, maxY - minY, maxZ - minZ, 4)
        setViewportCamera([cx, cy + span * 0.6, cz + span * 1.2], [cx, cy, cz], true)
      },
    })
    items.push({
      id: 'action-focus-selection',
      title: 'Focus Selection',
      subtitle: 'Frame the selected object in the viewport',
      group: 'Actions',
      icon: Frame,
      iconClass: 'text-fg-secondary',
      keywords: 'focus frame selection camera fit',
      run: () => {
        const sel = focusSelected()
        if (sel) {
          const [x, y, z] = sel.transform.position
          setViewportCamera([x, y + 2, z + 4], [x, y, z], true)
        }
      },
    })
    items.push({
      id: 'action-toggle-minimap',
      title: 'Toggle Minimap',
      subtitle: `Show or hide the viewport minimap (current: ${minimapEnabled ? 'on' : 'off'})`,
      group: 'Actions',
      icon: Layers,
      iconClass: 'text-fg-secondary',
      keywords: 'minimap overview overlay toggle',
      run: () => setMinimapEnabled(!minimapEnabled),
    })
    items.push({
      id: 'action-toggle-chat-panel',
      title: 'Toggle Chat Panel',
      subtitle: `Show or hide the left conversation panel (current: ${chatPanelVisible ? 'visible' : 'hidden'})`,
      group: 'Actions',
      icon: PanelLeftOpen,
      iconClass: 'text-accent-cyan',
      keywords: 'chat panel left sidebar toggle show hide collapse',
      run: () => setPanelVisibility('chat'),
    })
    items.push({
      id: 'action-toggle-right-panel',
      title: 'Toggle Right Panel',
      subtitle: `Show or hide the right workspace panel (current: ${rightPanelVisible ? 'visible' : 'hidden'})`,
      group: 'Actions',
      icon: PanelRightOpen,
      iconClass: 'text-accent-purple',
      keywords: 'right panel side workspace sidebar toggle show hide collapse',
      run: () => setPanelVisibility('right'),
    })
    items.push({
      id: 'action-deselect-all',
      title: 'Deselect All',
      subtitle: 'Clear the current object selection',
      group: 'Actions',
      icon: Tag,
      iconClass: 'text-fg-secondary',
      keywords: 'deselect clear selection unselect drop',
      run: () => clearSelection(),
    })
    if (onReopenOnboarding) {
      items.push({
        id: 'action-reopen-onboarding',
        title: 'Replay Onboarding Tour',
        subtitle: 'Reopen the first-visit walkthrough',
        group: 'Actions',
        icon: HelpCircle,
        iconClass: 'text-accent-cyan',
        keywords: 'onboarding tour help welcome replay guide',
        run: () => onReopenOnboarding(),
      })
    }

    return items
  }, [tools, skills, undo, redo, gridVisible, setGrid, focusSelected, setViewportCamera, setTransformMode, scene, selectedId, addAnnotation, requestCapture, renderQuality, setRenderQuality, editorMode, setEditorMode, setMinimapEnabled, minimapEnabled, setPanelVisibility, chatPanelVisible, rightPanelVisible, clearSelection, onReopenOnboarding])

  // Filter + rank
  const filtered = useMemo(() => {
    if (!query.trim()) return allItems
    return allItems
      .map((item) => ({ item, score: scoreItem(query, item) }))
      .filter((x) => x.score > 0)
      .sort((a, b) => b.score - a.score)
      .map((x) => x.item)
  }, [allItems, query])

  // Clamp active index when the filtered list shrinks
  useEffect(() => {
    if (activeIndex >= filtered.length) setActiveIndex(0)
  }, [filtered.length, activeIndex])

  // Auto-scroll the active row into view
  useEffect(() => {
    const list = listRef.current
    if (!list) return
    const row = list.querySelector<HTMLElement>(`[data-idx="${activeIndex}"]`)
    if (row) row.scrollIntoView({ block: 'nearest' })
  }, [activeIndex])

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setActiveIndex((i) => Math.min(i + 1, filtered.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActiveIndex((i) => Math.max(i - 1, 0))
    } else if (e.key === 'Enter') {
      e.preventDefault()
      const picked = filtered[activeIndex]
      if (picked) {
        picked.run(send)
        onClose()
      }
    } else if (e.key === 'Escape') {
      e.preventDefault()
      onClose()
    }
  }

  // Group filtered items, preserving the score order within each group.
  const grouped = useMemo(() => {
    const groups: Record<string, CommandItem[]> = {}
    for (const item of filtered) {
      if (!groups[item.group]) groups[item.group] = []
      groups[item.group].push(item)
    }
    return groups
  }, [filtered])

  // Flatten for indexing against the rendered order
  const flatOrdered = useMemo(() => {
    const order: CommandItem[] = []
    for (const g of ['Templates', 'Skills', 'Tools', 'Actions']) {
      if (grouped[g]) order.push(...grouped[g])
    }
    return order
  }, [grouped])

  // Re-align activeIndex against the flat render order so keyboard nav matches
  // what's actually on screen.
  useEffect(() => {
    const id = filtered[activeIndex]?.id
    if (!id) return
    const newIdx = flatOrdered.findIndex((x) => x.id === id)
    if (newIdx >= 0 && newIdx !== activeIndex) setActiveIndex(newIdx)
  }, [flatOrdered, filtered, activeIndex])

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.12 }}
          className="fixed inset-0 z-[60] flex items-start justify-center pt-[12vh] bg-black/60 backdrop-blur-sm"
          onClick={onClose}
        >
          <motion.div
            initial={{ scale: 0.97, opacity: 0, y: -8 }}
            animate={{ scale: 1, opacity: 1, y: 0 }}
            exit={{ scale: 0.97, opacity: 0, y: -8 }}
            transition={{ duration: 0.16 }}
            onClick={(e) => e.stopPropagation()}
            className="relative w-[640px] max-w-[92vw] max-h-[70vh] overflow-hidden rounded-xl border border-border bg-bg-panel shadow-2xl"
          >
            {/* Search header */}
            <div className="flex items-center gap-2.5 px-4 h-14 border-b border-border">
              <Search size={15} className="text-fg-muted shrink-0" />
              <input
                ref={inputRef}
                value={query}
                onChange={(e) => {
                  setQuery(e.target.value)
                  setActiveIndex(0)
                }}
                onKeyDown={handleKeyDown}
                placeholder="Search templates, skills, tools, actions…"
                className="flex-1 bg-transparent text-sm text-fg-primary placeholder:text-fg-muted outline-none"
              />
              <kbd className="hidden sm:inline-flex items-center px-1.5 h-5 rounded border border-border bg-bg-elevated text-[10px] font-mono text-fg-muted">
                Esc
              </kbd>
            </div>

            {/* Results */}
            <div ref={listRef} className="max-h-[calc(70vh-56px)] overflow-y-auto py-1">
              {flatOrdered.length === 0 ? (
                <div className="px-4 py-8 text-center">
                  <Command size={20} className="mx-auto text-fg-muted/40 mb-2" />
                  <p className="text-xs text-fg-muted">
                    No commands match “{query}”
                  </p>
                </div>
              ) : (
                ['Templates', 'Skills', 'Tools', 'Actions'].map((groupName) => {
                  const list = grouped[groupName]
                  if (!list || list.length === 0) return null
                  return (
                    <div key={groupName}>
                      <div className="px-4 pt-2 pb-1 text-[10px] uppercase tracking-wider text-fg-muted font-semibold">
                        {groupName}
                      </div>
                      {list.map((item) => {
                        const idx = flatOrdered.findIndex((x) => x.id === item.id)
                        const active = idx === activeIndex
                        const Icon = item.icon
                        return (
                          <button
                            key={item.id}
                            data-idx={idx}
                            onMouseMove={() => setActiveIndex(idx)}
                            onClick={() => {
                              item.run(send)
                              onClose()
                            }}
                            className={`w-full flex items-center gap-3 px-4 py-2 text-left transition-colors ${
                              active
                                ? 'bg-accent-cyan/10 border-l-2 border-accent-cyan'
                                : 'border-l-2 border-transparent hover:bg-bg-hover'
                            }`}
                          >
                            <Icon size={15} className={`${item.iconClass} shrink-0`} />
                            <div className="flex-1 min-w-0">
                              <div className="text-xs font-medium text-fg-primary truncate">
                                {item.title}
                              </div>
                              <div className="text-[10px] text-fg-muted truncate">
                                {item.subtitle}
                              </div>
                            </div>
                            {active && (
                              <CornerDownLeft
                                size={11}
                                className="text-fg-muted shrink-0"
                              />
                            )}
                          </button>
                        )
                      })}
                    </div>
                  )
                })
              )}
            </div>

            {/* Footer */}
            <footer className="flex items-center justify-between gap-2 px-4 h-9 border-t border-border-subtle text-[10px] text-fg-muted">
              <div className="flex items-center gap-1.5">
                <Sparkles size={10} className="text-accent-cyan" />
                <span>Command Palette</span>
              </div>
              <div className="flex items-center gap-3">
                <span className="flex items-center gap-1">
                  <kbd className="px-1 h-4 inline-flex items-center rounded border border-border bg-bg-elevated font-mono">↑</kbd>
                  <kbd className="px-1 h-4 inline-flex items-center rounded border border-border bg-bg-elevated font-mono">↓</kbd>
                  navigate
                </span>
                <span className="flex items-center gap-1">
                  <kbd className="px-1 h-4 inline-flex items-center rounded border border-border bg-bg-elevated font-mono">↵</kbd>
                  select
                </span>
              </div>
            </footer>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
