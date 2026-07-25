"""Editor control tools.

Exposes selection and camera focus operations so the Agent can drive the
editor viewport via natural language. These tools do not mutate the scene
geometry but emit editor-control events that the frontend consumes.
"""

from __future__ import annotations

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
