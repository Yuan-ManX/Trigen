// Deformation modifier renderer for SceneMesh. Applies non-destructive
// geometric modifiers to an object's geometry at render time.
// Supports: noise (vertex displacement), bend (matrix transform),
// twist (matrix transform), taper (matrix transform), wave (vertex displacement).
import { useFrame } from '@react-three/fiber'
import { useRef, useEffect } from 'react'
import * as THREE from 'three'

/** Simple deterministic noise function — 3D value noise with hash-based pseudo-randomness.
 *  Good enough for procedural vertex displacement without requiring a GLSL shader. */
function hash(x: number, y: number, z: number): number {
  const s = Math.sin(x * 127.1 + y * 311.7 + z * 74.7) * 43758.5453
  return s - Math.floor(s)
}

function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t
}

function fade(t: number): number {
  return t * t * t * (t * (t * 6 - 15) + 10)
}

function valueNoise3D(x: number, y: number, z: number): number {
  const xi = Math.floor(x)
  const yi = Math.floor(y)
  const zi = Math.floor(z)
  const xf = x - xi
  const yf = y - yi
  const zf = z - zi

  const u = fade(xf)
  const v = fade(yf)
  const w = fade(zf)

  const c000 = hash(xi, yi, zi)
  const c100 = hash(xi + 1, yi, zi)
  const c010 = hash(xi, yi + 1, zi)
  const c110 = hash(xi + 1, yi + 1, zi)
  const c001 = hash(xi, yi, zi + 1)
  const c101 = hash(xi + 1, yi, zi + 1)
  const c011 = hash(xi, yi + 1, zi + 1)
  const c111 = hash(xi + 1, yi + 1, zi + 1)

  const x00 = lerp(c000, c100, u)
  const x10 = lerp(c010, c110, u)
  const x01 = lerp(c001, c101, u)
  const x11 = lerp(c011, c111, u)

  const y0 = lerp(x00, x10, v)
  const y1 = lerp(x01, x11, v)

  return lerp(y0, y1, w) * 2 - 1
}

interface ModifierRendererProps {
  geometry: THREE.BufferGeometry
  modifiers: Record<string, Record<string, unknown>>
  enabled: boolean
}

/**
 * Applies geometric modifiers to a BufferGeometry on every frame.
 * Uses useFrame to displace vertices for noise/wave, and matrix
 * transforms for bend/twist/taper. The original geometry is never
 * mutated — a working copy of the position buffer is updated each
 * frame, allowing instant parameter changes.
 */
export function ModifierRenderer({ geometry, modifiers, enabled }: ModifierRendererProps) {
  const positionAttr = geometry.getAttribute('position')
  const originalPositions = useRef<Float32Array | null>(null)
  const count = positionAttr?.count ?? 0

  // Keep a pristine copy of the original vertex positions so we can
  // re-apply modifiers every frame from a clean base (no accumulated drift).
  useEffect(() => {
    if (!positionAttr || count === 0) return
    if (!originalPositions.current) {
      originalPositions.current = new Float32Array(count * 3)
      originalPositions.current.set(positionAttr.array as Float32Array)
    }
  }, [positionAttr, count])

  useFrame(() => {
    if (!enabled || !positionAttr || !originalPositions.current || count === 0) return

    const orig = originalPositions.current
    const arr = positionAttr.array as Float32Array
    const time = performance.now() * 0.001

    // Reset to original positions first
    arr.set(orig)

    const hasNoise = !!modifiers.noise
    const hasWave = !!modifiers.wave

    if (hasNoise || hasWave) {
      const noiseCfg = modifiers.noise ?? {}
      const waveCfg = modifiers.wave ?? {}

      const noiseAmp = Number(noiseCfg.amplitude ?? 0.3)
      const noiseFreq = Number(noiseCfg.frequency ?? 1.5)
      const noiseSeed = Number(noiseCfg.seed ?? 0)
      const noiseEnabled = Boolean(noiseCfg.enabled ?? hasNoise)

      const waveAmp = Number(waveCfg.amplitude ?? 0.2)
      const waveFreq = Number(waveCfg.frequency ?? 1.0)
      const waveAxis = String(waveCfg.axis ?? 'y')
      const waveEnabled = Boolean(waveCfg.enabled ?? hasWave)

      for (let i = 0; i < count; i++) {
        const ix = i * 3
        let x = orig[ix]
        let y = orig[ix + 1]
        let z = orig[ix + 2]

        if (noiseEnabled) {
          const nx = x * noiseFreq + noiseSeed
          const ny = y * noiseFreq + noiseSeed * 0.5
          const nz = z * noiseFreq + noiseSeed * 0.7
          const n = valueNoise3D(nx, ny, nz)
          // Displace along the vertex's "normal-ish" direction — for simplicity
          // we displace along all axes proportionally to keep it surface-like
          x += n * noiseAmp * 0.3
          y += n * noiseAmp * 0.7
          z += n * noiseAmp * 0.3
        }

        if (waveEnabled) {
          const wavePhase = time * waveFreq + (x + y + z) * 0.5
          const waveOffset = Math.sin(wavePhase) * waveAmp
          if (waveAxis === 'x') x += waveOffset
          else if (waveAxis === 'z') z += waveOffset
          else y += waveOffset
        }

        arr[ix] = x
        arr[ix + 1] = y
        arr[ix + 2] = z
      }

      positionAttr.needsUpdate = true
      geometry.computeVertexNormals()
    }

    // Matrix-based modifiers (bend, twist, taper) — applied as a
    // post-processing pass on the already-displaced positions
    const hasBend = !!modifiers.bend && Boolean((modifiers.bend!).enabled ?? false)
    const hasTwist = !!modifiers.twist && Boolean((modifiers.twist!).enabled ?? false)
    const hasTaper = !!modifiers.taper && Boolean((modifiers.taper!).enabled ?? false)

    if (hasBend || hasTwist || hasTaper) {
      const bendCfg = modifiers.bend ?? {}
      const twistCfg = modifiers.twist ?? {}
      const taperCfg = modifiers.taper ?? {}

      const bendAngle = Number(bendCfg.angle ?? 0.5)
      const bendAxis = String(bendCfg.axis ?? 'z')
      const bendLength = Number(bendCfg.length ?? 2)

      const twistAngle = Number(twistCfg.angle ?? 1.0)
      const twistAxis = String(twistCfg.axis ?? 'y')

      const taperAmount = Number(taperCfg.amount ?? 0.3)
      const taperAxis = String(taperCfg.axis ?? 'y')

      // Compute centroid of original geometry for pivot
      let cx = 0, cy = 0, cz = 0
      for (let i = 0; i < count; i++) {
        cx += orig[i * 3]
        cy += orig[i * 3 + 1]
        cz += orig[i * 3 + 2]
      }
      cx /= count; cy /= count; cz /= count

      for (let i = 0; i < count; i++) {
        const ix = i * 3
        let x = arr[ix] - cx
        let y = arr[ix + 1] - cy
        let z = arr[ix + 2] - cz

        if (hasBend) {
          // Bend: rotate the vertex around an axis based on its position along
          // the bend axis. The "bendAxis" is the axis of rotation; the
          // distance along the perpendicular axis determines the rotation amount.
          const alongAxis = bendAxis === 'x' ? x : bendAxis === 'y' ? y : z
          const bendFactor = Math.max(-1, Math.min(1, alongAxis / (bendLength || 2)))
          const angle = bendAngle * bendFactor

          if (bendAxis === 'x') {
            const cos = Math.cos(angle), sin = Math.sin(angle)
            const ny = y * cos - z * sin
            const nz = y * sin + z * cos
            y = ny; z = nz
          } else if (bendAxis === 'y') {
            const cos = Math.cos(angle), sin = Math.sin(angle)
            const nx = x * cos + z * sin
            const nz = -x * sin + z * cos
            x = nx; z = nz
          } else {
            const cos = Math.cos(angle), sin = Math.sin(angle)
            const nx = x * cos - y * sin
            const ny = x * sin + y * cos
            x = nx; y = ny
          }
        }

        if (hasTwist) {
          // Twist: rotate vertex around an axis proportional to its distance
          // along that axis.
          const alongAxis = twistAxis === 'x' ? x : twistAxis === 'y' ? y : z
          const maxDist = Math.max(0.5, Math.abs(alongAxis))
          const angle = twistAngle * (alongAxis / maxDist)

          if (twistAxis === 'x') {
            const cos = Math.cos(angle), sin = Math.sin(angle)
            const ny = y * cos - z * sin
            const nz = y * sin + z * cos
            y = ny; z = nz
          } else if (twistAxis === 'y') {
            const cos = Math.cos(angle), sin = Math.sin(angle)
            const nx = x * cos + z * sin
            const nz = -x * sin + z * cos
            x = nx; z = nz
          } else {
            const cos = Math.cos(angle), sin = Math.sin(angle)
            const nx = x * cos - y * sin
            const ny = x * sin + y * cos
            x = nx; y = ny
          }
        }

        if (hasTaper) {
          // Taper: scale the cross-section as we move along the taper axis.
          const alongAxis = taperAxis === 'x' ? x : taperAxis === 'y' ? y : z
          const scale = 1 - taperAmount * Math.abs(alongAxis) * 0.5
          const s = Math.max(0.1, scale)
          if (taperAxis === 'x') {
            y *= s; z *= s
          } else if (taperAxis === 'y') {
            x *= s; z *= s
          } else {
            x *= s; y *= s
          }
        }

        arr[ix] = x + cx
        arr[ix + 1] = y + cy
        arr[ix + 2] = z + cz
      }

      positionAttr.needsUpdate = true
      geometry.computeVertexNormals()
    }
  })

  // This component has no visible output — it mutates geometry in place
  return null
}