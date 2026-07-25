// Single mesh object rendering: maps R3F geometry based on geometry.type, handles selection highlight
// Includes optional TransformControls gizmo for direct viewport manipulation
import { Edges, TransformControls } from '@react-three/drei'
import { memo, useMemo, useState } from 'react'
import type { ThreeEvent } from '@react-three/fiber'
import * as THREE from 'three'
import { useScene } from '../../store/useScene'
import type { Geometry, SceneObject, Vec3 } from '../../types'

export type TransformMode = 'translate' | 'rotate' | 'scale'

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
    case 'ring':
      return (
        <ringGeometry args={[num('innerRadius', 0.4), num('outerRadius', 0.7), int('thetaSegments', 24)]} />
      )
    case 'capsule':
      return (
        <capsuleGeometry args={[num('radius', 0.4), num('length', 0.8), int('capSegments', 12), int('radialSegments', 16)]} />
      )
    case 'tube':
      return <TubeGeometryRenderer params={p} num={num} int={int} />
    default:
      return <boxGeometry args={[1, 1, 1]} />
  }
}

/** Tube geometry requires a Curve object; build a gentle curved path */
function TubeGeometryRenderer({
  params: _p,
  num,
  int,
}: {
  params: Record<string, number | number[]>
  num: (k: string, fallback: number) => number
  int: (k: string, fallback: number) => number
}) {
  const curve = useMemo(
    () =>
      new THREE.CatmullRomCurve3([
        new THREE.Vector3(-1, 0, 0),
        new THREE.Vector3(-0.3, 0.5, 0.3),
        new THREE.Vector3(0.3, -0.3, -0.3),
        new THREE.Vector3(1, 0, 0),
      ]),
    [],
  )
  return (
    <tubeGeometry args={[curve, int('tubularSegments', 64), num('radius', 0.3), int('radialSegments', 8), false]} />
  )
}

interface SceneMeshProps {
  object: SceneObject
  editMode?: boolean
  transformMode?: TransformMode
}

function SceneMeshBase({ object, editMode = true, transformMode = 'translate' }: SceneMeshProps) {
  const selectedId = useScene((s) => s.selectedId)
  const select = useScene((s) => s.select)
  const updateTransform = useScene((s) => s.updateTransform)
  // Use callback ref so re-render fires when mesh mounts
  const [meshObj, setMeshObj] = useState<THREE.Mesh | null>(null)

  const isSelected = selectedId === object.id
  const mat = object.material
  const transparent = mat.opacity < 1

  const handleClick = (e: ThreeEvent<MouseEvent>) => {
    e.stopPropagation()
    if (!object.locked) select(object.id)
  }

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

  const showGizmo = isSelected && editMode && meshObj !== null

  return (
    <>
      <mesh
        ref={setMeshObj}
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
          flatShading={mat.flat_shading ?? false}
          side={mat.side === 'double' ? THREE.DoubleSide : mat.side === 'back' ? THREE.BackSide : THREE.FrontSide}
        />
        {isSelected && (
          <Edges threshold={15} color="#00F0FF" renderOrder={2} scale={1.02} />
        )}
      </mesh>
      {showGizmo && meshObj && (
        <TransformControls
          object={meshObj}
          mode={transformMode}
          onObjectChange={() => {
            if (!meshObj) return
            updateTransform(object.id, {
              position: [meshObj.position.x, meshObj.position.y, meshObj.position.z] as Vec3,
              rotation: [meshObj.rotation.x, meshObj.rotation.y, meshObj.rotation.z] as Vec3,
              scale: [meshObj.scale.x, meshObj.scale.y, meshObj.scale.z] as Vec3,
            })
          }}
        />
      )}
    </>
  )
}

export const SceneMesh = memo(SceneMeshBase)
