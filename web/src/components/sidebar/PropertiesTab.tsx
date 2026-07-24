// 属性面板：选中对象的 transform / material 编辑
// Properties panel: edit transform / material of the selected object
import { Palette, Sliders, Target } from 'lucide-react'
import { useScene } from '../../store/useScene'
import type { Material, Vec3 } from '../../types'

/* ---------- 通用子组件 ---------- */
/* ---------- Common subcomponents ---------- */

interface NumberSliderProps {
  label: string
  value: number
  min: number
  max: number
  step: number
  onChange: (v: number) => void
}

/** 数值滑块 + 数字输入 */
/** Numeric slider + number input */
function NumberSlider({ label, value, min, max, step, onChange }: NumberSliderProps) {
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between">
        <label className="text-[11px] text-fg-secondary">{label}</label>
        <input
          type="number"
          value={Number(value.toFixed(3))}
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

interface Vec3EditorProps {
  label: string
  value: Vec3
  min: number
  max: number
  step: number
  onChange: (axis: 0 | 1 | 2, v: number) => void
}

/** 三轴向量编辑器 */
/** Three-axis vector editor */
function Vec3Editor({ label, value, min, max, step, onChange }: Vec3EditorProps) {
  const axes: Array<{ i: 0 | 1 | 2; name: string; color: string }> = [
    { i: 0, name: 'X', color: 'text-rose-400' },
    { i: 1, name: 'Y', color: 'text-emerald-400' },
    { i: 2, name: 'Z', color: 'text-accent-cyan' },
  ]
  return (
    <div className="space-y-2">
      <div className="text-[11px] font-medium text-fg-secondary">{label}</div>
      <div className="space-y-1.5">
        {axes.map((a) => (
          <div key={a.name} className="flex items-center gap-2">
            <span className={`w-3 text-[10px] font-mono ${a.color}`}>{a.name}</span>
            <input
              type="range"
              value={value[a.i]}
              min={min}
              max={max}
              step={step}
              onChange={(e) => onChange(a.i, parseFloat(e.target.value))}
              className="flex-1 h-1 accent-accent-cyan cursor-pointer"
            />
            <input
              type="number"
              value={Number(value[a.i].toFixed(3))}
              min={min}
              max={max}
              step={step}
              onChange={(e) => onChange(a.i, parseFloat(e.target.value) || 0)}
              className="w-16 text-right text-[11px] font-mono text-fg-primary bg-bg-base border border-border rounded px-1 py-0.5 outline-none focus:border-accent-cyan/50"
            />
          </div>
        ))}
      </div>
    </div>
  )
}

interface ColorFieldProps {
  label: string
  value: string
  onChange: (v: string) => void
}

/** 颜色选择器 */
/** Color picker */
function ColorField({ label, value, onChange }: ColorFieldProps) {
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

/* ---------- 主组件 ---------- */
/* ---------- Main component ---------- */

const RAD2DEG = 180 / Math.PI
const DEG2RAD = Math.PI / 180

export function PropertiesTab() {
  const object = useScene((s) => {
    const id = s.selectedId
    if (!id) return null
    return s.scene.objects.find((o) => o.id === id) ?? null
  })
  const updateTransformAxis = useScene((s) => s.updateTransformAxis)
  const updateMaterial = useScene((s) => s.updateMaterial)
  const renameObject = useScene((s) => s.renameObject)

  if (!object) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-center px-6 py-10">
        <Target size={20} className="text-fg-muted mb-2" />
        <p className="text-xs text-fg-secondary">未选中任何对象</p>
        <p className="text-[11px] text-fg-muted mt-1">
          点击 3D 画布中的对象或图层来编辑属性
        </p>
      </div>
    )
  }

  const t = object.transform
  const m: Material = object.material

  // 旋转以度数显示
  // Display rotation in degrees
  const rotDeg: Vec3 = [t.rotation[0] * RAD2DEG, t.rotation[1] * RAD2DEG, t.rotation[2] * RAD2DEG]

  const setRot = (axis: 0 | 1 | 2, deg: number) =>
    updateTransformAxis(object.id, 'rotation', axis, deg * DEG2RAD)

  return (
    <div className="overflow-y-auto h-full">
      {/* 名称 */}
      {/* Name */}
      <div className="px-3 py-3 border-b border-border-subtle">
        <label className="text-[10px] uppercase tracking-wider text-fg-muted">名称</label>
        <input
          value={object.name}
          onChange={(e) => renameObject(object.id, e.target.value)}
          className="mt-1 w-full text-sm text-fg-primary bg-bg-base border border-border rounded px-2 py-1.5 outline-none focus:border-accent-cyan/50"
        />
      </div>

      {/* 变换 */}
      {/* Transform */}
      <div className="px-3 py-3 border-b border-border-subtle space-y-3">
        <div className="flex items-center gap-1.5 text-[11px] font-semibold text-fg-primary">
          <Sliders size={12} className="text-accent-cyan" />
          变换
        </div>
        <Vec3Editor
          label="位置 Position"
          value={t.position}
          min={-10}
          max={10}
          step={0.1}
          onChange={(axis, v) => updateTransformAxis(object.id, 'position', axis, v)}
        />
        <Vec3Editor
          label="旋转 Rotation (°)"
          value={rotDeg}
          min={-180}
          max={180}
          step={1}
          onChange={setRot}
        />
        <Vec3Editor
          label="缩放 Scale"
          value={t.scale}
          min={0.1}
          max={5}
          step={0.1}
          onChange={(axis, v) => updateTransformAxis(object.id, 'scale', axis, v)}
        />
      </div>

      {/* 材质 */}
      {/* Material */}
      <div className="px-3 py-3 space-y-3">
        <div className="flex items-center gap-1.5 text-[11px] font-semibold text-fg-primary">
          <Palette size={12} className="text-accent-gold" />
          材质
        </div>
        <ColorField label="基础色" value={m.color} onChange={(v) => updateMaterial(object.id, { color: v })} />
        <ColorField label="自发光" value={m.emissive} onChange={(v) => updateMaterial(object.id, { emissive: v })} />
        <NumberSlider
          label="金属度 Metalness"
          value={m.metalness}
          min={0}
          max={1}
          step={0.01}
          onChange={(v) => updateMaterial(object.id, { metalness: v })}
        />
        <NumberSlider
          label="粗糙度 Roughness"
          value={m.roughness}
          min={0}
          max={1}
          step={0.01}
          onChange={(v) => updateMaterial(object.id, { roughness: v })}
        />
        <NumberSlider
          label="不透明度 Opacity"
          value={m.opacity}
          min={0}
          max={1}
          step={0.01}
          onChange={(v) => updateMaterial(object.id, { opacity: v })}
        />
        <NumberSlider
          label="自发光强度"
          value={m.emissive_intensity}
          min={0}
          max={3}
          step={0.05}
          onChange={(v) => updateMaterial(object.id, { emissive_intensity: v })}
        />

        {/* 线框开关 */}
        {/* Wireframe toggle */}
        <div className="flex items-center justify-between pt-1">
          <label className="text-[11px] text-fg-secondary">线框模式</label>
          <button
            onClick={() => updateMaterial(object.id, { wireframe: !m.wireframe })}
            className={`relative w-9 h-5 rounded-full transition-colors ${
              m.wireframe ? 'bg-accent-cyan' : 'bg-bg-hover'
            }`}
            aria-label="切换线框模式"
          >
            <span
              className={`absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white transition-transform ${
                m.wireframe ? 'translate-x-4' : 'translate-x-0'
              }`}
            />
          </button>
        </div>
      </div>
    </div>
  )
}
