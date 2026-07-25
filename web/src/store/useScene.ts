// Scene state management: object list, selection, local editing, undo/redo history
import { create } from 'zustand'
import {
  EMPTY_SCENE,
  type FogConfig,
  type Material,
  type SceneData,
  type SceneObject,
  type Transform,
  type Vec3,
} from '../types'

const MAX_HISTORY = 50

/** Deep clone a scene snapshot for the history stack */
function cloneScene(scene: SceneData): SceneData {
  return JSON.parse(JSON.stringify(scene))
}

interface SceneState {
  scene: SceneData
  selectedId: string | null
  past: SceneData[]
  future: SceneData[]

  /** Replace the entire scene without recording history (initial load) */
  setScene: (scene: SceneData) => void
  /** Apply a scene update from the Agent (records history) */
  applyScene: (scene: SceneData) => void
  /** Replace the scene without recording history (intermediate Agent updates) */
  replaceScene: (scene: SceneData) => void
  /** Commit the final Agent scene with the correct before-state for history */
  commitScene: (newScene: SceneData, previousScene: SceneData) => void
  /** Reset to an empty scene (records history) */
  clear: () => void

  /** Select an object by id; pass null to clear the selection */
  select: (id: string | null) => void
  selected: () => SceneObject | null

  /** Toggle visibility (records history) */
  toggleVisible: (id: string) => void
  /** Remove an object (records history) */
  removeObject: (id: string) => void
  /** Duplicate an object with a new id and slight position offset (records history) */
  duplicateObject: (id: string) => void

  /** Update transform (partial fields, records history) */
  updateTransform: (id: string, partial: Partial<Transform>) => void
  /** Update a single transform axis (records history) */
  updateTransformAxis: (
    id: string,
    field: 'position' | 'rotation' | 'scale',
    axis: 0 | 1 | 2,
    value: number,
  ) => void
  /** Update material (partial fields, records history) */
  updateMaterial: (id: string, partial: Partial<Material>) => void
  /** Rename (records history) */
  renameObject: (id: string, name: string) => void

  /** Scene-level: set background color (records history) */
  setBackground: (color: string) => void
  /** Scene-level: set fog (records history) */
  setFog: (fog: FogConfig | null) => void
  /** Scene-level: set grid visibility and size (records history) */
  setGrid: (visible: boolean, size?: number) => void

  /** Undo the last action */
  undo: () => void
  /** Redo the last undone action */
  redo: () => void
  /** Whether undo is available */
  canUndo: () => boolean
  /** Whether redo is available */
  canRedo: () => boolean
}

/** Helper function for immutable update of a specific object */
function mapObject(
  objects: SceneObject[],
  id: string,
  fn: (o: SceneObject) => SceneObject,
): SceneObject[] {
  return objects.map((o) => (o.id === id ? fn(o) : o))
}

function clampAxis(v: number, field: 'position' | 'rotation' | 'scale'): number {
  if (field === 'scale') return Math.max(0.01, v)
  return v
}

export const useScene = create<SceneState>((set, get) => ({
  scene: EMPTY_SCENE,
  selectedId: null,
  past: [],
  future: [],

  setScene: (scene) => set({ scene, past: [], future: [] }),

  applyScene: (incoming) =>
    set((state) => {
      const selectedStillExists =
        state.selectedId &&
        (incoming.objects.some((o) => o.id === state.selectedId) ||
          incoming.lights.some((l) => l.id === state.selectedId))
      const past = [...state.past, cloneScene(state.scene)].slice(-MAX_HISTORY)
      return {
        scene: incoming,
        selectedId: selectedStillExists ? state.selectedId : null,
        past,
        future: [],
      }
    }),

  replaceScene: (incoming) =>
    set((state) => {
      const selectedStillExists =
        state.selectedId &&
        (incoming.objects.some((o) => o.id === state.selectedId) ||
          incoming.lights.some((l) => l.id === state.selectedId))
      return {
        scene: incoming,
        selectedId: selectedStillExists ? state.selectedId : null,
      }
    }),

  commitScene: (newScene, previousScene) =>
    set((state) => {
      const selectedStillExists =
        state.selectedId &&
        (newScene.objects.some((o) => o.id === state.selectedId) ||
          newScene.lights.some((l) => l.id === state.selectedId))
      const past = [...state.past, cloneScene(previousScene)].slice(-MAX_HISTORY)
      return {
        scene: newScene,
        selectedId: selectedStillExists ? state.selectedId : null,
        past,
        future: [],
      }
    }),

  clear: () =>
    set((state) => ({
      scene: EMPTY_SCENE,
      selectedId: null,
      past: [...state.past, cloneScene(state.scene)].slice(-MAX_HISTORY),
      future: [],
    })),

  select: (id) => set({ selectedId: id }),

  selected: () => {
    const { scene, selectedId } = get()
    if (!selectedId) return null
    return scene.objects.find((o) => o.id === selectedId) ?? null
  },

  toggleVisible: (id) =>
    set((state) => ({
      past: [...state.past, cloneScene(state.scene)].slice(-MAX_HISTORY),
      future: [],
      scene: {
        ...state.scene,
        objects: mapObject(state.scene.objects, id, (o) => ({
          ...o,
          visible: !o.visible,
        })),
      },
    })),

  removeObject: (id) =>
    set((state) => ({
      past: [...state.past, cloneScene(state.scene)].slice(-MAX_HISTORY),
      future: [],
      scene: {
        ...state.scene,
        objects: state.scene.objects.filter((o) => o.id !== id),
      },
      selectedId: state.selectedId === id ? null : state.selectedId,
    })),

  duplicateObject: (id) =>
    set((state) => {
      const src = state.scene.objects.find((o) => o.id === id)
      if (!src) return state
      const newId = `${src.type}-${Date.now().toString(36)}`
      const copy: SceneObject = {
        ...src,
        id: newId,
        name: `${src.name} Copy`,
        transform: {
          ...src.transform,
          position: [
            src.transform.position[0] + 1.5,
            src.transform.position[1],
            src.transform.position[2],
          ] as Vec3,
        },
      }
      return {
        past: [...state.past, cloneScene(state.scene)].slice(-MAX_HISTORY),
        future: [],
        scene: {
          ...state.scene,
          objects: [...state.scene.objects, copy],
        },
        selectedId: newId,
      }
    }),

  updateTransform: (id, partial) =>
    set((state) => ({
      past: [...state.past, cloneScene(state.scene)].slice(-MAX_HISTORY),
      future: [],
      scene: {
        ...state.scene,
        objects: mapObject(state.scene.objects, id, (o) => ({
          ...o,
          transform: { ...o.transform, ...partial },
        })),
      },
    })),

  updateTransformAxis: (id, field, axis, value) =>
    set((state) => ({
      past: [...state.past, cloneScene(state.scene)].slice(-MAX_HISTORY),
      future: [],
      scene: {
        ...state.scene,
        objects: mapObject(state.scene.objects, id, (o) => {
          const next: Vec3 = [...o.transform[field]] as Vec3
          next[axis] = clampAxis(value, field)
          return { ...o, transform: { ...o.transform, [field]: next } }
        }),
      },
    })),

  updateMaterial: (id, partial) =>
    set((state) => ({
      past: [...state.past, cloneScene(state.scene)].slice(-MAX_HISTORY),
      future: [],
      scene: {
        ...state.scene,
        objects: mapObject(state.scene.objects, id, (o) => ({
          ...o,
          material: { ...o.material, ...partial },
        })),
      },
    })),

  renameObject: (id, name) =>
    set((state) => ({
      past: [...state.past, cloneScene(state.scene)].slice(-MAX_HISTORY),
      future: [],
      scene: {
        ...state.scene,
        objects: mapObject(state.scene.objects, id, (o) => ({ ...o, name })),
      },
    })),

  setBackground: (color) =>
    set((state) => ({
      past: [...state.past, cloneScene(state.scene)].slice(-MAX_HISTORY),
      future: [],
      scene: { ...state.scene, background: color },
    })),

  setFog: (fog) =>
    set((state) => ({
      past: [...state.past, cloneScene(state.scene)].slice(-MAX_HISTORY),
      future: [],
      scene: { ...state.scene, fog },
    })),

  setGrid: (visible, size) =>
    set((state) => ({
      past: [...state.past, cloneScene(state.scene)].slice(-MAX_HISTORY),
      future: [],
      scene: {
        ...state.scene,
        grid_visible: visible,
        grid_size: size ?? state.scene.grid_size,
      },
    })),

  undo: () =>
    set((state) => {
      if (state.past.length === 0) return state
      const previous = state.past[state.past.length - 1]
      const newPast = state.past.slice(0, -1)
      return {
        scene: previous,
        past: newPast,
        future: [cloneScene(state.scene), ...state.future].slice(0, MAX_HISTORY),
        selectedId: null,
      }
    }),

  redo: () =>
    set((state) => {
      if (state.future.length === 0) return state
      const next = state.future[0]
      const newFuture = state.future.slice(1)
      return {
        scene: next,
        past: [...state.past, cloneScene(state.scene)].slice(-MAX_HISTORY),
        future: newFuture,
        selectedId: null,
      }
    }),

  canUndo: () => get().past.length > 0,
  canRedo: () => get().future.length > 0,
}))
