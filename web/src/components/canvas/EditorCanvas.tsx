// 3D 画布容器：R3F Canvas，渲染场景对象/光源/网格地面
// 3D canvas container: R3F Canvas, renders scene objects / lights / grid ground
import { Canvas } from '@react-three/fiber'
import { Grid } from '@react-three/drei'
import { Suspense } from 'react'
import { useScene } from '../../store/useScene'
import { CameraRig } from './CameraRig'
import { SceneLight } from './SceneLight'
import { SceneMesh } from './SceneMesh'

/** 视口基础光照（场景无光源时的兜底，保证对象可见） */
/** Viewport base lighting (fallback when the scene has no lights, ensuring objects are visible) */
function ViewportBaseLights({ hasLights }: { hasLights: boolean }) {
  if (hasLights) {
    // 场景已有光源时，仅补一束极弱天光防止死角纯黑
    // When the scene already has lights, only add a very weak sky light to prevent pure black in dead corners
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

function SceneContent() {
  const scene = useScene((s) => s.scene)

  return (
    <>
      <color attach="background" args={[scene.background]} />
      <fog attach="fog" args={[scene.background, 18, 55]} />

      <ViewportBaseLights hasLights={scene.lights.length > 0} />

      {/* 光源 */}
      {/* Lights */}
      {scene.lights.map((l) => (
        <SceneLight key={l.id} light={l} />
      ))}

      {/* 网格地面 */}
      {/* Grid ground */}
      <Grid
        position={[0, 0, 0]}
        args={[40, 40]}
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

      {/* 接收阴影的透明地面 */}
      {/* Transparent ground that receives shadows */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0, 0]} receiveShadow>
        <planeGeometry args={[80, 80]} />
        <shadowMaterial transparent opacity={0.35} />
      </mesh>

      {/* 网格对象 */}
      {/* Mesh objects */}
      {scene.objects.map((o) => (
        <SceneMesh key={o.id} object={o} />
      ))}

      <CameraRig />
    </>
  )
}

export function EditorCanvas() {
  const select = useScene((s) => s.select)

  return (
    <Canvas
      shadows
      dpr={[1, 2]}
      camera={{ fov: 45, near: 0.1, far: 1000, position: [5, 4, 7] }}
      gl={{ antialias: true, preserveDrawingBuffer: true }}
      // 点击空白处取消选中
      // Click on blank area to deselect
      onPointerMissed={() => select(null)}
      style={{ width: '100%', height: '100%' }}
    >
      <Suspense fallback={null}>
        <SceneContent />
      </Suspense>
    </Canvas>
  )
}
