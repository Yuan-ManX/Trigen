// Pipeline node graph editor.
//
// Renders a modal overlay with a node palette (left), a draggable graph
// canvas (center) where nodes are wired together via bezier-curve edges,
// and a properties panel (right) for editing the selected node's inputs.
// A "Run" button executes the current graph through the SSE endpoint and
// reflects per-node status (running / success / failed / skipped) on each
// card in real time.
//
// The graph definition (nodes + edges) maps 1:1 to the backend pipeline
// JSON shape, so loading a backend template or sending the graph to
// /api/models/pipeline/sse needs no translation.
import { AnimatePresence, motion } from 'framer-motion'
import {
  AlertTriangle,
  Box as BoxIcon,
  CheckCircle2,
  ChevronRight,
  CircleDot,
  Eraser,
  ImageIcon,
  Loader2,
  Mic,
  Play,
  Plus,
  Sparkles,
  Type,
  Video as VideoIcon,
  X,
  Zap,
} from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  fetchPipelineNodeTypes,
  fetchPipelineTemplates,
  runPipelineStream,
  type PipelineTemplate,
} from '../../api/client'
import type {
  PipelineGraphEdge,
  PipelineGraphNode,
  PipelineNodeStatus,
  PipelineNodeType,
  PipelinePortType,
} from '../../types'

// ---------------------------------------------------------------------------
// Static metadata: human label + description + functional category for every
// built-in node type. The backend only returns port schemas, so the
// presentation metadata lives here.
// ---------------------------------------------------------------------------

type NodeCategory = PipelineNodeType['category']

interface NodeMeta {
  label: string
  description: string
  category: NodeCategory
}

const NODE_META: Record<string, NodeMeta> = {
  llm_complete: { label: 'LLM Complete', description: 'Single-shot LLM completion', category: 'llm' },
  llm_stream: { label: 'LLM Stream', description: 'Streaming LLM completion', category: 'llm' },
  generate_image: { label: 'Generate Image', description: 'Text-to-image synthesis', category: 'image' },
  generate_3d: { label: 'Generate 3D', description: 'Text-to-3D asset (GLB)', category: 'three_d' },
  generate_video: { label: 'Generate Video', description: 'Text-to-video synthesis', category: 'video' },
  generate_animation: { label: 'Generate Animation', description: 'Frame-by-frame animation', category: 'video' },
  tts: { label: 'Text-to-Speech', description: 'Synthesize speech audio', category: 'audio' },
  transcribe: { label: 'Transcribe Audio', description: 'Speech-to-text transcription', category: 'audio' },
  image_to_3d: { label: 'Image → 3D', description: 'Reconstruct 3D scene from an image', category: 'three_d' },
  literal: { label: 'Literal', description: 'Pass-through constant value', category: 'utility' },
}

const CATEGORY_META: Record<NodeCategory, { label: string; icon: typeof Type; color: string; accent: string }> = {
  llm: { label: 'Language', icon: Type, color: 'text-accent-cyan', accent: 'border-accent-cyan/40 bg-accent-cyan/5' },
  image: { label: 'Image', icon: ImageIcon, color: 'text-accent-purple', accent: 'border-accent-purple/40 bg-accent-purple/5' },
  three_d: { label: '3D', icon: BoxIcon, color: 'text-accent-emerald', accent: 'border-accent-emerald/40 bg-accent-emerald/5' },
  video: { label: 'Video', icon: VideoIcon, color: 'text-rose-400', accent: 'border-rose-400/40 bg-rose-400/5' },
  audio: { label: 'Audio', icon: Mic, color: 'text-amber-400', accent: 'border-amber-400/40 bg-amber-400/5' },
  utility: { label: 'Utility', icon: Zap, color: 'text-fg-muted', accent: 'border-border bg-bg-elevated/40' },
}

// ---------------------------------------------------------------------------
// Geometry constants for port layout. Nodes are a fixed width; ports stack
// vertically on either side. The bezier connection endpoints are derived
// from these so the SVG overlay stays in sync with the DOM.
// ---------------------------------------------------------------------------

const NODE_WIDTH = 220
const PORT_HEIGHT = 18
const HEADER_HEIGHT = 38

// ---------------------------------------------------------------------------
// Status badge presentation
// ---------------------------------------------------------------------------

const STATUS_META: Record<PipelineNodeStatus, { label: string; color: string; icon: typeof CheckCircle2 }> = {
  pending: { label: 'Pending', color: 'text-fg-muted', icon: CircleDot },
  running: { label: 'Running', color: 'text-accent-cyan', icon: Loader2 },
  success: { label: 'Success', color: 'text-emerald-400', icon: CheckCircle2 },
  failed: { label: 'Failed', color: 'text-rose-400', icon: AlertTriangle },
  skipped: { label: 'Skipped', color: 'text-amber-400', icon: AlertTriangle },
}

// ---------------------------------------------------------------------------
// Auto-layout: arrange nodes in a left-to-right flow based on edge depth.
// Used after loading a template so the graph is readable without manual
// dragging. Falls back to a vertical stack when there are no edges.
// ---------------------------------------------------------------------------

function autoLayout(nodes: PipelineGraphNode[], edges: PipelineGraphEdge[]): PipelineGraphNode[] {
  if (nodes.length === 0) return nodes

  // Compute depth (longest path from any source) for each node.
  const depthById = new Map<string, number>()
  const byId = new Map(nodes.map((n) => [n.id, n]))

  // Topological pass — nodes with no incoming edge start at depth 0.
  const incomingCount = new Map<string, number>()
  nodes.forEach((n) => incomingCount.set(n.id, 0))
  edges.forEach((e) => incomingCount.set(e.to, (incomingCount.get(e.to) ?? 0) + 1))

  const queue: string[] = nodes.filter((n) => (incomingCount.get(n.id) ?? 0) === 0).map((n) => n.id)
  depthById.clear()
  queue.forEach((id) => depthById.set(id, 0))

  while (queue.length > 0) {
    const id = queue.shift()!
    const depth = depthById.get(id) ?? 0
    for (const edge of edges) {
      if (edge.from === id) {
        const next = edge.to
        depthById.set(next, Math.max(depthById.get(next) ?? 0, depth + 1))
        const c = (incomingCount.get(next) ?? 1) - 1
        incomingCount.set(next, c)
        if (c === 0) queue.push(next)
      }
    }
  }

  // Any node not reached (cycle or isolated) gets depth 0.
  nodes.forEach((n) => {
    if (!depthById.has(n.id)) depthById.set(n.id, 0)
  })

  // Group by depth column, stack vertically within each column.
  const columns = new Map<number, PipelineGraphNode[]>()
  nodes.forEach((n) => {
    const d = depthById.get(n.id) ?? 0
    if (!columns.has(d)) columns.set(d, [])
    columns.get(d)!.push(n)
  })

  const COLUMN_GAP = 80
  const ROW_GAP = 32
  const positioned: PipelineGraphNode[] = []
  const maxColumn = Math.max(...columns.keys())
  for (let col = 0; col <= maxColumn; col++) {
    const colNodes = columns.get(col) ?? []
    const colHeight = colNodes.reduce((acc, n) => {
      const portCount = Math.max(
        Object.keys(NODE_META[n.type] ? NODE_META[n.type] : { inputs: 0, outputs: 0 }).length,
        1,
      )
      return acc + HEADER_HEIGHT + portCount * PORT_HEIGHT + ROW_GAP
    }, 0)
    let y = -colHeight / 2
    for (const node of colNodes) {
      const meta = NODE_META[node.type]
      const portCount = Math.max(meta ? Object.keys(node.inputs).length : 1, 1)
      const height = HEADER_HEIGHT + portCount * PORT_HEIGHT
      positioned.push({
        ...node,
        position: {
          x: col * (NODE_WIDTH + COLUMN_GAP) - (maxColumn * (NODE_WIDTH + COLUMN_GAP)) / 2,
          y: y + height / 2,
        },
      })
      y += height + ROW_GAP
    }
  }

  // Preserve nodes that weren't placed (shouldn't happen, but be safe).
  const placed = new Set(positioned.map((n) => n.id))
  for (const node of nodes) {
    if (!placed.has(node.id) && byId.has(node.id)) {
      positioned.push({ ...node, position: { x: 0, y: 0 } })
    }
  }
  return positioned
}

// ---------------------------------------------------------------------------
// Build a stable node id when adding from the palette.
// ---------------------------------------------------------------------------

function makeNodeId(type: string, existing: PipelineGraphNode[]): string {
  let i = 1
  const ids = new Set(existing.map((n) => n.id))
  while (ids.has(`${type}_${i}`)) i++
  return `${type}_${i}`
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

interface NodeGraphViewProps {
  open: boolean
  onClose: () => void
}

export function NodeGraphView({ open, onClose }: NodeGraphViewProps) {
  // ----- node type catalog (from backend) -----
  const [nodeTypes, setNodeTypes] = useState<PipelineNodeType[]>([])
  const [templates, setTemplates] = useState<PipelineTemplate[]>([])

  // ----- graph state -----
  const [nodes, setNodes] = useState<PipelineGraphNode[]>([])
  const [edges, setEdges] = useState<PipelineGraphEdge[]>([])
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null)
  const [statusById, setStatusById] = useState<Record<string, PipelineNodeStatus>>({})
  const [errorById, setErrorById] = useState<Record<string, string>>({})
  const [running, setRunning] = useState(false)
  const [summary, setSummary] = useState<{ succeeded: number; failed: number; total: number; elapsed: number } | null>(null)

  // ----- interaction refs -----
  const canvasRef = useRef<HTMLDivElement | null>(null)
  const draggingNodeRef = useRef<{ id: string; offsetX: number; offsetY: number } | null>(null)
  const pendingEdgeRef = useRef<{ from: string; output: string; x: number; y: number } | null>(null)
  const [pendingEdge, setPendingEdge] = useState<{ from: string; output: string; x: number; y: number } | null>(null)

  // Mirror nodeTypes into a ref so imperative handlers (addNode) can read
  // the latest catalog without re-creating their useCallback identity.
  const nodeTypesRef = useRef<PipelineNodeType[]>([])
  useEffect(() => {
    nodeTypesRef.current = nodeTypes
  }, [nodeTypes])

  // ----- load catalog on open -----
  useEffect(() => {
    if (!open) return
    let cancelled = false
    Promise.all([fetchPipelineNodeTypes(), fetchPipelineTemplates()])
      .then(([ntResp, tpls]) => {
        if (cancelled) return
        const enriched: PipelineNodeType[] = Object.entries(ntResp.node_types).map(([type, schema]) => {
          const meta = NODE_META[type] ?? {
            label: type,
            description: 'Custom runtime node',
            category: 'utility' as NodeCategory,
          }
          return {
            type,
            label: meta.label,
            description: meta.description,
            category: meta.category,
            inputs: schema.inputs ?? {},
            outputs: schema.outputs ?? {},
          }
        })
        // Stable ordering: by category then type so the palette doesn't reshuffle.
        enriched.sort((a, b) => a.category.localeCompare(b.category) || a.type.localeCompare(b.type))
        setNodeTypes(enriched)
        setTemplates(tpls)
      })
      .catch(() => {
        /* Catalog load failed — palette will render empty. */
      })
    return () => {
      cancelled = true
    }
  }, [open])

  // ----- reset graph state when modal closes -----
  useEffect(() => {
    if (!open) {
      setNodes([])
      setEdges([])
      setSelectedNodeId(null)
      setStatusById({})
      setErrorById({})
      setSummary(null)
      setRunning(false)
    }
  }, [open])

  // ----- palette grouped by category -----
  const paletteGroups = useMemo(() => {
    const groups = new Map<NodeCategory, PipelineNodeType[]>()
    for (const nt of nodeTypes) {
      if (!groups.has(nt.category)) groups.set(nt.category, [])
      groups.get(nt.category)!.push(nt)
    }
    return Array.from(groups.entries()).sort((a, b) => a[0].localeCompare(b[0]))
  }, [nodeTypes])

  const selectedNode = useMemo(
    () => nodes.find((n) => n.id === selectedNodeId) ?? null,
    [nodes, selectedNodeId],
  )
  const selectedNodeType = useMemo(
    () => (selectedNode ? nodeTypes.find((t) => t.type === selectedNode.type) ?? null : null),
    [selectedNode, nodeTypes],
  )

  // ----- node operations -----
  const addNode = useCallback((type: string) => {
    const schema = nodeTypesRef.current.find((p) => p.type === type)
    const inputs: Record<string, unknown> = {}
    // Seed default inputs from the schema so the user can edit them
    // immediately. If the type catalog hasn't loaded yet, inputs will
    // be empty and the user can re-add the node once it loads.
    if (schema) {
      for (const key of Object.keys(schema.inputs)) inputs[key] = ''
    }
    setNodes((prev) => {
      const id = makeNodeId(type, prev)
      const offset = prev.length * 24
      return [
        ...prev,
        {
          id,
          type,
          inputs,
          position: { x: 120 + offset, y: 120 + offset },
        },
      ]
    })
  }, [])

  const removeNode = useCallback((id: string) => {
    setNodes((prev) => prev.filter((n) => n.id !== id))
    setEdges((prev) => prev.filter((e) => e.from !== id && e.to !== id))
    setStatusById((prev) => {
      const next = { ...prev }
      delete next[id]
      return next
    })
    setErrorById((prev) => {
      const next = { ...prev }
      delete next[id]
      return next
    })
    setSelectedNodeId((cur) => (cur === id ? null : cur))
  }, [])

  const updateNodeInput = useCallback((id: string, key: string, value: unknown) => {
    setNodes((prev) =>
      prev.map((n) =>
        n.id === id ? { ...n, inputs: { ...n.inputs, [key]: value } } : n,
      ),
    )
  }, [])

  // ----- dragging nodes -----
  const onNodeMouseDown = useCallback((e: React.MouseEvent, node: PipelineGraphNode) => {
    e.stopPropagation()
    setSelectedNodeId(node.id)
    const canvas = canvasRef.current
    if (!canvas) return
    const rect = canvas.getBoundingClientRect()
    draggingNodeRef.current = {
      id: node.id,
      offsetX: e.clientX - rect.left - node.position.x,
      offsetY: e.clientY - rect.top - node.position.y,
    }
  }, [])

  useEffect(() => {
    if (!open) return
    const onMove = (e: MouseEvent) => {
      const canvas = canvasRef.current
      if (!canvas) return
      const rect = canvas.getBoundingClientRect()
      const x = e.clientX - rect.left
      const y = e.clientY - rect.top

      if (draggingNodeRef.current) {
        const { id, offsetX, offsetY } = draggingNodeRef.current
        setNodes((prev) =>
          prev.map((n) =>
            n.id === id ? { ...n, position: { x: x - offsetX, y: y - offsetY } } : n,
          ),
        )
      } else if (pendingEdgeRef.current) {
        pendingEdgeRef.current = { ...pendingEdgeRef.current, x, y }
        setPendingEdge({ ...pendingEdgeRef.current })
      }
    }
    const onUp = () => {
      draggingNodeRef.current = null
      if (pendingEdgeRef.current) {
        pendingEdgeRef.current = null
        setPendingEdge(null)
      }
    }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
    return () => {
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }
  }, [open])

  // ----- edge creation -----
  const onOutputPortMouseDown = useCallback(
    (e: React.MouseEvent, nodeId: string, output: string) => {
      e.stopPropagation()
      const canvas = canvasRef.current
      if (!canvas) return
      const rect = canvas.getBoundingClientRect()
      pendingEdgeRef.current = {
        from: nodeId,
        output,
        x: e.clientX - rect.left,
        y: e.clientY - rect.top,
      }
      setPendingEdge({ ...pendingEdgeRef.current })
    },
    [],
  )

  const onInputPortMouseUp = useCallback(
    (nodeId: string, input: string) => {
      if (!pendingEdgeRef.current) return
      const { from, output } = pendingEdgeRef.current
      if (from === nodeId) {
        pendingEdgeRef.current = null
        setPendingEdge(null)
        return
      }
      setEdges((prev) => {
        // Replace any existing edge into the same (nodeId, input) —
        // one upstream source per input.
        const filtered = prev.filter((e) => !(e.to === nodeId && e.input === input))
        return [...filtered, { from, output, to: nodeId, input }]
      })
      // Mirror the edge into the node's inputs so the backend pipeline
      // JSON carries the {"from":..,"output":..} reference.
      setNodes((prev) =>
        prev.map((n) =>
          n.id === nodeId
            ? { ...n, inputs: { ...n.inputs, [input]: { from, output } } }
            : n,
        ),
      )
      pendingEdgeRef.current = null
      setPendingEdge(null)
    },
    [],
  )

  const removeEdge = useCallback((edge: PipelineGraphEdge) => {
    setEdges((prev) => prev.filter((e) => !(e.from === edge.from && e.output === edge.output && e.to === edge.to && e.input === edge.input)))
    setNodes((prev) =>
      prev.map((n) =>
        n.id === edge.to
          ? { ...n, inputs: { ...n.inputs, [edge.input]: '' } }
          : n,
      ),
    )
  }, [])

  // ----- templates -----
  const loadTemplate = useCallback((tpl: PipelineTemplate) => {
    const rawNodes = (tpl.nodes ?? []) as Array<{
      id: string
      type: string
      inputs?: Record<string, unknown>
    }>
    const placed: PipelineGraphNode[] = rawNodes.map((n) => ({
      id: n.id,
      type: n.type,
      inputs: { ...(n.inputs ?? {}) },
      position: { x: 0, y: 0 },
    }))
    // Derive edges from {"from":..,"output":..} input refs.
    const derivedEdges: PipelineGraphEdge[] = []
    for (const node of placed) {
      for (const [key, value] of Object.entries(node.inputs)) {
        if (value && typeof value === 'object' && 'from' in value && 'output' in value) {
          const ref = value as { from: string; output: string }
          derivedEdges.push({ from: ref.from, output: ref.output, to: node.id, input: key })
        }
      }
    }
    const laid = autoLayout(placed, derivedEdges)
    setNodes(laid)
    setEdges(derivedEdges)
    setStatusById({})
    setErrorById({})
    setSummary(null)
    setSelectedNodeId(null)
  }, [])

  const clearGraph = useCallback(() => {
    setNodes([])
    setEdges([])
    setStatusById({})
    setErrorById({})
    setSummary(null)
    setSelectedNodeId(null)
  }, [])

  // ----- execution -----
  const runGraph = useCallback(async () => {
    if (running || nodes.length === 0) return
    setRunning(true)
    setStatusById({})
    setErrorById({})
    setSummary(null)
    // Mark every node pending so the UI shows the queue immediately.
    const initial: Record<string, PipelineNodeStatus> = {}
    nodes.forEach((n) => (initial[n.id] = 'pending'))
    setStatusById(initial)

    try {
      const payload = nodes.map((n) => ({
        id: n.id,
        type: n.type,
        inputs: n.inputs,
      }))
      for await (const ev of runPipelineStream('graph_editor', payload)) {
        if (ev.event === 'start' && ev.node_id) {
          setStatusById((prev) => ({ ...prev, [ev.node_id!]: 'running' }))
        } else if (ev.event === 'result' && ev.node_id) {
          const status = (ev.status ?? 'failed') as PipelineNodeStatus
          setStatusById((prev) => ({ ...prev, [ev.node_id!]: status }))
          if (ev.error) {
            setErrorById((prev) => ({ ...prev, [ev.node_id!]: ev.error! }))
          }
        } else if (ev.event === 'done') {
          setSummary({
            succeeded: ev.succeeded ?? 0,
            failed: ev.failed ?? 0,
            total: ev.node_count ?? 0,
            elapsed: ev.total_elapsed_ms ?? 0,
          })
        }
      }
    } catch (err) {
      // Surface a global failure on every pending/running node.
      const msg = err instanceof Error ? err.message : String(err)
      setStatusById((prev) => {
        const next = { ...prev }
        for (const [id, s] of Object.entries(next)) {
          if (s === 'pending' || s === 'running') next[id] = 'failed'
        }
        return next
      })
      setSummary({ succeeded: 0, failed: nodes.length, total: nodes.length, elapsed: 0 })
      void msg
    } finally {
      setRunning(false)
    }
  }, [nodes, running])

  // ----- port geometry helpers -----
  // Returns the (x, y) of a port center in canvas-space pixels.
  const portPos = useCallback(
    (node: PipelineGraphNode, side: 'in' | 'out', portIndex: number) => {
      const x = side === 'in' ? node.position.x : node.position.x + NODE_WIDTH
      const y = node.position.y + HEADER_HEIGHT / 2 + portIndex * PORT_HEIGHT + PORT_HEIGHT / 2
      return { x, y }
    },
    [],
  )

  // ----- render -----
  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.18 }}
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4"
          onClick={onClose}
          role="dialog"
          aria-modal="true"
          aria-label="Pipeline Node Graph Editor"
        >
          <motion.div
            initial={{ scale: 0.96, opacity: 0, y: 12 }}
            animate={{ scale: 1, opacity: 1, y: 0 }}
            exit={{ scale: 0.96, opacity: 0, y: 12 }}
            transition={{ duration: 0.22, ease: 'easeOut' }}
            onClick={(e) => e.stopPropagation()}
            className="relative w-[1180px] max-w-[95vw] h-[760px] max-h-[92vh] rounded-xl border border-border bg-bg-panel shadow-2xl overflow-hidden flex flex-col"
          >
            {/* Header */}
            <header className="flex items-center justify-between h-12 px-4 border-b border-border bg-bg-elevated/40">
              <div className="flex items-center gap-2.5">
                <div className="flex items-center justify-center w-7 h-7 rounded-md bg-accent-cyan/15 border border-accent-cyan/30">
                  <Sparkles size={14} className="text-accent-cyan" />
                </div>
                <div>
                  <h2 className="text-sm font-semibold text-fg-primary leading-tight">Pipeline Node Graph</h2>
                  <p className="text-[10px] text-fg-muted leading-tight">
                    Multi-step generation pipeline
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-2">
                {/* Template selector */}
                <select
                  className="text-[11px] bg-bg-elevated border border-border rounded px-2 py-1 text-fg-secondary hover:border-accent-cyan/40 transition-colors outline-none"
                  defaultValue=""
                  onChange={(e) => {
                    const id = e.target.value
                    const tpl = templates.find((t) => t.id === id)
                    if (tpl) loadTemplate(tpl)
                    e.target.value = ''
                  }}
                  title="Load a pre-built pipeline template"
                >
                  <option value="" disabled>
                    Load template…
                  </option>
                  {templates.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.name}
                    </option>
                  ))}
                </select>

                {/* Clear */}
                <button
                  onClick={clearGraph}
                  disabled={running || nodes.length === 0}
                  className="flex items-center gap-1.5 px-2.5 py-1 rounded-md border border-border text-[11px] text-fg-secondary hover:text-fg-primary hover:bg-bg-hover transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                  title="Clear the canvas"
                >
                  <Eraser size={12} />
                  Clear
                </button>

                {/* Run */}
                <button
                  onClick={runGraph}
                  disabled={running || nodes.length === 0}
                  className="flex items-center gap-1.5 px-3 py-1 rounded-md bg-accent-cyan/15 border border-accent-cyan/40 text-accent-cyan text-[11px] font-semibold hover:bg-accent-cyan/25 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  {running ? <Loader2 size={12} className="animate-spin" /> : <Play size={12} />}
                  {running ? 'Running…' : 'Run pipeline'}
                </button>

                <button
                  onClick={onClose}
                  aria-label="Close node graph editor"
                  className="flex items-center justify-center w-7 h-7 rounded text-fg-muted hover:text-fg-primary hover:bg-bg-hover transition-colors"
                >
                  <X size={15} />
                </button>
              </div>
            </header>

            {/* Body: palette | canvas | properties */}
            <div className="flex flex-1 min-h-0">
              {/* Palette */}
              <aside className="w-[220px] shrink-0 border-r border-border bg-bg-panel overflow-y-auto">
                <div className="px-3 py-2 text-[10px] uppercase tracking-wider text-fg-muted font-semibold border-b border-border-subtle sticky top-0 bg-bg-panel">
                  Node Palette
                </div>
                <div className="p-2 space-y-3">
                  {paletteGroups.length === 0 && (
                    <div className="text-[11px] text-fg-muted px-2 py-4 text-center">Loading…</div>
                  )}
                  {paletteGroups.map(([category, items]) => {
                    const meta = CATEGORY_META[category]
                    const CatIcon = meta.icon
                    return (
                      <div key={category}>
                        <div className={`flex items-center gap-1.5 px-1 mb-1.5 text-[10px] font-semibold uppercase tracking-wider ${meta.color}`}>
                          <CatIcon size={11} />
                          {meta.label}
                        </div>
                        <div className="space-y-1">
                          {items.map((nt) => (
                            <button
                              key={nt.type}
                              onClick={() => addNode(nt.type)}
                              className="w-full text-left rounded-md border border-border bg-bg-elevated/40 hover:bg-bg-hover hover:border-accent-cyan/40 transition-all px-2 py-1.5 group"
                            >
                              <div className="flex items-center justify-between gap-1.5">
                                <span className="text-[11px] font-medium text-fg-primary group-hover:text-accent-cyan transition-colors">
                                  {nt.label}
                                </span>
                                <Plus size={11} className="text-fg-muted opacity-0 group-hover:opacity-100 transition-opacity" />
                              </div>
                              <p className="text-[9.5px] text-fg-muted leading-tight mt-0.5 line-clamp-2">
                                {nt.description}
                              </p>
                            </button>
                          ))}
                        </div>
                      </div>
                    )
                  })}
                </div>
              </aside>

              {/* Canvas */}
              <div
                ref={canvasRef}
                onClick={() => setSelectedNodeId(null)}
                className="relative flex-1 overflow-hidden bg-bg-base"
                style={{
                  backgroundImage:
                    'radial-gradient(circle, rgba(148,163,184,0.08) 1px, transparent 1px)',
                  backgroundSize: '24px 24px',
                }}
              >
                {/* SVG edge layer */}
                <svg className="absolute inset-0 w-full h-full pointer-events-none">
                  <defs>
                    <marker
                      id="edge-arrow"
                      viewBox="0 0 10 10"
                      refX="8"
                      refY="5"
                      markerWidth="6"
                      markerHeight="6"
                      orient="auto-start-reverse"
                    >
                      <path d="M 0 0 L 10 5 L 0 10 z" fill="rgb(148,163,184)" />
                    </marker>
                  </defs>
                  {edges.map((edge) => {
                    const fromNode = nodes.find((n) => n.id === edge.from)
                    const toNode = nodes.find((n) => n.id === edge.to)
                    if (!fromNode || !toNode) return null
                    const fromType = nodeTypes.find((t) => t.type === fromNode.type)
                    const toType = nodeTypes.find((t) => t.type === toNode.type)
                    const fromIdx = fromType ? Object.keys(fromType.outputs).indexOf(edge.output) : -1
                    const toIdx = toType ? Object.keys(toType.inputs).indexOf(edge.input) : -1
                    if (fromIdx < 0 || toIdx < 0) return null
                    const a = portPos(fromNode, 'out', fromIdx)
                    const b = portPos(toNode, 'in', toIdx)
                    const midX = (a.x + b.x) / 2
                    const path = `M ${a.x},${a.y} C ${midX},${a.y} ${midX},${b.y} ${b.x},${b.y}`
                    return (
                      <g key={`${edge.from}.${edge.output}->${edge.to}.${edge.input}`} className="pointer-events-auto cursor-pointer" onClick={(e) => { e.stopPropagation(); removeEdge(edge) }}>
                        <path d={path} stroke="transparent" strokeWidth="10" fill="none" />
                        <path
                          d={path}
                          stroke="rgba(148,163,184,0.7)"
                          strokeWidth="1.6"
                          fill="none"
                          markerEnd="url(#edge-arrow)"
                        />
                      </g>
                    )
                  })}
                  {pendingEdge && (() => {
                    const fromNode = nodes.find((n) => n.id === pendingEdge.from)
                    if (!fromNode) return null
                    const fromType = nodeTypes.find((t) => t.type === fromNode.type)
                    const fromIdx = fromType ? Object.keys(fromType.outputs).indexOf(pendingEdge.output) : -1
                    if (fromIdx < 0) return null
                    const a = portPos(fromNode, 'out', fromIdx)
                    const b = { x: pendingEdge.x, y: pendingEdge.y }
                    const midX = (a.x + b.x) / 2
                    const path = `M ${a.x},${a.y} C ${midX},${a.y} ${midX},${b.y} ${b.x},${b.y}`
                    return <path d={path} stroke="rgba(34,211,238,0.7)" strokeWidth="1.6" fill="none" strokeDasharray="4 4" />
                  })()}
                </svg>

                {/* Nodes */}
                {nodes.map((node) => {
                  const meta = NODE_META[node.type] ?? {
                    label: node.type,
                    description: '',
                    category: 'utility' as NodeCategory,
                  }
                  const catMeta = CATEGORY_META[meta.category]
                  const CatIcon = catMeta.icon
                  const typeSchema = nodeTypes.find((t) => t.type === node.type)
                  const inKeys = typeSchema ? Object.keys(typeSchema.inputs) : []
                  const outKeys = typeSchema ? Object.keys(typeSchema.outputs) : []
                  const status = statusById[node.id] ?? null
                  const statusMeta = status ? STATUS_META[status] : null
                  const StatusIcon = statusMeta?.icon
                  const isSelected = selectedNodeId === node.id

                  return (
                    <div
                      key={node.id}
                      onMouseDown={(e) => onNodeMouseDown(e, node)}
                      className={`absolute rounded-md border bg-bg-panel shadow-lg select-none transition-shadow ${
                        isSelected
                          ? 'border-accent-cyan shadow-glow'
                          : 'border-border hover:border-fg-muted/40'
                      }`}
                      style={{
                        left: node.position.x,
                        top: node.position.y,
                        width: NODE_WIDTH,
                      }}
                    >
                      {/* Header */}
                      <div className={`flex items-center justify-between gap-2 px-2.5 h-[38px] border-b border-border-subtle ${catMeta.accent}`}>
                        <div className="flex items-center gap-1.5 min-w-0">
                          <CatIcon size={12} className={catMeta.color} />
                          <span className="text-[11px] font-semibold text-fg-primary truncate">
                            {meta.label}
                          </span>
                        </div>
                        <div className="flex items-center gap-1">
                          {StatusIcon && (
                            <StatusIcon
                              size={11}
                              className={`${statusMeta!.color} ${status === 'running' ? 'animate-spin' : ''}`}
                            />
                          )}
                          <button
                            onClick={(e) => { e.stopPropagation(); removeNode(node.id) }}
                            className="text-fg-muted hover:text-rose-400 transition-colors"
                            aria-label="Remove node"
                          >
                            <X size={11} />
                          </button>
                        </div>
                      </div>

                      {/* Ports */}
                      <div className="relative py-1.5">
                        {/* Input ports (left side) */}
                        {inKeys.map((key, idx) => {
                          const portType = typeSchema?.inputs[key] ?? 'any'
                          return (
                            <div
                              key={`in-${key}`}
                              onMouseUp={() => onInputPortMouseUp(node.id, key)}
                              className="flex items-center gap-1.5 h-[18px] px-2.5 text-[10px] text-fg-secondary hover:text-fg-primary"
                            >
                              <span
                                className="absolute left-0 w-[10px] h-[10px] -translate-x-1/2 rounded-full border border-border bg-bg-elevated hover:bg-accent-cyan hover:border-accent-cyan transition-colors"
                                style={{ marginTop: idx * PORT_HEIGHT + 6 }}
                                title={`${key}: ${portType}`}
                              />
                              <span className="font-mono text-fg-muted">{key}</span>
                              <span className="text-fg-muted/60 text-[9px]">:{portType}</span>
                            </div>
                          )
                        })}
                        {/* Output ports (right side) */}
                        {outKeys.map((key, idx) => {
                          const portType = typeSchema?.outputs[key] ?? 'any'
                          return (
                            <div
                              key={`out-${key}`}
                              onMouseDown={(e) => onOutputPortMouseDown(e, node.id, key)}
                              className="flex items-center justify-end gap-1.5 h-[18px] px-2.5 text-[10px] text-fg-secondary hover:text-fg-primary cursor-crosshair"
                            >
                              <span className="text-fg-muted/60 text-[9px]">{portType}:</span>
                              <span className="font-mono text-fg-muted">{key}</span>
                              <span
                                className="absolute right-0 w-[10px] h-[10px] translate-x-1/2 rounded-full border border-border bg-bg-elevated hover:bg-accent-cyan hover:border-accent-cyan transition-colors"
                                style={{ marginTop: idx * PORT_HEIGHT + 6 }}
                                title={`${key}: ${portType}`}
                              />
                            </div>
                          )
                        })}
                        {inKeys.length === 0 && outKeys.length === 0 && (
                          <div className="px-2.5 py-1 text-[10px] text-fg-muted italic">no ports</div>
                        )}
                      </div>

                      {/* Error message (when failed) */}
                      {errorById[node.id] && (
                        <div className="px-2.5 py-1 border-t border-rose-400/20 bg-rose-500/5 text-[9.5px] text-rose-400 leading-tight">
                          {errorById[node.id]}
                        </div>
                      )}
                    </div>
                  )
                })}

                {/* Empty state */}
                {nodes.length === 0 && (
                  <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                    <div className="text-center max-w-xs">
                      <div className="mx-auto w-12 h-12 rounded-full bg-bg-elevated border border-border flex items-center justify-center mb-3">
                        <ChevronRight size={20} className="text-fg-muted" />
                      </div>
                      <p className="text-[12px] text-fg-secondary font-medium">Empty pipeline graph</p>
                      <p className="text-[11px] text-fg-muted mt-1">
                        Click a node in the palette to add it, or load a template from the header.
                        Drag from an output port to an input port to wire nodes together.
                      </p>
                    </div>
                  </div>
                )}

                {/* Summary toast */}
                {summary && (
                  <div className="absolute bottom-3 right-3 rounded-md border border-border bg-bg-elevated/95 backdrop-blur shadow-lg px-3 py-2 text-[11px]">
                    <div className="flex items-center gap-2 mb-1">
                      <CheckCircle2 size={12} className={summary.failed === 0 ? 'text-emerald-400' : 'text-amber-400'} />
                      <span className="font-semibold text-fg-primary">
                        {summary.failed === 0 ? 'Pipeline complete' : 'Pipeline finished with errors'}
                      </span>
                    </div>
                    <div className="text-fg-muted">
                      <span className="text-emerald-400">{summary.succeeded} succeeded</span>
                      {' · '}
                      <span className="text-rose-400">{summary.failed} failed</span>
                      {' · '}
                      {summary.total} nodes · {summary.elapsed} ms
                    </div>
                  </div>
                )}
              </div>

              {/* Properties panel */}
              <aside className="w-[260px] shrink-0 border-l border-border bg-bg-panel overflow-y-auto">
                <div className="px-3 py-2 text-[10px] uppercase tracking-wider text-fg-muted font-semibold border-b border-border-subtle sticky top-0 bg-bg-panel">
                  Properties
                </div>
                {selectedNode && selectedNodeType ? (
                  <div className="p-3 space-y-3">
                    <div>
                      <div className="text-[11px] font-semibold text-fg-primary">{selectedNodeType.label}</div>
                      <div className="text-[10px] text-fg-muted mt-0.5">{selectedNodeType.description}</div>
                    </div>
                    <div className="text-[10px] text-fg-muted font-mono">
                      id: <span className="text-fg-secondary">{selectedNode.id}</span>
                    </div>

                    {Object.keys(selectedNodeType.inputs).length === 0 ? (
                      <p className="text-[11px] text-fg-muted italic">No editable inputs.</p>
                    ) : (
                      <div className="space-y-2">
                        {Object.entries(selectedNodeType.inputs).map(([key, type]) => {
                          const value = selectedNode.inputs[key]
                          const isRef = value && typeof value === 'object' && 'from' in value && 'output' in value
                          return (
                            <div key={key}>
                              <label className="flex items-center justify-between text-[10px] text-fg-muted mb-1">
                                <span className="font-mono">{key}</span>
                                <span className="text-fg-muted/60">:{type as PipelinePortType}</span>
                              </label>
                              {isRef ? (
                                <div className="flex items-center gap-1.5 text-[10px] px-2 py-1 rounded border border-accent-cyan/30 bg-accent-cyan/5 text-accent-cyan">
                                  <ChevronRight size={10} />
                                  <span className="font-mono">
                                    {(value as { from: string }).from}.{(value as { output: string }).output}
                                  </span>
                                </div>
                              ) : (
                                <input
                                  type={type === 'int' ? 'number' : 'text'}
                                  value={typeof value === 'string' || typeof value === 'number' ? String(value) : ''}
                                  onChange={(e) =>
                                    updateNodeInput(
                                      selectedNode.id,
                                      key,
                                      type === 'int' ? parseInt(e.target.value, 10) || 0 : e.target.value,
                                    )
                                  }
                                  className="w-full text-[11px] bg-bg-elevated border border-border rounded px-2 py-1 text-fg-primary outline-none focus:border-accent-cyan/50"
                                  placeholder={type === 'int' ? '0' : '…'}
                                />
                              )}
                            </div>
                          )
                        })}
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="p-3 text-[11px] text-fg-muted">
                    Select a node to edit its inputs.
                  </div>
                )}
              </aside>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
