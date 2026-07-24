// 图层面板：列出场景对象，支持选中 / 切换可见 / 删除
// Layers panel: lists scene objects, supports selection / visibility toggle / deletion
import {
  Box,
  Circle,
  Cone,
  Cylinder,
  Donut,
  Eye,
  EyeOff,
  Hexagon,
  Layers,
  Square,
  Trash2,
  Triangle,
} from 'lucide-react'
import { useScene } from '../../store/useScene'
import type { GeometryType } from '../../types'

/** 根据几何体类型返回图标 */
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
    default:
      return Box
  }
}

export function LayersTab() {
  const objects = useScene((s) => s.scene.objects)
  const selectedId = useScene((s) => s.selectedId)
  const select = useScene((s) => s.select)
  const toggleVisible = useScene((s) => s.toggleVisible)
  const removeObject = useScene((s) => s.removeObject)

  if (objects.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-center px-6 py-10">
        <Layers size={20} className="text-fg-muted mb-2" />
        <p className="text-xs text-fg-secondary">场景中暂无对象</p>
        <p className="text-[11px] text-fg-muted mt-1">
          通过对话让 AI 创建 3D 对象
        </p>
      </div>
    )
  }

  return (
    <div className="flex flex-col">
      <div className="px-3 py-2 text-[10px] uppercase tracking-wider text-fg-muted border-b border-border-subtle">
        对象 · {objects.length}
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
                aria-label={o.visible ? '隐藏' : '显示'}
              >
                {o.visible ? <Eye size={13} /> : <EyeOff size={13} />}
              </button>
              <button
                onClick={(e) => {
                  e.stopPropagation()
                  removeObject(o.id)
                }}
                className="text-fg-muted hover:text-rose-400 opacity-0 group-hover:opacity-100 transition-opacity"
                aria-label="删除"
              >
                <Trash2 size={13} />
              </button>
            </div>
          )
        })}
      </div>
    </div>
  )
}
