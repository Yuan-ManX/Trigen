// Minimap overlay: small top-down (x,z plane) outline of the scene rendered
// as an SVG. Mounted as a sibling of the R3F <Canvas> so it does NOT create a
// second WebGL context. Shows mesh objects as rectangles (sized by their
// world-space footprint), with the selection highlighted.
import { useMemo } from 'react'
import { useScene } from '../../store/useScene'

const SIZE = 140
const PADDING = 8

/** World units per minimap side before padding. The map auto-fits the scene
 *  bounds but uses this as the fallback extent when the scene is empty or
 *  all objects sit near the origin. */
const FALLBACK_EXTENT = 10

interface PlotRect {
  x: number
  y: number
  w: number
  h: number
  selected: boolean
  color: string
}

export function Minimap() {
  const objects = useScene((s) => s.scene.objects)
  const selectedId = useScene((s) => s.selectedId)

  // Project all objects into minimap space (x → x, z → y). Y is ignored —
  // this is a top-down view.
  const rects = useMemo<PlotRect[]>(() => {
    if (objects.length === 0) return []
    let minX = Infinity
    let maxX = -Infinity
    let minZ = Infinity
    let maxZ = -Infinity
    const footprints: Array<{
      id: string
      cx: number
      cz: number
      sx: number
      sz: number
    }> = []
    for (const o of objects) {
      if (!o.visible) continue
      const [px, , pz] = o.transform.position
      const [sx, , sz] = o.transform.scale
      const halfX = Math.max(Math.abs(sx), 0.2) / 2
      const halfZ = Math.max(Math.abs(sz), 0.2) / 2
      footprints.push({ id: o.id, cx: px, cz: pz, sx: halfX * 2, sz: halfZ * 2 })
      if (px - halfX < minX) minX = px - halfX
      if (px + halfX > maxX) maxX = px + halfX
      if (pz - halfZ < minZ) minZ = pz - halfZ
      if (pz + halfZ > maxZ) maxZ = pz + halfZ
    }
    if (footprints.length === 0) return []
    // Pad bounds so a single object doesn't fill the entire map.
    const padW = Math.max((maxX - minX) * 0.1, 1)
    const padH = Math.max((maxZ - minZ) * 0.1, 1)
    minX -= padW
    maxX += padW
    minZ -= padH
    maxZ += padH
    const worldW = Math.max(maxX - minX, FALLBACK_EXTENT)
    const worldH = Math.max(maxZ - minZ, FALLBACK_EXTENT)
    const scale = Math.min(
      (SIZE - PADDING * 2) / worldW,
      (SIZE - PADDING * 2) / worldH,
    )
    const offsetX = (SIZE - worldW * scale) / 2
    const offsetY = (SIZE - worldH * scale) / 2
    return footprints.map((f) => {
      const x = offsetX + (f.cx - f.sx / 2 - minX) * scale
      const y = offsetY + (f.cz - f.sz / 2 - minZ) * scale
      const w = Math.max(f.sx * scale, 2)
      const h = Math.max(f.sz * scale, 2)
      return {
        x,
        y,
        w,
        h,
        selected: f.id === selectedId,
        color: f.id === selectedId ? '#00F0FF' : '#7dd3fc',
      }
    })
  }, [objects, selectedId])

  return (
    <div
      className="absolute top-3 right-3 z-10 rounded-md border border-border bg-bg-panel/85 backdrop-blur p-1.5 shadow-lg pointer-events-none"
      style={{ width: SIZE, height: SIZE }}
      title="Top-down scene minimap (x,z plane)"
    >
      <svg
        width={SIZE - 4}
        height={SIZE - 4}
        viewBox={`0 0 ${SIZE} ${SIZE}`}
        className="overflow-visible"
      >
        {/* Axis cross at the world origin if it falls inside the map */}
        <line x1={SIZE / 2 - 4} y1={SIZE / 2} x2={SIZE / 2 + 4} y2={SIZE / 2} stroke="#3a3a4a" strokeWidth={0.75} />
        <line x1={SIZE / 2} y1={SIZE / 2 - 4} x2={SIZE / 2} y2={SIZE / 2 + 4} stroke="#3a3a4a" strokeWidth={0.75} />
        {rects.map((r, i) => (
          <rect
            key={i}
            x={r.x}
            y={r.y}
            width={r.w}
            height={r.h}
            rx={1}
            fill={r.color}
            fillOpacity={r.selected ? 0.85 : 0.45}
            stroke={r.selected ? '#00F0FF' : 'transparent'}
            strokeWidth={r.selected ? 1 : 0}
          />
        ))}
      </svg>
      <div className="absolute bottom-0.5 left-0 right-0 text-center text-[8px] text-fg-muted/70 font-mono">
        {objects.length} obj
      </div>
    </div>
  )
}
