// 3D canvas container: R3F Canvas, renders scene objects / lights / grid ground.
// Supports edit mode (interactive selection + transform gizmo) and run mode
// (auto-rotating showcase / camera animation playback).
import { Canvas, useThree } from '@react-three/fiber'
import { Environment, Grid, Html } from '@react-three/drei'
import { Move, RotateCw, Scaling } from 'lucide-react'
import { Suspense, useEffect, useMemo, useRef, useState } from 'react'
import * as THREE from 'three'
import { useScene } from '../../store/useScene'
import type { CameraObject } from '../../types'
import { CameraRig } from './CameraRig'
import { SceneLight } from './SceneLight'
import { SceneMesh, type TransformMode } from './SceneMesh'

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

      <CameraRig autoRotate={mode === 'run'} animation={animation} />
    </>
  )
}

export function EditorCanvas({ mode = 'edit' }: EditorCanvasProps) {
  const select = useScene((s) => s.select)
  const [transformMode, setTransformMode] = useState<TransformMode>('translate')

  return (
    <>
      <TransformToolbar mode={mode} current={transformMode} onChange={setTransformMode} />
      <Canvas
        shadows
        dpr={[1, 2]}
        camera={{ fov: 45, near: 0.1, far: 1000, position: [5, 4, 7] }}
        gl={{ antialias: true, preserveDrawingBuffer: true }}
        // Click on blank area to deselect (only in edit mode)
        onPointerMissed={() => {
          if (mode === 'edit') select(null)
        }}
        style={{ width: '100%', height: '100%' }}
      >
        <Suspense fallback={null}>
          <SceneContent mode={mode} transformMode={transformMode} />
        </Suspense>
      </Canvas>
    </>
  )
}
