// Properties panel: edit transform / material / geometry / animation of the
// selected object, or properties of the selected light / camera / group.
// Detects the selection kind by looking the id up across scene.objects /
// lights / cameras / groups, so the same panel serves every entity type.
import {
  Box,
  Camera as CameraIcon,
  Lightbulb,
  Palette,
  Sliders,
  Sparkles,
  Target,
  Triangle,
} from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useScene } from '../../store/useScene'
import type {
  CameraAnimation,
  CameraObject,
  Geometry,
  GeometryType,
  LightObject,
  LightType,
  Material,
  ObjectAnimation,
  Vec3,
} from '../../types'

/* ---------- Common subcomponents ---------- */

interface NumberSliderProps {
  label: string
  value: number
  min: number
  max: number
  step: number
  onChange: (v: number) => void
}

/** Numeric slider + number input. The label is also drag-to-scrub: hold
 *  pointer down on it and move horizontally to nudge the value by `step`
 *  per pixel of horizontal movement (clamped to [min, max]). Useful for
 *  fine-tuning without hunting for the tiny range thumb. */
function NumberSlider({ label, value, min, max, step, onChange }: NumberSliderProps) {
  // Drag-to-scrub state. lastX is the previous client X observed; while
  // dragging, every pointermove computes deltaX and applies it.
  const [dragging, setDragging] = useState(false)
  const lastXRef = useRef<number | null>(null)
  // Hold latest onChange in a ref so the move listener (attached once per
  // drag) always calls the freshest closure without re-binding on every
  // value change.
  const onChangeRef = useRef(onChange)
  useEffect(() => {
    onChangeRef.current = onChange
  }, [onChange])

  // While dragging, listen on window so movement outside the label still
  // counts. Also disable text selection globally while the drag is active
  // to avoid highlighting the label text on fast horizontal moves.
  useEffect(() => {
    if (!dragging) return
    const move = (e: PointerEvent) => {
      if (lastXRef.current === null) {
        lastXRef.current = e.clientX
        return
      }
      const dx = e.clientX - lastXRef.current
      lastXRef.current = e.clientX
      // Shift = 10x faster scrub for power users; matches common DCC tools.
      const speed = e.shiftKey ? 10 : 1
      const delta = dx * step * speed
      const next = Math.min(max, Math.max(min, value + delta))
      onChangeRef.current(next)
    }
    const up = () => {
      setDragging(false)
      lastXRef.current = null
    }
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', up)
    return () => {
      window.removeEventListener('pointermove', move)
      window.removeEventListener('pointerup', up)
    }
  }, [dragging, step, min, max, value])

  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between">
        <label
          onPointerDown={(e) => {
            // Start a drag scrub. Left-button only so right-click context
            // menus and middle-click paste keep working.
            if (e.button !== 0) return
            e.preventDefault()
            lastXRef.current = e.clientX
            setDragging(true)
          }}
          className={`text-[11px] text-fg-secondary select-none cursor-ew-resize ${
            dragging ? 'text-accent-cyan' : 'hover:text-fg-primary'
          }`}
          title="Drag horizontally to scrub · Shift = 10×"
        >
          {label}
        </label>
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

interface ToggleFieldProps {
  label: string
  value: boolean
  onChange: (v: boolean) => void
}

/** Toggle switch */
function ToggleField({ label, value, onChange }: ToggleFieldProps) {
  return (
    <div className="flex items-center justify-between">
      <label className="text-[11px] text-fg-secondary">{label}</label>
      <button
        onClick={() => onChange(!value)}
        className={`relative w-9 h-5 rounded-full transition-colors ${
          value ? 'bg-accent-cyan' : 'bg-bg-hover'
        }`}
        aria-label={label}
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

interface SelectFieldProps<T extends string> {
  label: string
  value: T
  options: Array<{ value: T; label: string }>
  onChange: (v: T) => void
}

/** Labeled select dropdown */
function SelectField<T extends string>({ label, value, options, onChange }: SelectFieldProps<T>) {
  return (
    <div className="flex items-center justify-between gap-2">
      <label className="text-[11px] text-fg-secondary shrink-0">{label}</label>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value as T)}
        className="flex-1 text-[11px] font-mono text-fg-primary bg-bg-base border border-border rounded px-1.5 py-1 outline-none focus:border-accent-cyan/50"
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </div>
  )
}

function SectionHeader({ icon: Icon, title, color }: { icon: typeof Box; title: string; color: string }) {
  return (
    <div className="flex items-center gap-1.5 text-[11px] font-semibold text-fg-primary">
      <Icon size={12} className={color} />
      {title}
    </div>
  )
}

/* ---------- Geometry editor ---------- */

/** Per-type parameter schema for the geometry editor.
 *  `int` params render as integer stepping sliders. */
const GEOMETRY_PARAMS: Record<
  GeometryType,
  Array<{ key: string; label: string; min: number; max: number; step: number; int?: boolean }>
> = {
  box: [
    { key: 'width', label: 'Width', min: 0.1, max: 5, step: 0.1 },
    { key: 'height', label: 'Height', min: 0.1, max: 5, step: 0.1 },
    { key: 'depth', label: 'Depth', min: 0.1, max: 5, step: 0.1 },
  ],
  sphere: [{ key: 'radius', label: 'Radius', min: 0.05, max: 3, step: 0.05 }],
  cylinder: [
    { key: 'radiusTop', label: 'Top Radius', min: 0, max: 2, step: 0.05 },
    { key: 'radiusBottom', label: 'Bottom Radius', min: 0, max: 2, step: 0.05 },
    { key: 'height', label: 'Height', min: 0.1, max: 5, step: 0.1 },
  ],
  cone: [
    { key: 'radius', label: 'Radius', min: 0.05, max: 2, step: 0.05 },
    { key: 'height', label: 'Height', min: 0.1, max: 5, step: 0.1 },
  ],
  torus: [
    { key: 'radius', label: 'Radius', min: 0.1, max: 2, step: 0.05 },
    { key: 'tube', label: 'Tube', min: 0.02, max: 0.8, step: 0.02 },
  ],
  plane: [
    { key: 'width', label: 'Width', min: 0.1, max: 10, step: 0.1 },
    { key: 'height', label: 'Height', min: 0.1, max: 10, step: 0.1 },
  ],
  torusKnot: [
    { key: 'radius', label: 'Radius', min: 0.1, max: 1.5, step: 0.05 },
    { key: 'tube', label: 'Tube', min: 0.02, max: 0.4, step: 0.02 },
    { key: 'p', label: 'P', min: 1, max: 8, step: 1, int: true },
    { key: 'q', label: 'Q', min: 1, max: 8, step: 1, int: true },
  ],
  dodecahedron: [{ key: 'radius', label: 'Radius', min: 0.05, max: 2, step: 0.05 }],
  icosahedron: [{ key: 'radius', label: 'Radius', min: 0.05, max: 2, step: 0.05 }],
  octahedron: [{ key: 'radius', label: 'Radius', min: 0.05, max: 2, step: 0.05 }],
  tetrahedron: [{ key: 'radius', label: 'Radius', min: 0.05, max: 2, step: 0.05 }],
  ring: [
    { key: 'innerRadius', label: 'Inner', min: 0.05, max: 2, step: 0.05 },
    { key: 'outerRadius', label: 'Outer', min: 0.1, max: 2.5, step: 0.05 },
  ],
  capsule: [
    { key: 'radius', label: 'Radius', min: 0.05, max: 1.5, step: 0.05 },
    { key: 'length', label: 'Length', min: 0.05, max: 3, step: 0.05 },
  ],
  tube: [{ key: 'radius', label: 'Radius', min: 0.05, max: 1, step: 0.05 }],
  lathe: [
    { key: 'segments', label: 'Segments', min: 4, max: 128, step: 1, int: true },
    { key: 'phiLength', label: 'Sweep Angle', min: 0.1, max: 6.28, step: 0.1 },
  ],
  extrude: [
    { key: 'depth', label: 'Depth', min: 0.05, max: 3, step: 0.05 },
    { key: 'bevelThickness', label: 'Bevel Thickness', min: 0, max: 0.5, step: 0.01 },
    { key: 'bevelSize', label: 'Bevel Size', min: 0, max: 0.5, step: 0.01 },
    { key: 'curveSegments', label: 'Curve Segments', min: 1, max: 32, step: 1, int: true },
  ],
  text: [
    { key: 'size', label: 'Size', min: 0.1, max: 3, step: 0.05 },
    { key: 'height', label: 'Height', min: 0, max: 1, step: 0.05 },
  ],
  spline: [
    { key: 'radius', label: 'Tube Radius', min: 0.01, max: 0.5, step: 0.01 },
    { key: 'tubularSegments', label: 'Tubular Segments', min: 8, max: 200, step: 1, int: true },
  ],
}

const GEOMETRY_TYPES: GeometryType[] = [
  'box', 'sphere', 'cylinder', 'cone', 'torus', 'plane', 'torusKnot',
  'dodecahedron', 'icosahedron', 'octahedron', 'tetrahedron', 'ring', 'capsule', 'tube',
  'lathe', 'extrude', 'text', 'spline',
]

function GeometryEditor({ object }: { object: { id: string; geometry: Geometry } }) {
  const updateGeometry = useScene((s) => s.updateGeometry)
  const setGeometry = useScene((s) => s.setGeometry)
  const g = object.geometry
  const params = GEOMETRY_PARAMS[g.type] ?? []

  return (
    <div className="px-3 py-3 border-b border-border-subtle space-y-3">
      <SectionHeader icon={Box} title="Geometry" color="text-accent-cyan" />
      <SelectField<GeometryType>
        label="Type"
        value={g.type}
        options={GEOMETRY_TYPES.map((t) => ({ value: t, label: t }))}
        onChange={(t) => setGeometry(object.id, { type: t, params: {} })}
      />
      {params.map((p) => {
        const raw = g.params[p.key]
        const fallback = p.int ? 1 : 0.5
        const val = typeof raw === 'number' ? raw : fallback
        return (
          <NumberSlider
            key={p.key}
            label={p.label}
            value={val}
            min={p.min}
            max={p.max}
            step={p.step}
            onChange={(v) => updateGeometry(object.id, { [p.key]: p.int ? Math.round(v) : v })}
          />
        )
      })}
    </div>
  )
}

/* ---------- Object animation editor ---------- */

const ANIM_TYPES: Array<{ value: ObjectAnimation['type']; label: string }> = [
  { value: 'orbit', label: 'Orbit' },
  { value: 'wave', label: 'Wave' },
  { value: 'bounce', label: 'Bounce' },
  { value: 'keyframe', label: 'Keyframe' },
]

function ObjectAnimationEditor({ object }: { object: { id: string; animation?: ObjectAnimation | null } }) {
  const updateAnimation = useScene((s) => s.updateAnimation)
  const anim = object.animation
  const hasAnim = !!anim

  return (
    <div className="px-3 py-3 border-b border-border-subtle space-y-3">
      <SectionHeader icon={Sparkles} title="Animation" color="text-accent-gold" />
      <ToggleField
        label="Enable Animation"
        value={hasAnim}
        onChange={(v) =>
          updateAnimation(object.id, v ? { type: 'orbit', duration: 4, loop: true, radius: 2, height: 1, axis: 'y', face_center: true } : null)
        }
      />
      {anim && (
        <>
          <SelectField<ObjectAnimation['type']>
            label="Type"
            value={anim.type}
            options={ANIM_TYPES}
            onChange={(t) => updateAnimation(object.id, { ...anim, type: t })}
          />
          <NumberSlider
            label="Duration (s)"
            value={anim.duration}
            min={0.5}
            max={20}
            step={0.5}
            onChange={(v) => updateAnimation(object.id, { ...anim, duration: v })}
          />
          <ToggleField
            label="Loop"
            value={anim.loop}
            onChange={(v) => updateAnimation(object.id, { ...anim, loop: v })}
          />
          {anim.type === 'orbit' && (
            <>
              <NumberSlider
                label="Radius"
                value={anim.radius ?? 2}
                min={0.1}
                max={8}
                step={0.1}
                onChange={(v) => updateAnimation(object.id, { ...anim, radius: v })}
              />
              <NumberSlider
                label="Height"
                value={anim.height ?? 1}
                min={-3}
                max={6}
                step={0.1}
                onChange={(v) => updateAnimation(object.id, { ...anim, height: v })}
              />
              <SelectField<'x' | 'y' | 'z'>
                label="Axis"
                value={(anim.axis ?? 'y') as 'x' | 'y' | 'z'}
                options={[
                  { value: 'x', label: 'X' },
                  { value: 'y', label: 'Y' },
                  { value: 'z', label: 'Z' },
                ]}
                onChange={(a) => updateAnimation(object.id, { ...anim, axis: a })}
              />
              <ToggleField
                label="Face Center"
                value={anim.face_center ?? false}
                onChange={(v) => updateAnimation(object.id, { ...anim, face_center: v })}
              />
            </>
          )}
          {anim.type === 'wave' && (
            <>
              <NumberSlider
                label="Amplitude"
                value={anim.amplitude ?? 1}
                min={0.05}
                max={4}
                step={0.05}
                onChange={(v) => updateAnimation(object.id, { ...anim, amplitude: v })}
              />
              <NumberSlider
                label="Frequency"
                value={anim.frequency ?? 0.5}
                min={0.05}
                max={4}
                step={0.05}
                onChange={(v) => updateAnimation(object.id, { ...anim, frequency: v })}
              />
            </>
          )}
          {anim.type === 'bounce' && (
            <>
              <NumberSlider
                label="Height"
                value={anim.height ?? 1.5}
                min={0.1}
                max={6}
                step={0.1}
                onChange={(v) => updateAnimation(object.id, { ...anim, height: v })}
              />
              <NumberSlider
                label="Bounces"
                value={anim.bounces ?? 3}
                min={1}
                max={10}
                step={1}
                onChange={(v) => updateAnimation(object.id, { ...anim, bounces: Math.round(v) })}
              />
              <ToggleField
                label="Squash"
                value={anim.squash ?? false}
                onChange={(v) => updateAnimation(object.id, { ...anim, squash: v })}
              />
            </>
          )}
        </>
      )}
    </div>
  )
}

/* ---------- Material editor ---------- */

function MaterialEditor({ object }: { object: { id: string; material: Material } }) {
  const updateMaterial = useScene((s) => s.updateMaterial)
  const m = object.material
  return (
    <div className="px-3 py-3 space-y-3">
      <SectionHeader icon={Palette} title="Material" color="text-accent-gold" />
      <ColorField label="Base Color" value={m.color} onChange={(v) => updateMaterial(object.id, { color: v })} />
      <ColorField label="Emissive" value={m.emissive} onChange={(v) => updateMaterial(object.id, { emissive: v })} />
      <NumberSlider
        label="Metalness"
        value={m.metalness}
        min={0}
        max={1}
        step={0.01}
        onChange={(v) => updateMaterial(object.id, { metalness: v })}
      />
      <NumberSlider
        label="Roughness"
        value={m.roughness}
        min={0}
        max={1}
        step={0.01}
        onChange={(v) => updateMaterial(object.id, { roughness: v })}
      />
      <NumberSlider
        label="Opacity"
        value={m.opacity}
        min={0}
        max={1}
        step={0.01}
        onChange={(v) => updateMaterial(object.id, { opacity: v })}
      />
      <NumberSlider
        label="Emissive Intensity"
        value={m.emissive_intensity}
        min={0}
        max={3}
        step={0.05}
        onChange={(v) => updateMaterial(object.id, { emissive_intensity: v })}
      />
      <SelectField
        label="Side"
        value={(m.side ?? 'front') as 'front' | 'back' | 'double'}
        options={[
          { value: 'front', label: 'Front' },
          { value: 'back', label: 'Back' },
          { value: 'double', label: 'Double' },
        ]}
        onChange={(v) => updateMaterial(object.id, { side: v })}
      />
      <ToggleField
        label="Flat Shading"
        value={m.flat_shading ?? false}
        onChange={(v) => updateMaterial(object.id, { flat_shading: v })}
      />
      <ToggleField
        label="Wireframe"
        value={m.wireframe}
        onChange={(v) => updateMaterial(object.id, { wireframe: v })}
      />
    </div>
  )
}

/* ---------- Light editor ---------- */

const LIGHT_TYPES: Array<{ value: LightType; label: string }> = [
  { value: 'ambient', label: 'Ambient' },
  { value: 'directional', label: 'Directional' },
  { value: 'point', label: 'Point' },
  { value: 'spot', label: 'Spot' },
  { value: 'hemisphere', label: 'Hemisphere' },
]

function LightEditor({ light }: { light: LightObject }) {
  const updateLight = useScene((s) => s.updateLight)
  const l = light
  return (
    <>
      <div className="px-3 py-3 border-b border-border-subtle space-y-3">
        <SectionHeader icon={Lightbulb} title="Light" color="text-accent-gold" />
        <SelectField<LightType>
          label="Type"
          value={l.type}
          options={LIGHT_TYPES}
          onChange={(t) => updateLight(l.id, { type: t })}
        />
        <ColorField
          label="Color"
          value={l.color}
          onChange={(v) => updateLight(l.id, { color: v })}
        />
        <NumberSlider
          label="Intensity"
          value={l.intensity}
          min={0}
          max={5}
          step={0.05}
          onChange={(v) => updateLight(l.id, { intensity: v })}
        />
        {l.type !== 'ambient' && (
          <Vec3Editor
            label="Position"
            value={l.position}
            min={-15}
            max={15}
            step={0.1}
            onChange={(axis, v) => {
              const next: Vec3 = [...l.position] as Vec3
              next[axis] = v
              updateLight(l.id, { position: next })
            }}
          />
        )}
        {(l.type === 'directional' || l.type === 'spot') && (
          <Vec3Editor
            label="Target"
            value={l.target ?? [0, 0, 0]}
            min={-15}
            max={15}
            step={0.1}
            onChange={(axis, v) => {
              const base: Vec3 = l.target ? [...l.target] as Vec3 : [0, 0, 0]
              base[axis] = v
              updateLight(l.id, { target: base })
            }}
          />
        )}
        {l.type === 'spot' && (
          <>
            <NumberSlider
              label="Angle (rad)"
              value={l.angle ?? Math.PI / 6}
              min={0.05}
              max={Math.PI / 2}
              step={0.02}
              onChange={(v) => updateLight(l.id, { angle: v })}
            />
            <NumberSlider
              label="Penumbra"
              value={l.penumbra ?? 0}
              min={0}
              max={1}
              step={0.05}
              onChange={(v) => updateLight(l.id, { penumbra: v })}
            />
          </>
        )}
        {(l.type === 'point' || l.type === 'spot') && (
          <>
            <NumberSlider
              label="Distance"
              value={l.distance ?? 0}
              min={0}
              max={30}
              step={0.5}
              onChange={(v) => updateLight(l.id, { distance: v })}
            />
            <NumberSlider
              label="Decay"
              value={l.decay ?? 2}
              min={0}
              max={4}
              step={0.1}
              onChange={(v) => updateLight(l.id, { decay: v })}
            />
          </>
        )}
        <ToggleField
          label="Cast Shadow"
          value={l.cast_shadow}
          onChange={(v) => updateLight(l.id, { cast_shadow: v })}
        />
      </div>
    </>
  )
}

/* ---------- Camera editor ---------- */

const CAM_ANIM_TYPES: Array<{ value: CameraAnimation['type']; label: string }> = [
  { value: 'orbit', label: 'Orbit' },
  { value: 'flythrough', label: 'Flythrough' },
]

function CameraEditor({ camera }: { camera: CameraObject }) {
  const updateCamera = useScene((s) => s.updateCamera)
  const c = camera
  const anim = c.animation
  return (
    <div className="px-3 py-3 border-b border-border-subtle space-y-3">
      <SectionHeader icon={CameraIcon} title="Camera" color="text-accent-cyan" />
      <SelectField
        label="Type"
        value={c.type}
        options={[
          { value: 'perspective', label: 'Perspective' },
          { value: 'orthographic', label: 'Orthographic' },
        ]}
        onChange={(t) => updateCamera(c.id, { type: t })}
      />
      <Vec3Editor
        label="Position"
        value={c.position}
        min={-20}
        max={20}
        step={0.1}
        onChange={(axis, v) => {
          const next: Vec3 = [...c.position] as Vec3
          next[axis] = v
          updateCamera(c.id, { position: next })
        }}
      />
      <Vec3Editor
        label="Target"
        value={c.target}
        min={-20}
        max={20}
        step={0.1}
        onChange={(axis, v) => {
          const next: Vec3 = [...c.target] as Vec3
          next[axis] = v
          updateCamera(c.id, { target: next })
        }}
      />
      <NumberSlider
        label="FOV"
        value={c.fov}
        min={10}
        max={120}
        step={1}
        onChange={(v) => updateCamera(c.id, { fov: v })}
      />
      <NumberSlider
        label="Near"
        value={c.near}
        min={0.01}
        max={2}
        step={0.01}
        onChange={(v) => updateCamera(c.id, { near: v })}
      />
      <NumberSlider
        label="Far"
        value={c.far}
        min={50}
        max={2000}
        step={10}
        onChange={(v) => updateCamera(c.id, { far: v })}
      />
      <ToggleField
        label="Enable Animation"
        value={!!anim}
        onChange={(v) =>
          updateCamera(c.id, {
            animation: v
              ? { type: 'orbit', duration: 10, loop: true, target: [0, 0.5, 0], radius: 6, height: 3 }
              : null,
          })
        }
      />
      {anim && (
        <>
          <SelectField<CameraAnimation['type']>
            label="Anim Type"
            value={anim.type}
            options={CAM_ANIM_TYPES}
            onChange={(t) => updateCamera(c.id, { animation: { ...anim, type: t } })}
          />
          <NumberSlider
            label="Duration (s)"
            value={anim.duration}
            min={1}
            max={60}
            step={1}
            onChange={(v) => updateCamera(c.id, { animation: { ...anim, duration: v } })}
          />
          <ToggleField
            label="Loop"
            value={anim.loop}
            onChange={(v) => updateCamera(c.id, { animation: { ...anim, loop: v } })}
          />
          {anim.type === 'orbit' && (
            <>
              <NumberSlider
                label="Radius"
                value={anim.radius ?? 6}
                min={1}
                max={20}
                step={0.5}
                onChange={(v) => updateCamera(c.id, { animation: { ...anim, radius: v } })}
              />
              <NumberSlider
                label="Height"
                value={anim.height ?? 3}
                min={-5}
                max={15}
                step={0.5}
                onChange={(v) => updateCamera(c.id, { animation: { ...anim, height: v } })}
              />
            </>
          )}
        </>
      )}
    </div>
  )
}

/* ---------- Main component ---------- */

const RAD2DEG = 180 / Math.PI
const DEG2RAD = Math.PI / 180

/** Resolves the selected entity (object / light / camera / group) and its kind. */
function useSelectedEntity() {
  return useScene((s) => {
    const id = s.selectedId
    if (!id) return { kind: 'none' as const, id }
    const obj = s.scene.objects.find((o) => o.id === id)
    if (obj) return { kind: 'object' as const, id, entity: obj }
    const light = s.scene.lights.find((l) => l.id === id)
    if (light) return { kind: 'light' as const, id, entity: light }
    const camera = s.scene.cameras.find((c) => c.id === id)
    if (camera) return { kind: 'camera' as const, id, entity: camera }
    const group = s.scene.groups.find((g) => g.id === id)
    if (group) return { kind: 'group' as const, id, entity: group }
    return { kind: 'none' as const, id }
  })
}

export function PropertiesTab() {
  const sel = useSelectedEntity()
  const updateTransformAxis = useScene((s) => s.updateTransformAxis)
  const renameObject = useScene((s) => s.renameObject)
  const renameGroup = useScene((s) => s.renameGroup)
  const updateLight = useScene((s) => s.updateLight)
  const updateCamera = useScene((s) => s.updateCamera)

  if (sel.kind === 'none') {
    return (
      <div className="flex flex-col items-center justify-center h-full text-center px-6 py-10">
        <Target size={20} className="text-fg-muted mb-2" />
        <p className="text-xs text-fg-secondary">Nothing selected</p>
        <p className="text-[11px] text-fg-muted mt-1">
          Click an object, light, or camera to edit its properties
        </p>
      </div>
    )
  }

  // Light selected
  if (sel.kind === 'light') {
    const light = sel.entity
    return (
      <div className="overflow-y-auto h-full">
        <div className="px-3 py-3 border-b border-border-subtle">
          <label className="text-[10px] uppercase tracking-wider text-fg-muted">Light Name</label>
          <input
            value={light.name}
            onChange={(e) => updateLight(light.id, { name: e.target.value })}
            className="mt-1 w-full text-sm text-fg-primary bg-bg-base border border-border rounded px-2 py-1.5 outline-none focus:border-accent-cyan/50"
          />
        </div>
        <LightEditor light={light} />
      </div>
    )
  }

  // Camera selected
  if (sel.kind === 'camera') {
    const camera = sel.entity
    return (
      <div className="overflow-y-auto h-full">
        <div className="px-3 py-3 border-b border-border-subtle">
          <label className="text-[10px] uppercase tracking-wider text-fg-muted">Camera Name</label>
          <input
            value={camera.name}
            onChange={(e) => updateCamera(camera.id, { name: e.target.value })}
            className="mt-1 w-full text-sm text-fg-primary bg-bg-base border border-border rounded px-2 py-1.5 outline-none focus:border-accent-cyan/50"
          />
        </div>
        <CameraEditor camera={camera} />
      </div>
    )
  }

  // Group selected
  if (sel.kind === 'group') {
    const group = sel.entity
    const childCount = group.child_ids.length
    return (
      <div className="overflow-y-auto h-full">
        <div className="px-3 py-3 border-b border-border-subtle">
          <label className="text-[10px] uppercase tracking-wider text-fg-muted">Group Name</label>
          <input
            value={group.name}
            onChange={(e) => renameGroup(group.id, e.target.value)}
            className="mt-1 w-full text-sm text-fg-primary bg-bg-base border border-border rounded px-2 py-1.5 outline-none focus:border-accent-cyan/50"
          />
        </div>
        <div className="px-3 py-3 space-y-2">
          <SectionHeader icon={Triangle} title="Children" color="text-accent-gold" />
          <div className="text-[11px] text-fg-secondary">
            {childCount} object{childCount === 1 ? '' : 's'} in this group
          </div>
          <div className="text-[10px] text-fg-muted">
            Use the Outliner to add or remove objects from this group.
          </div>
        </div>
      </div>
    )
  }

  // Object selected (default)
  const object = sel.entity
  const t = object.transform
  const setRot = (axis: 0 | 1 | 2, deg: number) =>
    updateTransformAxis(object.id, 'rotation', axis, deg * DEG2RAD)
  const rotDeg: Vec3 = [t.rotation[0] * RAD2DEG, t.rotation[1] * RAD2DEG, t.rotation[2] * RAD2DEG]

  return (
    <div className="overflow-y-auto h-full">
      {/* Name */}
      <div className="px-3 py-3 border-b border-border-subtle">
        <label className="text-[10px] uppercase tracking-wider text-fg-muted">Name</label>
        <input
          value={object.name}
          onChange={(e) => renameObject(object.id, e.target.value)}
          className="mt-1 w-full text-sm text-fg-primary bg-bg-base border border-border rounded px-2 py-1.5 outline-none focus:border-accent-cyan/50"
        />
      </div>

      {/* Transform */}
      <div className="px-3 py-3 border-b border-border-subtle space-y-3">
        <SectionHeader icon={Sliders} title="Transform" color="text-accent-cyan" />
        <Vec3Editor
          label="Position"
          value={t.position}
          min={-10}
          max={10}
          step={0.1}
          onChange={(axis, v) => updateTransformAxis(object.id, 'position', axis, v)}
        />
        <Vec3Editor
          label="Rotation (°)"
          value={rotDeg}
          min={-180}
          max={180}
          step={1}
          onChange={setRot}
        />
        <Vec3Editor
          label="Scale"
          value={t.scale}
          min={0.1}
          max={5}
          step={0.1}
          onChange={(axis, v) => updateTransformAxis(object.id, 'scale', axis, v)}
        />
      </div>

      <GeometryEditor object={object} />
      <ObjectAnimationEditor object={object} />
      <MaterialEditor object={object} />
    </div>
  )
}
