"""Grid visibility tools.

Toggles scene grid visibility and adjusts grid size.
"""

from __future__ import annotations

from typing import Any, Dict

from trigen.scene import Scene
from trigen.tools.base import SceneDelta, ToolBase, ToolResult


_TOGGLE_GRID_PARAMS = {
    "type": "object",
    "properties": {
        "visible": {
            "type": "boolean",
            "description": "Whether visible; if omitted, toggles the current state",
        },
    },
    "required": [],
}


_SET_GRID_SIZE_PARAMS = {
    "type": "object",
    "properties": {
        "size": {"type": "number", "description": "Grid size (positive number)"},
    },
    "required": ["size"],
}


class ToggleGridTool(ToolBase):
    """Toggle grid visibility tool."""

    name = "toggle_grid"
    description = "Toggle scene grid visibility (on/off); can be set explicitly via the visible parameter."

    def schema(self) -> Dict[str, Any]:
        return _TOGGLE_GRID_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        old = scene.grid_visible
        if "visible" in arguments:
            scene.grid_visible = bool(arguments["visible"])
        else:
            scene.grid_visible = not scene.grid_visible
        state = "shown" if scene.grid_visible else "hidden"
        return ToolResult(
            success=True,
            message=f"Grid visibility: {old} -> {scene.grid_visible} ({state})",
            deltas=[SceneDelta(action="set_grid", payload={"grid_visible": scene.grid_visible})],
            data={"grid_visible": scene.grid_visible},
        )


class SetGridSizeTool(ToolBase):
    """Set grid size tool."""

    name = "set_grid_size"
    description = "Set the scene grid size."

    def schema(self) -> Dict[str, Any]:
        return _SET_GRID_SIZE_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        try:
            size = float(arguments.get("size", 0))
        except (TypeError, ValueError):
            return ToolResult(success=False, message="Grid size must be a number")
        if size <= 0:
            return ToolResult(success=False, message=f"Grid size must be positive, received {size}")
        old = scene.grid_size
        scene.grid_size = size
        return ToolResult(
            success=True,
            message=f"Grid size: {old} -> {scene.grid_size}",
            deltas=[SceneDelta(action="set_grid", payload={"grid_size": scene.grid_size})],
            data={"grid_size": scene.grid_size},
        )
