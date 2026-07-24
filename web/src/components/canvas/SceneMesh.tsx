// 单个网格对象渲染：根据 geometry.type 映射 R3F 几何体，处理选中高亮
// Single mesh object rendering: maps R3F geometry based on geometry.type, handles selection highlight
import { Edges } from '@react-three/drei'
import { memo, useMemo } from 'react'
import type { ThreeEvent } from '@react-three/fiber'
import { useScene } from '../../store/useScene'
import type { Geometry, SceneObject } from '../../types'

/** 根据几何体类型与参数构造对应的 R3F 几何组件 */
/** Build the corresponding R3F geometry component based on geometry type and parameters */
function GeometryRenderer({ geometry }: { geometry: Geometry }) {
  const p = geometry.params
  const num = (k: string, fallback: number): number => {
    const v = p[k]
    return typeof v === 'number' ? v : fallback
  }
  const int = (k: string, fallback: number): number => {
    const v = p[k]
    return typeof v === 'number' ? Math.max(1, Math.round(v)) : fallback
  }

  switch (geometry.type) {
    case 'box':
      return (
        <boxGeometry
          args={[num('width', 1), num('height', 1), num('depth', 1), int('widthSegments', 1), int('heightSegments', 1), int('depthSegments', 1)]}
        />
      )
    case 'sphere':
      return (
        <sphereGeometry args={[num('radius', 0.6), int('widthSegments', 32), int('heightSegments', 16)]} />
      )
    case 'cylinder':
      return (
        <cylinderGeometry
          args={[num('radiusTop', 0.5), num('radiusBottom', 0.5), num('height', 1.2), int('radialSegments', 32)]}
        />
      )
    case 'cone':
      return <coneGeometry args={[num('radius', 0.6), num('height', 1.2), int('radialSegments', 32)]} />
    case 'torus':
      return (
        <torusGeometry args={[num('radius', 0.6), num('tube', 0.2), int('radialSegments', 12), int('tubularSegments', 48)]} />
      )
    case 'plane':
      return (
        <planeGeometry args={[num('width', 2), num('height', 2), int('widthSegments', 1), int('heightSegments', 1)]} />
      )
    case 'torusKnot':
      return (
        <torusKnotGeometry
          args={[num('radius', 0.6), num('tube', 0.2), int('tubularSegments', 64), int('radialSegments', 8), int('p', 2), int('q', 3)]}
        />
      )
    case 'dodecahedron':
      return <dodecahedronGeometry args={[num('radius', 0.6), int('detail', 0)]} />
    case 'icosahedron':
      return <icosahedronGeometry args={[num('radius', 0.6), int('detail', 0)]} />
    case 'octahedron':
      return <octahedronGeometry args={[num('radius', 0.6), int('detail', 0)]} />
    case 'tetrahedron':
      return <tetrahedronGeometry args={[num('radius', 0.6), int('detail', 0)]} />
    default:
      return <boxGeometry args={[1, 1, 1]} />
  }
}

interface SceneMeshProps {
  object: SceneObject
}

function SceneMeshBase({ object }: SceneMeshProps) {
  const selectedId = useScene((s) => s.selectedId)
  const select = useScene((s) => s.select)

  const isSelected = selectedId === object.id
  const mat = object.material
  const transparent = mat.opacity < 1

  const handleClick = (e: ThreeEvent<MouseEvent>) => {
    e.stopPropagation()
    if (!object.locked) select(object.id)
  }

  // 缓存旋转/缩放/位置，避免每次都创建新数组
  // Cache rotation/scale/position to avoid creating new arrays every time
  const transform = useMemo(
    () => ({
      position: object.transform.position,
      rotation: object.transform.rotation,
      scale: object.transform.scale,
    }),
    [object.transform.position, object.transform.rotation, object.transform.scale],
  )

  if (!object.visible) return null

  return (
    <mesh
      position={transform.position}
      rotation={transform.rotation}
      scale={transform.scale}
      onClick={handleClick}
      castShadow
      receiveShadow
      userData={{ id: object.id, name: object.name }}
    >
      <GeometryRenderer geometry={object.geometry} />
      <meshStandardMaterial
        color={mat.color}
        metalness={mat.metalness}
        roughness={mat.roughness}
        opacity={mat.opacity}
        transparent={transparent}
        wireframe={mat.wireframe}
        emissive={mat.emissive}
        emissiveIntensity={mat.emissive_intensity}
      />
      {isSelected && (
        <Edges threshold={15} color="#00F0FF" renderOrder={2} scale={1.02} />
      )}
    </mesh>
  )
}

export const SceneMesh = memo(SceneMeshBase)
