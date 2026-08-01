"""Viewport, playback, and session editor control tools.

These tools let the Agent drive editor functions that live entirely on the
frontend (viewport camera, animation playback, undo/redo history, panel
focus, grid snapping, render quality, viewport capture). Each tool emits an
``editor_*`` SceneDelta that the frontend dispatches to the matching local
store; the backend Scene itself is unchanged.
"""

from __future__ import annotations

from typing import Any, Dict, List

from trigen.scene import Scene
from trigen.tools.base import SceneDelta, ToolBase, ToolResult


_VIEWPORT_CAMERA_PARAMS = {
    "type": "object",
    "properties": {
        "position": {
            "type": "array",
            "items": {"type": "number"},
            "description": "Camera position [x, y, z]",
        },
        "target": {
            "type": "array",
            "items": {"type": "number"},
            "description": "Camera look-at target [x, y, z] (default [0, 0.5, 0])",
        },
        "smooth": {"type": "boolean", "description": "Animate the camera transition (default true)"},
    },
    "required": ["position"],
}


_PLAY_PARAMS = {
    "type": "object",
    "properties": {
        "from_start": {"type": "boolean", "description": "Restart from time 0 (default false)"},
    },
    "required": [],
}


_SEEK_PARAMS = {
    "type": "object",
    "properties": {
        "time": {"type": "number", "description": "Timeline position in seconds"},
    },
    "required": ["time"],
}


_SET_SELECTION_PARAMS = {
    "type": "object",
    "properties": {
        "targets": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Object ids or names to select (multi-selection)",
        },
        "clear": {"type": "boolean", "description": "Clear previous selection (default true)"},
    },
    "required": ["targets"],
}


_CAPTURE_VIEWPORT_PARAMS = {
    "type": "object",
    "properties": {
        "filename": {"type": "string", "description": "Output filename without extension (default viewport_<ts>)"},
        "download": {"type": "boolean", "description": "Trigger a browser download (default true)"},
    },
    "required": [],
}


_PLAYBACK_SPEED_PARAMS = {
    "type": "object",
    "properties": {
        "speed": {"type": "number", "description": "Playback speed multiplier (0.25 - 4.0)"},
    },
    "required": ["speed"],
}


_GRID_SNAP_PARAMS = {
    "type": "object",
    "properties": {
        "enabled": {"type": "boolean", "description": "Turn grid snapping on or off"},
        "increment": {"type": "number", "description": "Snap increment in world units (default 0.5)"},
    },
    "required": ["enabled"],
}


_FOCUS_PANEL_PARAMS = {
    "type": "object",
    "properties": {
        "panel": {
            "type": "string",
            "enum": ["layers", "outliner", "timeline", "properties", "scene"],
            "description": "Right panel tab to focus",
        },
    },
    "required": ["panel"],
}


_RENDER_QUALITY_PARAMS = {
    "type": "object",
    "properties": {
        "quality": {
            "type": "string",
            "enum": ["low", "medium", "high"],
            "description": "Viewport render quality (affects DPR / antialiasing)",
        },
    },
    "required": ["quality"],
}


class SetViewportCameraTool(ToolBase):
    """Move the interactive viewport camera to an explicit position + target."""

    name = "set_viewport_camera"
    description = "Position the viewport camera at a given position looking at a target. Use for precise viewpoint control."

    def schema(self) -> Dict[str, Any]:
        return _VIEWPORT_CAMERA_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        pos = arguments.get("position")
        if not isinstance(pos, list) or len(pos) != 3:
            return ToolResult(success=False, message="position must be [x, y, z]")
        target = arguments.get("target", [0, 0.5, 0])
        if not isinstance(target, list) or len(target) != 3:
            return ToolResult(success=False, message="target must be [x, y, z]")
        smooth = bool(arguments.get("smooth", True))
        cam_pos = [float(pos[0]), float(pos[1]), float(pos[2])]
        cam_target = [float(target[0]), float(target[1]), float(target[2])]
        return ToolResult(
            success=True,
            message=f"Viewport camera moved to {cam_pos} looking at {cam_target}",
            deltas=[SceneDelta(
                action="editor_viewport_camera",
                payload={"position": cam_pos, "target": cam_target, "smooth": smooth},
            )],
            data={"position": cam_pos, "target": cam_target},
        )


class PlayAnimationTool(ToolBase):
    """Start or resume timeline playback on the frontend."""

    name = "play_animation"
    description = "Start or resume animation playback in the viewport timeline."

    def schema(self) -> Dict[str, Any]:
        return _PLAY_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        from_start = bool(arguments.get("from_start", False))
        return ToolResult(
            success=True,
            message="Playback started" + (" from start" if from_start else ""),
            deltas=[SceneDelta(action="editor_play", payload={"from_start": from_start})],
        )


class PauseAnimationTool(ToolBase):
    """Pause timeline playback."""

    name = "pause_animation"
    description = "Pause animation playback, keeping the current playhead position."

    def schema(self) -> Dict[str, Any]:
        return {"type": "object", "properties": {}, "required": []}

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        return ToolResult(
            success=True,
            message="Playback paused",
            deltas=[SceneDelta(action="editor_pause", payload={})],
        )


class SeekAnimationTool(ToolBase):
    """Seek the timeline playhead to a specific time."""

    name = "seek_animation"
    description = "Seek the animation timeline to a specific time in seconds."

    def schema(self) -> Dict[str, Any]:
        return _SEEK_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        try:
            time_val = float(arguments.get("time", 0))
        except (TypeError, ValueError):
            return ToolResult(success=False, message="time must be a number")
        if time_val < 0:
            return ToolResult(success=False, message="time must be >= 0")
        return ToolResult(
            success=True,
            message=f"Timeline seeked to {time_val}s",
            deltas=[SceneDelta(action="editor_seek", payload={"time": time_val})],
        )


class SetSelectionTool(ToolBase):
    """Set multi-selection by object ids or names."""

    name = "set_selection"
    description = "Select multiple objects at once by id or name. Replaces or extends the current selection."

    def schema(self) -> Dict[str, Any]:
        return _SET_SELECTION_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        targets = arguments.get("targets")
        if not isinstance(targets, list) or not targets:
            return ToolResult(success=False, message="targets must be a non-empty array")
        objs = scene.find_objects([str(t) for t in targets])
        if not objs:
            return ToolResult(success=False, message="No matching objects found")
        ids = [o.id for o in objs]
        clear = bool(arguments.get("clear", True))
        names = ", ".join(o.name for o in objs[:5])
        if len(objs) > 5:
            names += f", ... ({len(objs)} total)"
        return ToolResult(
            success=True,
            message=f"Selected {len(objs)} object(s): {names}",
            deltas=[SceneDelta(action="editor_set_selection", payload={"ids": ids, "clear": clear})],
            data={"ids": ids},
        )


class CaptureViewportTool(ToolBase):
    """Request the frontend to capture the current viewport as an image."""

    name = "capture_viewport"
    description = "Capture the current viewport as a PNG image and trigger a download."

    def schema(self) -> Dict[str, Any]:
        return _CAPTURE_VIEWPORT_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        import time as _time
        filename = str(arguments.get("filename", "")).strip() or f"viewport_{int(_time.time())}"
        download = bool(arguments.get("download", True))
        return ToolResult(
            success=True,
            message=f"Viewport capture requested: {filename}.png",
            deltas=[SceneDelta(action="editor_capture_viewport", payload={"filename": filename, "download": download})],
            data={"filename": filename},
        )


class SetPlaybackSpeedTool(ToolBase):
    """Set the animation playback speed multiplier."""

    name = "set_playback_speed"
    description = "Set the animation playback speed multiplier (0.25 to 4.0)."

    def schema(self) -> Dict[str, Any]:
        return _PLAYBACK_SPEED_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        try:
            speed = float(arguments.get("speed", 1.0))
        except (TypeError, ValueError):
            return ToolResult(success=False, message="speed must be a number")
        if speed < 0.25 or speed > 4.0:
            return ToolResult(success=False, message="speed must be between 0.25 and 4.0")
        return ToolResult(
            success=True,
            message=f"Playback speed set to {speed}x",
            deltas=[SceneDelta(action="editor_set_playback_speed", payload={"speed": speed})],
            data={"speed": speed},
        )


class ToggleGridSnappingTool(ToolBase):
    """Enable or disable grid snapping with an optional increment."""

    name = "toggle_grid_snapping"
    description = "Enable or disable grid snapping for transform edits, with an optional snap increment."

    def schema(self) -> Dict[str, Any]:
        return _GRID_SNAP_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        enabled = bool(arguments.get("enabled"))
        increment = float(arguments.get("increment", 0.5))
        if increment <= 0:
            return ToolResult(success=False, message="increment must be > 0")
        state = "enabled" if enabled else "disabled"
        return ToolResult(
            success=True,
            message=f"Grid snapping {state} (increment {increment})",
            deltas=[SceneDelta(action="editor_toggle_grid_snapping", payload={"enabled": enabled, "increment": increment})],
            data={"enabled": enabled, "increment": increment},
        )


class FocusPanelTool(ToolBase):
    """Switch the right panel to a specific tab."""

    name = "focus_panel"
    description = "Switch the right panel to a specific tab (layers, outliner, timeline, properties, scene)."

    def schema(self) -> Dict[str, Any]:
        return _FOCUS_PANEL_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        panel = str(arguments.get("panel", "")).lower()
        valid = {"layers", "outliner", "timeline", "properties", "scene"}
        if panel not in valid:
            return ToolResult(success=False, message=f"panel must be one of {sorted(valid)}")
        return ToolResult(
            success=True,
            message=f"Panel focused: {panel}",
            deltas=[SceneDelta(action="editor_focus_panel", payload={"panel": panel})],
            data={"panel": panel},
        )


class UndoSceneTool(ToolBase):
    """Undo the last scene action on the frontend history stack."""

    name = "undo_scene"
    description = "Undo the last scene editing action (frontend history)."

    def schema(self) -> Dict[str, Any]:
        return {"type": "object", "properties": {}, "required": []}

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        return ToolResult(
            success=True,
            message="Undo requested",
            deltas=[SceneDelta(action="editor_undo", payload={})],
        )


class RedoSceneTool(ToolBase):
    """Redo the last undone scene action on the frontend history stack."""

    name = "redo_scene"
    description = "Redo the last undone scene action (frontend history)."

    def schema(self) -> Dict[str, Any]:
        return {"type": "object", "properties": {}, "required": []}

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        return ToolResult(
            success=True,
            message="Redo requested",
            deltas=[SceneDelta(action="editor_redo", payload={})],
        )


class SetRenderQualityTool(ToolBase):
    """Set the viewport render quality (low/medium/high)."""

    name = "set_render_quality"
    description = "Set the viewport render quality: low (faster), medium, or high (sharper)."

    def schema(self) -> Dict[str, Any]:
        return _RENDER_QUALITY_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        quality = str(arguments.get("quality", "medium")).lower()
        if quality not in ("low", "medium", "high"):
            return ToolResult(success=False, message="quality must be low, medium, or high")
        return ToolResult(
            success=True,
            message=f"Render quality set to {quality}",
            deltas=[SceneDelta(action="editor_set_render_quality", payload={"quality": quality})],
            data={"quality": quality},
        )
