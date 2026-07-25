// 3D canvas container: R3F Canvas, renders scene objects / lights / grid ground
// Supports edit mode (interactive selection + transform gizmo) and run mode (auto-rotating showcase)
import { Canvas } from '@react-three/fiber'
import { Grid } from '@react-three/drei'
import { Move, RotateCw, Scaling } from 'lucide-react'
import { Suspense, useState } from 'react'
import { useScene } from '../../store/useScene'
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

  return (
    <>
      <color attach="background" args={[scene.background]} />
      <fog attach="fog" args={[fogColor, fogNear, fogFar]} />

      <ViewportBaseLights hasLights={scene.lights.length > 0} />

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

      <CameraRig autoRotate={mode === 'run'} />
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
