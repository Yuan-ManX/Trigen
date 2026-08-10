"""Advanced editor-control tools.

Exposes higher-level 3D editor capabilities as Agent-callable tools so the
left-side chat surface can drive every editor feature: object isolation
(solo mode), transform presets (center/ground/reset), section clipping
planes, pivot-point editing, batch material application, and named-layer
organization. These complement the primitive-level tools rather than
duplicating them.
"""

from __future__ import annotations

import json
import math
import os
import uuid
from dataclasses import fields as _dc_fields
from typing import Any, Dict, List, Optional, get_type_hints

from trigen.scene import MATERIAL_PRESETS, Material, Scene
from trigen.tools.base import SceneDelta, ToolBase, ToolResult


# --- Isolate object — solo mode (hide everything except the target) ---

_ISOLATE_PARAMS = {
    "type": "object",
    "properties": {
        "target": {
            "type": "string",
            "description": "Object id or name to isolate (solo). All other objects are hidden.",
        },
        "restore": {
            "type": "boolean",
            "description": "If true, restore visibility for all objects (exit solo mode).",
        },
    },
    "required": ["target"],
}


class IsolateObjectTool(ToolBase):
    """Solo-mode isolation: hide every object except the target."""

    name = "isolate_object"
    description = (
        "Isolate an object (solo mode): hide all other scene objects so only "
        "the target remains visible. Set restore=true to exit solo mode and "
        "reveal every object again."
    )

    def schema(self) -> Dict[str, Any]:
        return _ISOLATE_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        target_id = str(arguments.get("target", ""))
        restore = bool(arguments.get("restore", False))
        obj = scene.find_object(target_id)
        if not obj and not restore:
            return ToolResult(success=False, message=f"Object not found: {target_id}")

        deltas: List[SceneDelta] = []
        if restore:
            for o in scene.objects:
                if not o.visible:
                    o.visible = True
                    deltas.append(SceneDelta(action="update", target_id=o.id, payload={"visible": True}))
            return ToolResult(
                success=True,
                message="Exited solo mode; all objects visible.",
                deltas=deltas,
                data={"restore": True},
            )

        for o in scene.objects:
            want_visible = o.id == obj.id
            if o.visible != want_visible:
                o.visible = want_visible
                deltas.append(SceneDelta(action="update", target_id=o.id, payload={"visible": want_visible}))
        return ToolResult(
            success=True,
            message=f"Isolated '{obj.name}' ({len(deltas)} object(s) hidden).",
            deltas=deltas,
            data={"isolated_id": obj.id, "hidden_count": len(deltas)},
        )


# --- Reset transform — presets (center / ground / reset rotation|scale) ---

_RESET_TRANSFORM_PARAMS = {
    "type": "object",
    "properties": {
        "target": {"type": "string", "description": "Target object id or name"},
        "preset": {
            "type": "string",
            "enum": ["center_origin", "ground_to_floor", "reset_rotation", "reset_scale", "reset_all"],
            "description": (
                "center_origin: move to world origin (x=0,z=0, keep y). "
                "ground_to_floor: drop min-y to 0. "
                "reset_rotation: zero rotation. "
                "reset_scale: scale back to [1,1,1]. "
                "reset_all: all of the above."
            ),
        },
    },
    "required": ["target", "preset"],
}


def _bbox_min_y(obj: Any) -> float:
    """Approximate the lowest Y of an object based on geometry + scale."""
    geo_type = obj.geometry.type
    sy = obj.transform.scale[1]
    py = obj.transform.position[1]
    if geo_type in ("box", "cylinder", "capsule", "cone"):
        return py - sy  # half-height
    if geo_type == "sphere":
        return py - sy
    if geo_type == "plane":
        return py
    return py - sy


class ResetTransformTool(ToolBase):
    """Apply a transform preset (center on origin, ground to floor, reset)."""

    name = "reset_transform"
    description = (
        "Apply a transform preset to an object: center on the world origin, "
        "ground it to the floor (min-y=0), reset rotation to zero, reset scale "
        "to [1,1,1], or reset all of these at once."
    )

    def schema(self) -> Dict[str, Any]:
        return _RESET_TRANSFORM_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        target_id = str(arguments.get("target", ""))
        preset = str(arguments.get("preset", ""))
        obj = scene.find_object(target_id)
        if not obj:
            return ToolResult(success=False, message=f"Object not found: {target_id}")
        if preset not in ("center_origin", "ground_to_floor", "reset_rotation", "reset_scale", "reset_all"):
            return ToolResult(success=False, message=f"Unknown preset: {preset}")

        tf = obj.transform
        changes: List[str] = []
        if preset in ("center_origin", "reset_all"):
            tf.position = [0.0, tf.position[1], 0.0]
            changes.append("position.xz->0")
        if preset in ("reset_rotation", "reset_all"):
            tf.rotation = [0.0, 0.0, 0.0]
            changes.append("rotation->0")
        if preset in ("reset_scale", "reset_all"):
            tf.scale = [1.0, 1.0, 1.0]
            changes.append("scale->[1,1,1]")
        if preset in ("ground_to_floor", "reset_all"):
            min_y = _bbox_min_y(obj)
            tf.position[1] = tf.position[1] - min_y
            changes.append(f"position.y grounded (was {min_y:.3f} below 0)")

        return ToolResult(
            success=True,
            message=f"Reset transform '{preset}' on '{obj.name}': {', '.join(changes)}",
            deltas=[SceneDelta(action="update", target_id=obj.id, payload={"transform": tf.to_dict()})],
            data={"preset": preset, "transform": tf.to_dict()},
        )


# --- Set clipping plane — section cutaway view (editor-side state) ---

_SET_CLIPPING_PLANE_PARAMS = {
    "type": "object",
    "properties": {
        "enabled": {"type": "boolean", "description": "Whether the clipping plane is active"},
        "axis": {
            "type": "string",
            "enum": ["x", "y", "z"],
            "description": "World axis to clip along (default y)",
        },
        "position": {"type": "number", "description": "Position along the axis where geometry is cut (default 0)"},
        "invert": {"type": "boolean", "description": "Invert the clip direction (default false)"},
    },
    "required": ["enabled"],
}


class SetClippingPlaneTool(ToolBase):
    """Toggle a section cutaway plane for inspecting interior geometry."""

    name = "set_clipping_plane"
    description = (
        "Enable or disable a section clipping plane to cut away geometry along "
        "a world axis (x/y/z) at a given position. Useful for inspecting "
        "interiors, assemblies, and stacked structures without deleting objects."
    )

    def schema(self) -> Dict[str, Any]:
        return _SET_CLIPPING_PLANE_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        enabled = bool(arguments.get("enabled", False))
        axis = str(arguments.get("axis", "y")).lower()
        if axis not in ("x", "y", "z"):
            return ToolResult(success=False, message=f"axis must be x/y/z, got {axis}")
        position = float(arguments.get("position", 0.0))
        invert = bool(arguments.get("invert", False))
        payload = {"enabled": enabled, "axis": axis, "position": position, "invert": invert}
        return ToolResult(
            success=True,
            message=f"Clipping plane {'enabled' if enabled else 'disabled'} (axis={axis}, pos={position:.2f}).",
            deltas=[SceneDelta(action="editor_set_clipping_plane", payload=payload)],
            data=payload,
        )


# --- Set object pivot — pivot-point offset for rotation/scaling ---

_SET_PIVOT_PARAMS = {
    "type": "object",
    "properties": {
        "target": {"type": "string", "description": "Target object id or name"},
        "pivot": {
            "type": "array",
            "items": {"type": "number"},
            "description": "Local pivot offset [x, y, z] relative to the object origin.",
        },
        "reset": {"type": "boolean", "description": "Reset pivot back to the object origin [0,0,0]"},
    },
    "required": ["target"],
}


class SetObjectPivotTool(ToolBase):
    """Set an object's pivot-point offset for rotation and scaling."""

    name = "set_object_pivot"
    description = (
        "Set an object's pivot-point offset (local [x,y,z]) so subsequent "
        "rotations and scales orbit around the new pivot instead of the "
        "geometry origin. Useful for door hinges, gear axles, and robotic joints."
    )

    def schema(self) -> Dict[str, Any]:
        return _SET_PIVOT_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        target_id = str(arguments.get("target", ""))
        obj = scene.find_object(target_id)
        if not obj:
            return ToolResult(success=False, message=f"Object not found: {target_id}")

        if bool(arguments.get("reset", False)):
            pivot = [0.0, 0.0, 0.0]
        else:
            raw = arguments.get("pivot", [0.0, 0.0, 0.0])
            if not isinstance(raw, list) or len(raw) != 3:
                return ToolResult(success=False, message="pivot must be a 3-element array [x,y,z]")
            pivot = [float(v) for v in raw]

        # Store pivot as a tag payload so it persists with the object and the
        # frontend renderer can apply it as a transform-parent offset.
        tag = f"pivot:{pivot[0]:.4f},{pivot[1]:.4f},{pivot[2]:.4f}"
        obj.tags = [t for t in obj.tags if not t.startswith("pivot:")]
        obj.tags.append(tag)
        return ToolResult(
            success=True,
            message=f"Pivot for '{obj.name}' set to [{pivot[0]:.3f}, {pivot[1]:.3f}, {pivot[2]:.3f}].",
            deltas=[SceneDelta(action="update", target_id=obj.id, payload={"tags": list(obj.tags)})],
            data={"pivot": pivot},
        )


# --- Apply material batch — apply a preset/color to multiple targets at once ---

_APPLY_MATERIAL_BATCH_PARAMS = {
    "type": "object",
    "properties": {
        "targets": {
            "type": "array",
            "items": {"type": "string"},
            "description": "List of object ids or names to update",
        },
        "preset": {
            "type": "string",
            "enum": list(MATERIAL_PRESETS.keys()),
            "description": "Preset material name applied to every target",
        },
        "color": {"type": "string", "description": "(Optional) override color applied to every target"},
        "metalness": {"type": "number", "description": "(Optional) override metalness 0-1"},
        "roughness": {"type": "number", "description": "(Optional) override roughness 0-1"},
    },
    "required": ["targets"],
}


class ApplyMaterialBatchTool(ToolBase):
    """Apply a material preset or color to multiple objects in one call."""

    name = "apply_material_batch"
    description = (
        "Apply a material preset and/or color/metalness/roughness overrides to "
        "multiple objects at once. More efficient than calling apply_material "
        "repeatedly when styling a group of objects identically."
    )

    def schema(self) -> Dict[str, Any]:
        return _APPLY_MATERIAL_BATCH_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        targets = arguments.get("targets", [])
        if not isinstance(targets, list) or not targets:
            return ToolResult(success=False, message="targets must be a non-empty array")
        preset = str(arguments.get("preset", ""))
        preset_data = MATERIAL_PRESETS.get(preset) if preset else None
        if preset and not preset_data:
            return ToolResult(success=False, message=f"Unknown preset: {preset}")

        color_override = arguments.get("color")
        metalness_override = arguments.get("metalness")
        roughness_override = arguments.get("roughness")

        deltas: List[SceneDelta] = []
        applied = 0
        missing = 0
        for tgt in targets:
            obj = scene.find_object(str(tgt))
            if not obj:
                missing += 1
                continue
            if preset_data:
                obj.material.color = str(preset_data.get("color", obj.material.color))
                obj.material.metalness = float(preset_data.get("metalness", obj.material.metalness))
                obj.material.roughness = float(preset_data.get("roughness", obj.material.roughness))
                obj.material.opacity = float(preset_data.get("opacity", obj.material.opacity))
                if "emissive" in preset_data:
                    obj.material.emissive = str(preset_data["emissive"])
                if "emissive_intensity" in preset_data:
                    obj.material.emissive_intensity = float(preset_data["emissive_intensity"])
                if "wireframe" in preset_data:
                    obj.material.wireframe = bool(preset_data["wireframe"])
            if color_override:
                obj.material.color = str(color_override)
            if metalness_override is not None:
                obj.material.metalness = max(0.0, min(1.0, float(metalness_override)))
            if roughness_override is not None:
                obj.material.roughness = max(0.0, min(1.0, float(roughness_override)))
            deltas.append(SceneDelta(action="update", target_id=obj.id, payload={"material": obj.material.to_dict()}))
            applied += 1

        if applied == 0:
            return ToolResult(success=False, message="None of the targets were found in the scene.")
        msg = f"Applied material to {applied} object(s)"
        if preset:
            msg += f" (preset={preset})"
        if missing:
            msg += f"; {missing} target(s) not found"
        return ToolResult(
            success=True,
            message=msg,
            deltas=deltas,
            data={"applied_count": applied, "missing_count": missing, "preset": preset},
        )


# --- Set object layer — named-layer organization + per-layer visibility ---

_SET_OBJECT_LAYER_PARAMS = {
    "type": "object",
    "properties": {
        "target": {"type": "string", "description": "Target object id or name"},
        "layer": {"type": "string", "description": "Layer name to assign the object to"},
        "toggle_layer": {
            "type": "string",
            "description": "(Optional) toggle visibility of every object on this layer name",
        },
        "visible": {
            "type": "boolean",
            "description": "Visibility state when toggling a layer (default true)",
        },
    },
    "required": ["target", "layer"],
}


def _layer_of(obj: Any) -> str:
    """Return the layer name tagged on an object (default 'default')."""
    for t in obj.tags:
        if t.startswith("layer:"):
            return t[len("layer:"):]
    return "default"


class SetObjectLayerTool(ToolBase):
    """Assign an object to a named layer and toggle whole-layer visibility."""

    name = "set_object_layer"
    description = (
        "Organize objects into named layers for grouping and bulk visibility "
        "control. Assign an object to a layer, then toggle the visibility of "
        "every object on that layer at once — ideal for show/hide structural, "
        "decorative, or annotation groups."
    )

    def schema(self) -> Dict[str, Any]:
        return _SET_OBJECT_LAYER_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        target_id = str(arguments.get("target", ""))
        layer = str(arguments.get("layer", "")).strip()
        toggle_layer = str(arguments.get("toggle_layer", "")).strip()
        visible = bool(arguments.get("visible", True))
        if not layer:
            return ToolResult(success=False, message="layer name is required")

        obj = scene.find_object(target_id)
        deltas: List[SceneDelta] = []
        assigned = False
        if obj:
            obj.tags = [t for t in obj.tags if not t.startswith("layer:")]
            obj.tags.append(f"layer:{layer}")
            assigned = True

        # Optional: toggle visibility of every object on toggle_layer
        toggled = 0
        if toggle_layer:
            for o in scene.objects:
                if _layer_of(o) == toggle_layer and o.visible != visible:
                    o.visible = visible
                    deltas.append(SceneDelta(action="update", target_id=o.id, payload={"visible": visible}))
                    toggled += 1

        parts = []
        if assigned:
            parts.append(f"assigned '{obj.name}' to layer '{layer}'")
        if toggle_layer:
            parts.append(f"toggled layer '{toggle_layer}' to visible={visible} ({toggled} object(s))")
        if not parts:
            return ToolResult(success=False, message=f"Object not found: {target_id}")
        return ToolResult(
            success=True,
            message="; ".join(parts),
            deltas=deltas,
            data={"layer": layer, "toggle_layer": toggle_layer, "toggled_count": toggled},
        )


# --- Set minimap visibility — toggle the editor viewport minimap ---

_SET_MINIMAP_PARAMS = {
    "type": "object",
    "properties": {
        "enabled": {
            "type": "boolean",
            "description": "Whether the minimap overlay is visible in the viewport.",
        },
    },
    "required": ["enabled"],
}


class SetMinimapTool(ToolBase):
    """Toggle the editor viewport minimap overlay."""

    name = "set_minimap"
    description = (
        "Show or hide the viewport minimap overlay. The minimap renders a "
        "top-down schematic of the scene so users can navigate large scenes "
        "without losing spatial context."
    )

    def schema(self) -> Dict[str, Any]:
        return _SET_MINIMAP_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        enabled = bool(arguments.get("enabled", False))
        payload = {"enabled": enabled}
        return ToolResult(
            success=True,
            message=f"Minimap {'enabled' if enabled else 'disabled'}.",
            deltas=[SceneDelta(action="editor_set_minimap", payload=payload)],
            data=payload,
        )


# --- Set shadows — toggle viewport shadow rendering ---

_SET_SHADOWS_PARAMS = {
    "type": "object",
    "properties": {
        "enabled": {
            "type": "boolean",
            "description": "Whether real-time shadows are rendered in the viewport.",
        },
    },
    "required": ["enabled"],
}


class SetShadowsTool(ToolBase):
    """Toggle real-time shadow rendering in the viewport."""

    name = "set_shadows"
    description = (
        "Enable or disable real-time shadow rendering for the viewport. "
        "Disabling shadows improves performance on integrated GPUs; enabling "
        "them gives a more accurate preview of the final lit scene."
    )

    def schema(self) -> Dict[str, Any]:
        return _SET_SHADOWS_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        enabled = bool(arguments.get("enabled", False))
        payload = {"enabled": enabled}
        return ToolResult(
            success=True,
            message=f"Shadows {'enabled' if enabled else 'disabled'}.",
            deltas=[SceneDelta(action="editor_set_shadows", payload=payload)],
            data=payload,
        )


# --- Set viewport projection — perspective / orthographic ---

_SET_PROJECTION_PARAMS = {
    "type": "object",
    "properties": {
        "mode": {
            "type": "string",
            "enum": ["perspective", "orthographic"],
            "description": "Viewport camera projection mode.",
        },
    },
    "required": ["mode"],
}


class SetViewportProjectionTool(ToolBase):
    """Switch the viewport camera between perspective and orthographic."""

    name = "set_viewport_projection"
    description = (
        "Switch the viewport camera projection between perspective (depth-foreshortened) "
        "and orthographic (parallel, no distortion). Orthographic is useful for "
        "precise alignment, front/side/top views, and parametric modeling."
    )

    def schema(self) -> Dict[str, Any]:
        return _SET_PROJECTION_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        mode = str(arguments.get("mode", "")).lower()
        if mode not in ("perspective", "orthographic"):
            return ToolResult(success=False, message=f"mode must be perspective or orthographic, got {mode}")
        payload = {"mode": mode}
        return ToolResult(
            success=True,
            message=f"Viewport projection set to {mode}.",
            deltas=[SceneDelta(action="editor_set_projection", payload=payload)],
            data=payload,
        )


# --- Set editor mode — edit / run (preview) toggle ---

_SET_EDITOR_MODE_PARAMS = {
    "type": "object",
    "properties": {
        "mode": {
            "type": "string",
            "enum": ["edit", "run"],
            "description": "Editor mode: edit (authoring) or run (playback/preview).",
        },
    },
    "required": ["mode"],
}


class SetEditorModeTool(ToolBase):
    """Toggle the editor between authoring (edit) and playback (run) modes."""

    name = "set_editor_mode"
    description = (
        "Switch the editor between edit mode (authoring, gizmos, snapping) and "
        "run mode (preview/playback with animations and physics running). Useful "
        "for previewing an animation or interaction without leaving the editor."
    )

    def schema(self) -> Dict[str, Any]:
        return _SET_EDITOR_MODE_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        mode = str(arguments.get("mode", "")).lower()
        if mode not in ("edit", "run"):
            return ToolResult(success=False, message=f"mode must be edit or run, got {mode}")
        payload = {"mode": mode}
        return ToolResult(
            success=True,
            message=f"Editor mode set to {mode}.",
            deltas=[SceneDelta(action="editor_set_mode", payload=payload)],
            data=payload,
        )


# --- Save / load named scene slots — workspace-persisted snapshots ---

_SET_SCENE_SLOT_PARAMS = {
    "type": "object",
    "properties": {
        "slot": {
            "type": "string",
            "description": "Slot name (filename-safe). Overwrites an existing slot.",
        },
    },
    "required": ["slot"],
}

_LOAD_SCENE_SLOT_PARAMS = {
    "type": "object",
    "properties": {
        "slot": {"type": "string", "description": "Slot name to load."},
        "clear_scene": {
            "type": "boolean",
            "description": "If true (default), replace the current scene. If false, merge objects.",
        },
    },
    "required": ["slot"],
}


def _slot_dir() -> str:
    """Return the workspace directory used for scene-slot snapshots."""
    # Default to a workspace-relative path; orchestrator passes a configured
    # workspace via the tool's _workspace_dir attribute when registered.
    base = os.environ.get(
        "TRIGEN_WORKSPACE",
        os.path.join(os.getcwd(), ".trigen", "workspace"),
    )
    return os.path.join(base, "scene_slots")


def _slot_path(name: str) -> str:
    safe = "".join(c for c in name if c.isalnum() or c in ("-", "_")) or "default"
    return os.path.join(_slot_dir(), f"{safe}.json")


class SaveSceneSlotTool(ToolBase):
    """Persist the current scene to a named slot for later recall."""

    name = "save_scene_slot"
    description = (
        "Save the current scene to a named slot under the workspace so it can be "
        "recalled later with load_scene_slot. Useful for snapshots, alternative "
        "compositions, or saving progress before a destructive edit."
    )

    def schema(self) -> Dict[str, Any]:
        return _SET_SCENE_SLOT_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        slot = str(arguments.get("slot", "")).strip()
        if not slot:
            return ToolResult(success=False, message="slot name is required")
        path = _slot_path(slot)
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(scene.to_dict(), f, ensure_ascii=False, indent=2)
        except Exception as e:
            return ToolResult(success=False, message=f"Failed to save slot '{slot}': {e}")
        payload = {"slot": slot, "path": path, "object_count": len(scene.objects)}
        return ToolResult(
            success=True,
            message=f"Saved scene to slot '{slot}' ({len(scene.objects)} object(s)).",
            deltas=[SceneDelta(action="editor_save_scene_slot", payload=payload)],
            data=payload,
        )


class LoadSceneSlotTool(ToolBase):
    """Load a previously-saved scene slot, replacing or merging into the scene."""

    name = "load_scene_slot"
    description = (
        "Load a named scene slot previously saved with save_scene_slot. By "
        "default replaces the current scene; set clear_scene=false to merge "
        "the slot's objects into the current scene instead."
    )

    def schema(self) -> Dict[str, Any]:
        return _LOAD_SCENE_SLOT_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        slot = str(arguments.get("slot", "")).strip()
        if not slot:
            return ToolResult(success=False, message="slot name is required")
        clear_scene = bool(arguments.get("clear_scene", True))
        path = _slot_path(slot)
        if not os.path.exists(path):
            return ToolResult(success=False, message=f"Slot '{slot}' not found")
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            loaded = Scene.from_dict(data)
        except Exception as e:
            return ToolResult(success=False, message=f"Failed to load slot '{slot}': {e}")

        deltas: List[SceneDelta] = []
        if clear_scene:
            # Snapshot existing object ids so the frontend can remove them.
            for o in scene.objects:
                deltas.append(SceneDelta(action="delete", target_id=o.id))
            scene.objects = list(loaded.objects)
            scene.lights = list(loaded.lights)
            scene.cameras = list(loaded.cameras)
            scene.groups = list(loaded.groups)
            scene.background = loaded.background
            scene.environment = loaded.environment
            scene.fog = loaded.fog
            scene.grid_visible = loaded.grid_visible
            scene.grid_size = loaded.grid_size
            for o in scene.objects:
                deltas.append(SceneDelta(action="create", target_id=o.id, payload=o.to_dict()))
            action_summary = f"replaced scene with slot '{slot}'"
        else:
            for o in loaded.objects:
                scene.objects.append(o)
                deltas.append(SceneDelta(action="create", target_id=o.id, payload=o.to_dict()))
            action_summary = f"merged {len(loaded.objects)} object(s) from slot '{slot}'"

        payload = {"slot": slot, "clear_scene": clear_scene, "object_count": len(scene.objects)}
        return ToolResult(
            success=True,
            message=f"Loaded slot '{slot}'; {action_summary}.",
            deltas=deltas,
            data=payload,
        )


# --- Set material property — set any extended PBR field by name + value ---

# Material field name -> python type, resolved once from the Material
# dataclass via get_type_hints (handles `from __future__ import annotations`
# which stringifies dataclass field types). Used by
# SetMaterialPropertyTool to coerce incoming JSON values to the right
# type and reject unknown property names up front.
_MATERIAL_FIELD_TYPES: Dict[str, Any] = get_type_hints(Material)


def _coerce_material_value(name: str, raw: Any) -> Any:
    """Coerce a raw JSON value to the type expected by Material.<name>."""
    target = _MATERIAL_FIELD_TYPES.get(name)
    if target is None:
        raise ValueError(f"unknown material property: {name}")
    if target is bool:
        return bool(raw)
    if target is float:
        return float(raw)
    if target is str:
        return str(raw)
    # Lists / dicts fall through — accept as-is.
    return raw


_SET_MATERIAL_PROPERTY_PARAMS = {
    "type": "object",
    "properties": {
        "target": {"type": "string", "description": "Target object id or name"},
        "property": {
            "type": "string",
            "description": (
                "Material field name to set. Covers the base PBR fields "
                "(color, metalness, roughness, opacity, wireframe, emissive, "
                "emissive_intensity, flat_shading, side) and the extended "
                "physical fields (clearcoat, clearcoat_roughness, transmission, "
                "thickness, ior, iridescence, iridescence_ior, "
                "iridescence_thickness_min, iridescence_thickness_max, sheen, "
                "sheen_color, sheen_roughness, specular_intensity, "
                "specular_color, attenuation_color, attenuation_distance)."
            ),
        },
        "value": {
            "description": (
                "Value for the property. Numbers/booleans/strings are "
                "coerced to the field's type."
            ),
        },
    },
    "required": ["target", "property", "value"],
}


class SetMaterialPropertyTool(ToolBase):
    """Set a single named material property on an object."""

    name = "set_material_property"
    description = (
        "Set any single material property by name + value. Covers every "
        "base PBR field plus the extended physical fields (clearcoat, "
        "transmission, ior, iridescence, sheen, specular, attenuation). "
        "Use apply_material for the common color/metalness/roughness combo; "
        "use this tool for fine-grained control of a single extended field."
    )

    def schema(self) -> Dict[str, Any]:
        return _SET_MATERIAL_PROPERTY_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        target_id = str(arguments.get("target", ""))
        obj = scene.find_object(target_id)
        if not obj:
            return ToolResult(success=False, message=f"Object not found: {target_id}")
        prop = str(arguments.get("property", "")).strip()
        if not prop:
            return ToolResult(success=False, message="property name is required")
        if prop not in _MATERIAL_FIELD_TYPES:
            return ToolResult(
                success=False,
                message=f"Unknown material property '{prop}'. Available: {', '.join(sorted(_MATERIAL_FIELD_TYPES))}",
            )
        try:
            value = _coerce_material_value(prop, arguments.get("value"))
        except (ValueError, TypeError) as e:
            return ToolResult(success=False, message=f"Invalid value for '{prop}': {e}")

        setattr(obj.material, prop, value)
        return ToolResult(
            success=True,
            message=f"{obj.name} material.{prop} = {value!r}",
            deltas=[SceneDelta(action="update", target_id=obj.id, payload={"material": obj.material.to_dict()})],
            data={"property": prop, "value": value, "material": obj.material.to_dict()},
        )


# --- Set geometry params — modify the geometry.params dict in place ---

_SET_GEOMETRY_PARAMS_PARAMS = {
    "type": "object",
    "properties": {
        "target": {"type": "string", "description": "Target object id or name"},
        "params": {
            "type": "object",
            "description": (
                "Key/value overrides merged into the geometry params dict. "
                "e.g. {\"radius\": 0.8, \"widthSegments\": 64} for a sphere, "
                "{\"depth\": 0.6, \"bevelEnabled\": false} for an extrude."
            ),
            "additionalProperties": True,
        },
        "replace": {
            "type": "boolean",
            "description": "If true, replace the params dict entirely instead of merging.",
        },
    },
    "required": ["target", "params"],
}


class SetGeometryParamsTool(ToolBase):
    """Merge or replace the geometry.params dict of an object."""

    name = "set_geometry_params"
    description = (
        "Modify the parameters of an object's geometry (e.g. sphere radius, "
        "cylinder height, torus tube, extrude depth, lathe segments) by "
        "merging a partial params dict. Set replace=true to overwrite the "
        "params dict entirely. Does not change the geometry type."
    )

    def schema(self) -> Dict[str, Any]:
        return _SET_GEOMETRY_PARAMS_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        target_id = str(arguments.get("target", ""))
        obj = scene.find_object(target_id)
        if not obj:
            return ToolResult(success=False, message=f"Object not found: {target_id}")
        params = arguments.get("params")
        if not isinstance(params, dict) or not params:
            return ToolResult(success=False, message="params must be a non-empty object")
        replace = bool(arguments.get("replace", False))
        if replace:
            obj.geometry.params = dict(params)
        else:
            obj.geometry.params = {**obj.geometry.params, **params}
        return ToolResult(
            success=True,
            message=f"{obj.name} geometry params {'replaced' if replace else 'updated'}: {list(params.keys())}",
            deltas=[SceneDelta(action="update", target_id=obj.id, payload={"geometry": obj.geometry.to_dict()})],
            data={"geometry": obj.geometry.to_dict(), "replace": replace},
        )


# --- Set object parent — assign / clear an object's group_id (hierarchy) ---

_SET_OBJECT_PARENT_PARAMS = {
    "type": "object",
    "properties": {
        "target": {"type": "string", "description": "Target object id or name"},
        "group_id": {
            "type": "string",
            "description": "Parent group id (or group name). Pass null/empty to detach from any group.",
        },
    },
    "required": ["target"],
}


class SetObjectParentTool(ToolBase):
    """Assign an object to a parent group (or detach it)."""

    name = "set_object_parent"
    description = (
        "Parent an object to a group by setting its group_id and updating "
        "the group's child_ids. Pass an empty group_id to detach. Accepts "
        "either a group id or a group name."
    )

    def schema(self) -> Dict[str, Any]:
        return _SET_OBJECT_PARENT_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        target_id = str(arguments.get("target", ""))
        obj = scene.find_object(target_id)
        if not obj:
            return ToolResult(success=False, message=f"Object not found: {target_id}")
        group_id_raw = arguments.get("group_id")
        group_id = str(group_id_raw).strip() if group_id_raw else ""

        # Remove the object from its current group's child_ids first.
        if obj.group_id:
            for g in scene.groups:
                if obj.id in g.child_ids:
                    g.child_ids = [c for c in g.child_ids if c != obj.id]

        if not group_id:
            obj.group_id = None
            return ToolResult(
                success=True,
                message=f"'{obj.name}' detached from any group.",
                deltas=[SceneDelta(action="update", target_id=obj.id, payload={"group_id": None})],
                data={"group_id": None},
            )

        # Resolve by id or name.
        target_group = None
        for g in scene.groups:
            if g.id == group_id or g.name.lower() == group_id.lower():
                target_group = g
                break
        if not target_group:
            return ToolResult(success=False, message=f"Group not found: {group_id}")

        obj.group_id = target_group.id
        if obj.id not in target_group.child_ids:
            target_group.child_ids.append(obj.id)
        return ToolResult(
            success=True,
            message=f"'{obj.name}' parented to group '{target_group.name}'.",
            deltas=[SceneDelta(action="update", target_id=obj.id, payload={"group_id": target_group.id})],
            data={"group_id": target_group.id, "group_name": target_group.name},
        )


# --- Add annotation — create a new on-canvas annotation anchored to an
# --- object id or a world-space position.

_ADD_ANNOTATION_PARAMS = {
    "type": "object",
    "properties": {
        "object_id": {
            "type": "string",
            "description": "(Optional) object id or name to anchor the annotation to. When set, the annotation follows the object's transform.",
        },
        "position": {
            "type": "array",
            "items": {"type": "number"},
            "description": "World-space anchor position [x, y, z]. Used directly when object_id is null.",
        },
        "text": {"type": "string", "description": "Annotation body text."},
        "title": {"type": "string", "description": "(Optional) short title rendered as a header."},
        "color": {"type": "string", "description": "(Optional) accent color, hex such as #22d3ee."},
        "id": {"type": "string", "description": "(Optional) explicit id; auto-generated when omitted."},
    },
    "required": ["text"],
}


class AddAnnotationTool(ToolBase):
    """Create a new on-canvas annotation in the scene."""

    name = "add_annotation"
    description = (
        "Add an on-canvas annotation (a labeled pin) anchored to an object "
        "or a world-space position. Annotations follow their object's "
        "transform every frame and serialize with the scene."
    )

    def schema(self) -> Dict[str, Any]:
        return _ADD_ANNOTATION_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        text = str(arguments.get("text", "")).strip()
        if not text:
            return ToolResult(success=False, message="text is required")
        object_id_raw = arguments.get("object_id")
        object_id: Optional[str] = None
        if object_id_raw:
            obj = scene.find_object(str(object_id_raw))
            if obj:
                object_id = obj.id
            else:
                # Allow caller to pass an explicit id even if not in scene.
                object_id = str(object_id_raw)

        position = arguments.get("position")
        if isinstance(position, list) and len(position) >= 3:
            pos = [float(position[0]), float(position[1]), float(position[2])]
        elif object_id:
            # Default to the anchored object's position.
            obj = scene.find_object(object_id)
            pos = list(obj.transform.position) if obj else [0.0, 1.0, 0.0]
        else:
            pos = [0.0, 1.0, 0.0]

        ann_id = str(arguments.get("id") or f"ann_{uuid.uuid4().hex[:8]}")
        annotation = {
            "id": ann_id,
            "object_id": object_id,
            "position": pos,
            "text": text,
            "title": str(arguments.get("title") or "") or None,
            "color": str(arguments.get("color") or "#22d3ee"),
            "visible": True,
        }
        scene.annotations.append(annotation)
        return ToolResult(
            success=True,
            message=f"Added annotation '{ann_id}'" + (f" on '{object_id}'" if object_id else ""),
            deltas=[SceneDelta(action="add_annotation", target_id=ann_id, payload=annotation)],
            data={"annotation": annotation, "count": len(scene.annotations)},
        )


# --- Remove annotation — delete an annotation by id ---

_REMOVE_ANNOTATION_PARAMS = {
    "type": "object",
    "properties": {
        "id": {"type": "string", "description": "Annotation id to remove."},
    },
    "required": ["id"],
}


class RemoveAnnotationTool(ToolBase):
    """Remove an annotation by id."""

    name = "remove_annotation"
    description = (
        "Remove an on-canvas annotation by id. Use list_objects or scene_info "
        "first to discover annotation ids if you don't already have one."
    )

    def schema(self) -> Dict[str, Any]:
        return _REMOVE_ANNOTATION_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        ann_id = str(arguments.get("id", "")).strip()
        if not ann_id:
            return ToolResult(success=False, message="id is required")
        before = len(scene.annotations)
        scene.annotations = [a for a in scene.annotations if a.get("id") != ann_id]
        if len(scene.annotations) == before:
            return ToolResult(success=False, message=f"Annotation not found: {ann_id}")
        return ToolResult(
            success=True,
            message=f"Removed annotation '{ann_id}'.",
            deltas=[SceneDelta(action="remove_annotation", target_id=ann_id, payload={"id": ann_id})],
            data={"id": ann_id, "count": len(scene.annotations)},
        )


# --- Configure shortcuts — emit a no-op editor delta the frontend can ignore ---

_CONFIGURE_SHORTCUTS_PARAMS = {
    "type": "object",
    "properties": {
        "shortcuts": {
            "type": "object",
            "description": (
                "Mapping of action name -> key binding (e.g. "
                "{\"frame_all\": \"A\", \"toggle_grid\": \"G\"}). The frontend "
                "currently ignores this delta; the binding is recorded for "
                "future use."
            ),
            "additionalProperties": True,
        },
    },
    "required": ["shortcuts"],
}


class ConfigureShortcutsTool(ToolBase):
    """Emit an editor_configure_shortcuts delta (recorded, frontend-ignored)."""

    name = "configure_shortcuts"
    description = (
        "Record a custom keyboard-shortcut mapping. The frontend currently "
        "ignores this delta (bindings are not yet reassignable at runtime), "
        "but the mapping is logged on the backend for future use."
    )

    def schema(self) -> Dict[str, Any]:
        return _CONFIGURE_SHORTCUTS_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        shortcuts = arguments.get("shortcuts")
        if not isinstance(shortcuts, dict) or not shortcuts:
            return ToolResult(success=False, message="shortcuts must be a non-empty object")
        payload = {"shortcuts": dict(shortcuts)}
        return ToolResult(
            success=True,
            message=f"Recorded {len(shortcuts)} shortcut binding(s) (frontend may ignore).",
            deltas=[SceneDelta(action="editor_configure_shortcuts", payload=payload)],
            data=payload,
        )
