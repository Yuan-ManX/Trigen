// Editor control state: transform mode, playback speed, grid snapping,
// render quality, active panel, viewport camera, viewport capture trigger,
// and transient measurement overlay state.
// Driven by Agent editor_* deltas dispatched from useChat, and also by local
// UI interactions (toolbar buttons). Lifted out of component-local state so
// the Agent can drive every editor function through the same store.
import { create } from 'zustand'
import type { Vec3 } from '../types'

export type TransformMode = 'translate' | 'rotate' | 'scale'
export type RenderQuality = 'low' | 'medium' | 'high'
export type PanelTab = 'layers' | 'outliner' | 'timeline' | 'properties' | 'scene'

export interface ViewportCameraState {
  position: Vec3
  target: Vec3
  /** Monotonic token; bumped on every set so consumers can react even if
   *  position/target are unchanged from a previous request. */
  token: number
  smooth: boolean
}

/** Transient measurement overlay descriptor. Rendered as a line between
 *  two world positions with a distance label at the midpoint. */
export interface MeasurementOverlayState {
  aPosition: Vec3
  bPosition: Vec3
  distance: number
  label: string
  /** Monotonic token so repeated identical measurements still trigger a
   *  re-render / re-mount of the overlay. */
  token: number
}

interface EditorState {
  transformMode: TransformMode
  gridSnapEnabled: boolean
  snapIncrement: number
  renderQuality: RenderQuality
  activePanel: PanelTab
  viewportCamera: ViewportCameraState | null
  /** Incremented each time a viewport capture is requested; the canvas
   *  component watches this counter and renders a PNG download. */
  captureCounter: number
  captureFilename: string
  /** Active measurement overlay, or null when cleared. Set by the
   *  editor_measure delta from measure_distance tool execution. */
  measurement: MeasurementOverlayState | null

  setTransformMode: (m: TransformMode) => void
  setGridSnap: (enabled: boolean, increment?: number) => void
  setRenderQuality: (q: RenderQuality) => void
  setActivePanel: (p: PanelTab) => void
  setViewportCamera: (position: Vec3, target: Vec3, smooth?: boolean) => void
  requestCapture: (filename?: string) => void
  setMeasurement: (m: Omit<MeasurementOverlayState, 'token'> | null) => void
  clearMeasurement: () => void
}

export const useEditor = create<EditorState>((set) => ({
  transformMode: 'translate',
  gridSnapEnabled: false,
  snapIncrement: 0.5,
  renderQuality: 'high',
  activePanel: 'layers',
  viewportCamera: null,
  captureCounter: 0,
  captureFilename: 'viewport',
  measurement: null,

  setTransformMode: (m) => set({ transformMode: m }),
  setGridSnap: (enabled, increment) =>
    set((state) => ({
      gridSnapEnabled: enabled,
      snapIncrement: increment ?? state.snapIncrement,
    })),
  setRenderQuality: (q) => set({ renderQuality: q }),
  setActivePanel: (p) => set({ activePanel: p }),
  setViewportCamera: (position, target, smooth = true) =>
    set((state) => ({
      viewportCamera: { position, target, smooth, token: (state.viewportCamera?.token ?? 0) + 1 },
    })),
  requestCapture: (filename) =>
    set((state) => ({
      captureCounter: state.captureCounter + 1,
      captureFilename: filename ?? `viewport_${Date.now()}`,
    })),
  setMeasurement: (m) =>
    set((state) => ({
      measurement: m
        ? { ...m, token: (state.measurement?.token ?? 0) + 1 }
        : null,
    })),
  clearMeasurement: () => set({ measurement: null }),
}))
