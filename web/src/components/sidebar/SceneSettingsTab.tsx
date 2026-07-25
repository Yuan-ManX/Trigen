// Scene settings tab: background color, fog, grid controls
import { CloudFog, Grid3x3, Palette } from 'lucide-react'
import { useScene } from '../../store/useScene'
import type { FogConfig } from '../../types'

/** Color picker field */
function ColorField({
  label,
  value,
  onChange,
}: {
  label: string
  value: string
  onChange: (v: string) => void
}) {
  return (
    <div className="flex items-center justify-between">
      <label className="text-[11px] text-fg-secondary">{label}</label>
      <div className="flex items-center gap-2">
        <span className="text-[11px] font-mono text-fg-muted uppercase">{value}</span>
        <input
          type="color"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="w-7 h-7 rounded border border-border bg-transparent cursor-pointer p-0"
        />
      </div>
    </div>
  )
}

/** Numeric slider + input */
function NumberSlider({
  label,
  value,
  min,
  max,
  step,
  onChange,
}: {
  label: string
  value: number
  min: number
  max: number
  step: number
  onChange: (v: number) => void
}) {
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between">
        <label className="text-[11px] text-fg-secondary">{label}</label>
        <input
          type="number"
          value={Number(value.toFixed(2))}
          min={min}
          max={max}
          step={step}
          onChange={(e) => onChange(parseFloat(e.target.value) || 0)}
          className="w-16 text-right text-[11px] font-mono text-fg-primary bg-bg-base border border-border rounded px-1 py-0.5 outline-none focus:border-accent-cyan/50"
        />
      </div>
      <input
        type="range"
        value={value}
        min={min}
        max={max}
        step={step}
        onChange={(e) => onChange(parseFloat(e.target.value))}
        className="w-full h-1 accent-accent-cyan cursor-pointer"
      />
    </div>
  )
}

/** Toggle switch */
function ToggleField({
  label,
  value,
  onChange,
}: {
  label: string
  value: boolean
  onChange: (v: boolean) => void
}) {
  return (
    <div className="flex items-center justify-between">
      <label className="text-[11px] text-fg-secondary">{label}</label>
      <button
        onClick={() => onChange(!value)}
        className={`relative w-9 h-5 rounded-full transition-colors ${
          value ? 'bg-accent-cyan' : 'bg-bg-hover'
        }`}
      >
        <span
          className={`absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white transition-transform ${
            value ? 'translate-x-4' : 'translate-x-0'
          }`}
        />
      </button>
    </div>
  )
}

export function SceneSettingsTab() {
  const scene = useScene((s) => s.scene)
  const setBackground = useScene((s) => s.setBackground)
  const setFog = useScene((s) => s.setFog)
  const setGrid = useScene((s) => s.setGrid)

  const fog: FogConfig | null = scene.fog

  const updateFog = (partial: Partial<FogConfig>) => {
    const current: FogConfig = fog ?? { color: '#050505', near: 10, far: 50 }
    setFog({ ...current, ...partial })
  }

  return (
    <div className="overflow-y-auto h-full">
      {/* Background */}
      <div className="px-3 py-3 border-b border-border-subtle space-y-3">
        <div className="flex items-center gap-1.5 text-[11px] font-semibold text-fg-primary">
          <Palette size={12} className="text-accent-cyan" />
          Background
        </div>
        <ColorField
          label="Background Color"
          value={scene.background}
          onChange={(v) => setBackground(v)}
        />
      </div>

      {/* Fog */}
      <div className="px-3 py-3 border-b border-border-subtle space-y-3">
        <div className="flex items-center gap-1.5 text-[11px] font-semibold text-fg-primary">
          <CloudFog size={12} className="text-accent-gold" />
          Fog
        </div>
        <ToggleField
          label="Enable Fog"
          value={fog !== null}
          onChange={(v) => {
            if (v) {
              setFog({ color: scene.background, near: 10, far: 50 })
            } else {
              setFog(null)
            }
          }}
        />
        {fog && (
          <>
            <ColorField
              label="Fog Color"
              value={fog.color}
              onChange={(v) => updateFog({ color: v })}
            />
            <NumberSlider
              label="Near"
              value={fog.near}
              min={0}
              max={50}
              step={0.5}
              onChange={(v) => updateFog({ near: v })}
            />
            <NumberSlider
              label="Far"
              value={fog.far}
              min={5}
              max={200}
              step={1}
              onChange={(v) => updateFog({ far: v })}
            />
          </>
        )}
      </div>

      {/* Grid */}
      <div className="px-3 py-3 space-y-3">
        <div className="flex items-center gap-1.5 text-[11px] font-semibold text-fg-primary">
          <Grid3x3 size={12} className="text-accent-cyan" />
          Grid
        </div>
        <ToggleField
          label="Show Grid"
          value={scene.grid_visible}
          onChange={(v) => setGrid(v)}
        />
        <NumberSlider
          label="Grid Size"
          value={scene.grid_size}
          min={2}
          max={50}
          step={1}
          onChange={(v) => setGrid(scene.grid_visible, v)}
        />
      </div>
    </div>
  )
}
