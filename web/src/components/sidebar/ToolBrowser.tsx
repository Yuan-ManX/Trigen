// Tool browser tab: catalogs every Agent-callable tool, grouped by the
// backend's functional taxonomy. Selecting a tool expands an inline
// parameter form generated from its JSON Schema; the Run button invokes
// the tool directly via /api/tools/execute and pushes the resulting scene
// into the editor store with an undoable commit.
import {
  AlertTriangle,
  Boxes,
  Camera,
  Clock,
  Code2,
  Eye,
  Flag,
  Layers,
  Lightbulb,
  Loader2,
  Package,
  Pin,
  Play,
  Search,
  Settings2,
  Sparkles,
  Star,
  Wand2,
  Wrench,
  X,
} from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { executeTool, fetchToolCategories } from '../../api/client'
import { useScene } from '../../store/useScene'
import type { ToolCategoriesResponse, ToolSchema } from '../../types'

/** localStorage keys for pinned (favorites) and recently-used tools. */
const FAVORITES_KEY = 'trigen.toolFavorites'
const RECENTS_KEY = 'trigen.toolRecents'
/** Maximum number of recent tools to remember. */
const MAX_RECENTS = 8

/** Read a JSON array from localStorage; return [] on any error. */
function readList(key: string): string[] {
  try {
    const raw = localStorage.getItem(key)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed.filter((x) => typeof x === 'string') : []
  } catch {
    return []
  }
}

/** Persist a string array to localStorage; silently ignore failures. */
function writeList(key: string, list: string[]): void {
  try {
    localStorage.setItem(key, JSON.stringify(list))
  } catch {
    // Ignore quota / privacy-mode failures — favorites are best-effort.
  }
}

/** Hook over a localStorage-backed string list. Returns the list, a setter
 *  that accepts an updater, and a no-op for ergonomics. Re-syncs from
 *  storage when the window regains focus so multiple tabs stay consistent. */
function useStoredList(key: string): [string[], (updater: (prev: string[]) => string[]) => void] {
  const [list, setList] = useState<string[]>(() => readList(key))
  useEffect(() => {
    const onFocus = () => setList(readList(key))
    window.addEventListener('focus', onFocus)
    return () => window.removeEventListener('focus', onFocus)
  }, [key])
  const update = useCallback(
    (updater: (prev: string[]) => string[]) => {
      setList((prev) => {
        const next = updater(prev)
        writeList(key, next)
        return next
      })
    },
    [key],
  )
  return [list, update]
}

/** Visual metadata for each functional category. The backend taxonomy is
 *  the single source of truth for category names; this map only styles
 *  how they render in the browser. Unknown categories fall back to a
 *  neutral icon + accent. */
const CATEGORY_META: Record<string, { icon: typeof Boxes; color: string; label: string }> = {
  creation: { icon: Boxes, color: 'text-amber-300', label: 'Creation' },
  transform: { icon: Layers, color: 'text-cyan-300', label: 'Transform' },
  material: { icon: Sparkles, color: 'text-fuchsia-400', label: 'Material' },
  lighting: { icon: Lightbulb, color: 'text-yellow-300', label: 'Lighting' },
  camera: { icon: Camera, color: 'text-sky-300', label: 'Camera' },
  scene: { icon: Package, color: 'text-emerald-400', label: 'Scene' },
  editor: { icon: Settings2, color: 'text-violet-300', label: 'Editor' },
  animation: { icon: Play, color: 'text-rose-300', label: 'Animation' },
  procedural: { icon: Wand2, color: 'text-teal-300', label: 'Procedural' },
  multimodal: { icon: Eye, color: 'text-pink-300', label: 'Multimodal' },
  export: { icon: Code2, color: 'text-orange-300', label: 'Export' },
  inspection: { icon: Search, color: 'text-blue-300', label: 'Inspection' },
  skills: { icon: Flag, color: 'text-lime-300', label: 'Skills' },
}

const DEFAULT_CATEGORY_META = {
  icon: Wrench,
  color: 'text-accent-cyan',
  label: 'Other',
}

function categoryMeta(category: string) {
  return CATEGORY_META[category] ?? DEFAULT_CATEGORY_META
}

/** A single tool's parameters property map. */
type ParamMap = Record<string, {
  type?: string
  description?: string
  enum?: unknown[]
  default?: unknown
  items?: { type?: string }
}>

/** Pull the parameter property map out of a tool's JSON Schema. */
function extractParams(tool: ToolSchema): ParamMap {
  const params = tool.parameters as { properties?: ParamMap }
  return params?.properties ?? {}
}

/** Pull the required parameter names out of a tool's JSON Schema. */
function extractRequired(tool: ToolSchema): string[] {
  const params = tool.parameters as { required?: string[] }
  return params?.required ?? []
}

/** Coerce a raw schema default value into the right shape for a field. */
function defaultValueFor(param: ParamMap[string]): unknown {
  if (param.default !== undefined) return param.default
  switch (param.type) {
    case 'string':
      return ''
    case 'number':
    case 'integer':
      return 0
    case 'boolean':
      return false
    case 'array':
      return []
    case 'object':
      return {}
    default:
      return ''
  }
}

/** Build the initial arguments object from a tool's schema. */
function buildInitialArgs(tool: ToolSchema): Record<string, unknown> {
  const params = extractParams(tool)
  const args: Record<string, unknown> = {}
  for (const [name, schema] of Object.entries(params)) {
    args[name] = defaultValueFor(paramSchema(name, schema))
  }
  return args
}

/** Resolve the parameter schema, normalizing vec3 arrays into a special
 *  pseudo-type so the form can render three number inputs side by side. */
function paramSchema(_name: string, schema: ParamMap[string]): ParamMap[string] & { isVec3?: boolean } {
  const itemsType = schema.items?.type
  const isVec3 = schema.type === 'array' && itemsType === 'number'
  return { ...schema, isVec3 }
}

interface ToolBrowserProps {
  /** Session id used for direct tool execution. Falls back to 'default'
   *  when not provided (the backend isolates scenes per session). */
  sessionId?: string
}

export function ToolBrowser({ sessionId = 'default' }: ToolBrowserProps) {
  const [data, setData] = useState<ToolCategoriesResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const [expandedCategory, setExpandedCategory] = useState<string | null>(null)
  const [selectedTool, setSelectedTool] = useState<string | null>(null)
  const [running, setRunning] = useState(false)
  const [runResult, setRunResult] = useState<{ ok: boolean; message: string } | null>(null)
  const [args, setArgs] = useState<Record<string, unknown>>({})
  const [favorites, setFavorites] = useStoredList(FAVORITES_KEY)
  const [recents, setRecents] = useStoredList(RECENTS_KEY)
  const commitScene = useScene((s) => s.commitScene)
  const currentScene = useScene((s) => s.scene)

  /** Toggle a tool's pinned/favorite state. */
  const toggleFavorite = useCallback((name: string) => {
    setFavorites((prev) =>
      prev.includes(name) ? prev.filter((n) => n !== name) : [name, ...prev],
    )
  }, [setFavorites])

  /** Push a tool name onto the recents stack (deduped, capped at MAX_RECENTS). */
  const pushRecent = useCallback((name: string) => {
    setRecents((prev) => {
      const next = [name, ...prev.filter((n) => n !== name)]
      return next.slice(0, MAX_RECENTS)
    })
  }, [setRecents])

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    fetchToolCategories()
      .then((payload) => {
        if (cancelled) return
        setData(payload)
        setError(null)
      })
      .catch((err: unknown) => {
        if (cancelled) return
        setError(err instanceof Error ? err.message : 'Failed to load tool catalog')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  /** All tools flattened, for searching across categories. */
  const allTools = useMemo<ToolSchema[]>(() => {
    if (!data) return []
    return Object.values(data.categories).flat()
  }, [data])

  /** Tool name → schema lookup, used to resolve favorites/recents lists
   *  (which only store names) into renderable rows. */
  const toolByName = useMemo(() => {
    const map = new Map<string, ToolSchema>()
    for (const t of allTools) map.set(t.name, t)
    return map
  }, [allTools])

  /** Pinned (favorite) tools that exist in the current catalog. Hidden
   *  entirely when a search query is active so it doesn't shadow results. */
  const favoriteTools = useMemo<ToolSchema[]>(
    () =>
      favorites
        .map((name) => toolByName.get(name))
        .filter((t): t is ToolSchema => Boolean(t)),
    [favorites, toolByName],
  )

  /** Recently-used tools that exist in the current catalog. */
  const recentTools = useMemo<ToolSchema[]>(
    () =>
      recents
        .map((name) => toolByName.get(name))
        .filter((t): t is ToolSchema => Boolean(t)),
    [recents, toolByName],
  )

  /** Filtered category groups — when the query is empty, mirrors the
   *  backend's category order; when typing, only categories containing a
   *  matching tool are shown (and the query auto-expands them). */
  const filteredGroups = useMemo(() => {
    if (!data) return [] as Array<{ category: string; tools: ToolSchema[] }>
    const q = query.trim().toLowerCase()
    const groups: Array<{ category: string; tools: ToolSchema[] }> = []
    for (const cat of Object.keys(data.categories)) {
      const tools = data.categories[cat]
      const filtered = q
        ? tools.filter(
            (t) =>
              t.name.toLowerCase().includes(q) ||
              t.description.toLowerCase().includes(q),
          )
        : tools
      if (filtered.length > 0) groups.push({ category: cat, tools: filtered })
    }
    return groups
  }, [data, query])

  /** Look up the currently selected tool's schema. */
  const selectedSchema = useMemo<ToolSchema | null>(() => {
    if (!selectedTool) return null
    return allTools.find((t) => t.name === selectedTool) ?? null
  }, [allTools, selectedTool])

  /** Reset the parameter form whenever the selected tool changes. */
  useEffect(() => {
    if (selectedSchema) {
      setArgs(buildInitialArgs(selectedSchema))
      setRunResult(null)
    } else {
      setArgs({})
      setRunResult(null)
    }
  }, [selectedSchema])

  /** Run the selected tool with the current argument values. On success,
   *  commit the returned scene so undo/redo covers the change, and bump
   *  the tool to the top of the recents list. */
  const handleRun = () => {
    if (!selectedSchema) return
    setRunning(true)
    setRunResult(null)
    executeTool(selectedSchema.name, args, sessionId)
      .then((result) => {
        if (result.success && result.scene) {
          commitScene(result.scene, currentScene)
        }
        if (result.success) {
          pushRecent(selectedSchema.name)
        }
        setRunResult({ ok: result.success, message: result.message })
      })
      .catch((err: unknown) => {
        setRunResult({
          ok: false,
          message: err instanceof Error ? err.message : 'Tool execution failed',
        })
      })
      .finally(() => setRunning(false))
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full text-fg-muted text-[11px] gap-2">
        <Loader2 size={13} className="animate-spin" />
        Loading tools…
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-fg-muted text-[11px] gap-2 p-4 text-center">
        <X size={16} className="text-rose-400" />
        <p>{error}</p>
      </div>
    )
  }

  if (!data || data.total_tools === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-fg-muted text-[11px] gap-2 p-4 text-center">
        <Wrench size={16} />
        <p>No tools registered.</p>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="px-3 py-2.5 border-b border-border-subtle">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1.5">
            <Wrench size={12} className="text-accent-cyan" />
            <span className="text-[11px] font-semibold text-fg-primary">Tool Browser</span>
          </div>
          <span className="text-[9px] text-fg-muted font-mono">
            {data.total_tools} · {data.total_categories} cats
          </span>
        </div>
        <p className="text-[9.5px] text-fg-muted mt-1 leading-relaxed">
          Run any tool directly — args go straight to the scene.
        </p>
      </div>

      {/* Search */}
      <div className="px-2.5 py-2 border-b border-border-subtle">
        <div className="relative">
          <Search size={11} className="absolute left-2 top-1/2 -translate-y-1/2 text-fg-muted" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search tools…"
            className="w-full pr-2 py-1.5 text-[11px] bg-bg-base border border-border-subtle rounded text-fg-primary placeholder:text-fg-muted outline-none focus:border-accent-cyan/50"
            style={{ paddingLeft: 22 }}
          />
        </div>
      </div>

      {/* Tool list */}
      <div className="flex-1 overflow-y-auto p-2 space-y-1.5">
        {/* Pinned (favorites) — hidden while searching so it doesn't shadow
            the result list. Rendered above categories for fast access. */}
        {!query.trim() && favoriteTools.length > 0 && (
          <div className="space-y-1">
            <div className="flex items-center gap-1.5 px-1 py-0.5">
              <Pin size={11} className="text-accent-gold" />
              <span className="text-[9.5px] uppercase tracking-wider font-semibold text-fg-secondary">
                Pinned
              </span>
              <span className="text-[9px] text-fg-muted/60 font-mono ml-auto">
                {favoriteTools.length}
              </span>
            </div>
            <div className="space-y-0.5 ml-0.5">
              {favoriteTools.map((tool) => {
                const isSelected = selectedTool === tool.name
                return (
                  <ToolRow
                    key={tool.name}
                    tool={tool}
                    selected={isSelected}
                    onSelect={() => setSelectedTool(isSelected ? null : tool.name)}
                    isFavorite
                    onToggleFavorite={() => toggleFavorite(tool.name)}
                  />
                )
              })}
            </div>
          </div>
        )}

        {/* Recently used — hidden while searching. Renders a compact list
            capped by MAX_RECENTS so it doesn't dominate the panel. */}
        {!query.trim() && recentTools.length > 0 && (
          <div className="space-y-1">
            <div className="flex items-center gap-1.5 px-1 py-0.5">
              <Clock size={11} className="text-fg-secondary" />
              <span className="text-[9.5px] uppercase tracking-wider font-semibold text-fg-secondary">
                Recent
              </span>
              <span className="text-[9px] text-fg-muted/60 font-mono ml-auto">
                {recentTools.length}
              </span>
            </div>
            <div className="space-y-0.5 ml-0.5">
              {recentTools.map((tool) => {
                const isSelected = selectedTool === tool.name
                return (
                  <ToolRow
                    key={tool.name}
                    tool={tool}
                    selected={isSelected}
                    onSelect={() => setSelectedTool(isSelected ? null : tool.name)}
                    isFavorite={favorites.includes(tool.name)}
                    onToggleFavorite={() => toggleFavorite(tool.name)}
                  />
                )
              })}
            </div>
          </div>
        )}

        {filteredGroups.map((group) => {
          const meta = categoryMeta(group.category)
          const GroupIcon = meta.icon
          const isExpanded = expandedCategory === group.category || !!query.trim()
          return (
            <div key={group.category} className="space-y-1">
              <button
                onClick={() => setExpandedCategory(isExpanded && !query.trim() ? null : group.category)}
                className="w-full flex items-center gap-1.5 px-1 py-0.5 hover:bg-bg-hover/40 rounded transition-colors"
              >
                <GroupIcon size={11} className={meta.color} />
                <span className="text-[9.5px] uppercase tracking-wider font-semibold text-fg-secondary">
                  {meta.label}
                </span>
                <span className="text-[9px] text-fg-muted/60 font-mono ml-auto">
                  {group.tools.length}
                </span>
              </button>
              {isExpanded && (
                <div className="space-y-0.5 ml-0.5">
                  {group.tools.map((tool) => {
                    const isSelected = selectedTool === tool.name
                    return (
                      <ToolRow
                        key={tool.name}
                        tool={tool}
                        selected={isSelected}
                        onSelect={() => setSelectedTool(isSelected ? null : tool.name)}
                        isFavorite={favorites.includes(tool.name)}
                        onToggleFavorite={() => toggleFavorite(tool.name)}
                      />
                    )
                  })}
                </div>
              )}
            </div>
          )
        })}
        {filteredGroups.length === 0 && (
          <div className="px-3 py-6 text-center text-[11px] text-fg-muted">
            No tools match “{query}”.
          </div>
        )}
      </div>

      {/* Inline parameter form for the selected tool */}
      {selectedSchema && (
        <ToolParamForm
          tool={selectedSchema}
          args={args}
          onArgsChange={setArgs}
          onRun={handleRun}
          running={running}
          result={runResult}
          onClose={() => {
            setSelectedTool(null)
            setArgs({})
            setRunResult(null)
          }}
        />
      )}
    </div>
  )
}

interface ToolRowProps {
  tool: ToolSchema
  selected: boolean
  onSelect: () => void
  /** True when this tool is in the user's favorites (star filled). */
  isFavorite?: boolean
  /** Toggle handler for the favorite star. Clicking the star stops
   *  propagation so it doesn't also select the row. */
  onToggleFavorite?: () => void
}

function ToolRow({ tool, selected, onSelect, isFavorite, onToggleFavorite }: ToolRowProps) {
  const paramCount = useMemo(() => Object.keys(extractParams(tool)).length, [tool])
  return (
    <div
      onClick={onSelect}
      className={`w-full group cursor-pointer flex flex-col gap-0.5 rounded-md border px-2 py-1.5 text-left transition-colors ${
        selected
          ? 'border-accent-cyan/50 bg-accent-cyan/10'
          : 'border-transparent hover:bg-bg-hover hover:border-border'
      }`}
    >
      <div className="flex items-center justify-between gap-2">
        <span
          className={`text-[10.5px] font-medium truncate ${
            selected ? 'text-accent-cyan' : 'text-fg-primary group-hover:text-accent-cyan'
          }`}
        >
          {tool.name}
        </span>
        <div className="flex items-center gap-1 shrink-0">
          {tool.requires_approval && (
            <AlertTriangle
              size={9}
              className="text-rose-400"
              aria-label="Requires approval"
            />
          )}
          {paramCount > 0 && (
            <span
              title={`${paramCount} parameter${paramCount === 1 ? '' : 's'}`}
              className="text-[8.5px] font-mono text-fg-muted/70 border border-border-subtle rounded px-1 py-px"
            >
              {paramCount}p
            </span>
          )}
          {onToggleFavorite && (
            <button
              onClick={(e) => {
                e.stopPropagation()
                onToggleFavorite()
              }}
              aria-label={isFavorite ? 'Unpin tool' : 'Pin tool'}
              title={isFavorite ? 'Unpin from favorites' : 'Pin to favorites'}
              className={`shrink-0 transition-colors ${
                isFavorite
                  ? 'text-accent-gold'
                  : 'text-fg-muted/50 hover:text-accent-gold opacity-0 group-hover:opacity-100'
              }`}
            >
              <Star size={10} fill={isFavorite ? 'currentColor' : 'none'} />
            </button>
          )}
        </div>
      </div>
      <p className="text-[9px] text-fg-muted leading-snug line-clamp-2">
        {tool.description}
      </p>
    </div>
  )
}

interface ToolParamFormProps {
  tool: ToolSchema
  args: Record<string, unknown>
  onArgsChange: (next: Record<string, unknown>) => void
  onRun: () => void
  running: boolean
  result: { ok: boolean; message: string } | null
  onClose: () => void
}

function ToolParamForm({
  tool,
  args,
  onArgsChange,
  onRun,
  running,
  result,
  onClose,
}: ToolParamFormProps) {
  const params = useMemo(() => extractParams(tool), [tool])
  const required = useMemo(() => new Set(extractRequired(tool)), [tool])
  const paramEntries = useMemo(() => Object.entries(params), [params])

  const setArg = (name: string, value: unknown) => {
    onArgsChange({ ...args, [name]: value })
  }

  /** A required field is satisfied when it has a non-empty value. */
  const requiredSatisfied = useMemo(() => {
    for (const name of required) {
      const v = args[name]
      if (v === undefined || v === null || v === '') return false
      if (Array.isArray(v) && v.length === 0) return false
    }
    return true
  }, [args, required])

  const canRun = !running && requiredSatisfied

  return (
    <div className="border-t border-border bg-bg-elevated/60 flex flex-col max-h-[55%]">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-border-subtle">
        <div className="flex flex-col min-w-0">
          <span className="text-[11px] font-semibold text-accent-cyan truncate">
            {tool.name}
          </span>
          <span className="text-[9px] text-fg-muted line-clamp-1">
            {tool.description}
          </span>
        </div>
        <button
          onClick={onClose}
          aria-label="Close parameter form"
          className="shrink-0 ml-2 w-5 h-5 rounded flex items-center justify-center text-fg-muted hover:text-fg-primary hover:bg-bg-hover"
        >
          <X size={11} />
        </button>
      </div>

      {/* Parameter inputs */}
      <div className="overflow-y-auto px-3 py-2 space-y-2 flex-1">
        {paramEntries.length === 0 ? (
          <p className="text-[10px] text-fg-muted italic">This tool takes no parameters.</p>
        ) : (
          paramEntries.map(([name, raw]) => {
            const schema = paramSchema(name, raw)
            const isRequired = required.has(name)
            return (
              <ParameterInput
                key={name}
                name={name}
                schema={schema}
                value={args[name]}
                isRequired={isRequired}
                onChange={(v) => setArg(name, v)}
              />
            )
          })
        )}
      </div>

      {/* Run result */}
      {result && (
        <div
          className={`mx-3 mb-2 px-2 py-1.5 rounded text-[10px] border ${
            result.ok
              ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-300'
              : 'border-rose-500/40 bg-rose-500/10 text-rose-300'
          }`}
        >
          {result.message}
        </div>
      )}

      {/* Footer: Run button */}
      <div className="px-3 py-2 border-t border-border-subtle flex items-center justify-between gap-2">
        <span className="text-[9px] text-fg-muted">
          {required.size > 0
            ? `${required.size} required`
            : 'No required fields'}
        </span>
        <button
          onClick={onRun}
          disabled={!canRun}
          className="flex items-center gap-1.5 px-3 h-7 rounded-md bg-accent-cyan text-bg-base disabled:bg-bg-hover disabled:text-fg-muted disabled:cursor-not-allowed hover:shadow-glow transition-all text-[10.5px] font-medium"
        >
          {running ? <Loader2 size={11} className="animate-spin" /> : <Play size={11} />}
          <span>{running ? 'Running…' : 'Run'}</span>
        </button>
      </div>
    </div>
  )
}

interface ParameterInputProps {
  name: string
  schema: ParamMap[string] & { isVec3?: boolean }
  value: unknown
  isRequired: boolean
  onChange: (value: unknown) => void
}

function ParameterInput({ name, schema, value, isRequired, onChange }: ParameterInputProps) {
  const label = (
    <div className="flex items-center justify-between mb-0.5">
      <label className="text-[10px] text-fg-secondary font-medium">
        {name}
        {isRequired && <span className="text-rose-400 ml-0.5">*</span>}
      </label>
      <span className="text-[8.5px] text-fg-muted/70 font-mono">{schema.type ?? 'any'}</span>
    </div>
  )

  // Detect hex color fields so we can offer a color picker alongside the
  // text input. Matches fields named "color" or "emissive".
  const isColorField =
    schema.type === 'string' && (name === 'color' || name === 'emissive')

  // String with enum → select dropdown
  if (schema.type === 'string' && schema.enum && schema.enum.length > 0) {
    return (
      <div>
        {label}
        <select
          value={String(value ?? '')}
          onChange={(e) => onChange(e.target.value)}
          className="w-full text-[10.5px] bg-bg-base border border-border-subtle rounded px-1.5 py-1 text-fg-primary outline-none focus:border-accent-cyan/50"
        >
          {schema.enum.map((opt) => (
            <option key={String(opt)} value={String(opt)}>
              {String(opt)}
            </option>
          ))}
        </select>
        {schema.description && (
          <p className="text-[8.5px] text-fg-muted/70 mt-0.5 leading-snug">{schema.description}</p>
        )}
      </div>
    )
  }

  // Vec3 array → three side-by-side number inputs
  if (schema.isVec3) {
    const arr = Array.isArray(value) ? value : [0, 0, 0]
    const setIdx = (i: number, v: number) => {
      const next = [...(arr as number[])]
      while (next.length < 3) next.push(0)
      next[i] = v
      onChange(next)
    }
    return (
      <div>
        {label}
        <div className="grid grid-cols-3 gap-1">
          {['x', 'y', 'z'].map((axis, i) => (
            <input
              key={axis}
              type="number"
              value={Number((arr as number[])[i] ?? 0)}
              step={0.1}
              onChange={(e) => setIdx(i, parseFloat(e.target.value) || 0)}
              className="w-full text-[10.5px] font-mono bg-bg-base border border-border-subtle rounded px-1 py-1 text-fg-primary outline-none focus:border-accent-cyan/50 text-center"
              placeholder={axis}
            />
          ))}
        </div>
        {schema.description && (
          <p className="text-[8.5px] text-fg-muted/70 mt-0.5 leading-snug">{schema.description}</p>
        )}
      </div>
    )
  }

  // Boolean → toggle switch
  if (schema.type === 'boolean') {
    return (
      <div>
        <div className="flex items-center justify-between">
          <label className="text-[10px] text-fg-secondary font-medium">
            {name}
            {isRequired && <span className="text-rose-400 ml-0.5">*</span>}
          </label>
          <button
            onClick={() => onChange(!value)}
            className={`relative w-7 h-3.5 rounded-full transition-colors ${
              value ? 'bg-accent-cyan' : 'bg-bg-hover'
            }`}
            role="switch"
            aria-checked={!!value}
          >
            <span
              className={`absolute top-0.5 left-0.5 w-2.5 h-2.5 rounded-full bg-white transition-transform ${
                value ? 'translate-x-3' : ''
              }`}
            />
          </button>
        </div>
        {schema.description && (
          <p className="text-[8.5px] text-fg-muted/70 mt-0.5 leading-snug">{schema.description}</p>
        )}
      </div>
    )
  }

  // Number → numeric input
  if (schema.type === 'number' || schema.type === 'integer') {
    return (
      <div>
        {label}
        <input
          type="number"
          value={value === '' || value === undefined ? 0 : Number(value)}
          step={schema.type === 'integer' ? 1 : 0.1}
          onChange={(e) => onChange(parseFloat(e.target.value) || 0)}
          className="w-full text-[10.5px] font-mono bg-bg-base border border-border-subtle rounded px-1.5 py-1 text-fg-primary outline-none focus:border-accent-cyan/50"
        />
        {schema.description && (
          <p className="text-[8.5px] text-fg-muted/70 mt-0.5 leading-snug">{schema.description}</p>
        )}
      </div>
    )
  }

  // Color hex → text input + native color picker
  if (isColorField) {
    const hex = String(value ?? '#ffffff')
    return (
      <div>
        {label}
        <div className="flex items-center gap-1">
          <input
            type="text"
            value={hex}
            onChange={(e) => onChange(e.target.value)}
            className="flex-1 text-[10.5px] font-mono bg-bg-base border border-border-subtle rounded px-1.5 py-1 text-fg-primary outline-none focus:border-accent-cyan/50"
            placeholder="#rrggbb"
          />
          <input
            type="color"
            value={/^#[0-9a-fA-F]{6}$/.test(hex) ? hex : '#ffffff'}
            onChange={(e) => onChange(e.target.value)}
            className="w-7 h-7 rounded border border-border-subtle bg-transparent cursor-pointer p-0"
            aria-label={`${name} color picker`}
          />
        </div>
        {schema.description && (
          <p className="text-[8.5px] text-fg-muted/70 mt-0.5 leading-snug">{schema.description}</p>
        )}
      </div>
    )
  }

  // String (default) → text input
  if (schema.type === 'string') {
    return (
      <div>
        {label}
        <input
          type="text"
          value={String(value ?? '')}
          onChange={(e) => onChange(e.target.value)}
          className="w-full text-[10.5px] bg-bg-base border border-border-subtle rounded px-1.5 py-1 text-fg-primary outline-none focus:border-accent-cyan/50"
        />
        {schema.description && (
          <p className="text-[8.5px] text-fg-muted/70 mt-0.5 leading-snug">{schema.description}</p>
        )}
      </div>
    )
  }

  // Array (non-vec3) → comma-separated text input
  if (schema.type === 'array') {
    const text = Array.isArray(value) ? value.join(', ') : String(value ?? '')
    return (
      <div>
        {label}
        <input
          type="text"
          value={text}
          onChange={(e) => {
            const parts = e.target.value
              .split(',')
              .map((s) => s.trim())
              .filter((s) => s.length > 0)
            onChange(parts)
          }}
          className="w-full text-[10.5px] font-mono bg-bg-base border border-border-subtle rounded px-1.5 py-1 text-fg-primary outline-none focus:border-accent-cyan/50"
          placeholder="a, b, c"
        />
        {schema.description && (
          <p className="text-[8.5px] text-fg-muted/70 mt-0.5 leading-snug">{schema.description}</p>
        )}
      </div>
    )
  }

  // Object / unknown → JSON textarea
  return (
    <div>
      {label}
      <textarea
        value={typeof value === 'string' ? value : JSON.stringify(value, null, 2)}
        onChange={(e) => {
          try {
            onChange(JSON.parse(e.target.value))
          } catch {
            onChange(e.target.value)
          }
        }}
        rows={3}
        className="w-full text-[10px] font-mono bg-bg-base border border-border-subtle rounded px-1.5 py-1 text-fg-primary outline-none focus:border-accent-cyan/50 resize-none"
        placeholder="{}"
      />
      {schema.description && (
        <p className="text-[8.5px] text-fg-muted/70 mt-0.5 leading-snug">{schema.description}</p>
      )}
    </div>
  )
}
