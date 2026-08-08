// NodeGraphView — visual DAG viewer for the scene's procedural node graph.
// Renders nodes in topological order with edges showing data flow. Users can
// execute, clear, or inspect individual nodes. Mirrors the
// configure_node_graph / execute_node_graph Agent tools.
import { useState } from 'react'
import { Camera, Group, Layers, Palette, Play, Trash2, Zap, Box } from 'lucide-react'
import { useScene } from '../../store/useScene'
import { useChat } from '../../store/useChat'
import type { NodeGraphData, NodeGraphNode } from '../../types'

const _TYPE_ICON: Record<string, typeof Box> = {
  create: Box,
  modify: Zap,
  material: Palette,
  light: Layers,
  transform: Zap,
  animate: Zap,
  export: Camera,
  group: Group,
  compose: Camera,
}

const _TYPE_COLOR: Record<string, string> = {
  create: '#22c55e',
  modify: '#f97316',
  material: '#a855f7',
  light: '#eab308',
  transform: '#3b82f6',
  animate: '#ec4899',
  export: '#06b6d4',
  group: '#6366f1',
  compose: '#ef4444',
}

interface NodeBlockProps {
  node: NodeGraphNode
  topoIndex: number
  total: number
  onSelect: (id: string) => void
  selected: boolean
}

function NodeBlock({ node, topoIndex, total, onSelect, selected }: NodeBlockProps) {
  const Icon = _TYPE_ICON[node.type] || Box
  const color = _TYPE_COLOR[node.type] || '#888888'

  return (
    <button
      onClick={() => onSelect(node.id)}
      className={`relative flex flex-col items-start p-1.5 rounded border transition-all text-left w-full ${
        selected
          ? 'border-accent-cyan bg-bg-hover-active shadow-sm'
          : 'border-border bg-bg-input hover:border-border-hover hover:bg-bg-hover'
      }`}
      style={{ minHeight: 44 }}
    >
      <div className="flex items-center gap-1 w-full">
        <div
          className="w-5 h-5 rounded flex items-center justify-center shrink-0"
          style={{ backgroundColor: `${color}22`, color }}
        >
          <Icon size={10} />
        </div>
        <span className="text-[10px] font-medium text-fg-primary truncate flex-1">
          {node.tool_name || node.type}
        </span>
        <span className="text-[9px] text-fg-muted tabular-nums">
          {topoIndex + 1}/{total}
        </span>
      </div>
      <div className="flex items-center gap-1 mt-0.5">
        <span
          className="text-[9px] px-1 py-px rounded"
          style={{ backgroundColor: `${color}18`, color }}
        >
          {node.type}
        </span>
        <span className="text-[9px] text-fg-muted truncate">
          {node.category}
        </span>
      </div>
    </button>
  )
}

interface EdgeLineProps {
  from: string
  to: string
  fromColor: string
}

function EdgeLine({ from: _from, to, fromColor }: EdgeLineProps) {
  return (
    <div className="flex items-center gap-0.5 py-0.5">
      <div className="w-1.5 h-0.5 rounded" style={{ backgroundColor: fromColor }} />
      <div className="text-[8px] text-fg-muted">→</div>
      <div className="text-[9px] text-fg-muted truncate">{to}</div>
    </div>
  )
}

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

export function NodeGraphView() {
  const nodeGraph = useScene((s) => s.scene.nodeGraph)
  const sessionId = useChat((s) => s.sessionId)
  const [selectedNode, setSelectedNode] = useState<string | null>(null)

  const graph = nodeGraph as NodeGraphData | null

  const sendTool = (name: string, args: Record<string, unknown>) => {
    _runTool(name, sessionId, args)
  }

  const handleExecute = () => {
    if (!graph) return
    sendTool('execute_node_graph', { graph_name: graph.name })
  }

  const handleClear = () => {
    if (!graph) return
    if (!confirm(`Delete node graph "${graph.name}"?`)) return
    sendTool('delete_node_graph', { graph_name: graph.name })
    setSelectedNode(null)
  }

  const handleList = () => {
    sendTool('list_node_graphs', {})
  }

  if (!graph) {
    return (
      <div className="flex flex-col h-full">
        <div className="flex items-center justify-between h-9 px-2 border-b border-border">
          <div className="flex items-center gap-1.5">
            <Zap size={13} className="text-accent-purple" />
            <span className="text-xs font-medium text-fg-primary">Node Graph</span>
          </div>
          <button
            onClick={handleList}
            className="text-[10px] text-fg-muted hover:text-fg-secondary px-1.5 py-0.5 rounded hover:bg-bg-hover"
          >
            List
          </button>
        </div>
        <div className="flex flex-col items-center justify-center h-full text-center px-3">
          <Zap size={20} className="text-fg-muted mb-2 opacity-50" />
          <div className="text-fg-muted text-xs leading-relaxed">
            No node graph configured.
            <br />
            Ask the Agent to create a procedural pipeline.
          </div>
        </div>
      </div>
    )
  }

  const nodesById = new Map(graph.nodes.map((n) => [n.id, n]))
  const selectedNodeData = selectedNode ? nodesById.get(selectedNode) : null

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between h-9 px-2 border-b border-border">
        <div className="flex items-center gap-1.5">
          <Zap size={13} className="text-accent-purple" />
          <span className="text-xs font-medium text-fg-primary truncate max-w-[120px]">
            {graph.name}
          </span>
          <span className="text-[10px] text-fg-muted">
            {graph.nodes.length}n · {graph.edges.length}e
          </span>
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={handleExecute}
            className="flex items-center gap-0.5 px-1.5 py-0.5 text-[10px] rounded bg-accent-green/20 hover:bg-accent-green/30 text-accent-green transition-colors"
            title="Execute graph"
          >
            <Play size={9} />
            Run
          </button>
          <button
            onClick={handleClear}
            className="flex items-center gap-0.5 px-1.5 py-0.5 text-[10px] rounded bg-bg-hover hover:bg-bg-hover-active text-fg-muted hover:text-accent-red transition-colors"
            title="Delete graph"
          >
            <Trash2 size={9} />
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-1.5">
        {/* Topological pipeline */}
        <div className="mb-2">
          <div className="text-[10px] uppercase tracking-wider text-fg-muted mb-1">
            Pipeline · Topological Order
          </div>
          <div className="flex flex-col gap-1">
            {graph.topological_order.map((nid, idx) => {
              const node = nodesById.get(nid)
              if (!node) return null
              return (
                <NodeBlock
                  key={nid}
                  node={node}
                  topoIndex={idx}
                  total={graph.topological_order.length}
                  onSelect={setSelectedNode}
                  selected={selectedNode === nid}
                />
              )
            })}
          </div>
        </div>

        {/* Edge list */}
        <div className="mb-2">
          <div className="text-[10px] uppercase tracking-wider text-fg-muted mb-1">
            Edges · Data Flow
          </div>
          <div className="flex flex-col gap-0.5 bg-bg-input rounded p-1">
            {graph.edges.map((edge, i) => {
              const fromNode = nodesById.get(edge.from)
              const fromColor = _TYPE_COLOR[fromNode?.type || ''] || '#888888'
              return (
                <EdgeLine
                  key={i}
                  from={edge.from}
                  to={edge.to}
                  fromColor={fromColor}
                />
              )
            })}
          </div>
        </div>

        {/* Node detail */}
        {selectedNodeData && (
          <div className="border-t border-border pt-2">
            <div className="text-[10px] uppercase tracking-wider text-fg-muted mb-1">
              Selected Node
            </div>
            <div className="bg-bg-input rounded p-2 text-[10px] font-mono text-fg-secondary">
              <div className="flex justify-between">
                <span className="text-fg-muted">id</span>
                <span>{selectedNodeData.id}</span>
              </div>
              <div className="flex justify-between mt-0.5">
                <span className="text-fg-muted">type</span>
                <span style={{ color: _TYPE_COLOR[selectedNodeData.type] || '#888' }}>
                  {selectedNodeData.type}
                </span>
              </div>
              <div className="flex justify-between mt-0.5">
                <span className="text-fg-muted">tool</span>
                <span>{selectedNodeData.tool_name || 'auto'}</span>
              </div>
              <div className="mt-1 border-t border-border pt-1">
                <div className="text-fg-muted">params:</div>
                <pre className="text-[9px] mt-0.5 whitespace-pre-wrap break-all">
                  {JSON.stringify(selectedNodeData.params, null, 1)}
                </pre>
              </div>
            </div>
          </div>
        )}

        {/* Categories legend */}
        <div className="mt-2 pt-2 border-t border-border">
          <div className="text-[10px] uppercase tracking-wider text-fg-muted mb-1">
            Categories
          </div>
          <div className="flex flex-wrap gap-1">
            {graph.categories_used.map((cat) => (
              <span
                key={cat}
                className="text-[9px] px-1.5 py-0.5 rounded bg-bg-hover text-fg-secondary"
              >
                {cat}
              </span>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
