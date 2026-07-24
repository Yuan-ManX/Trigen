// 场景状态管理：对象列表、选中、本地编辑
// Scene state management: object list, selection, local editing
import { create } from 'zustand'
import {
  EMPTY_SCENE,
  type Material,
  type SceneData,
  type SceneObject,
  type Transform,
  type Vec3,
} from '../types'

interface SceneState {
  scene: SceneData
  selectedId: string | null

  /** 整体替换场景 */
  /** Replace the entire scene */
  setScene: (scene: SceneData) => void
  /** 应用一次场景更新事件（合并对象：按 id 覆盖） */
  /** Apply a scene update event (merge objects: overwrite by id) */
  applyScene: (scene: SceneData) => void
  /** 重置为空场景 */
  /** Reset to an empty scene */
  clear: () => void

  /** 选中对象（按 id），传 null 清除选中 */
  /** Select an object by id; pass null to clear the selection */
  select: (id: string | null) => void
  selected: () => SceneObject | null

  /** 切换可见性 */
  /** Toggle visibility */
  toggleVisible: (id: string) => void
  /** 删除对象 */
  /** Remove an object */
  removeObject: (id: string) => void

  /** 更新变换（部分字段） */
  /** Update transform (partial fields) */
  updateTransform: (id: string, partial: Partial<Transform>) => void
  /** 更新单个变换轴 */
  /** Update a single transform axis */
  updateTransformAxis: (
    id: string,
    field: 'position' | 'rotation' | 'scale',
    axis: 0 | 1 | 2,
    value: number,
  ) => void
  /** 更新材质（部分字段） */
  /** Update material (partial fields) */
  updateMaterial: (id: string, partial: Partial<Material>) => void
  /** 重命名 */
  /** Rename */
  renameObject: (id: string, name: string) => void
}

/** 不可变更新指定对象的辅助函数 */
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

  setScene: (scene) => set({ scene }),

  applyScene: (incoming) =>
    set((state) => {
      // 简单策略：直接用后端场景替换，但保留当前选中（若仍存在）
      // Simple strategy: replace with the backend scene directly, but keep the current selection if it still exists
      const selectedStillExists =
        state.selectedId &&
        (incoming.objects.some((o) => o.id === state.selectedId) ||
          incoming.lights.some((l) => l.id === state.selectedId))
      return {
        scene: incoming,
        selectedId: selectedStillExists ? state.selectedId : null,
      }
    }),

  clear: () => set({ scene: EMPTY_SCENE, selectedId: null }),

  select: (id) => set({ selectedId: id }),

  selected: () => {
    const { scene, selectedId } = get()
    if (!selectedId) return null
    return scene.objects.find((o) => o.id === selectedId) ?? null
  },

  toggleVisible: (id) =>
    set((state) => ({
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
      scene: {
        ...state.scene,
        objects: state.scene.objects.filter((o) => o.id !== id),
      },
      selectedId: state.selectedId === id ? null : state.selectedId,
    })),

  updateTransform: (id, partial) =>
    set((state) => ({
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
      scene: {
        ...state.scene,
        objects: mapObject(state.scene.objects, id, (o) => ({ ...o, name })),
      },
    })),
}))
