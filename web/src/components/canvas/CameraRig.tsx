// Camera control: OrbitControls + sync with scene cameras set by Agent.
// When a camera animation descriptor is present (and we are in run mode),
// the controls are disabled and the camera is driven along the animation path.
import { OrbitControls } from '@react-three/drei'
import { useFrame, useThree } from '@react-three/fiber'
import { useEffect, useRef } from 'react'
import * as THREE from 'three'
import { useScene } from '../../store/useScene'
import type { CameraAnimation } from '../../types'

interface CameraRigProps {
  autoRotate?: boolean
  /** Optional animation descriptor; when set, the viewport camera plays it. */
  animation?: CameraAnimation | null
}

export function CameraRig({ autoRotate = false, animation = null }: CameraRigProps) {
  const camera = useThree((s) => s.camera)
  const controlsRef = useRef<any>(null)
  const cameras = useScene((s) => s.scene.cameras)
  const animClock = useRef(0)

  // Set the initial camera position (only once on mount)
  useEffect(() => {
    camera.position.set(5, 4, 7)
    camera.lookAt(0, 0, 0)
  }, [camera])

  // Sync viewport camera when a ViewportCamera exists in the scene
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

  // Disable OrbitControls while an animation is playing so manual input
  // does not fight the scripted camera motion.
  const playing = !!animation
  useEffect(() => {
    if (controlsRef.current) {
      controlsRef.current.enabled = !playing
    }
  }, [playing])

  useFrame((_, delta) => {
    if (!animation) return
    const duration = Math.max(0.1, animation.duration ?? 6)
    animClock.current += delta
    let t = animClock.current / duration
    if (animation.loop !== false) {
      t = t % 1
    } else if (t > 1) {
      t = 1
    }

    const target = new THREE.Vector3(
      animation.target?.[0] ?? 0,
      animation.target?.[1] ?? 0,
      animation.target?.[2] ?? 0,
    )

    if (animation.type === 'orbit') {
      const radius = Math.max(0.01, animation.radius ?? 5)
      const height = animation.height ?? target.y
      const angle = t * Math.PI * 2
      camera.position.set(
        target.x + radius * Math.cos(angle),
        height,
        target.z + radius * Math.sin(angle),
      )
      camera.lookAt(target)
    } else if (animation.type === 'flythrough' && animation.points && animation.points.length >= 2) {
      const pts = animation.points
      const seg = (pts.length - 1) * t
      const i = Math.min(pts.length - 2, Math.floor(seg))
      const f = seg - i
      const a = new THREE.Vector3(pts[i][0], pts[i][1], pts[i][2])
      const b = new THREE.Vector3(pts[i + 1][0], pts[i + 1][1], pts[i + 1][2])
      const pos = a.lerp(b, f)
      camera.position.copy(pos)
      camera.lookAt(target)
    }
  })

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
      autoRotate={autoRotate && !playing}
      autoRotateSpeed={0.8}
    />
  )
}
