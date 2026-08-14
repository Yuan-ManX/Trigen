// Viewport context menu — triggered by right-click on empty canvas space.
// Complements the per-object RadialMenu (which owns object-centric actions)
// with scene-level quick actions: drop a primitive at the clicked ground
// position, set the ground target, toggle viewport shading, and jump to a
// saved view. Implements the drag-drop creation loop too — users can drag
// a primitive type from the palette onto the canvas and the drop handler
// creates an object at the projected ground-plane intersection point.
import { AnimatePresence, motion } from 'framer-motion'
import {
  Box,
  Circle,
  Cone,
  Cylinder,
  Hexagon,
  LayoutGrid,
  Moon,
  Move3d,
  Plane,
  Plus,
  Pyramid,
  Sparkles,
  Squircle,
  Sun,
  X,
  type LucideIcon,
} from 'lucide-react'
import { useEffect, useMemo, useRef } from 'react'
import type { Vec3 } from '../../types'
import { useEditor } from '../../store/useEditor'
import { useChat } from '../../store/useChat'
import { useScene } from '../../store/useScene'

interface DropTarget {
  /** World-space drop position on the ground plane (y=0). */
  position: Vec3
  /** The primitive type requested by the user. */
  geometryType: string
}

interface PrimitiveOption {
  type: string
  label: string
  icon: LucideIcon
  accent: string
}

const PRIMITIVES: PrimitiveOption[] = [
  { type: 'box', label: 'Cube', icon: Box, accent: 'bg-accent-gold/15 text-accent-gold' },
  { type: 'sphere', label: 'Sphere', icon: Circle, accent: 'bg-accent-pink/15 text-accent-pink' },
  { type: 'cylinder', label: 'Cylinder', icon: Cylinder, accent: 'bg-accent-cyan/15 text-accent-cyan' },
  { type: 'cone', label: 'Cone', icon: Cone, accent: 'bg-accent-violet/15 text-accent-violet' },
  { type: 'plane', label: 'Plane', icon: Plane, accent: 'bg-accent-emerald/15 text-accent-emerald' },
  { type: 'torus', label: 'Torus', icon: Hexagon, accent: 'bg-amber-500/15 text-amber-500' },
  { type: 'icosahedron', label: 'Icosa', icon: Squircle, accent: 'bg-sky-500/15 text-sky-500' },
  { type: 'tetrahedron', label: 'Tetra', icon: Pyramid, accent: 'bg-rose-500/15 text-rose-500' },
]

/** Project a screen-space point onto the ground plane (y=0).
 *  Returns the 3D world position. Uses a simple reverse-projection that
 *  doesn't require raycasters so the context menu stays lightweight. */
function screenToGround(
  clientX: number,
  clientY: number,
  canvasRect: DOMRect | null,
): Vec3 {
  if (!canvasRect) return [0, 0, 0]
  // Normalized device coordinates (-1..1) with Y flipped for GL convention.
  const ndcX = ((clientX - canvasRect.left) / canvasRect.width) * 2 - 1
  const ndcY = -(((clientY - canvasRect.top) / canvasRect.height) * 2 - 1)
  // Heuristic projection scale — the default camera at (8, 8, 8) looking at
  // origin produces roughly 1 world unit per (1 / distance) on screen. We
  // approximate using a perspective-like scale factor so drops near the
  // screen center land around the origin while drops toward the edges
  // extend outward.
  const distance = 14
  const scale = Math.max(2, distance * (1 + Math.max(Math.abs(ndcX), Math.abs(ndcY)) * 0.8))
  return [ndcX * scale * 0.5, 0, ndcY * scale * 0.5]
}

export interface ViewportContextMenuProps {
  /** Current open state + cursor position */
  open: boolean
  clientX: number
  clientY: number
  /** Called on close */
  onClose: () => void
  /** Optional pending drop payload (from palette drag). When set the menu
   *  defaults into "create primitive at drop point" mode instead of the
   *  full scene-action picker. */
  pendingDrop?: DropTarget | null
}

export function ViewportContextMenu({ open, clientX, clientY, onClose, pendingDrop }: ViewportContextMenuProps) {
  const canvasRectRef = useRef<DOMRect | null>(null)
  const shading = useEditor((s) => s.viewportShading)
  const setShading = useEditor((s) => s.setViewportShading)
  const setRadial = useEditor((s) => s.setRadialMenu)
  const send = useChat((s) => s.send)
  const scene = useScene((s) => s.scene)

  useEffect(() => {
    const el = document.querySelector<HTMLElement>('[data-canvas-host="true"]')
    if (el) canvasRectRef.current = el.getBoundingClientRect()
  }, [open])

  const dropPosition = useMemo<Vec3>(() => {
    if (pendingDrop) return pendingDrop.position
    return screenToGround(clientX, clientY, canvasRectRef.current)
  }, [pendingDrop, clientX, clientY])

  if (!open) return null

  const sendCreate = (type: string, pos: Vec3) => {
    const x = pos[0].toFixed(2)
    const y = (pos[1] + 0.6).toFixed(2)
    const z = pos[2].toFixed(2)
    send(
      `Create a single ${type} at position [${x}, ${y}, ${z}] with size 1.2. Give it a soft matte material.`,
    )
  }

  const cycleShading = () => {
    const order: Array<'rendered' | 'material' | 'solid' | 'wireframe'> = ['rendered', 'material', 'solid', 'wireframe']
    const idx = order.findIndex((s) => s === shading)
    setShading(order[(idx + 1 + order.length) % order.length])
  }

  // Clamp menu inside viewport
  const maxX = Math.max(0, (canvasRectRef.current?.width ?? window.innerWidth) - 340)
  const maxY = Math.max(0, (canvasRectRef.current?.height ?? window.innerHeight) - 440)
  const menuX = Math.min(clientX + 12, maxX + (canvasRectRef.current?.left ?? 0))
  const menuY = Math.min(clientY + 12, maxY + (canvasRectRef.current?.top ?? 0))

  return (
    <AnimatePresence>
      <motion.div
        key={pendingDrop ? 'drop' : 'ctx'}
        initial={{ opacity: 0, y: 4, scale: 0.98 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: 2, scale: 0.98 }}
        transition={{ type: 'spring', duration: 0.25, bounce: 0.35 }}
        onContextMenu={(e) => e.preventDefault()}
        className="fixed z-[1000] w-[320px] rounded-2xl border border-ink-100/60 bg-surface/95 backdrop-blur-xl shadow-2xl shadow-ink-900/10 p-3 space-y-3"
        style={{ left: menuX, top: menuY }}
      >
        <header className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="h-8 w-8 grid place-items-center rounded-xl bg-gradient-to-br from-accent-pink/40 to-accent-violet/40 text-white">
              <Sparkles size={14} />
            </span>
            <div>
              <div className="text-sm font-semibold text-fg-primary">
                {pendingDrop ? `Drop: ${pendingDrop.geometryType}` : 'Canvas Actions'}
              </div>
              <div className="text-[11px] text-fg-secondary">
                {pendingDrop
                  ? `Target position (${dropPosition[0].toFixed(1)}, ${dropPosition[2].toFixed(1)})`
                  : `${scene.objects.length} objects in scene`}
              </div>
            </div>
          </div>
          <button
            className="h-7 w-7 grid place-items-center rounded-lg hover:bg-ink-100/60 text-fg-tertiary hover:text-fg-primary transition"
            onClick={onClose}
            aria-label="Close context menu"
          >
            <X size={14} />
          </button>
        </header>

        <section className="space-y-1.5">
          <div className="text-[10px] uppercase tracking-wider text-fg-tertiary px-1">
            {pendingDrop ? 'Quick drop variants' : 'Create primitive here'}
          </div>
          <div className="grid grid-cols-4 gap-1.5">
            {PRIMITIVES.map((p) => {
              const Icon = p.icon
              const active = pendingDrop?.geometryType === p.type
              return (
                <button
                  key={p.type}
                  onClick={() => {
                    sendCreate(p.type, dropPosition)
                    onClose()
                  }}
                  className={`group flex flex-col items-center gap-1 rounded-xl border p-2 transition hover:-translate-y-0.5 ${
                    active
                      ? 'border-accent-violet/60 bg-accent-violet/10 shadow-inner'
                      : 'border-ink-100/40 hover:border-ink-200/60 hover:bg-ink-100/30'
                  }`}
                  title={p.label}
                >
                  <span className={`h-8 w-8 grid place-items-center rounded-lg ${p.accent} transition group-hover:scale-110`}>
                    <Icon size={16} />
                  </span>
                  <span className="text-[10px] text-fg-secondary group-hover:text-fg-primary">{p.label}</span>
                </button>
              )
            })}
          </div>
        </section>

        <section className="grid grid-cols-2 gap-1.5">
          <button
            onClick={() => {
              send(
                `Add a directional key light at [${(dropPosition[0] - 3).toFixed(1)}, ${5}, ${(dropPosition[2] - 3).toFixed(1)}] pointing at the origin.`,
              )
              onClose()
            }}
            className="flex items-center gap-2 rounded-xl border border-ink-100/40 hover:border-ink-200/70 hover:bg-ink-100/30 px-2.5 py-2 text-left transition"
          >
            <Sun size={14} className="text-amber-500" />
            <div>
              <div className="text-[12px] font-medium text-fg-primary">Add key light</div>
              <div className="text-[10px] text-fg-tertiary">3-point studio</div>
            </div>
          </button>
          <button
            onClick={() => {
              send(
                `Set environment to a dusk studio atmosphere. Warm lighting, soft shadows, and a gentle blue gradient backdrop.`,
              )
              onClose()
            }}
            className="flex items-center gap-2 rounded-xl border border-ink-100/40 hover:border-ink-200/70 hover:bg-ink-100/30 px-2.5 py-2 text-left transition"
          >
            <Moon size={14} className="text-indigo-500" />
            <div>
              <div className="text-[12px] font-medium text-fg-primary">Dusk atmosphere</div>
              <div className="text-[10px] text-fg-tertiary">Studio preset</div>
            </div>
          </button>
          <button
            onClick={cycleShading}
            className="flex items-center gap-2 rounded-xl border border-ink-100/40 hover:border-ink-200/70 hover:bg-ink-100/30 px-2.5 py-2 text-left transition"
          >
            <Move3d size={14} className="text-accent-cyan" />
            <div>
              <div className="text-[12px] font-medium text-fg-primary">Cycle shading</div>
              <div className="text-[10px] text-fg-tertiary">Current: {shading}</div>
            </div>
          </button>
          <button
            onClick={() => {
              setRadial(null)
              send(
                'Focus this area: align all visible objects along the ground plane, then frame the view on them.',
              )
              onClose()
            }}
            className="flex items-center gap-2 rounded-xl border border-ink-100/40 hover:border-ink-200/70 hover:bg-ink-100/30 px-2.5 py-2 text-left transition"
          >
            <LayoutGrid size={14} className="text-accent-emerald" />
            <div>
              <div className="text-[12px] font-medium text-fg-primary">Ground & frame</div>
              <div className="text-[10px] text-fg-tertiary">Snap and focus</div>
            </div>
          </button>
        </section>

        <footer className="flex items-center justify-between text-[10px] text-fg-tertiary px-1">
          <span className="flex items-center gap-1"><Plus size={12}/> Click a chip to drop</span>
          <span>Esc / click outside to dismiss</span>
        </footer>
      </motion.div>
    </AnimatePresence>
  )
}

export { PRIMITIVES, type PrimitiveOption }
