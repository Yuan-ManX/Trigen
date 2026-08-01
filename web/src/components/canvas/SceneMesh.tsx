// Single mesh object rendering: maps R3F geometry based on geometry.type, handles selection highlight
// Includes optional TransformControls gizmo for direct viewport manipulation.
// When an object carries an animation descriptor, a useFrame hook overrides
// its transform every frame from the shared playback clock.
import { Edges, TransformControls } from '@react-three/drei'
import { memo, useMemo, useState } from 'react'
import { useFrame, type ThreeEvent } from '@react-three/fiber'
import * as THREE from 'three'
import { useEditor } from '../../store/useEditor'
import { usePlayback } from '../../store/usePlayback'
import { useScene } from '../../store/useScene'
import type { Geometry, ObjectAnimation, SceneObject, Vec3 } from '../../types'

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

interface AnimTransform {
  position: [number, number, number]
  rotation: [number, number, number]
  scale: [number, number, number]
}

/**
 * Solve an object's animated transform for a given absolute time.
 * Returns position / rotation / scale to apply imperatively each frame.
 * When the descriptor is missing or the type is unknown, the base transform
 * is returned unchanged so the mesh stays at its authored pose.
 */
function solveAnimation(
  anim: ObjectAnimation,
  time: number,
  basePos: Vec3,
  baseRot: Vec3,
  baseScale: Vec3,
): AnimTransform {
  const dur = Math.max(0.001, anim.duration)
  const phase = anim.loop ? (time % dur) / dur : Math.min(1, time / dur)

  switch (anim.type) {
    case 'orbit': {
      const center = anim.center ?? [0, 0, 0]
      const radius = anim.radius ?? 3
      const height = anim.height ?? basePos[1]
      const axis = anim.axis ?? 'y'
      const angle = phase * Math.PI * 2
      let pos: [number, number, number]
      if (axis === 'y') {
        pos = [center[0] + Math.cos(angle) * radius, height, center[2] + Math.sin(angle) * radius]
      } else if (axis === 'x') {
        pos = [center[0], center[1] + Math.cos(angle) * radius, center[2] + Math.sin(angle) * radius]
      } else {
        pos = [center[0] + Math.cos(angle) * radius, center[1] + Math.sin(angle) * radius, center[2]]
      }
      const rotation: [number, number, number] = anim.face_center && axis === 'y'
        ? [0, -angle + Math.PI / 2, 0]
        : [baseRot[0], baseRot[1], baseRot[2]]
      return { position: pos, rotation, scale: [baseScale[0], baseScale[1], baseScale[2]] }
    }
    case 'wave': {
      const amp = anim.amplitude ?? 1
      const freq = anim.frequency ?? 0.5
      const y = Math.sin(time * Math.PI * 2 * freq) * amp
      return {
        position: [basePos[0], basePos[1] + y, basePos[2]],
        rotation: [baseRot[0], baseRot[1], baseRot[2]],
        scale: [baseScale[0], baseScale[1], baseScale[2]],
      }
    }
    case 'bounce': {
      const height = anim.height ?? 1.5
      const bounces = anim.bounces ?? 3
      const b = Math.abs(Math.sin(phase * Math.PI * bounces))
      const y = b * height
      let scale: [number, number, number] = [baseScale[0], baseScale[1], baseScale[2]]
      if (anim.squash) {
        // Compress Y and expand XZ near the ground (b small)
        const squashAmt = (1 - b) * 0.15
        scale = [baseScale[0] * (1 + squashAmt), baseScale[1] * (1 - squashAmt), baseScale[2] * (1 + squashAmt)]
      }
      return {
        position: [basePos[0], basePos[1] + y, basePos[2]],
        rotation: [baseRot[0], baseRot[1], baseRot[2]],
        scale,
      }
    }
    case 'keyframe': {
      const kfs = anim.keyframes ?? []
      if (kfs.length === 0) return { position: basePos, rotation: baseRot, scale: baseScale }
      const t = phase
      let a = kfs[0]
      let bKf = kfs[kfs.length - 1]
      for (let i = 0; i < kfs.length - 1; i++) {
        if (t >= kfs[i].t && t <= kfs[i + 1].t) {
          a = kfs[i]
          bKf = kfs[i + 1]
          break
        }
      }
      const span = bKf.t - a.t || 1
      const lt = Math.max(0, Math.min(1, (t - a.t) / span))
      const easing = anim.easing ?? 'linear'
      let eased = lt
      if (easing === 'easeIn') eased = lt * lt
      else if (easing === 'easeOut') eased = 1 - (1 - lt) * (1 - lt)
      else if (easing === 'easeInOut') eased = lt < 0.5 ? 2 * lt * lt : 1 - Math.pow(-2 * lt + 2, 2) / 2
      const lerpN = (x?: number, y?: number) => (x !== undefined && y !== undefined ? x + (y - x) * eased : x ?? y ?? 0)
      const lerp3 = (x?: Vec3, y?: Vec3): [number, number, number] => [
        lerpN(x?.[0], y?.[0]),
        lerpN(x?.[1], y?.[1]),
        lerpN(x?.[2], y?.[2]),
      ]
      return {
        position: lerp3(a.position, bKf.position),
        rotation: lerp3(a.rotation, bKf.rotation),
        scale: lerp3(a.scale, bKf.scale),
      }
    }
    default:
      return { position: basePos, rotation: baseRot, scale: baseScale }
  }
}

function SceneMeshBase({ object, editMode = true, transformMode = 'translate' }: SceneMeshProps) {
  const selectedId = useScene((s) => s.selectedId)
  const selectedIds = useScene((s) => s.selectedIds)
  const select = useScene((s) => s.select)
  const updateTransform = useScene((s) => s.updateTransform)
  const currentTime = usePlayback((s) => s.currentTime)
  const gridSnapEnabled = useEditor((s) => s.gridSnapEnabled)
  const snapIncrement = useEditor((s) => s.snapIncrement)
  // Use callback ref so re-render fires when mesh mounts
  const [meshObj, setMeshObj] = useState<THREE.Mesh | null>(null)

  // Apply the animation descriptor every frame so orbit / wave / bounce /
  // keyframe motions stay in sync with the shared playback playhead.
  useFrame(() => {
    if (!meshObj || !object.animation) return
    const solved = solveAnimation(
      object.animation,
      currentTime,
      object.transform.position,
      object.transform.rotation,
      object.transform.scale,
    )
    meshObj.position.set(solved.position[0], solved.position[1], solved.position[2])
    meshObj.rotation.set(solved.rotation[0], solved.rotation[1], solved.rotation[2])
    meshObj.scale.set(solved.scale[0], solved.scale[1], solved.scale[2])
  })

  const isSelected = selectedIds.includes(object.id)
  // Gizmo attaches to the primary (last-clicked) selection only, so multi-select
  // stays inspectable without stacking multiple transform handles.
  const isPrimary = selectedId === object.id
  const mat = object.material
  const transparent = mat.opacity < 1

  const handleClick = (e: ThreeEvent<MouseEvent>) => {
    e.stopPropagation()
    if (object.locked) return
    // Shift/Meta click toggles membership in the multi-selection
    const additive = e.shiftKey || e.metaKey || e.ctrlKey
    select(object.id, additive)
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

  // Disable the gizmo for animated objects: the playback loop owns their
  // transform, so manual dragging would immediately be overwritten.
  const showGizmo = isPrimary && isSelected && editMode && meshObj !== null && !object.animation
  // Secondary selections render in a warmer accent so the user can tell the
  // primary gizmo target apart from the rest of the multi-selection.
  const edgeColor = isPrimary ? '#00F0FF' : '#FFB800'

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
          <Edges threshold={15} color={edgeColor} renderOrder={2} scale={1.02} />
        )}
      </mesh>
      {showGizmo && meshObj && (
        <TransformControls
          object={meshObj}
          mode={transformMode}
          onObjectChange={() => {
            if (!meshObj) return
            let px = meshObj.position.x
            let py = meshObj.position.y
            let pz = meshObj.position.z
            let rx = meshObj.rotation.x
            let ry = meshObj.rotation.y
            let rz = meshObj.rotation.z
            let sx = meshObj.scale.x
            let sy = meshObj.scale.y
            let sz = meshObj.scale.z
            if (gridSnapEnabled) {
              const inc = snapIncrement > 0 ? snapIncrement : 0.5
              const snap = (v: number, s: number) => Math.round(v / s) * s
              px = snap(px, inc)
              py = snap(py, inc)
              pz = snap(pz, inc)
              // Rotation snaps to 15° steps in radians
              const rotInc = (15 * Math.PI) / 180
              rx = snap(rx, rotInc)
              ry = snap(ry, rotInc)
              rz = snap(rz, rotInc)
              // Scale snaps to 0.1 steps (floored to a positive minimum)
              const scaleInc = 0.1
              sx = Math.max(0.01, snap(sx, scaleInc))
              sy = Math.max(0.01, snap(sy, scaleInc))
              sz = Math.max(0.01, snap(sz, scaleInc))
              // Write the snapped values back to the mesh so the gizmo
              // visually hops to the grid point during the drag.
              meshObj.position.set(px, py, pz)
              meshObj.rotation.set(rx, ry, rz)
              meshObj.scale.set(sx, sy, sz)
            }
            updateTransform(object.id, {
              position: [px, py, pz] as Vec3,
              rotation: [rx, ry, rz] as Vec3,
              scale: [sx, sy, sz] as Vec3,
            })
          }}
        />
      )}
    </>
  )
}

export const SceneMesh = memo(SceneMeshBase)
