"""Viewport control gap tools.

Four Agent-callable tools that close the remaining viewport-control gaps
between the backend tool registry and the 3D editor surface:

  * ``set_xray_mode`` — toggle X-ray (see-through) viewport mode so the
    Agent can peer through occluding geometry to inspect or select
    objects behind it. Emits an ``editor_set_xray`` delta.
  * ``set_selection_color`` — set the highlight color used to outline the
    active selection in the viewport. Emits an
    ``editor_set_selection_color`` delta.
  * ``snap_selection_to_ground`` — drop one or more objects so their
    lowest point rests on a floor plane (default y=0). Mutates scene
    transforms and emits ``update`` deltas per object. Distinct from
    ``reset_transform`` (single-object, also resets rotation/scale).
  * ``set_viewport_resolution`` — set a granular viewport render scale
    (0.25x - 2.0x) controlling the device pixel ratio. Complements
    ``set_render_quality`` (low/medium/high presets) with explicit
    numeric control. Emits an ``editor_set_viewport_resolution`` delta.
"""

from __future__ import annotations

from typing import Any, Dict, List

from trigen.scene import Scene
from trigen.tools.base import SceneDelta, ToolBase, ToolResult


# --- set_xray_mode ---------------------------------------------------------

_SET_XRAY_MODE_PARAMS = {
    "type": "object",
    "properties": {
        "enabled": {
            "type": "boolean",
            "description": "Turn X-ray (see-through) viewport mode on or off.",
        },
        "opacity": {
            "type": "number",
            "description": "Object transparency when X-ray is active (0.05 - 1.0, default 0.5).",
        },
    },
    "required": ["enabled"],
}


class SetXrayModeTool(ToolBase):
    """Toggle X-ray (see-through) viewport mode.

    When enabled, the viewport renders occluding objects semi-transparently
    so the Agent can inspect, select, or place geometry behind them.
    Mirrors the ``set_shadows`` / ``set_minimap`` editor-state tools.
    """

    name = "set_xray_mode"
    description = (
        "Toggle X-ray (see-through) viewport mode so occluding objects render "
        "semi-transparently, revealing geometry behind them. Optional opacity "
        "controls the transparency strength."
    )

    def schema(self) -> Dict[str, Any]:
        return _SET_XRAY_MODE_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        enabled = bool(arguments.get("enabled", False))
        try:
            opacity = float(arguments.get("opacity", 0.5))
        except (TypeError, ValueError):
            return ToolResult(success=False, message="opacity must be a number")
        if opacity < 0.05 or opacity > 1.0:
            return ToolResult(success=False, message="opacity must be between 0.05 and 1.0")
        payload: Dict[str, Any] = {"enabled": enabled, "opacity": opacity}
        return ToolResult(
            success=True,
            message=f"X-ray mode {'enabled' if enabled else 'disabled'} (opacity {opacity}).",
            deltas=[SceneDelta(action="editor_set_xray", payload=payload)],
            data=payload,
        )


# --- set_selection_color ---------------------------------------------------

_SET_SELECTION_COLOR_PARAMS = {
    "type": "object",
    "properties": {
        "color": {
            "type": "string",
            "description": "Highlight color (hex, e.g. '#00F0FF') used to outline the active selection.",
        },
    },
    "required": ["color"],
}


class SetSelectionColorTool(ToolBase):
    """Set the viewport selection highlight color.

    Controls the outline / tint color applied to the active selection in
    the viewport. Useful for accessibility (high-contrast highlights) or
    to match a project's accent palette.
    """

    name = "set_selection_color"
    description = (
        "Set the viewport highlight color for the active selection (hex color). "
        "Use for high-contrast outlines or to match a project accent palette."
    )

    def schema(self) -> Dict[str, Any]:
        return _SET_SELECTION_COLOR_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        color = str(arguments.get("color", "")).strip()
        if not color:
            return ToolResult(success=False, message="color is required")
        if not color.startswith("#") or len(color) not in (4, 7):
            return ToolResult(
                success=False,
                message="color must be a hex string like '#00F0FF' or '#0FF'",
            )
        payload = {"color": color}
        return ToolResult(
            success=True,
            message=f"Selection highlight color set to {color}.",
            deltas=[SceneDelta(action="editor_set_selection_color", payload=payload)],
            data=payload,
        )


# --- snap_selection_to_ground ----------------------------------------------

_SNAP_TO_GROUND_PARAMS = {
    "type": "object",
    "properties": {
        "targets": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Object ids or names to ground. If omitted, every object in the scene is grounded.",
        },
        "floor": {
            "type": "number",
            "description": "World Y position of the ground plane (default 0.0).",
        },
    },
    "required": [],
}


def _bbox_min_y(obj: Any) -> float:
    """Approximate the lowest Y of an object based on geometry + scale.

    Mirrors the helper in ``advanced_editor_tools`` so this module stays
    self-contained without importing a private symbol.
    """
    geo_type = obj.geometry.type
    sy = obj.transform.scale[1]
    py = obj.transform.position[1]
    if geo_type in ("box", "cylinder", "capsule", "cone", "sphere", "torus", "icosahedron", "dodecahedron", "octahedron", "tetrahedron", "torusKnot"):
        return py - sy
    if geo_type == "plane":
        return py
    return py - sy


class SnapSelectionToGroundTool(ToolBase):
    """Drop one or more objects so their lowest point rests on a floor plane.

    Mutates each target's ``transform.position.y`` so the object's
    bounding-box minimum Y equals the floor value (default 0.0). Emits one
    ``update`` delta per moved object. Distinct from ``reset_transform``
    (single-object, also resets rotation/scale): this tool only adjusts Y
    and operates on a multi-object selection or the whole scene at once.
    """

    name = "snap_selection_to_ground"
    description = (
        "Drop one or more objects so their lowest point rests on a floor "
        "plane (default y=0). Accepts a list of targets; if omitted, grounds "
        "every object in the scene. Only adjusts the Y position."
    )

    def schema(self) -> Dict[str, Any]:
        return _SNAP_TO_GROUND_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        try:
            floor = float(arguments.get("floor", 0.0))
        except (TypeError, ValueError):
            return ToolResult(success=False, message="floor must be a number")

        targets_arg = arguments.get("targets")
        if isinstance(targets_arg, list) and targets_arg:
            objs = scene.find_objects([str(t) for t in targets_arg])
        else:
            objs = list(scene.objects)

        if not objs:
            return ToolResult(success=False, message="No objects to ground")

        deltas: List[SceneDelta] = []
        moved: List[str] = []
        skipped: List[str] = []
        for obj in objs:
            if obj.locked:
                skipped.append(obj.name)
                continue
            min_y = _bbox_min_y(obj)
            offset = floor - min_y
            # Skip objects already resting on (or below) the floor.
            if abs(offset) < 1e-6:
                continue
            obj.transform.position[1] = obj.transform.position[1] + offset
            deltas.append(
                SceneDelta(action="update", target_id=obj.id, payload={"transform": obj.transform.to_dict()})
            )
            moved.append(obj.name)

        if not moved:
            return ToolResult(
                success=True,
                message="All objects already rest on the floor; nothing to ground.",
                data={"floor": floor, "moved": 0, "skipped": skipped},
            )

        names = ", ".join(moved[:5])
        if len(moved) > 5:
            names += f", ... ({len(moved)} total)"
        message = f"Grounded {len(moved)} object(s) to y={floor}: {names}"
        if skipped:
            message += f"; skipped {len(skipped)} locked object(s)"
        return ToolResult(
            success=True,
            message=message,
            deltas=deltas,
            data={"floor": floor, "moved": len(moved), "moved_names": moved, "skipped": skipped},
        )


# --- set_viewport_resolution -----------------------------------------------

_SET_VIEWPORT_RESOLUTION_PARAMS = {
    "type": "object",
    "properties": {
        "scale": {
            "type": "number",
            "description": "Viewport render scale multiplier (0.25 - 2.0). 1.0 = native pixel ratio; lower is faster, higher is sharper.",
        },
    },
    "required": ["scale"],
}


class SetViewportResolutionTool(ToolBase):
    """Set a granular viewport render scale.

    Controls the device pixel ratio used by the viewport renderer as a
    continuous scale factor. Complements ``set_render_quality`` (which
    exposes low/medium/high presets) with explicit numeric control for
    cases where the Agent needs a precise trade-off between sharpness and
    frame rate.
    """

    name = "set_viewport_resolution"
    description = (
        "Set the viewport render scale (0.25 - 2.0) controlling the device "
        "pixel ratio. Lower values are faster (lower resolution); higher "
        "values are sharper (supersampled). Complements set_render_quality."
    )

    def schema(self) -> Dict[str, Any]:
        return _SET_VIEWPORT_RESOLUTION_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        try:
            scale = float(arguments.get("scale", 1.0))
        except (TypeError, ValueError):
            return ToolResult(success=False, message="scale must be a number")
        if scale < 0.25 or scale > 2.0:
            return ToolResult(success=False, message="scale must be between 0.25 and 2.0")
        payload = {"scale": scale}
        return ToolResult(
            success=True,
            message=f"Viewport render scale set to {scale}x.",
            deltas=[SceneDelta(action="editor_set_viewport_resolution", payload=payload)],
            data=payload,
        )
