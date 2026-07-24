// 光源渲染：根据 type 映射 ambientLight/directionalLight/pointLight/spotLight
// Light rendering: maps ambientLight/directionalLight/pointLight/spotLight based on type
import { useEffect, useRef } from 'react'
import type { Group } from 'three'
import type { LightObject } from '../../types'

interface SceneLightProps {
  light: LightObject
}

export function SceneLight({ light }: SceneLightProps) {
  const groupRef = useRef<Group>(null)

  // 将光源 target 指向 group 内的占位对象，避免共用默认 target
  // Point the light target to a placeholder object inside the group to avoid sharing the default target
  useEffect(() => {
    const g = groupRef.current
    if (!g) return
    const dirOrSpot = g.children.find(
      (c) => c.type === 'DirectionalLight' || c.type === 'SpotLight',
    ) as
      | (import('three').DirectionalLight & { target?: import('three').Object3D })
      | (import('three').SpotLight & { target?: import('three').Object3D })
      | undefined
    const targetObj = g.children.find((c) => c.userData?.isTarget)
    if (dirOrSpot && targetObj) {
      dirOrSpot.target = targetObj as import('three').Object3D
    }
  }, [light.type])

  const common = {
    color: light.color,
    intensity: light.intensity,
  }

  return (
    <group ref={groupRef}>
      {light.type === 'ambient' && <ambientLight {...common} />}
      {light.type === 'directional' && (
        <directionalLight
          {...common}
          position={light.position}
          castShadow={light.cast_shadow}
          shadow-mapSize-width={1024}
          shadow-mapSize-height={1024}
          shadow-camera-near={0.5}
          shadow-camera-far={50}
          shadow-camera-left={-10}
          shadow-camera-right={10}
          shadow-camera-top={10}
          shadow-camera-bottom={-10}
        />
      )}
      {light.type === 'point' && (
        <pointLight
          {...common}
          position={light.position}
          castShadow={light.cast_shadow}
          distance={0}
          decay={2}
        />
      )}
      {light.type === 'spot' && (
        <spotLight
          {...common}
          position={light.position}
          angle={Math.PI / 6}
          penumbra={0.2}
          castShadow={light.cast_shadow}
          shadow-mapSize-width={1024}
          shadow-mapSize-height={1024}
        />
      )}
      {/* 方向光/聚光灯的目标占位对象 */}
      {/* Target placeholder object for directional/spot lights */}
      {(light.type === 'directional' || light.type === 'spot') && (
        <object3D
          position={light.target ?? [0, 0, 0]}
          userData={{ isTarget: true }}
        />
      )}
    </group>
  )
}
