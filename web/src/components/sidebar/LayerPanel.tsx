// LayerPanel — manage scene layers: create, rename, recolor, lock,
// show/hide, reorder. Mirrors the create_layer / delete_layer /
// set_layer_color Agent tools so the user can drive layers either
// through the Agent chat or directly via the panel.
import { ChevronDown, ChevronRight, Eye, Lock, Plus, Trash2, Users } from 'lucide-react'
import { useState } from 'react'
import { useScene } from '../../store/useScene'
import { useChat } from '../../store/useChat'
import type { LayerInfo } from '../../types'

async function _runTool(name: string, sessionId: string, args: Record<string, unknown>) {
  try {
    await fetch('/api/agent/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, session_id: sessionId, arguments: args }),
    })
  } catch {
    // Silently ignore — the server may be offline during development.
  }
}

interface LayerRowProps {
  id: string
  layer: LayerInfo
  depth: number
  onToggleVisible: (id: string) => void
  onToggleLock: (id: string) => void
  onDelete: (id: string) => void
  onColorChange: (id: string, color: string) => void
  onRename: (id: string, name: string) => void
}

function LayerRow({ id, layer, depth, onToggleVisible, onToggleLock, onDelete, onColorChange, onRename }: LayerRowProps) {
  const [editing, setEditing] = useState(false)
  const [nameBuffer, setNameBuffer] = useState(layer.name)

  return (
    <div
      className="group flex items-center gap-1 h-8 px-2 text-xs hover:bg-bg-hover rounded-sm"
      style={{ paddingLeft: 8 + depth * 16 }}
    >
      <span
        className="w-2.5 h-2.5 rounded-full shrink-0 cursor-pointer"
        style={{ backgroundColor: layer.color }}
        onClick={() => {
          const next = prompt('Layer color (hex):', layer.color)
          if (next) onColorChange(id, next)
        }}
        title="Click to change color"
      />
      {editing ? (
        <input
          autoFocus
          value={nameBuffer}
          onChange={(e) => setNameBuffer(e.target.value)}
          onBlur={() => {
            onRename(id, nameBuffer.trim() || layer.name)
            setEditing(false)
          }}
          onKeyDown={(e) => {
            if (e.key === 'Enter') (e.target as HTMLInputElement).blur()
            if (e.key === 'Escape') {
              setNameBuffer(layer.name)
              setEditing(false)
            }
          }}
          className="flex-1 bg-bg-input border border-border rounded px-1 text-xs text-fg-primary outline-none focus:border-accent-cyan"
        />
      ) : (
        <span
          className="flex-1 text-fg-primary truncate cursor-pointer"
          onDoubleClick={() => setEditing(true)}
          title={layer.name}
        >
          {layer.name}
        </span>
      )}
      <span className="text-fg-muted text-[10px] tabular-nums">{layer.object_count}</span>
      <button
        onClick={() => onToggleVisible(id)}
        className={`opacity-0 group-hover:opacity-100 p-0.5 rounded transition-opacity ${!layer.visible ? 'opacity-100 text-accent-cyan' : 'text-fg-muted hover:text-fg-secondary'}`}
        title={layer.visible ? 'Hide layer' : 'Show layer'}
      >
        <Eye size={12} className={!layer.visible ? 'opacity-50' : ''} />
      </button>
      <button
        onClick={() => onToggleLock(id)}
        className={`opacity-0 group-hover:opacity-100 p-0.5 rounded transition-opacity ${layer.locked ? 'opacity-100 text-accent-yellow' : 'text-fg-muted hover:text-fg-secondary'}`}
        title={layer.locked ? 'Unlock layer' : 'Lock layer'}
      >
        <Lock size={12} className={layer.locked ? 'text-accent-yellow' : ''} />
      </button>
      <button
        onClick={() => onDelete(id)}
        className="opacity-0 group-hover:opacity-100 p-0.5 rounded text-fg-muted hover:text-accent-red transition-opacity"
        title="Delete layer"
      >
        <Trash2 size={12} />
      </button>
    </div>
  )
}

export function LayerPanel() {
  const layers = useScene((s) => s.scene.layers) ?? {}
  const sessionId = useChat((s) => s.sessionId)
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set())

  const entries = Object.entries(layers)
  const rootEntries = entries.filter(([, l]) => !l.parent)
  const childEntries = entries.filter(([, l]) => !!l.parent)

  const sendTool = (name: string, args: Record<string, unknown>) => {
    _runTool(name, sessionId, args)
  }

  const handleCreate = () => {
    const name = prompt('New layer name:', 'New Layer')
    if (!name) return
    const color = prompt('Layer color (hex):', '#8888ff') || '#8888ff'
    sendTool('create_layer', { name, color })
  }

  const handleDelete = (id: string) => {
    if (!confirm(`Delete layer "${layers[id]?.name}"?`)) return
    sendTool('delete_layer', { name: id })
  }

  const handleColorChange = (id: string, color: string) => {
    sendTool('set_layer_color', { name: id, color })
  }

  const handleRename = (id: string, newName: string) => {
    sendTool('rename_layer', { name: id, new_name: newName })
  }

  const handleToggleVisible = (id: string) => {
    const layer = layers[id]
    if (!layer) return
    sendTool('set_layer_visible', { name: id, visible: !layer.visible })
  }

  const handleToggleLock = (id: string) => {
    const layer = layers[id]
    if (!layer) return
    sendTool('set_layer_locked', { name: id, locked: !layer.locked })
  }

  const hasLayers = entries.length > 0

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between h-9 px-2 border-b border-border">
        <div className="flex items-center gap-1.5">
          <Users size={13} className="text-accent-cyan" />
          <span className="text-xs font-medium text-fg-primary">Layers</span>
          <span className="text-[10px] text-fg-muted">({entries.length})</span>
        </div>
        <button
          onClick={handleCreate}
          className="flex items-center gap-0.5 px-1.5 py-0.5 text-[10px] rounded bg-bg-hover hover:bg-bg-hover-active text-fg-secondary hover:text-fg-primary transition-colors"
          title="Create layer"
        >
          <Plus size={10} />
          New
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-1">
        {!hasLayers && (
          <div className="flex flex-col items-center justify-center h-full text-center px-3">
            <div className="text-fg-muted text-xs leading-relaxed">
              No layers yet.
              <br />
              Use <span className="text-fg-secondary">+ New</span> or ask the Agent
              to create a layer.
            </div>
          </div>
        )}

        {hasLayers &&
          rootEntries.map(([id, layer]) => {
            const children = childEntries.filter(([, l]) => l.parent === id)
            const isExpanded = expandedGroups.has(id) || children.length === 0
            return (
              <div key={id}>
                {children.length > 0 && (
                  <button
                    onClick={() =>
                      setExpandedGroups((prev) => {
                        const next = new Set(prev)
                        if (next.has(id)) next.delete(id)
                        else next.add(id)
                        return next
                      })
                    }
                    className="flex items-center gap-0.5 w-full text-fg-muted hover:text-fg-secondary"
                  >
                    {isExpanded ? <ChevronDown size={10} /> : <ChevronRight size={10} />}
                  </button>
                )}
                <LayerRow
                  id={id}
                  layer={layer}
                  depth={0}
                  onToggleVisible={handleToggleVisible}
                  onToggleLock={handleToggleLock}
                  onDelete={handleDelete}
                  onColorChange={handleColorChange}
                  onRename={handleRename}
                />
                {isExpanded &&
                  children.map(([cid, cl]) => (
                    <LayerRow
                      key={cid}
                      id={cid}
                      layer={cl}
                      depth={1}
                      onToggleVisible={handleToggleVisible}
                      onToggleLock={handleToggleLock}
                      onDelete={handleDelete}
                      onColorChange={handleColorChange}
                      onRename={handleRename}
                    />
                  ))}
              </div>
            )
          })}
      </div>
    </div>
  )
}
