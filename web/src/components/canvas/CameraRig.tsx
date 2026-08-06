// Camera control: OrbitControls + sync with scene cameras set by Agent.
// When a camera animation descriptor is present (and we are in run mode),
// the controls are disabled and the camera is driven along the animation path.
// When a cinematic storyboard is present and playing, the camera instead
// travels through the ordered shots (dolly/pan between consecutive poses).
import { OrbitControls } from '@react-three/drei'
import { useFrame, useThree } from '@react-three/fiber'
import { useEffect, useRef } from 'react'
import * as THREE from 'three'
import { useScene } from '../../store/useScene'
import type { CameraAnimation, Storyboard } from '../../types'

interface CameraRigProps {
  autoRotate?: boolean
  /** Optional animation descriptor; when set, the viewport camera plays it. */
  animation?: CameraAnimation | null
  /** Optional cinematic storyboard; when present and playing, drives the
   *  camera through its ordered shots instead of OrbitControls. */
  storyboard?: Storyboard | null
}

/** Ease a progress value [0,1] into [0,1] using a named easing curve. */
function ease(progress: number, curve: string): number {
  const t = Math.max(0, Math.min(1, progress))
  switch (curve) {
    case 'easeIn':
      return t * t
    case 'easeOut':
      return 1 - (1 - t) * (1 - t)
    case 'easeInOut':
      return t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2
    case 'linear':
    default:
      return t
  }
}

export function CameraRig({ autoRotate = false, animation = null, storyboard = null }: CameraRigProps) {
  const camera = useThree((s) => s.camera)
  const controlsRef = useRef<any>(null)
  const cameras = useScene((s) => s.scene.cameras)
  const animClock = useRef(0)
  // Per-shot playback clock for the cinematic storyboard.
  const shotClock = useRef(0)

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

  // Disable OrbitControls while an animation or storyboard is playing so
  // manual input does not fight the scripted camera motion.
  const playing = !!animation || !!storyboard?.playing
  useEffect(() => {
    if (controlsRef.current) {
      controlsRef.current.enabled = !playing
    }
  }, [playing])

  useFrame((_, delta) => {
    // Cinematic storyboard playback takes priority over single-camera
    // animation: it is an explicit directional sequence.
    if (storyboard && storyboard.playing && storyboard.shots.length > 0) {
      const shots = storyboard.shots
      const speed = Math.max(0.25, storyboard.speed ?? 1)
      const idx = Math.max(0, Math.min(shots.length - 1, storyboard.index ?? 0))
      const shot = shots[idx]
      const next = shots[(idx + 1) % shots.length]
      const duration = Math.max(0.1, shot.duration ?? 3) / speed

      shotClock.current += delta
      let t = shotClock.current / duration
      if (t >= 1) {
        t = 0
        shotClock.current = 0
        // Advance the sequence index so the panel highlights the active shot.
        const nextIdx = (idx + 1) % shots.length
        if (nextIdx === 0 && storyboard.loop === false) {
          // Non-looping: stop at the final shot.
          return
        }
        storyboard.index = nextIdx
      }
      const eased = ease(t, shot.easing)

      const fromPos = new THREE.Vector3(...shot.position)
      const fromTarget = new THREE.Vector3(...shot.target)
      const toPos = new THREE.Vector3(...next.position)
      const toTarget = new THREE.Vector3(...next.target)

      camera.position.lerpVectors(fromPos, toPos, eased)
      camera.lookAt(fromTarget.clone().lerp(toTarget, eased))
      // Only perspective cameras carry a fov; interpolate it for a subtle
      // dolly zoom between shots.
      if (camera instanceof THREE.PerspectiveCamera && shot.fov) {
        camera.fov = THREE.MathUtils.lerp(shot.fov, next.fov ?? shot.fov, eased)
        camera.updateProjectionMatrix()
      }
      return
    }

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
