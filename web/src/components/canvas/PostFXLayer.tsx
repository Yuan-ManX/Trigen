// Post-processing effects layer for the R3F viewport. Reads
// scene.post_processing config and composes an EffectComposer pipeline
// with bloom, tone mapping, brightness/contrast, hue/saturation,
// vignette, film grain, DOF, and chromatic aberration.
import { EffectComposer, Bloom, ToneMapping, BrightnessContrast, HueSaturation, Vignette, Noise, DepthOfField, ChromaticAberration } from '@react-three/postprocessing'
import { useScene } from '../../store/useScene'

/**
 * Reads the scene's post_processing dict and builds the EffectComposer
 * pipeline dynamically. Each effect is enabled independently based on
 * the "enabled" flag in its config, with sensible defaults for missing
 * keys so individual effects can be toggled without re-specifying
 * every parameter.
 */
export function PostFXLayer() {
  const postFX = useScene((s) => s.scene.post_processing)

  // Early return if no post-processing is configured — avoids mounting
  // an empty composer that would still consume GPU resources.
  if (!postFX || Object.keys(postFX).length === 0) return null

  const bloomCfg = postFX.bloom ?? {}
  const tmCfg = postFX.tone_mapping ?? {}
  const cgCfg = postFX.color_grading ?? {}
  const vignetteCfg = postFX.vignette ?? {}
  const grainCfg = postFX.film_grain ?? {}
  const dofCfg = postFX.dof ?? {}
  const chromaticCfg = postFX.chromatic_aberration ?? {}

  const hasAnyEffect =
    (bloomCfg.enabled ?? false) ||
    (tmCfg.enabled ?? false) ||
    (cgCfg.enabled ?? false) ||
    (vignetteCfg.enabled ?? false) ||
    (grainCfg.enabled ?? false) ||
    (dofCfg.enabled ?? false) ||
    (chromaticCfg.enabled ?? false)

  if (!hasAnyEffect) return null

  // Build EffectComposer with all enabled effects
  return (
    <EffectComposer multisampling={0}>
      {(bloomCfg.enabled ?? false) && (
        <Bloom
          intensity={Number(bloomCfg.intensity ?? 1.2)}
          luminanceThreshold={Number(bloomCfg.threshold ?? 0.15)}
          luminanceSmoothing={Number(bloomCfg.smoothing ?? 0.9)}
          mipmapBlur={Boolean(bloomCfg.mipmapBlur ?? true)}
        />
      )}

      {(tmCfg.enabled ?? false) && (
        <ToneMapping mode={Number(tmCfg.mode ?? 4) as any} />
      )}

      {(cgCfg.enabled ?? false) && (
        <BrightnessContrast
          brightness={Number(cgCfg.brightness ?? 0)}
          contrast={Number(cgCfg.contrast ?? 1)}
        />
      )}

      {(cgCfg.enabled ?? false) && (
        <HueSaturation
          hue={Number(cgCfg.hue ?? 0)}
          saturation={Number(cgCfg.saturation ?? 0)}
        />
      )}

      {(dofCfg.enabled ?? false) && (
        <DepthOfField
          focusDistance={Number(dofCfg.focusDistance ?? 0)}
          focalLength={Number(dofCfg.focalLength ?? 0)}
          bokehScale={Number(dofCfg.bokehScale ?? 3)}
        />
      )}

      {(vignetteCfg.enabled ?? false) && (
        <Vignette
          offset={Number(vignetteCfg.offset ?? 0.3)}
          darkness={Number(vignetteCfg.darkness ?? 0.6)}
        />
      )}

      {(grainCfg.enabled ?? false) && (
        <Noise
          premultiply
          opacity={Number(grainCfg.opacity ?? 0.2)}
        />
      )}

      {(chromaticCfg.enabled ?? false) && (
        <ChromaticAberration
          offset={[Number(chromaticCfg.offsetX ?? 0.0008), Number(chromaticCfg.offsetY ?? 0.0008)] as any}
          radialModulation={Boolean(chromaticCfg.radialModulation ?? false)}
          modulationOffset={Number(chromaticCfg.modulationOffset ?? 0)}
        />
      )}
    </EffectComposer>
  )
}