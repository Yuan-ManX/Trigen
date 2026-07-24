// 相机控制：OrbitControls + 初始视角
// Camera control: OrbitControls + initial view
import { OrbitControls } from '@react-three/drei'
import { useThree } from '@react-three/fiber'
import { useEffect } from 'react'

export function CameraRig() {
  const camera = useThree((s) => s.camera)

  // 设置初始相机位置（仅一次）
  // Set the initial camera position (only once)
  useEffect(() => {
    camera.position.set(5, 4, 7)
    camera.lookAt(0, 0, 0)
  }, [camera])

  return (
    <OrbitControls
      makeDefault
      enableDamping
      dampingFactor={0.08}
      minDistance={2}
      maxDistance={40}
      maxPolarAngle={Math.PI / 2 + 0.2}
      target={[0, 0.5, 0]}
    />
  )
}
