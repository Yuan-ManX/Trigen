// 3D canvas container: R3F Canvas, renders scene objects / lights / grid ground.
// Supports edit mode (interactive selection + transform gizmo) and run mode
// (auto-rotating showcase / camera animation playback).
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { Environment, Grid, Html } from '@react-three/drei'
import { Magnet, Move, RotateCw, Scaling } from 'lucide-react'
import { Suspense, useEffect, useMemo, useRef } from 'react'
import * as THREE from 'three'
import { useEditor, type TransformMode } from '../../store/useEditor'
import { usePlayback } from '../../store/usePlayback'
import { useScene } from '../../store/useScene'
import type { CameraObject } from '../../types'
import { CameraRig } from './CameraRig'
import { Minimap } from './Minimap'
import { RadialMenu } from './RadialMenu'
import { SceneLight } from './SceneLight'
import { SceneMesh } from './SceneMesh'

interface EditorCanvasProps {
  mode?: 'edit' | 'run'
}

/** Transform mode toolbar overlay */
function TransformToolbar({
  mode,
  current,
  onChange,
}: {
  mode: 'edit' | 'run'
  current: TransformMode
  onChange: (m: TransformMode) => void
}) {
  const gridSnapEnabled = useEditor((s) => s.gridSnapEnabled)
  const snapIncrement = useEditor((s) => s.snapIncrement)
  const setGridSnap = useEditor((s) => s.setGridSnap)
  if (mode !== 'edit') return null
  const buttons: Array<{ id: TransformMode; icon: typeof Move; label: string }> = [
    { id: 'translate', icon: Move, label: 'Move' },
    { id: 'rotate', icon: RotateCw, label: 'Rotate' },
    { id: 'scale', icon: Scaling, label: 'Scale' },
  ]
  return (
    <div className="absolute top-3 left-1/2 -translate-x-1/2 z-10 flex items-center gap-0.5 rounded-md border border-border bg-bg-panel/90 backdrop-blur p-0.5">
      {buttons.map((b) => {
        const Icon = b.icon
        const active = current === b.id
        return (
          <button
            key={b.id}
            onClick={() => onChange(b.id)}
            className={`flex items-center gap-1.5 px-2.5 py-1 rounded text-[11px] font-medium transition-colors ${
              active
                ? 'bg-accent-cyan/15 text-accent-cyan'
                : 'text-fg-muted hover:text-fg-secondary'
            }`}
            title={b.label}
          >
            <Icon size={12} />
            <span>{b.label}</span>
          </button>
        )
      })}
      {/* Snap-to-grid toggle: when enabled, gizmo drags round to snapIncrement */}
      <div className="mx-1 h-4 w-px bg-border-subtle" />
      <button
        onClick={() => setGridSnap(!gridSnapEnabled, snapIncrement)}
        className={`flex items-center gap-1.5 px-2 py-1 rounded text-[11px] font-medium transition-colors ${
          gridSnapEnabled
            ? 'bg-accent-gold/15 text-accent-gold'
            : 'text-fg-muted hover:text-fg-secondary'
        }`}
        title={
          gridSnapEnabled
            ? `Grid snap ON (increment ${snapIncrement})`
            : 'Grid snap OFF'
        }
        aria-pressed={gridSnapEnabled}
      >
        <Magnet size={12} />
        <span>Snap {gridSnapEnabled ? `${snapIncrement}` : 'Off'}</span>
      </button>
    </div>
  )
}

/** Viewport base lighting (fallback when the scene has no lights, ensuring objects are visible) */
function ViewportBaseLights({ hasLights }: { hasLights: boolean }) {
  if (hasLights) {
    return <hemisphereLight color="#ffffff" groundColor="#202028" intensity={0.08} />
  }
  return (
    <>
      <ambientLight intensity={0.6} />
      <directionalLight position={[5, 8, 5]} intensity={0.8} castShadow />
      <hemisphereLight color="#aab4ff" groundColor="#1a1a24" intensity={0.3} />
    </>
  )
}

// drei <Environment> ships a fixed set of built-in HDRIs. Map the backend's
// friendly preset names onto them; anything else falls back to a URL load.
const DREI_ENV_PRESETS = new Set([
  'apartment', 'city', 'dawn', 'forest', 'lobby',
  'night', 'park', 'studio', 'sunset', 'warehouse',
])

interface ParsedEnvironment {
  preset?: string
  url?: string
  intensity: number
}

function parseEnvironment(env: string | null): ParsedEnvironment | null {
  if (!env) return null
  const [rawUrl, intensityStr] = env.split('|')
  const url = (rawUrl ?? '').trim()
  if (!url) return null
  const intensity = parseFloat(intensityStr ?? '1')
  const norm = url.replace(/\.hdr$/i, '').toLowerCase()
  if (DREI_ENV_PRESETS.has(norm)) {
    return { preset: norm, intensity: Number.isFinite(intensity) ? intensity : 1 }
  }
  if (/^https?:\/\//i.test(url)) {
    return { url, intensity: Number.isFinite(intensity) ? intensity : 1 }
  }
  // Unknown bare filename (e.g. "neutral.hdr") — no HDRI to load, but we still
  // want the intensity applied to whatever environment the scene already has.
  return { intensity: Number.isFinite(intensity) ? intensity : 1 }
}

/** Renders the HDRI environment and applies the intensity to the scene. */
function EnvironmentLayer({ env }: { env: string | null }) {
  const scene = useThree((s) => s.scene)
  const parsed = useMemo(() => parseEnvironment(env), [env])

  useEffect(() => {
    // three.js r0.163+ exposes scene.environmentIntensity for fine-grained
    // control over image-based lighting strength.
    ;(scene as any).environmentIntensity = parsed?.intensity ?? 1
  }, [scene, parsed?.intensity])

  if (!parsed) return null
  if (parsed.preset) {
    return <Environment preset={parsed.preset as any} />
  }
  if (parsed.url) {
    return <Environment files={parsed.url} />
  }
  return null
}

/** A small gizmo marking a scene camera's position and look direction. */
function CameraMarker({ camera }: { camera: CameraObject }) {
  const groupRef = useRef<THREE.Group>(null)
  useEffect(() => {
    if (!groupRef.current) return
    const pos = new THREE.Vector3(camera.position[0], camera.position[1], camera.position[2])
    const target = new THREE.Vector3(camera.target[0], camera.target[1], camera.target[2])
    groupRef.current.position.copy(pos)
    // Orient the group so its -Z axis faces the target (Three.js camera convention)
    const dir = target.clone().sub(pos)
    if (dir.lengthSq() > 1e-6) {
      const m = new THREE.Matrix4().lookAt(pos, target, new THREE.Vector3(0, 1, 0))
      groupRef.current.quaternion.setFromRotationMatrix(m)
    }
  }, [camera.position, camera.target])

  return (
    <group ref={groupRef}>
      {/* Camera body */}
      <mesh>
        <boxGeometry args={[0.3, 0.2, 0.2]} />
        <meshStandardMaterial color="#FFB800" emissive="#FFB800" emissiveIntensity={0.4} />
      </mesh>
      {/* Lens (points toward -Z, i.e. the target) */}
      <mesh position={[0, 0, -0.2]}>
        <coneGeometry args={[0.12, 0.2, 16]} />
        <meshStandardMaterial color="#FFB800" emissive="#FFB800" emissiveIntensity={0.4} />
      </mesh>
      <Html distanceFactor={10} position={[0, 0.35, 0]} center>
        <div className="pointer-events-none whitespace-nowrap rounded bg-bg-panel/80 px-1.5 py-0.5 text-[10px] text-accent-cyan border border-accent-cyan/30">
          {camera.name}
        </div>
      </Html>
    </group>
  )
}

/**
 * Single-frame clock driver for object animations. Mounted once inside the
 * Canvas; calls the playback store's tick so the Timeline playhead advances
 * in lockstep with the viewport render loop.
 */
function PlaybackDriver() {
  const tick = usePlayback((s) => s.tick)
  useFrame(() => tick(performance.now()))
  return null
}

/**
 * Syncs the viewport camera when the Agent requests an explicit position +
 * target via set_viewport_camera / focus_object. Watches the token counter so
 * repeated identical requests still trigger a move.
 */
function ViewportCameraSync() {
  const camera = useThree((s) => s.camera)
  const controls = useThree((s) => (s as any).controls)
  const vc = useEditor((s) => s.viewportCamera)
  useEffect(() => {
    if (!vc) return
    const target = new THREE.Vector3(vc.target[0], vc.target[1], vc.target[2])
    camera.position.set(vc.position[0], vc.position[1], vc.position[2])
    camera.lookAt(target)
    if (controls) {
      controls.target.copy(target)
      controls.update()
    }
  }, [vc?.token, camera, controls])
  return null
}

/**
 * Captures the viewport as a PNG download when the Agent requests it via
 * capture_viewport. Watches the capture counter so repeated requests fire.
 */
function ViewportCapture() {
  const gl = useThree((s) => s.gl)
  const counter = useEditor((s) => s.captureCounter)
  const filename = useEditor((s) => s.captureFilename)
  useEffect(() => {
    if (counter === 0) return
    // preserveDrawingBuffer is enabled on the Canvas, so the framebuffer
    // contents persist and toDataURL captures the current viewport.
    const dataUrl = gl.domElement.toDataURL('image/png')
    const link = document.createElement('a')
    link.href = dataUrl
    link.download = `${filename}.png`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
  }, [counter, gl, filename])
  return null
}

/**
 * Renders the active measurement overlay: a line between two world positions
 * with a distance label at the midpoint, plus endpoint markers. Driven by the
 * editor_measure delta emitted from the measure_distance tool.
 */
function MeasurementOverlay() {
  const measurement = useEditor((s) => s.measurement)
  const clearMeasurement = useEditor((s) => s.clearMeasurement)
  // Re-mount the overlay whenever a new measurement token arrives so the
  // auto-clear timer resets cleanly.
  const token = measurement?.token ?? 0
  useEffect(() => {
    if (token === 0) return
    const id = window.setTimeout(() => clearMeasurement(), 8000)
    return () => window.clearTimeout(id)
  }, [token, clearMeasurement])

  if (!measurement) return null
  const { aPosition, bPosition, label } = measurement
  const mid: [number, number, number] = [
    (aPosition[0] + bPosition[0]) / 2,
    (aPosition[1] + bPosition[1]) / 2 + 0.15,
    (aPosition[2] + bPosition[2]) / 2,
  ]
  return (
    <group>
      {/* Dashed line between the two measured positions */}
      <line>
        <bufferGeometry>
          <bufferAttribute
            attach="attributes-position"
            args={[new Float32Array([...aPosition, ...bPosition]), 3]}
          />
        </bufferGeometry>
        <lineDashedMaterial
          color="#00F0FF"
          dashSize={0.2}
          gapSize={0.1}
          linewidth={2}
          depthTest={false}
          transparent
          opacity={0.9}
        />
      </line>
      {/* Endpoint markers */}
      <mesh position={aPosition}>
        <sphereGeometry args={[0.06, 16, 16]} />
        <meshBasicMaterial color="#00F0FF" depthTest={false} transparent opacity={0.95} />
      </mesh>
      <mesh position={bPosition}>
        <sphereGeometry args={[0.06, 16, 16]} />
        <meshBasicMaterial color="#FFB800" depthTest={false} transparent opacity={0.95} />
      </mesh>
      {/* Distance label at the midpoint */}
      <Html position={mid} center distanceFactor={10}>
        <div className="pointer-events-none whitespace-nowrap rounded bg-bg-panel/90 px-2 py-1 text-[11px] font-mono text-accent-cyan border border-accent-cyan/40 shadow-glow">
          {label}
        </div>
      </Html>
    </group>
  )
}

/**
 * Applies the active clipping plane to the WebGLRenderer. Watches the
 * clippingPlane token so repeated identical states still re-apply. Uses
 * the renderer's global clippingPlanes array (applies to every material).
 *
 * Plane convention: a point is KEPT when normal·point + constant >= 0.
 * - invert=false → keep the positive side (normal points in +axis direction)
 * - invert=true  → keep the negative side (normal points in -axis direction)
 */
function ClippingPlaneSync() {
  const gl = useThree((s) => s.gl)
  const cp = useEditor((s) => s.clippingPlane)
  useEffect(() => {
    if (!cp || !cp.enabled) {
      gl.clippingPlanes = []
      return
    }
    const sign = cp.invert ? -1 : 1
    const normal =
      cp.axis === 'x'
        ? new THREE.Vector3(sign, 0, 0)
        : cp.axis === 'z'
          ? new THREE.Vector3(0, 0, sign)
          : new THREE.Vector3(0, sign, 0)
    // constant = -sign * position so the plane sits at `position` along axis.
    const plane = new THREE.Plane(normal, -sign * cp.position)
    gl.clippingPlanes = [plane]
    return () => {
      gl.clippingPlanes = []
    }
  }, [cp?.token, cp?.enabled, cp?.axis, cp?.position, cp?.invert, gl])
  return null
}

/**
 * On-canvas annotation overlay. Renders one anchored bubble per
 * annotation in the scene. Annotations anchored to an object_id track
 * that object's current transform every frame, so the label follows
 * drag / animation. Annotations with no anchor stay at their world
 * position. Edit mode only — hidden in run mode for a clean showcase.
 */
function AnnotationLayer() {
  const annotations = useScene((s) => s.scene.annotations ?? [])
  const objects = useScene((s) => s.scene.objects)
  const removeAnnotation = useScene((s) => s.removeAnnotation)
  // Resolve anchored annotations to a live world position each render.
  // Pull the object transform from the store so drag updates propagate
  // without needing a separate event channel.
  const objPos = (id: string | null | undefined): [number, number, number] | null => {
    if (!id) return null
    const o = objects.find((x) => x.id === id)
    if (!o) return null
    return o.transform.position
  }
  if (annotations.length === 0) return null
  return (
    <group>
      {annotations.map((a) => {
        if (a.visible === false) return null
        const anchor = objPos(a.object_id)
        const pos: [number, number, number] = anchor ?? a.position
        // Offset the bubble slightly above the anchor so the leader line
        // is visible and the text does not overlap the geometry.
        const bubblePos: [number, number, number] = [pos[0], pos[1] + 0.6, pos[2]]
        const accent = a.color ?? '#FFB800'
        return (
          <group key={a.id}>
            {/* Pin marker at the anchor point */}
            <mesh position={pos}>
              <sphereGeometry args={[0.05, 12, 12]} />
              <meshBasicMaterial color={accent} depthTest={false} transparent opacity={0.95} />
            </mesh>
            {/* Leader line from anchor up to the bubble */}
            <line>
              <bufferGeometry>
                <bufferAttribute
                  attach="attributes-position"
                  args={[new Float32Array([...pos, ...bubblePos]), 3]}
                />
              </bufferGeometry>
              <lineBasicMaterial color={accent} depthTest={false} transparent opacity={0.7} />
            </line>
            <Html position={bubblePos} center distanceFactor={10} zIndexRange={[40, 0]}>
              <div
                className="pointer-events-auto max-w-[200px] rounded-md border bg-bg-panel/95 px-2 py-1.5 shadow-lg backdrop-blur"
                style={{ borderColor: `${accent}66` }}
              >
                <div className="flex items-start justify-between gap-2">
                  {a.title && (
                    <div
                      className="text-[10px] font-semibold uppercase tracking-wide"
                      style={{ color: accent }}
                    >
                      {a.title}
                    </div>
                  )}
                  <button
                    onClick={() => removeAnnotation(a.id)}
                    aria-label="Remove annotation"
                    className="shrink-0 text-fg-muted hover:text-rose-400 text-[10px] leading-none"
                  >
                    ×
                  </button>
                </div>
                <div className="text-[11px] leading-snug text-fg-secondary whitespace-pre-wrap">
                  {a.text}
                </div>
              </div>
            </Html>
          </group>
        )
      })}
    </group>
  )
}

function SceneContent({
  mode,
  transformMode,
}: {
  mode: 'edit' | 'run'
  transformMode: TransformMode
}) {
  const scene = useScene((s) => s.scene)
  const fogColor = scene.fog?.color ?? scene.background
  const fogNear = scene.fog?.near ?? 18
  const fogFar = scene.fog?.far ?? 55

  // Pick the first camera carrying an animation descriptor; in run mode the
  // viewport plays it, in edit mode we leave the camera interactive.
  const animation = useMemo(() => {
    if (mode !== 'run') return null
    for (const c of scene.cameras) {
      if (c.animation) return c.animation
    }
    return null
  }, [scene.cameras, mode])

  // Render markers for scene cameras except the internal ViewportCamera.
  const visibleCameras = scene.cameras.filter((c) => c.name !== 'ViewportCamera')

  return (
    <>
      <color attach="background" args={[scene.background]} />
      <fog attach="fog" args={[fogColor, fogNear, fogFar]} />

      {/* Advance the animation clock every frame; no-op when paused */}
      <PlaybackDriver />

      <ViewportBaseLights hasLights={scene.lights.length > 0} />
      <EnvironmentLayer env={scene.environment} />

      {/* Lights */}
      {scene.lights.map((l) => (
        <SceneLight key={l.id} light={l} />
      ))}

      {/* Grid ground — hidden in run mode for a cleaner showcase */}
      {mode === 'edit' && (
        <Grid
          visible={scene.grid_visible}
          position={[0, 0, 0]}
          args={[scene.grid_size, scene.grid_size]}
          cellSize={0.5}
          cellThickness={0.6}
          cellColor="#2a2a35"
          sectionSize={2.5}
          sectionThickness={1}
          sectionColor="#3a3a4a"
          fadeDistance={32}
          fadeStrength={1}
          infiniteGrid
          followCamera={false}
        />
      )}

      {/* Transparent ground that receives shadows */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0, 0]} receiveShadow>
        <planeGeometry args={[80, 80]} />
        <shadowMaterial transparent opacity={0.35} />
      </mesh>

      {/* Mesh objects — pass editMode and transformMode for gizmo support */}
      {scene.objects.map((o) => (
        <SceneMesh
          key={o.id}
          object={o}
          editMode={mode === 'edit'}
          transformMode={transformMode}
        />
      ))}

      {/* Scene camera markers (gizmo + label) */}
      {visibleCameras.map((c) => (
        <CameraMarker key={c.id} camera={c} />
      ))}

      {/* On-canvas annotation overlay — edit mode only */}
      {mode === 'edit' && <AnnotationLayer />}

      <CameraRig autoRotate={mode === 'run'} animation={animation} storyboard={scene.storyboard ?? null} />
    </>
  )
}

export function EditorCanvas({ mode = 'edit' }: EditorCanvasProps) {
  const select = useScene((s) => s.select)
  const transformMode = useEditor((s) => s.transformMode)
  const setTransformMode = useEditor((s) => s.setTransformMode)
  const renderQuality = useEditor((s) => s.renderQuality)
  const clippingPlane = useEditor((s) => s.clippingPlane)
  const minimapEnabled = useEditor((s) => s.minimapEnabled)
  const shadowsEnabled = useEditor((s) => s.shadowsEnabled)
  const projectionMode = useEditor((s) => s.projectionMode)

  // Map render quality to device pixel ratio range
  const dpr: [number, number] = renderQuality === 'low' ? [1, 1] : renderQuality === 'medium' ? [1, 1.5] : [1, 2]

  const clippingActive = !!clippingPlane?.enabled
  const clippingLabel = clippingPlane
    ? `Clipping: ON (${clippingPlane.axis.toUpperCase()}=${clippingPlane.position.toFixed(2)}${clippingPlane.invert ? ' ¬' : ''})`
    : ''

  // Camera config: orthographic uses an orthographic-projection frustum;
  // perspective uses a fov-based frustum. The CameraRig component handles
  // per-frame positioning regardless of projection type.
  const cameraConfig = projectionMode === 'orthographic'
    ? { near: 0.1, far: 1000, position: [5, 4, 7] as [number, number, number], zoom: 80 }
    : { fov: 45, near: 0.1, far: 1000, position: [5, 4, 7] as [number, number, number] }

  return (
    <>
      <TransformToolbar mode={mode} current={transformMode} onChange={setTransformMode} />
      <Canvas
        shadows={shadowsEnabled}
        dpr={dpr}
        camera={cameraConfig}
        gl={{ antialias: renderQuality !== 'low', preserveDrawingBuffer: true }}
        // Click on blank area to deselect (only in edit mode)
        onPointerMissed={() => {
          if (mode === 'edit') select(null)
        }}
        style={{ width: '100%', height: '100%' }}
      >
        <Suspense fallback={null}>
          <SceneContent mode={mode} transformMode={transformMode} />
          <ViewportCameraSync />
          <ViewportCapture />
          <MeasurementOverlay />
          <ClippingPlaneSync />
        </Suspense>
      </Canvas>

      {/* Minimap overlay (top-down x,z projection). Edit mode only — in run
          mode the viewport is a clean showcase. */}
      {mode === 'edit' && minimapEnabled && <Minimap />}

      {/* Clipping-plane active badge (sits just below the transform toolbar) */}
      {clippingActive && (
        <div
          className="absolute top-14 left-1/2 -translate-x-1/2 z-10 rounded-md border border-fuchsia-500/40 bg-fuchsia-500/10 px-2.5 py-1 text-[10px] font-mono text-fuchsia-300 backdrop-blur pointer-events-none"
          title="A clipping plane is active. Disable via set_clipping_plane(enabled=false)."
        >
          {clippingLabel}
        </div>
      )}

      {/* Radial pie-menu overlay (right-click on a mesh). Rendered as a
          fixed-position portal so it floats above the canvas; only present
          in edit mode — run mode is a clean showcase. */}
      {mode === 'edit' && <RadialMenu />}
    </>
  )
}
