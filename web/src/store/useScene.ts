// Scene state management: object list, selection, local editing, undo/redo history
import { create } from 'zustand'
import {
  EMPTY_SCENE,
  type Annotation,
  type CameraObject,
  type FogConfig,
  type Geometry,
  type GroupObject,
  type LightObject,
  type Material,
  type ObjectAnimation,
  type PhysicsDescriptor,
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
  /** Primary (last-clicked) selected object id; null when nothing is selected */
  selectedId: string | null
  /** Full multi-selection set; selectedId is always the last entry when non-empty */
  selectedIds: string[]
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

  /** Select an object by id; pass null to clear the selection. When additive is true, toggle id in the multi-selection. */
  select: (id: string | null, additive?: boolean) => void
  /** Toggle membership of an id in the multi-selection */
  toggleSelect: (id: string) => void
  /** Clear the entire selection */
  clearSelection: () => void
  /** Select every object in the scene */
  selectAll: () => void
  /** Primary selected object (mirrors selectedId) */
  selected: () => SceneObject | null

  /** Toggle visibility (records history) */
  toggleVisible: (id: string) => void
  /** Toggle lock state (records history) */
  toggleLock: (id: string) => void
  /** Remove an object (records history) */
  removeObject: (id: string) => void
  /** Duplicate an object with a new id and slight position offset (records history) */
  duplicateObject: (id: string) => void
  /** Group the given object ids under a new group (records history) */
  groupObjects: (ids: string[], name?: string) => void
  /** Move an object into a group (used by drag-to-group) */
  assignToGroup: (objectId: string, groupId: string | null) => void

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
  /** Update geometry params (partial merge of `geometry.params`, records history) */
  updateGeometry: (id: string, partial: Record<string, number | number[]>) => void
  /** Replace the geometry entirely (records history) */
  setGeometry: (id: string, geometry: Geometry) => void
  /** Set / clear object animation descriptor (records history) */
  updateAnimation: (id: string, animation: ObjectAnimation | null) => void
  /** Set / clear object physics descriptor (records history) */
  updatePhysics: (id: string, physics: PhysicsDescriptor | null) => void
  /** Rename (records history) */
  renameObject: (id: string, name: string) => void
  /** Move an object to a new index in scene.objects (records history) */
  reorderObject: (id: string, toIndex: number) => void
  /** Reorder objects by an explicit id list (records history) */
  reorderObjectsById: (orderedIds: string[]) => void

  /** Update a light (partial fields, records history) */
  updateLight: (id: string, partial: Partial<LightObject>) => void
  /** Remove a light (records history) */
  removeLight: (id: string) => void
  /** Rename a group (records history) */
  renameGroup: (id: string, name: string) => void

  /** Update a scene camera (partial fields, records history) */
  updateCamera: (id: string, partial: Partial<CameraObject>) => void
  /** Remove a scene camera (records history) */
  removeCamera: (id: string) => void

  /** Scene-level: set background color (records history) */
  setBackground: (color: string) => void
  /** Scene-level: set fog (records history) */
  setFog: (fog: FogConfig | null) => void
  /** Scene-level: set grid visibility and size (records history) */
  setGrid: (visible: boolean, size?: number) => void
  /** Scene-level: set HDRI environment string ("url|intensity" or null) (records history) */
  setEnvironment: (env: string | null) => void
  /** Scene-level: replace the camera list (records history) */
  setCameras: (cameras: CameraObject[]) => void
  /** Scene-level: replace the light list (records history) */
  setLights: (lights: LightObject[]) => void

  /** Scene-level: add a new on-canvas annotation (records history) */
  addAnnotation: (annotation: Annotation) => void
  /** Scene-level: update an existing annotation by id (records history) */
  updateAnnotation: (id: string, partial: Partial<Annotation>) => void
  /** Scene-level: remove an annotation by id (records history) */
  removeAnnotation: (id: string) => void
  /** Scene-level: replace the entire annotation list (records history) */
  setAnnotations: (annotations: Annotation[]) => void

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
  selectedIds: [],
  past: [],
  future: [],

  setScene: (scene) => set({ scene, past: [], future: [], selectedIds: [], selectedId: null }),

  applyScene: (incoming) =>
    set((state) => {
      const validIds = new Set<string>([
        ...incoming.objects.map((o) => o.id),
        ...incoming.lights.map((l) => l.id),
      ])
      const nextSelectedIds = state.selectedIds.filter((id) => validIds.has(id))
      const selectedStillExists = state.selectedId && validIds.has(state.selectedId)
      const past = [...state.past, cloneScene(state.scene)].slice(-MAX_HISTORY)
      // Sync viewport shading from scene metadata (set by the
      // set_viewport_shading Agent tool) to the editor store so the
      // renderer picks up the mode on the next render pass.
      const meta = (incoming as unknown as Record<string, unknown>).metadata as
        Record<string, unknown> | undefined
      if (meta?.viewport_shading) {
        const mode = meta.viewport_shading as string
        if (['wireframe', 'solid', 'material', 'rendered'].includes(mode)) {
          // Lazy import to avoid circular dependency at module load time
          import('./useEditor').then(({ useEditor }) => {
            useEditor.getState().setViewportShading(
              mode as 'wireframe' | 'solid' | 'material' | 'rendered',
            )
          })
        }
      }
      return {
        scene: incoming,
        selectedId: selectedStillExists ? state.selectedId : nextSelectedIds[nextSelectedIds.length - 1] ?? null,
        selectedIds: nextSelectedIds,
        past,
        future: [],
      }
    }),

  replaceScene: (incoming) =>
    set((state) => {
      const validIds = new Set<string>([
        ...incoming.objects.map((o) => o.id),
        ...incoming.lights.map((l) => l.id),
      ])
      const nextSelectedIds = state.selectedIds.filter((id) => validIds.has(id))
      const selectedStillExists = state.selectedId && validIds.has(state.selectedId)
      return {
        scene: incoming,
        selectedId: selectedStillExists ? state.selectedId : nextSelectedIds[nextSelectedIds.length - 1] ?? null,
        selectedIds: nextSelectedIds,
      }
    }),

  commitScene: (newScene, previousScene) =>
    set((state) => {
      const validIds = new Set<string>([
        ...newScene.objects.map((o) => o.id),
        ...newScene.lights.map((l) => l.id),
      ])
      const nextSelectedIds = state.selectedIds.filter((id) => validIds.has(id))
      const selectedStillExists = state.selectedId && validIds.has(state.selectedId)
      const past = [...state.past, cloneScene(previousScene)].slice(-MAX_HISTORY)
      return {
        scene: newScene,
        selectedId: selectedStillExists ? state.selectedId : nextSelectedIds[nextSelectedIds.length - 1] ?? null,
        selectedIds: nextSelectedIds,
        past,
        future: [],
      }
    }),

  clear: () =>
    set((state) => ({
      scene: EMPTY_SCENE,
      selectedId: null,
      selectedIds: [],
      past: [...state.past, cloneScene(state.scene)].slice(-MAX_HISTORY),
      future: [],
    })),

  select: (id, additive = false) =>
    set((state) => {
      if (id === null) {
        return { selectedId: null, selectedIds: [] }
      }
      if (additive) {
        const has = state.selectedIds.includes(id)
        const next = has
          ? state.selectedIds.filter((x) => x !== id)
          : [...state.selectedIds, id]
        return {
          selectedIds: next,
          selectedId: next.length ? next[next.length - 1] : null,
        }
      }
      return { selectedIds: [id], selectedId: id }
    }),

  toggleSelect: (id) => get().select(id, true),

  clearSelection: () => set({ selectedId: null, selectedIds: [] }),

  selectAll: () =>
    set((state) => ({
      selectedIds: state.scene.objects.map((o) => o.id),
      selectedId: state.scene.objects[state.scene.objects.length - 1]?.id ?? null,
    })),

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

  toggleLock: (id) =>
    set((state) => ({
      past: [...state.past, cloneScene(state.scene)].slice(-MAX_HISTORY),
      future: [],
      scene: {
        ...state.scene,
        objects: mapObject(state.scene.objects, id, (o) => ({
          ...o,
          locked: !o.locked,
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
      selectedIds: state.selectedIds.filter((x) => x !== id),
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

  groupObjects: (ids, name) =>
    set((state) => {
      if (ids.length === 0) return state
      const idSet = new Set(ids)
      const groupId = `group-${Date.now().toString(36)}`
      const groupName = name ?? `Group ${state.scene.groups.length + 1}`
      const group: GroupObject = {
        id: groupId,
        name: groupName,
        child_ids: [...ids],
        visible: true,
        locked: false,
      }
      return {
        past: [...state.past, cloneScene(state.scene)].slice(-MAX_HISTORY),
        future: [],
        scene: {
          ...state.scene,
          groups: [...state.scene.groups, group],
          objects: state.scene.objects.map((o) =>
            idSet.has(o.id) ? { ...o, group_id: groupId } : o,
          ),
        },
        selectedId: groupId,
        selectedIds: [groupId],
      }
    }),

  assignToGroup: (objectId, groupId) =>
    set((state) => ({
      past: [...state.past, cloneScene(state.scene)].slice(-MAX_HISTORY),
      future: [],
      scene: {
        ...state.scene,
        objects: mapObject(state.scene.objects, objectId, (o) => ({
          ...o,
          group_id: groupId,
        })),
        groups: state.scene.groups.map((g) => {
          if (groupId === g.id) {
            if (!g.child_ids.includes(objectId)) {
              return { ...g, child_ids: [...g.child_ids, objectId] }
            }
            return g
          }
          // Remove from any previous group
          if (g.child_ids.includes(objectId)) {
            return { ...g, child_ids: g.child_ids.filter((id) => id !== objectId) }
          }
          return g
        }),
      },
    })),

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

  updateGeometry: (id, partial) =>
    set((state) => ({
      past: [...state.past, cloneScene(state.scene)].slice(-MAX_HISTORY),
      future: [],
      scene: {
        ...state.scene,
        objects: mapObject(state.scene.objects, id, (o) => ({
          ...o,
          geometry: { ...o.geometry, params: { ...o.geometry.params, ...partial } },
        })),
      },
    })),

  setGeometry: (id, geometry) =>
    set((state) => ({
      past: [...state.past, cloneScene(state.scene)].slice(-MAX_HISTORY),
      future: [],
      scene: {
        ...state.scene,
        objects: mapObject(state.scene.objects, id, (o) => ({ ...o, geometry })),
      },
    })),

  updateAnimation: (id, animation) =>
    set((state) => ({
      past: [...state.past, cloneScene(state.scene)].slice(-MAX_HISTORY),
      future: [],
      scene: {
        ...state.scene,
        objects: mapObject(state.scene.objects, id, (o) => ({ ...o, animation })),
      },
    })),

  updatePhysics: (id, physics) =>
    set((state) => ({
      past: [...state.past, cloneScene(state.scene)].slice(-MAX_HISTORY),
      future: [],
      scene: {
        ...state.scene,
        objects: mapObject(state.scene.objects, id, (o) => ({ ...o, physics })),
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

  reorderObject: (id, toIndex) =>
    set((state) => {
      const from = state.scene.objects.findIndex((o) => o.id === id)
      if (from < 0 || from === toIndex) return state
      const next = [...state.scene.objects]
      const [moved] = next.splice(from, 1)
      const clamped = Math.max(0, Math.min(toIndex, next.length))
      next.splice(clamped, 0, moved)
      return {
        past: [...state.past, cloneScene(state.scene)].slice(-MAX_HISTORY),
        future: [],
        scene: { ...state.scene, objects: next },
      }
    }),

  reorderObjectsById: (orderedIds) =>
    set((state) => {
      const byId = new Map(state.scene.objects.map((o) => [o.id, o] as const))
      const next: SceneObject[] = []
      for (const id of orderedIds) {
        const o = byId.get(id)
        if (o) {
          next.push(o)
          byId.delete(id)
        }
      }
      // Append any objects not in the ordered list (e.g. new ones) at the end
      for (const o of byId.values()) next.push(o)
      if (next.length !== state.scene.objects.length) return state
      return {
        past: [...state.past, cloneScene(state.scene)].slice(-MAX_HISTORY),
        future: [],
        scene: { ...state.scene, objects: next },
      }
    }),

  updateLight: (id, partial) =>
    set((state) => ({
      past: [...state.past, cloneScene(state.scene)].slice(-MAX_HISTORY),
      future: [],
      scene: {
        ...state.scene,
        lights: state.scene.lights.map((l) => (l.id === id ? { ...l, ...partial } : l)),
      },
    })),

  removeLight: (id) =>
    set((state) => ({
      past: [...state.past, cloneScene(state.scene)].slice(-MAX_HISTORY),
      future: [],
      scene: {
        ...state.scene,
        lights: state.scene.lights.filter((l) => l.id !== id),
      },
      selectedId: state.selectedId === id ? null : state.selectedId,
      selectedIds: state.selectedIds.filter((x) => x !== id),
    })),

  renameGroup: (id, name) =>
    set((state) => ({
      past: [...state.past, cloneScene(state.scene)].slice(-MAX_HISTORY),
      future: [],
      scene: {
        ...state.scene,
        groups: state.scene.groups.map((g) => (g.id === id ? { ...g, name } : g)),
      },
    })),

  updateCamera: (id, partial) =>
    set((state) => ({
      past: [...state.past, cloneScene(state.scene)].slice(-MAX_HISTORY),
      future: [],
      scene: {
        ...state.scene,
        cameras: state.scene.cameras.map((c) => (c.id === id ? { ...c, ...partial } : c)),
      },
    })),

  removeCamera: (id) =>
    set((state) => ({
      past: [...state.past, cloneScene(state.scene)].slice(-MAX_HISTORY),
      future: [],
      scene: {
        ...state.scene,
        cameras: state.scene.cameras.filter((c) => c.id !== id),
      },
      selectedId: state.selectedId === id ? null : state.selectedId,
      selectedIds: state.selectedIds.filter((x) => x !== id),
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

  setEnvironment: (env) =>
    set((state) => ({
      past: [...state.past, cloneScene(state.scene)].slice(-MAX_HISTORY),
      future: [],
      scene: { ...state.scene, environment: env },
    })),

  setCameras: (cameras) =>
    set((state) => ({
      past: [...state.past, cloneScene(state.scene)].slice(-MAX_HISTORY),
      future: [],
      scene: { ...state.scene, cameras },
    })),

  setLights: (lights) =>
    set((state) => ({
      past: [...state.past, cloneScene(state.scene)].slice(-MAX_HISTORY),
      future: [],
      scene: { ...state.scene, lights },
    })),

  addAnnotation: (annotation) =>
    set((state) => ({
      past: [...state.past, cloneScene(state.scene)].slice(-MAX_HISTORY),
      future: [],
      scene: {
        ...state.scene,
        annotations: [...(state.scene.annotations ?? []), annotation],
      },
    })),

  updateAnnotation: (id, partial) =>
    set((state) => ({
      past: [...state.past, cloneScene(state.scene)].slice(-MAX_HISTORY),
      future: [],
      scene: {
        ...state.scene,
        annotations: (state.scene.annotations ?? []).map((a) =>
          a.id === id ? { ...a, ...partial } : a,
        ),
      },
    })),

  removeAnnotation: (id) =>
    set((state) => ({
      past: [...state.past, cloneScene(state.scene)].slice(-MAX_HISTORY),
      future: [],
      scene: {
        ...state.scene,
        annotations: (state.scene.annotations ?? []).filter((a) => a.id !== id),
      },
    })),

  setAnnotations: (annotations) =>
    set((state) => ({
      past: [...state.past, cloneScene(state.scene)].slice(-MAX_HISTORY),
      future: [],
      scene: { ...state.scene, annotations },
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
        selectedIds: [],
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
        selectedIds: [],
      }
    }),

  canUndo: () => get().past.length > 0,
  canRedo: () => get().future.length > 0,
}))
