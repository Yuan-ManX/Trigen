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
export type PanelTab = 'layers' | 'outliner' | 'timeline' | 'properties' | 'scene' | 'skills' | 'tools' | 'memory' | 'activity' | 'checkpoints' | 'storyboard' | 'critique' | 'constraints' | 'layerPanel' | 'nodegraph' | 'toolPresets'

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

/** Clipping plane descriptor. When enabled, the canvas clips the scene along
 *  the given axis at the given position. Driven by the
 *  editor_set_clipping_plane delta from set_clipping_plane tool execution. */
export interface ClippingPlaneState {
  enabled: boolean
  axis: 'x' | 'y' | 'z'
  position: number
  invert: boolean
  /** Monotonic token so repeated identical states still trigger a re-render. */
  token: number
}

/** Viewport projection mode — perspective (depth-foreshortened) or
 *  orthographic (parallel, no distortion). Driven by the editor_set_projection
 *  delta from set_viewport_projection tool execution. */
export type ViewportProjection = 'perspective' | 'orthographic'

/** Editor authoring mode — edit (gizmos, snapping) or run (playback preview).
 *  Driven by the editor_set_mode delta from set_editor_mode tool execution. */
export type EditorMode = 'edit' | 'run'

/** Viewport shading mode — controls how objects are rendered in the viewport.
 *  Driven by the editor_set_viewport_shading delta from set_viewport_shading
 *  tool execution, and also by the local W keyboard shortcut. */
export type ViewportShading = 'wireframe' | 'solid' | 'material' | 'rendered'

/** Cinematic camera flythrough descriptor. Driven by the
 *  editor_camera_flythrough delta from camera_flythrough tool execution.
 *  The canvas component watches the token to (re)start the preview. */
export interface CameraFlythroughState {
  waypoints: Array<{
    position: Vec3
    target: Vec3
    dwell: number
    speed: number
  }>
  loop: boolean
  smooth: boolean
  speed: number
  duration: number
  distance: number
  /** Monotonic token so repeated identical descriptors still trigger a
   *  re-render / replay of the flythrough. */
  token: number
}

/** Radial context-menu descriptor. Triggered by right-clicking a mesh in
 *  the viewport; the canvas renders a pie-menu overlay at the cursor. The
 *  token re-triggers the open animation even for repeated clicks on the
 *  same object. */
export interface RadialMenuState {
  objectId: string
  /** Viewport-space origin (px) where the menu anchors. */
  x: number
  y: number
  token: number
}

/** Turntable orbit descriptor. Driven by the editor_orbit_viewport delta
 *  from the orbit_viewport tool execution. The canvas component watches
 *  the token to (re)start the turntable orbit; when ``active`` is false
 *  the camera rig cancels any active orbit and returns to free look. */
export interface OrbitViewportState {
  active: boolean
  target: Vec3
  radius: number
  height: number
  speed: number
  duration: number
  loop: boolean
  /** Monotonic token so repeated identical descriptors still trigger a
   *  re-render / replay of the orbit. */
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
  /** Active clipping plane, or null when disabled. Set by the
   *  editor_set_clipping_plane delta from set_clipping_plane execution. */
  clippingPlane: ClippingPlaneState | null
  /** Whether the viewport minimap overlay is visible. Driven by the
   *  editor_set_minimap delta from set_minimap tool execution. */
  minimapEnabled: boolean
  /** Whether real-time shadows are rendered in the viewport. Driven by the
   *  editor_set_shadows delta from set_shadows tool execution. */
  shadowsEnabled: boolean
  /** Viewport projection mode. Driven by the editor_set_projection delta
   *  from set_viewport_projection tool execution. */
  projectionMode: ViewportProjection
  /** Editor authoring mode (edit vs run/preview). Driven by the
   *  editor_set_mode delta from set_editor_mode tool execution. */
  editorMode: EditorMode
  /** Viewport shading mode. Driven by the editor_set_viewport_shading
   *  delta from set_viewport_shading tool execution. */
  viewportShading: ViewportShading
  /** Active cinematic camera flythrough, or null when cleared. Set by the
   *  editor_camera_flythrough delta from camera_flythrough tool execution. */
  cameraFlythrough: CameraFlythroughState | null
  /** Active radial context-menu, or null when dismissed. Set by the
   *  onContextMenu handler in SceneMesh; rendered as a pie overlay. */
  radialMenu: RadialMenuState | null
  /** Active turntable orbit, or null when inactive. Set by the
   *  editor_orbit_viewport delta from orbit_viewport tool execution. */
  orbitViewport: OrbitViewportState | null
  /** Visibility of the left chat panel. Driven by the editor_toggle_panel
   *  delta from the toggle_panel tool execution, and also by local Ctrl+B. */
  chatPanelVisible: boolean
  /** Visibility of the right side panel. Driven by the editor_toggle_panel
   *  delta from the toggle_panel tool execution, and also by local Ctrl+Shift+B. */
  rightPanelVisible: boolean
  /** Monotonic token bumped every time a panel-visibility change is requested
   *  so AppShell (which owns the actual open/close state) can react even when
   *  the requested visibility matches the current state. */
  panelToggleToken: number

  setTransformMode: (m: TransformMode) => void
  setGridSnap: (enabled: boolean, increment?: number) => void
  setRenderQuality: (q: RenderQuality) => void
  setActivePanel: (p: PanelTab) => void
  setViewportCamera: (position: Vec3, target: Vec3, smooth?: boolean) => void
  requestCapture: (filename?: string) => void
  setMeasurement: (m: Omit<MeasurementOverlayState, 'token'> | null) => void
  clearMeasurement: () => void
  setClippingPlane: (cp: Omit<ClippingPlaneState, 'token'> | null) => void
  setMinimapEnabled: (enabled: boolean) => void
  setShadowsEnabled: (enabled: boolean) => void
  setProjectionMode: (mode: ViewportProjection) => void
  setEditorMode: (mode: EditorMode) => void
  setViewportShading: (shading: ViewportShading) => void
  setCameraFlythrough: (f: Omit<CameraFlythroughState, 'token'> | null) => void
  clearCameraFlythrough: () => void
  setRadialMenu: (m: Omit<RadialMenuState, 'token'> | null) => void
  clearRadialMenu: () => void
  setOrbitViewport: (o: Omit<OrbitViewportState, 'token'> | null) => void
  clearOrbitViewport: () => void
  setPanelVisibility: (panel: 'chat' | 'right', visible?: boolean) => void
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
  clippingPlane: null,
  minimapEnabled: true,
  shadowsEnabled: true,
  projectionMode: 'perspective',
  editorMode: 'edit',
  viewportShading: 'solid',
  cameraFlythrough: null,
  radialMenu: null,
  orbitViewport: null,
  chatPanelVisible: true,
  rightPanelVisible: true,
  panelToggleToken: 0,

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
  setClippingPlane: (cp) =>
    set((state) => ({
      clippingPlane: cp
        ? { ...cp, token: (state.clippingPlane?.token ?? 0) + 1 }
        : null,
    })),
  setMinimapEnabled: (enabled) => set({ minimapEnabled: enabled }),
  setShadowsEnabled: (enabled) => set({ shadowsEnabled: enabled }),
  setProjectionMode: (mode) => set({ projectionMode: mode }),
  setEditorMode: (mode) => set({ editorMode: mode }),
  setViewportShading: (shading) => set({ viewportShading: shading }),
  setCameraFlythrough: (f) =>
    set((state) => ({
      cameraFlythrough: f
        ? { ...f, token: (state.cameraFlythrough?.token ?? 0) + 1 }
        : null,
    })),
  clearCameraFlythrough: () => set({ cameraFlythrough: null }),
  setRadialMenu: (m) =>
    set((state) => ({
      radialMenu: m
        ? { ...m, token: (state.radialMenu?.token ?? 0) + 1 }
        : null,
    })),
  clearRadialMenu: () => set({ radialMenu: null }),
  setOrbitViewport: (o) =>
    set((state) => ({
      orbitViewport: o
        ? { ...o, token: (state.orbitViewport?.token ?? 0) + 1 }
        : null,
    })),
  clearOrbitViewport: () => set({ orbitViewport: null }),
  setPanelVisibility: (panel, visible) =>
    set((state) => {
      const next = visible === undefined
        ? panel === 'chat'
          ? !state.chatPanelVisible
          : !state.rightPanelVisible
        : visible
      return panel === 'chat'
        ? { chatPanelVisible: next, panelToggleToken: state.panelToggleToken + 1 }
        : { rightPanelVisible: next, panelToggleToken: state.panelToggleToken + 1 }
    }),
}))
