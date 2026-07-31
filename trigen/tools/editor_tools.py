"""Editor control tools.

Exposes selection and camera focus operations so the Agent can drive the
editor viewport via natural language. These tools do not mutate the scene
geometry but emit editor-control events that the frontend consumes.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List

from trigen.scene import Scene
from trigen.tools.base import SceneDelta, ToolBase, ToolResult


_SELECT_PARAMS = {
    "type": "object",
    "properties": {
        "target": {"type": "string", "description": "Target object id or name"},
        "clear": {"type": "boolean", "description": "Whether to clear other selections (default true)"},
    },
    "required": ["target"],
}


_FOCUS_PARAMS = {
    "type": "object",
    "properties": {
        "target": {"type": "string", "description": "Target object id or name"},
        "distance": {"type": "number", "description": "Camera distance (default 5)"},
    },
    "required": ["target"],
}


_LOCK_PARAMS = {
    "type": "object",
    "properties": {
        "target": {"type": "string", "description": "Target object id or name"},
        "locked": {"type": "boolean", "description": "Lock state (default true)"},
    },
    "required": ["target"],
}


_VISIBILITY_PARAMS = {
    "type": "object",
    "properties": {
        "target": {"type": "string", "description": "Target object id or name"},
        "visible": {"type": "boolean", "description": "Visibility state (default true)"},
    },
    "required": ["target"],
}


_RENAME_PARAMS = {
    "type": "object",
    "properties": {
        "target": {"type": "string", "description": "Target object id or name"},
        "name": {"type": "string", "description": "New object name"},
    },
    "required": ["target", "name"],
}


_TRANSFORM_MODE_PARAMS = {
    "type": "object",
    "properties": {
        "mode": {
            "type": "string",
            "enum": ["translate", "rotate", "scale"],
            "description": "Gizmo interaction mode",
        },
    },
    "required": ["mode"],
}


_FRAME_VIEW_PARAMS = {
    "type": "object",
    "properties": {
        "targets": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Object ids or names to frame; if omitted, frames all objects",
        },
        "target": {"type": "string", "description": "Single object id or name to frame (ignored when targets is set)"},
        "distance": {"type": "number", "description": "Extra distance margin factor (default 1.5)"},
    },
    "required": [],
}


class SelectObjectTool(ToolBase):
    """Select object tool.

    Emits an editor-control event so the frontend highlights the object
    and switches the right panel to its properties.
    """

    name = "select_object"
    description = "Select the specified object, linked to the editor properties panel."

    def schema(self) -> Dict[str, Any]:
        return _SELECT_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        target_id = arguments.get("target", "")
        obj = scene.find_object(target_id)
        if not obj:
            return ToolResult(success=False, message=f"Object not found: {target_id}")

        return ToolResult(
            success=True,
            message=f"Selected {obj.name}",
            deltas=[SceneDelta(action="editor_select", target_id=obj.id, payload={"clear": bool(arguments.get("clear", True))})],
            data={"selected_id": obj.id, "selected_name": obj.name},
        )


class FocusObjectTool(ToolBase):
    """Focus object tool.

    Emits an editor-control event so the frontend camera moves to frame
    the target object.
    """

    name = "focus_object"
    description = "Focus the camera on the specified object."

    def schema(self) -> Dict[str, Any]:
        return _FOCUS_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        target_id = arguments.get("target", "")
        obj = scene.find_object(target_id)
        if not obj:
            return ToolResult(success=False, message=f"Object not found: {target_id}")

        distance = float(arguments.get("distance", 5.0))
        # Compute a camera position offset from the object
        pos = obj.transform.position
        cam_pos = [pos[0] + distance * 0.7, pos[1] + distance * 0.5, pos[2] + distance * 0.7]

        return ToolResult(
            success=True,
            message=f"Focused on {obj.name}, camera position {cam_pos}",
            deltas=[
                SceneDelta(
                    action="editor_focus",
                    target_id=obj.id,
                    payload={
                        "target": pos,
                        "camera_position": cam_pos,
                        "distance": distance,
                    },
                )
            ],
            data={
                "focus_id": obj.id,
                "focus_name": obj.name,
                "camera_position": cam_pos,
                "target": pos,
            },
        )


class LockObjectTool(ToolBase):
    """Lock or unlock an object so the editor gizmo cannot move it."""

    name = "lock_object"
    description = "Lock or unlock an object, preventing or allowing transform edits in the editor."

    def schema(self) -> Dict[str, Any]:
        return _LOCK_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        target_id = arguments.get("target", "")
        obj = scene.find_object(target_id)
        if not obj:
            return ToolResult(success=False, message=f"Object not found: {target_id}")
        locked = bool(arguments.get("locked", True))
        obj.locked = locked
        state = "locked" if locked else "unlocked"
        return ToolResult(
            success=True,
            message=f"{obj.name} is now {state}",
            deltas=[SceneDelta(action="update", target_id=obj.id, payload=obj.to_dict())],
            data={"object": obj.to_dict(), "locked": locked},
        )


class SetVisibilityTool(ToolBase):
    """Toggle object visibility."""

    name = "set_visibility"
    description = "Show or hide an object in the viewport without removing it from the scene."

    def schema(self) -> Dict[str, Any]:
        return _VISIBILITY_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        target_id = arguments.get("target", "")
        obj = scene.find_object(target_id)
        if not obj:
            return ToolResult(success=False, message=f"Object not found: {target_id}")
        visible = bool(arguments.get("visible", True))
        obj.visible = visible
        state = "visible" if visible else "hidden"
        return ToolResult(
            success=True,
            message=f"{obj.name} is now {state}",
            deltas=[SceneDelta(action="update", target_id=obj.id, payload=obj.to_dict())],
            data={"object": obj.to_dict(), "visible": visible},
        )


class RenameObjectTool(ToolBase):
    """Rename an existing object."""

    name = "rename_object"
    description = "Rename an existing object. Subsequent tool calls can reference the new name."

    def schema(self) -> Dict[str, Any]:
        return _RENAME_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        target_id = arguments.get("target", "")
        obj = scene.find_object(target_id)
        if not obj:
            return ToolResult(success=False, message=f"Object not found: {target_id}")
        new_name = str(arguments.get("name", "")).strip()
        if not new_name:
            return ToolResult(success=False, message="New name must be a non-empty string")
        old_name = obj.name
        # Ensure the new name does not collide with another object's name
        for other in scene.objects:
            if other is not obj and other.name.lower() == new_name.lower():
                return ToolResult(success=False, message=f"Name '{new_name}' is already in use")
        obj.name = scene.next_auto_name(new_name) if new_name == old_name else new_name
        return ToolResult(
            success=True,
            message=f"Renamed {old_name} -> {obj.name}",
            deltas=[SceneDelta(action="update", target_id=obj.id, payload=obj.to_dict())],
            data={"object": obj.to_dict(), "old_name": old_name, "new_name": obj.name},
        )


class SetTransformModeTool(ToolBase):
    """Switch the editor gizmo interaction mode (translate/rotate/scale)."""

    name = "set_transform_mode"
    description = "Switch the editor gizmo mode to translate, rotate, or scale for the selected object."

    def schema(self) -> Dict[str, Any]:
        return _TRANSFORM_MODE_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        mode = str(arguments.get("mode", "translate")).lower()
        if mode not in ("translate", "rotate", "scale"):
            return ToolResult(success=False, message=f"Invalid mode: {mode}")
        return ToolResult(
            success=True,
            message=f"Gizmo mode set to {mode}",
            deltas=[SceneDelta(action="editor_transform_mode", payload={"mode": mode})],
            data={"mode": mode},
        )


class FrameViewTool(ToolBase):
    """Frame the viewport camera around one or more objects' bounding boxes."""

    name = "frame_view"
    description = "Frame the viewport camera around one or more objects (or the whole scene when no target is given)."

    def schema(self) -> Dict[str, Any]:
        return _FRAME_VIEW_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        targets_arg = arguments.get("targets")
        objs: List = []
        if isinstance(targets_arg, list) and targets_arg:
            objs = scene.find_objects([str(t) for t in targets_arg])
        elif arguments.get("target"):
            single = scene.find_object(str(arguments.get("target")))
            objs = [single] if single else []
        if not objs:
            objs = list(scene.objects)
        if not objs:
            return ToolResult(success=False, message="No objects to frame")

        # Compute combined bounding-box center and extent
        mins = [math.inf, math.inf, math.inf]
        maxs = [-math.inf, -math.inf, -math.inf]
        for o in objs:
            op = o.transform.position
            sx, sy, sz = o.transform.scale
            # Use a unit-half-extent fallback scaled by object scale
            ext = [0.5 * sx, 0.5 * sy, 0.5 * sz]
            for i in range(3):
                mins[i] = min(mins[i], op[i] - ext[i])
                maxs[i] = max(maxs[i], op[i] + ext[i])
        center = [(mins[i] + maxs[i]) / 2.0 for i in range(3)]
        extent = [max(1e-3, maxs[i] - mins[i]) for i in range(3)]
        margin = float(arguments.get("distance", 1.5))
        radius = max(extent) * margin
        # Place the camera along a diagonal so all axes are visible
        cam_pos = [
            center[0] + radius * 0.7,
            center[1] + radius * 0.5,
            center[2] + radius * 0.7,
        ]
        names = ", ".join(o.name for o in objs[:5])
        if len(objs) > 5:
            names += f", ... ({len(objs)} total)"
        return ToolResult(
            success=True,
            message=f"Framed {len(objs)} object(s): {names}; camera {cam_pos} -> {center}",
            deltas=[
                SceneDelta(
                    action="editor_focus",
                    payload={
                        "targets": [o.id for o in objs],
                        "target": center,
                        "camera_position": cam_pos,
                        "extent": extent,
                        "distance": radius,
                    },
                )
            ],
            data={
                "targets": [o.id for o in objs],
                "center": center,
                "extent": extent,
                "camera_position": cam_pos,
            },
        )
