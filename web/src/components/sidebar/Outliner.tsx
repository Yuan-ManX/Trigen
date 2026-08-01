// Outliner: hierarchical scene tree showing groups as parent nodes and
// ungrouped objects at root level. Supports visibility / lock toggles,
// multi-selection sync, group creation from the current selection,
// expand / collapse per group, and drag-to-reorder objects within
// scene.objects (the source-of-truth ordering on the backend).
import {
  Box,
  ChevronDown,
  ChevronRight,
  Circle,
  Cone,
  Cylinder,
  Disc,
  Donut,
  Eye,
  EyeOff,
  FolderClosed,
  FolderOpen,
  Group as GroupIcon,
  Hexagon,
  Lock,
  Unlock,
  Pill,
  Square,
  Triangle,
  Waypoints,
} from 'lucide-react'
import { useMemo, useState } from 'react'
import { useScene } from '../../store/useScene'
import type { GeometryType, GroupObject, SceneObject } from '../../types'

/** Map a geometry type to a small icon for visual scanning */
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

interface RowProps {
  object: SceneObject
  depth: number
  dragState: DragState
}

function ObjectRow({ object, depth, dragState }: RowProps) {
  const selectedId = useScene((s) => s.selectedId)
  const selectedIds = useScene((s) => s.selectedIds)
  const select = useScene((s) => s.select)
  const toggleVisible = useScene((s) => s.toggleVisible)
  const toggleLock = useScene((s) => s.toggleLock)

  const Icon = geometryIcon(object.geometry.type)
  const isSelected = selectedIds.includes(object.id)
  const isPrimary = selectedId === object.id
  const hasAnim = !!object.animation
  const isDropTarget = dragState.overId === object.id && dragState.draggedId !== object.id

  return (
    <div
      draggable
      onDragStart={(e) => {
        e.dataTransfer.effectAllowed = 'move'
        // setData is required for Firefox to initiate a drag
        e.dataTransfer.setData('text/plain', object.id)
        dragState.setDragged(object.id)
      }}
      onDragEnd={() => dragState.clear()}
      onDragOver={(e) => {
        e.preventDefault()
        e.dataTransfer.dropEffect = 'move'
        if (dragState.draggedId && dragState.draggedId !== object.id) {
          dragState.setOver(object.id)
        }
      }}
      onDragLeave={() => {
        if (dragState.overId === object.id) dragState.setOver(null)
      }}
      onDrop={(e) => {
        e.preventDefault()
        e.stopPropagation()
        if (dragState.draggedId && dragState.draggedId !== object.id) {
          dragState.commitReorder(object.id)
        } else {
          dragState.clear()
        }
      }}
      onClick={(e) => select(object.id, e.shiftKey || e.metaKey || e.ctrlKey)}
      className={`group flex items-center gap-1.5 cursor-pointer border-l-2 transition-colors ${
        isPrimary
          ? 'bg-accent-cyan/10 border-accent-cyan'
          : isSelected
            ? 'bg-accent-cyan/5 border-accent-cyan/40'
            : isDropTarget
              ? 'bg-accent-gold/10 border-accent-gold/60'
              : 'border-transparent hover:bg-bg-hover'
      } ${dragState.draggedId === object.id ? 'opacity-50' : ''}`}
      style={{ paddingLeft: 12 + depth * 14, paddingRight: 12 }}
    >
      <Icon
        size={13}
        className={isPrimary ? 'text-accent-cyan' : 'text-fg-secondary shrink-0'}
      />
      <span
        className={`flex-1 text-xs truncate ${
          isPrimary ? 'text-fg-primary' : 'text-fg-secondary'
        } ${object.locked ? 'opacity-60' : ''}`}
      >
        {object.name}
      </span>
      {hasAnim && (
        <span
          className="w-1.5 h-1.5 rounded-full bg-accent-gold shrink-0"
          title={`Animated: ${object.animation?.type}`}
        />
      )}
      <button
        onClick={(e) => {
          e.stopPropagation()
          toggleLock(object.id)
        }}
        className={`shrink-0 transition-opacity ${
          object.locked
            ? 'text-amber-400 opacity-100'
            : 'text-fg-muted hover:text-fg-primary opacity-0 group-hover:opacity-100'
        }`}
        aria-label={object.locked ? 'Unlock' : 'Lock'}
      >
        {object.locked ? <Lock size={12} /> : <Unlock size={12} />}
      </button>
      <button
        onClick={(e) => {
          e.stopPropagation()
          toggleVisible(object.id)
        }}
        className="shrink-0 text-fg-muted hover:text-fg-primary opacity-0 group-hover:opacity-100 transition-opacity"
        aria-label={object.visible ? 'Hide' : 'Show'}
      >
        {object.visible ? <Eye size={13} /> : <EyeOff size={13} />}
      </button>
    </div>
  )
}

interface GroupRowProps {
  group: GroupObject
  objects: SceneObject[]
  dragState: DragState
}

function GroupRow({ group, objects, dragState }: GroupRowProps) {
  const [collapsed, setCollapsed] = useState(false)
  const selectedIds = useScene((s) => s.selectedIds)
  const select = useScene((s) => s.select)

  const childObjects = objects.filter((o) => o.group_id === group.id)
  // A group is "active" when any of its children is selected
  const hasSelectedChild = childObjects.some((o) => selectedIds.includes(o.id))
  // Dropping onto a group header moves the dragged object into the group
  const isDropTarget = dragState.overId === group.id && !!dragState.draggedId

  return (
    <div>
      <div
        draggable
        onDragStart={(e) => {
          e.dataTransfer.effectAllowed = 'move'
          e.dataTransfer.setData('text/plain', group.id)
          dragState.setDragged(group.id)
        }}
        onDragEnd={() => dragState.clear()}
        onDragOver={(e) => {
          e.preventDefault()
          e.dataTransfer.dropEffect = 'move'
          if (dragState.draggedId && dragState.draggedId !== group.id) {
            dragState.setOver(group.id)
          }
        }}
        onDragLeave={() => {
          if (dragState.overId === group.id) dragState.setOver(null)
        }}
        onDrop={(e) => {
          e.preventDefault()
          e.stopPropagation()
          if (dragState.draggedId && dragState.draggedId !== group.id) {
            // Treat dropping on a group as an assignment into the group
            const draggedObj = objects.find((o) => o.id === dragState.draggedId)
            if (draggedObj) {
              useScene.getState().assignToGroup(draggedObj.id, group.id)
            }
          }
          dragState.clear()
        }}
        onClick={(e) => {
          // Clicking a group header selects all its children
          if (e.shiftKey || e.metaKey || e.ctrlKey) {
            childObjects.forEach((o) => select(o.id, true))
          } else {
            childObjects.forEach((o) => select(o.id, e.shiftKey || e.metaKey || e.ctrlKey))
            // Select last as primary
            if (childObjects.length > 0) select(childObjects[childObjects.length - 1].id)
          }
        }}
        className={`group flex items-center gap-1.5 cursor-pointer border-l-2 transition-colors ${
          hasSelectedChild
            ? 'bg-accent-gold/10 border-accent-gold'
            : isDropTarget
              ? 'bg-accent-cyan/10 border-accent-cyan/60'
              : 'border-transparent hover:bg-bg-hover'
        }`}
        style={{ paddingLeft: 12, paddingRight: 12 }}
      >
        <button
          onClick={(e) => {
            e.stopPropagation()
            setCollapsed((c) => !c)
          }}
          className="text-fg-muted hover:text-fg-primary shrink-0"
          aria-label={collapsed ? 'Expand' : 'Collapse'}
        >
          {collapsed ? <ChevronRight size={13} /> : <ChevronDown size={13} />}
        </button>
        {collapsed ? (
          <FolderClosed size={13} className="text-accent-gold shrink-0" />
        ) : (
          <FolderOpen size={13} className="text-accent-gold shrink-0" />
        )}
        <span className="flex-1 text-xs truncate text-fg-primary font-medium">
          {group.name}
        </span>
        <span className="text-[10px] text-fg-muted font-mono shrink-0">
          {childObjects.length}
        </span>
      </div>
      {!collapsed &&
        childObjects.map((o) => <ObjectRow key={o.id} object={o} depth={1} dragState={dragState} />)}
      {!collapsed && childObjects.length === 0 && (
        <div
          className="text-[10px] text-fg-muted italic"
          style={{ paddingLeft: 40, paddingRight: 12, paddingTop: 4, paddingBottom: 4 }}
        >
          Empty group
        </div>
      )}
    </div>
  )
}

/** Drag state shared between Outliner rows. Held in the parent so rows can
 *  read the currently-dragged id and report drop targets via callbacks. */
interface DragState {
  draggedId: string | null
  overId: string | null
  setDragged: (id: string | null) => void
  setOver: (id: string | null) => void
  clear: () => void
  /** Reorder scene.objects so the dragged id lands at the target's index */
  commitReorder: (targetId: string) => void
}

export function Outliner() {
  const objects = useScene((s) => s.scene.objects)
  const groups = useScene((s) => s.scene.groups)
  const selectedIds = useScene((s) => s.selectedIds)
  const groupObjects = useScene((s) => s.groupObjects)
  const reorderObject = useScene((s) => s.reorderObject)

  const [draggedId, setDraggedId] = useState<string | null>(null)
  const [overId, setOverId] = useState<string | null>(null)

  const dragState: DragState = useMemo(
    () => ({
      draggedId,
      overId,
      setDragged: (id) => setDraggedId(id),
      setOver: (id) => setOverId(id),
      clear: () => {
        setDraggedId(null)
        setOverId(null)
      },
      commitReorder: (targetId) => {
        const dragged = draggedId
        setDraggedId(null)
        setOverId(null)
        if (!dragged || dragged === targetId) return
        const targetIndex = objects.findIndex((o) => o.id === targetId)
        if (targetIndex < 0) return
        reorderObject(dragged, targetIndex)
      },
    }),
    [draggedId, overId, objects, reorderObject],
  )

  // Objects that don't belong to any group, shown at root level
  const rootObjects = useMemo(
    () => objects.filter((o) => !o.group_id),
    [objects],
  )

  if (objects.length === 0 && groups.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-center px-6 py-10">
        <GroupIcon size={20} className="text-fg-muted mb-2" />
        <p className="text-xs text-fg-secondary">Scene tree is empty</p>
        <p className="text-[11px] text-fg-muted mt-1">
          Create objects and group them via chat
        </p>
      </div>
    )
  }

  const canGroup = selectedIds.length >= 2

  return (
    <div className="flex flex-col h-full">
      {/* Toolbar */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-border-subtle">
        <span className="text-[10px] uppercase tracking-wider text-fg-muted">
          Tree · {objects.length} obj · {groups.length} grp
        </span>
        <button
          onClick={() => groupObjects(selectedIds)}
          disabled={!canGroup}
          className={`flex items-center gap-1 text-[10px] px-2 py-1 rounded transition-colors ${
            canGroup
              ? 'text-accent-cyan hover:bg-accent-cyan/10'
              : 'text-fg-muted cursor-not-allowed opacity-50'
          }`}
          title={canGroup ? `Group ${selectedIds.length} selected` : 'Select 2+ objects to group'}
        >
          <GroupIcon size={11} />
          Group
        </button>
      </div>

      {/* Tree body */}
      <div className="flex-1 overflow-y-auto py-1">
        {groups.map((g) => (
          <GroupRow key={g.id} group={g} objects={objects} dragState={dragState} />
        ))}
        {rootObjects.map((o) => (
          <ObjectRow key={o.id} object={o} depth={0} dragState={dragState} />
        ))}
      </div>

      {/* Drag hint footer */}
      <div className="px-3 py-1.5 border-t border-border-subtle text-[10px] text-fg-muted">
        Drag rows to reorder · Drop onto a group to assign
      </div>
    </div>
  )
}
