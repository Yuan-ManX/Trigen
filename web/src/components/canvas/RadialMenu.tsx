// Radial pie-menu overlay for the 3D viewport. Triggered by right-clicking
// a mesh: shows six actions arranged in a hexagon around the cursor. Each
// wedge is a hover-target; clicking a wedge runs its action and dismisses
// the menu. Clicking outside, pressing Escape, or re-right-clicking also
// dismisses it.
//
// The actions cover the most common per-object shortcuts so the user can
// stay in the viewport instead of darting to the sidebar.
import { AnimatePresence, motion } from 'framer-motion'
import {
  Copy,
  Crosshair,
  EyeOff,
  MessageSquare as AnnotationIcon,
  RotateCcw,
  Trash2,
} from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { useEditor } from '../../store/useEditor'
import { useScene } from '../../store/useScene'

interface RadialAction {
  id: string
  label: string
  icon: typeof Copy
  /** Accent color (Tailwind text-* class) applied to icon + wedge hover. */
  accent: string
  /** Whether the action is destructive — used for the wedge hover tint. */
  danger?: boolean
}

const ACTIONS: RadialAction[] = [
  { id: 'duplicate', label: 'Duplicate', icon: Copy, accent: 'text-accent-cyan' },
  { id: 'focus', label: 'Focus', icon: Crosshair, accent: 'text-accent-cyan' },
  { id: 'delete', label: 'Delete', icon: Trash2, accent: 'text-rose-400', danger: true },
  { id: 'reset', label: 'Reset Xform', icon: RotateCcw, accent: 'text-amber-300' },
  { id: 'hide', label: 'Toggle Hide', icon: EyeOff, accent: 'text-fg-secondary' },
  { id: 'annotate', label: 'Annotate', icon: AnnotationIcon, accent: 'text-accent-gold' },
]

// Geometry of the pie. Six wedges of 60° each, anchored at the cursor.
const WEDGE_DEG = 360 / ACTIONS.length
const OUTER_RADIUS = 78
const INNER_RADIUS = 22
// Each wedge icon sits at this radius from the center.
const ICON_RADIUS = (OUTER_RADIUS + INNER_RADIUS) / 2

/** Build the SVG path for a single wedge (donut slice). */
function wedgePath(startDeg: number, endDeg: number): string {
  // 0° points up (north); rotate -90 so the first wedge's leading edge
  // starts at the top of the circle.
  const toRad = (d: number) => ((d - 90) * Math.PI) / 180
  const outerA = toRad(startDeg)
  const outerB = toRad(endDeg)
  const innerA = toRad(startDeg)
  const innerB = toRad(endDeg)
  const ox1 = OUTER_RADIUS * Math.cos(outerA)
  const oy1 = OUTER_RADIUS * Math.sin(outerA)
  const ox2 = OUTER_RADIUS * Math.cos(outerB)
  const oy2 = OUTER_RADIUS * Math.sin(outerB)
  const ix1 = INNER_RADIUS * Math.cos(innerA)
  const iy1 = INNER_RADIUS * Math.sin(innerA)
  const ix2 = INNER_RADIUS * Math.cos(innerB)
  const iy2 = INNER_RADIUS * Math.sin(innerB)
  const largeArc = endDeg - startDeg > 180 ? 1 : 0
  return [
    `M ${ox1} ${oy1}`,
    `A ${OUTER_RADIUS} ${OUTER_RADIUS} 0 ${largeArc} 1 ${ox2} ${oy2}`,
    `L ${ix2} ${iy2}`,
    `A ${INNER_RADIUS} ${INNER_RADIUS} 0 ${largeArc} 0 ${ix1} ${iy1}`,
    'Z',
  ].join(' ')
}

/** Clamp the menu origin so the whole circle stays on-screen. */
function clampOrigin(x: number, y: number): { x: number; y: number } {
  const margin = OUTER_RADIUS + 8
  const vw = window.innerWidth
  const vh = window.innerHeight
  return {
    x: Math.max(margin, Math.min(vw - margin, x)),
    y: Math.max(margin, Math.min(vh - margin, y)),
  }
}

export function RadialMenu() {
  const radial = useEditor((s) => s.radialMenu)
  const clear = useEditor((s) => s.clearRadialMenu)
  const [hovered, setHovered] = useState<number | null>(null)

  // Reset hover whenever a new menu opens (token change).
  useEffect(() => {
    setHovered(null)
  }, [radial?.token])

  // Dismiss on Escape. Kept separate from the overlay click handler so it
  // works even if focus is elsewhere in the document.
  useEffect(() => {
    if (!radial) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') clear()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [radial, clear])

  if (!radial) return null
  const origin = clampOrigin(radial.x, radial.y)

  return (
    <AnimatePresence>
      <RadialMenuBody
        key={radial.token}
        origin={origin}
        objectId={radial.objectId}
        hovered={hovered}
        setHovered={setHovered}
        onAction={() => clear()}
        onDismiss={clear}
      />
    </AnimatePresence>
  )
}

interface RadialMenuBodyProps {
  origin: { x: number; y: number }
  objectId: string
  hovered: number | null
  setHovered: (i: number | null) => void
  onAction: () => void
  onDismiss: () => void
}

function RadialMenuBody({
  origin,
  objectId,
  hovered,
  setHovered,
  onAction,
  onDismiss,
}: RadialMenuBodyProps) {
  // Look up the target object on every render so the action handlers see
  // fresh transform data (the user might right-click, then drag the object
  // with the menu open — unlikely, but cheap to be correct).
  const obj = useScene((s) => s.scene.objects.find((o) => o.id === objectId) ?? null)
  const duplicateObject = useScene((s) => s.duplicateObject)
  const removeObject = useScene((s) => s.removeObject)
  const updateTransform = useScene((s) => s.updateTransform)
  const toggleVisible = useScene((s) => s.toggleVisible)
  const sceneRef = useRef(useScene.getState())
  sceneRef.current = useScene.getState()
  const setViewportCamera = useEditor((s) => s.setViewportCamera)
  const addAnnotation = useScene((s) => s.addAnnotation)

  /** Run the action for wedge `i`. */
  const runAction = (i: number) => {
    const action = ACTIONS[i]
    const target = sceneRef.current.scene.objects.find((o) => o.id === objectId)
    if (!target) {
      onAction()
      return
    }
    switch (action.id) {
      case 'duplicate':
        duplicateObject(target.id)
        break
      case 'focus': {
        const [x, y, z] = target.transform.position
        setViewportCamera([x, y + 2, z + 4], [x, y, z], true)
        break
      }
      case 'delete':
        removeObject(target.id)
        break
      case 'reset':
        updateTransform(target.id, {
          position: [0, 0, 0],
          rotation: [0, 0, 0],
          scale: [1, 1, 1],
        })
        break
      case 'hide':
        toggleVisible(target.id)
        break
      case 'annotate':
        addAnnotation({
          id: `ann_${Date.now().toString(36)}`,
          object_id: target.id,
          position: [...target.transform.position] as [number, number, number],
          title: target.name,
          text: '',
          color: '#FFB800',
          visible: true,
        })
        break
    }
    onAction()
  }

  // Precompute wedge paths so we don't recompute on every hover change.
  const wedges = useMemo(
    () =>
      ACTIONS.map((_, i) => ({
        path: wedgePath(i * WEDGE_DEG, (i + 1) * WEDGE_DEG),
        iconX: ICON_RADIUS * Math.cos(((i * WEDGE_DEG + WEDGE_DEG / 2 - 90) * Math.PI) / 180),
        iconY: ICON_RADIUS * Math.sin(((i * WEDGE_DEG + WEDGE_DEG / 2 - 90) * Math.PI) / 180),
      })),
    [],
  )

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.12 }}
      className="fixed inset-0 z-[60]"
      onPointerDown={(e) => {
        // Click outside the pie dismisses; clicks on wedges stopPropagation.
        if (e.target === e.currentTarget) onDismiss()
      }}
      onContextMenu={(e) => {
        // Suppress the browser's native context menu so the radial stays.
        e.preventDefault()
        onDismiss()
      }}
    >
      <div
        className="absolute"
        style={{ left: origin.x, top: origin.y, width: 0, height: 0 }}
      >
        <motion.div
          initial={{ scale: 0.4, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          exit={{ scale: 0.6, opacity: 0 }}
          transition={{ type: 'spring', stiffness: 480, damping: 28 }}
          className="absolute"
          style={{
            left: -OUTER_RADIUS - 12,
            top: -OUTER_RADIUS - 12,
            width: OUTER_RADIUS * 2 + 24,
            height: OUTER_RADIUS * 2 + 24,
          }}
        >
          <svg
            width={OUTER_RADIUS * 2 + 24}
            height={OUTER_RADIUS * 2 + 24}
            viewBox={`${-OUTER_RADIUS - 12} ${-OUTER_RADIUS - 12} ${OUTER_RADIUS * 2 + 24} ${OUTER_RADIUS * 2 + 24}`}
            className="overflow-visible"
          >
            {/* Soft backdrop ring so the menu reads against any scene. */}
            <circle
              cx={0}
              cy={0}
              r={OUTER_RADIUS + 6}
              fill="rgba(5,5,5,0.55)"
              stroke="rgba(0,240,255,0.18)"
              strokeWidth={1}
            />
            {wedges.map((w, i) => {
              const action = ACTIONS[i]
              const isHovered = hovered === i
              const Icon = action.icon
              return (
                <g
                  key={action.id}
                  onPointerEnter={() => setHovered(i)}
                  onPointerLeave={() => setHovered(hovered === i ? null : hovered)}
                  onPointerDown={(e) => {
                    e.stopPropagation()
                    runAction(i)
                  }}
                  style={{ cursor: 'pointer' }}
                >
                  <path
                    d={w.path}
                    fill={
                      isHovered
                        ? action.danger
                          ? 'rgba(244,63,94,0.22)'
                          : 'rgba(0,240,255,0.22)'
                        : 'rgba(15,18,28,0.55)'
                    }
                    stroke={
                      isHovered
                        ? action.danger
                          ? 'rgba(244,63,94,0.7)'
                          : 'rgba(0,240,255,0.7)'
                        : 'rgba(60,72,90,0.45)'
                    }
                    strokeWidth={isHovered ? 1.4 : 0.8}
                    style={{ transition: 'fill 80ms, stroke 80ms' }}
                  />
                  {/* Icon */}
                  <g transform={`translate(${w.iconX}, ${w.iconY})`}>
                    <Icon
                      size={15}
                      className={action.accent}
                      style={{
                        transform: 'translate(-50%, -50%)',
                        opacity: isHovered ? 1 : 0.78,
                        transition: 'opacity 80ms',
                      }}
                      strokeWidth={isHovered ? 2.2 : 1.8}
                    />
                  </g>
                </g>
              )
            })}
            {/* Center hub: dismiss zone + object name initial. */}
            <circle
              cx={0}
              cy={0}
              r={INNER_RADIUS - 2}
              fill="rgba(5,5,5,0.9)"
              stroke="rgba(0,240,255,0.35)"
              strokeWidth={1}
              onPointerDown={(e) => {
                e.stopPropagation()
                onDismiss()
              }}
              style={{ cursor: 'pointer' }}
            />
            <text
              x={0}
              y={0}
              textAnchor="middle"
              dominantBaseline="central"
              fontSize={13}
              fontFamily="ui-monospace, monospace"
              fill="rgba(0,240,255,0.85)"
              style={{ pointerEvents: 'none', userSelect: 'none' }}
            >
              {obj ? obj.name.slice(0, 1).toUpperCase() : '?'}
            </text>
          </svg>
        </motion.div>

        {/* Hover tooltip — shows the action label near the cursor. */}
        <AnimatePresence>
          {hovered !== null && (
            <motion.div
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 4 }}
              transition={{ duration: 0.1 }}
              className="absolute pointer-events-none whitespace-nowrap rounded border border-border bg-bg-elevated/95 px-2 py-1 text-[10px] font-medium text-fg-primary shadow-lg"
              style={{
                left: OUTER_RADIUS + 14,
                top: -10,
              }}
            >
              {ACTIONS[hovered].label}
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </motion.div>
  )
}
