// Camera control: OrbitControls + sync with scene cameras set by Agent
import { OrbitControls } from '@react-three/drei'
import { useThree } from '@react-three/fiber'
import { useEffect, useRef } from 'react'
import * as THREE from 'three'
import { useScene } from '../../store/useScene'

export function CameraRig({ autoRotate = false }: { autoRotate?: boolean }) {
  const camera = useThree((s) => s.camera)
  const controlsRef = useRef<any>(null)
  const cameras = useScene((s) => s.scene.cameras)

  // Set the initial camera position (only once on mount)
  useEffect(() => {
    camera.position.set(5, 4, 7)
    camera.lookAt(0, 0, 0)
  }, [camera])

  // Sync viewport camera when a ViewportCamera exists in the scene
  // This allows the Agent's set_view tool to control the viewport
  useEffect(() => {
    const vc = cameras.find((c) => c.name === 'ViewportCamera')
    if (!vc) return
    const target = new THREE.Vector3(vc.target[0], vc.target[1], vc.target[2])
    camera.position.set(vc.position[0], vc.position[1], vc.position[2])
    camera.lookAt(target)
    if (controlsRef.current) {
      controlsRef.current.target.copy(target)
      controlsRef.current.update()
    }
  }, [cameras, camera])

  return (
    <OrbitControls
      ref={controlsRef}
      makeDefault
      enableDamping
      dampingFactor={0.08}
      minDistance={2}
      maxDistance={40}
      maxPolarAngle={Math.PI / 2 + 0.2}
      target={[0, 0.5, 0]}
      autoRotate={autoRotate}
      autoRotateSpeed={0.8}
    />
  )
}
