"""Advanced editor-control tools.

Exposes higher-level 3D editor capabilities as Agent-callable tools so the
left-side chat surface can drive every editor feature: object isolation
(solo mode), transform presets (center/ground/reset), section clipping
planes, pivot-point editing, batch material application, and named-layer
organization. These complement the primitive-level tools rather than
duplicating them.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List

from trigen.scene import MATERIAL_PRESETS, Scene
from trigen.tools.base import SceneDelta, ToolBase, ToolResult


# ---------------------------------------------------------------------------
# 1. Isolate object — solo mode (hide everything except the target)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# 2. Reset transform — presets (center / ground / reset rotation|scale)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# 3. Set clipping plane — section cutaway view (editor-side state)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# 4. Set object pivot — pivot-point offset for rotation/scaling
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# 5. Apply material batch — apply a preset/color to multiple targets at once
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# 6. Set object layer — named-layer organization + per-layer visibility
# ---------------------------------------------------------------------------

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
