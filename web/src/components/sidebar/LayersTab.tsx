// Layers panel: lists scene objects and lights, supports selection / visibility toggle / deletion
import {
  Box,
  Circle,
  Cone,
  Cylinder,
  Disc,
  Donut,
  Eye,
  EyeOff,
  Hexagon,
  Layers,
  Lightbulb,
  Pill,
  Square,
  Trash2,
  Triangle,
  Waypoints,
} from 'lucide-react'
import { useScene } from '../../store/useScene'
import type { GeometryType, LightType } from '../../types'

/** Return an icon based on the geometry type */
function geometryIcon(type: GeometryType) {
  switch (type) {
    case 'box':
      return Box
    case 'sphere':
      return Circle
    case 'cylinder':
      return Cylinder
    case 'cone':
      return Cone
    case 'torus':
    case 'torusKnot':
      return Donut
    case 'plane':
      return Square
    case 'dodecahedron':
    case 'icosahedron':
      return Hexagon
    case 'octahedron':
      return Hexagon
    case 'tetrahedron':
      return Triangle
    case 'ring':
      return Disc
    case 'capsule':
      return Pill
    case 'tube':
      return Waypoints
    default:
      return Box
  }
}

/** Return an icon based on the light type */
function lightIcon(_type: LightType) {
  return Lightbulb
}

export function LayersTab() {
  const objects = useScene((s) => s.scene.objects)
  const lights = useScene((s) => s.scene.lights)
  const selectedId = useScene((s) => s.selectedId)
  const select = useScene((s) => s.select)
  const toggleVisible = useScene((s) => s.toggleVisible)
  const removeObject = useScene((s) => s.removeObject)

  if (objects.length === 0 && lights.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-center px-6 py-10">
        <Layers size={20} className="text-fg-muted mb-2" />
        <p className="text-xs text-fg-secondary">No objects in the scene</p>
        <p className="text-[11px] text-fg-muted mt-1">
          Ask the AI to create 3D objects via chat
        </p>
      </div>
    )
  }

  return (
    <div className="flex flex-col">
      <div className="px-3 py-2 text-[10px] uppercase tracking-wider text-fg-muted border-b border-border-subtle">
        Objects · {objects.length}
      </div>
      <div className="overflow-y-auto">
        {objects.map((o) => {
          const Icon = geometryIcon(o.geometry.type)
          const active = o.id === selectedId
          return (
            <div
              key={o.id}
              onClick={() => select(o.id)}
              className={`group flex items-center gap-2 px-3 py-2 cursor-pointer border-l-2 transition-colors ${
                active
                  ? 'bg-accent-cyan/10 border-accent-cyan'
                  : 'border-transparent hover:bg-bg-hover'
              }`}
            >
              <Icon
                size={14}
                className={active ? 'text-accent-cyan' : 'text-fg-secondary'}
              />
              <span
                className={`flex-1 text-xs truncate ${
                  active ? 'text-fg-primary' : 'text-fg-secondary'
                }`}
              >
                {o.name}
              </span>

              <button
                onClick={(e) => {
                  e.stopPropagation()
                  toggleVisible(o.id)
                }}
                className="text-fg-muted hover:text-fg-primary opacity-0 group-hover:opacity-100 transition-opacity"
                aria-label={o.visible ? 'Hide' : 'Show'}
              >
                {o.visible ? <Eye size={13} /> : <EyeOff size={13} />}
              </button>
              <button
                onClick={(e) => {
                  e.stopPropagation()
                  removeObject(o.id)
                }}
                className="text-fg-muted hover:text-rose-400 opacity-0 group-hover:opacity-100 transition-opacity"
                aria-label="Delete"
              >
                <Trash2 size={13} />
              </button>
            </div>
          )
        })}
      </div>

      {lights.length > 0 && (
        <>
          <div className="px-3 py-2 text-[10px] uppercase tracking-wider text-fg-muted border-b border-t border-border-subtle">
            Lights · {lights.length}
          </div>
          <div className="overflow-y-auto">
            {lights.map((l) => {
              const Icon = lightIcon(l.type)
              const active = l.id === selectedId
              return (
                <div
                  key={l.id}
                  onClick={() => select(l.id)}
                  className={`group flex items-center gap-2 px-3 py-2 cursor-pointer border-l-2 transition-colors ${
                    active
                      ? 'bg-accent-gold/10 border-accent-gold'
                      : 'border-transparent hover:bg-bg-hover'
                  }`}
                >
                  <Icon
                    size={14}
                    className={active ? 'text-accent-gold' : 'text-fg-secondary'}
                  />
                  <span
                    className={`flex-1 text-xs truncate ${
                      active ? 'text-fg-primary' : 'text-fg-secondary'
                    }`}
                  >
                    {l.name}
                  </span>
                  <span className="text-[10px] font-mono text-fg-muted uppercase">
                    {l.type}
                  </span>
                </div>
              )
            })}
          </div>
        </>
      )}
    </div>
  )
}
