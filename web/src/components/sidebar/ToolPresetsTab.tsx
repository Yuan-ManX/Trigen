// Tool Presets tab: parameterized quick forms for the newest generative tool
// families — voxel sculpting, particle systems, LOD chains, mesh repair,
// self-evaluation, and consensus voting. Loads per-tool defaults from the
// backend /api/presets/tools endpoint and executes each tool directly via
// /api/tools/execute, committing the resulting scene into the editor store
// so every change is undoable and reflects in the viewport immediately.
import { Boxes, Cog, Flame, Layers, Loader2, Play, RefreshCw, ShieldCheck, Sparkles, Wand2 } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { executeTool, fetchToolPresets, type ToolPresetDescriptor, type ToolPresetsResponse } from '../../api/client'
import { useChat } from '../../store/useChat'
import { useScene } from '../../store/useScene'
import type { SceneObject } from '../../types'

/** Resolve a preset icon by tool name. */
function presetIcon(name: string) {
  switch (name) {
    case 'voxel_sculpt':
      return Boxes
    case 'create_particle_system':
      return Flame
    case 'generate_lod_chain':
      return Layers
    case 'repair_mesh':
      return ShieldCheck
    case 'self_evaluate':
      return Cog
    case 'consensus_vote':
      return Sparkles
    default:
      return Wand2
  }
}

/** Pick the first mesh object in the scene, if any (used as a target). */
function firstMesh(objects: SceneObject[]): SceneObject | undefined {
  return objects.find((o) => o.type === 'mesh' || o.type === 'group')
}

export function ToolPresetsTab() {
  const [presets, setPresets] = useState<ToolPresetsResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selected, setSelected] = useState<string>('voxel_sculpt')
  const [args, setArgs] = useState<Record<string, unknown>>({})
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState<{ ok: boolean; message: string } | null>(null)

  const commitScene = useScene((s) => s.commitScene)
  const currentScene = useScene((s) => s.scene)
  const sessionId = useChat((s) => s.sessionId)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    fetchToolPresets()
      .then((payload) => {
        if (cancelled) return
        setPresets(payload)
        setError(null)
      })
      .catch((err: unknown) => {
        if (cancelled) return
        setError(err instanceof Error ? err.message : 'Failed to load tool presets')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const descriptor: ToolPresetDescriptor | undefined = presets?.tools[selected]

  // Reset arguments whenever the selected tool changes.
  useEffect(() => {
    if (descriptor) setArgs({ ...descriptor.defaults })
    else setArgs({})
    setResult(null)
  }, [selected]) // eslint-disable-line react-hooks/exhaustive-deps

  const run = async () => {
    if (!descriptor || running) return
    setRunning(true)
    setResult(null)
    // For target-based tools, default the target to the first mesh if empty.
    const merged = { ...args }
    if ((selected === 'generate_lod_chain' || selected === 'repair_mesh') && !merged.target) {
      const mesh = firstMesh(currentScene?.objects ?? [])
      if (mesh) merged.target = mesh.name
    }
    try {
      const res = await executeTool(selected, merged, sessionId || 'default')
      if (res.scene) commitScene(res.scene, currentScene)
      setResult({ ok: res.success, message: res.message || (res.success ? 'Done' : 'Failed') })
    } catch (err) {
      setResult({ ok: false, message: err instanceof Error ? err.message : 'Execution failed' })
    } finally {
      setRunning(false)
    }
  }

  const reset = () => {
    if (descriptor) setArgs({ ...descriptor.defaults })
    setResult(null)
  }

  const set = (key: string, value: unknown) => setArgs((prev) => ({ ...prev, [key]: value }))

  const renderSelect = (key: string, label: string, options: string[] | undefined) => {
    if (!options) return null
    return (
      <label className="block">
        <span className="text-[10px] uppercase tracking-wider text-fg-muted">{label}</span>
        <select
          value={String(args[key] ?? options[0])}
          onChange={(e) => set(key, e.target.value)}
          className="w-full mt-0.5 px-2 py-1 rounded-md border border-border bg-bg-base text-[12px] text-fg-primary focus:outline-none focus:border-accent-cyan"
        >
          {options.map((o) => (
            <option key={o} value={o}>
              {o}
            </option>
          ))}
        </select>
      </label>
    )
  }

  const renderNumber = (key: string, label: string, step = 0.1) => (
    <label className="block">
      <span className="text-[10px] uppercase tracking-wider text-fg-muted">{label}</span>
      <input
        type="number"
        step={step}
        value={Number(args[key] ?? 0)}
        onChange={(e) => set(key, Number(e.target.value))}
        className="w-full mt-0.5 px-2 py-1 rounded-md border border-border bg-bg-base text-[12px] text-fg-primary focus:outline-none focus:border-accent-cyan"
      />
    </label>
  )

  const renderToggle = (key: string, label: string) => (
    <label className="flex items-center justify-between text-[12px] text-fg-secondary">
      <span>{label}</span>
      <input
        type="checkbox"
        checked={Boolean(args[key])}
        onChange={(e) => set(key, e.target.checked)}
        className="accent-accent-cyan"
      />
    </label>
  )

  const body = useMemo(() => {
    if (loading)
      return (
        <div className="flex flex-col items-center justify-center py-16 text-fg-muted">
          <Loader2 size={20} className="animate-spin mb-2" />
          <span className="text-[11px]">Loading tool presets…</span>
        </div>
      )
    if (error)
      return <div className="px-4 py-6 text-[12px] text-rose-300">{error}</div>
    if (!descriptor) return null

    const Icon = presetIcon(selected)
    return (
      <div className="space-y-3">
        {/* Tool family selector */}
        <div className="flex flex-wrap gap-1.5">
          {Object.keys(presets?.tools ?? {}).map((toolName) => {
            const BtnIcon = presetIcon(toolName)
            const active = selected === toolName
            return (
              <button
                key={toolName}
                onClick={() => setSelected(toolName)}
                title={presets?.tools[toolName].label}
                className={`flex items-center gap-1 px-2 py-1 rounded-md text-[10px] font-medium border transition-colors ${
                  active
                    ? 'text-accent-cyan border-accent-cyan/40 bg-accent-cyan/10'
                    : 'text-fg-muted border-border hover:text-fg-secondary hover:bg-bg-hover'
                }`}
              >
                <BtnIcon size={11} />
                {presets?.tools[toolName].label}
              </button>
            )
          })}
        </div>

        <div className="flex items-center gap-2">
          <div className="flex items-center justify-center w-8 h-8 rounded-lg border border-border bg-bg-elevated">
            <Icon size={15} className="text-accent-cyan" />
          </div>
          <div>
            <div className="text-[13px] font-semibold text-fg-primary">{descriptor.label}</div>
            <div className="text-[10px] text-fg-muted capitalize">{descriptor.category}</div>
          </div>
        </div>

        <div className="space-y-2.5">
          {selected === 'voxel_sculpt' && (
            <>
              {renderSelect('operation', 'Operation', descriptor.operations)}
              {renderNumber('radius', 'Radius', 1)}
              {renderNumber('size', 'Cell Size', 1)}
            </>
          )}
          {selected === 'create_particle_system' && (
            <>
              {renderSelect('effect_type', 'Effect', descriptor.effects)}
              {renderNumber('intensity', 'Intensity', 0.1)}
              {renderNumber('scale', 'Scale', 0.1)}
            </>
          )}
          {selected === 'generate_lod_chain' && (
            <>
              {renderNumber('levels', 'Levels', 1)}
              {renderNumber('reduction_factor', 'Reduction', 0.05)}
              {renderToggle('auto_tag', 'Auto-tag levels')}
            </>
          )}
          {selected === 'repair_mesh' && (
            <>
              {renderSelect('fixes', 'Fixes', descriptor.fixes)}
              {renderNumber('min_wall_thickness', 'Min Wall Thickness', 0.01)}
              {renderToggle('report_only', 'Report only')}
            </>
          )}
          {selected === 'self_evaluate' && (
            <>
              <label className="block">
                <span className="text-[10px] uppercase tracking-wider text-fg-muted">Goal</span>
                <input
                  type="text"
                  value={String(args.goal ?? '')}
                  onChange={(e) => set('goal', e.target.value)}
                  placeholder="e.g. polish the scene"
                  className="w-full mt-0.5 px-2 py-1 rounded-md border border-border bg-bg-base text-[12px] text-fg-primary focus:outline-none focus:border-accent-cyan"
                />
              </label>
              {renderToggle('auto_fix', 'Auto-fix suggestions')}
            </>
          )}
          {selected === 'consensus_vote' && (
            <>
              {renderSelect('strategy', 'Strategy', descriptor.strategies)}
              <label className="block">
                <span className="text-[10px] uppercase tracking-wider text-fg-muted">Prompt</span>
                <textarea
                  value={String(args.prompt ?? '')}
                  onChange={(e) => set('prompt', e.target.value)}
                  rows={2}
                  placeholder="Question to dispatch to multiple models"
                  className="w-full mt-0.5 px-2 py-1 rounded-md border border-border bg-bg-base text-[12px] text-fg-primary focus:outline-none focus:border-accent-cyan resize-none"
                />
              </label>
              {renderNumber('max_models', 'Max Models', 1)}
            </>
          )}
        </div>

        {result && (
          <div
            className={`px-2.5 py-1.5 rounded-md text-[11px] border ${
              result.ok
                ? 'text-accent-emerald border-accent-emerald/30 bg-accent-emerald/10'
                : 'text-rose-300 border-rose-300/30 bg-rose-300/10'
            }`}
          >
            {result.message}
          </div>
        )}

        <div className="flex items-center gap-2 pt-1">
          <button
            onClick={run}
            disabled={running}
            className="flex items-center gap-1.5 flex-1 justify-center px-3 py-1.5 rounded-md bg-accent-cyan/15 text-accent-cyan border border-accent-cyan/30 text-[11px] font-semibold hover:bg-accent-cyan/25 disabled:opacity-50 transition-colors"
          >
            {running ? <Loader2 size={12} className="animate-spin" /> : <Play size={12} />}
            {running ? 'Running…' : 'Run'}
          </button>
          <button
            onClick={reset}
            aria-label="Reset defaults"
            className="flex items-center justify-center w-8 h-8 rounded-md border border-border text-fg-muted hover:text-fg-primary hover:bg-bg-hover transition-colors"
          >
            <RefreshCw size={13} />
          </button>
        </div>
      </div>
    )
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [presets, loading, error, descriptor, args, running, result, selected, currentScene, sessionId])

  return (
    <div className="flex flex-col h-full">
      <div className="px-3 py-2.5 border-b border-border">
        <div className="text-[10px] uppercase tracking-wider text-fg-muted font-semibold">
          Generative Tools
        </div>
        <div className="text-[11px] text-fg-secondary mt-0.5">
          Parameterized forms for voxel, particles, LOD, repair, and evaluation.
        </div>
      </div>
      <div className="flex-1 overflow-y-auto px-3 py-3">{body}</div>
    </div>
  )
}
