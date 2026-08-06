"""Cinematic storyboard tools — sequence-level camera direction.

Lets the Agent compose, edit, and play a scripted camera tour of the scene.
A storyboard is a scene-level, ordered list of shots (each a camera pose,
duration, and easing curve); when played, the viewport camera glides
between them to narrate the scene like a film sequence.

These tools read/write ``Scene.storyboard`` (a plain dict), so the storyboard
persists with the scene, round-trips through checkpoints, and reaches the
frontend via the ordinary scene-update channel. Playback state is also stored
on the storyboard so the frontend camera rig can drive itself without extra
round-trips.

1. ``ComposeStoryTool``  — compose_story: create/replace the storyboard.
2. ``AddShotTool``       — add_shot: append a shot to the storyboard.
3. ``UpdateShotTool``    — update_shot: edit a shot's fields.
4. ``RemoveShotTool``    — remove_shot: delete a shot.
5. ``ListStoryTool``     — list_story: read the storyboard.
6. ``ClearStoryTool``    — clear_story: remove the storyboard.
7. ``PlayStoryTool``     — play_story: set playback state (play/pause/stop/speed).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from trigen.scene import Scene
from trigen.storyboard import (
    DEFAULT_EASING,
    EASINGS,
    new_shot,
    new_storyboard,
    total_duration,
    update_shot_fields,
)
from trigen.tools.base import SceneDelta, ToolBase, ToolResult


def _story(scene: Scene) -> Optional[Dict[str, Any]]:
    """Return the scene storyboard (may be None)."""
    return scene.storyboard


def _ensure(scene: Scene) -> Dict[str, Any]:
    """Return the storyboard, creating an empty one if absent."""
    if scene.storyboard is None:
        scene.storyboard = new_storyboard("Untitled scene", shots=[])
    return scene.storyboard


def _story_delta(action: str, storyboard: Dict[str, Any]) -> SceneDelta:
    """A delta that carries the full storyboard so the frontend can sync."""
    return SceneDelta(action=action, payload={"storyboard": storyboard})


_COMPOSE_PARAMS = {
    "type": "object",
    "properties": {
        "title": {
            "type": "string",
            "description": "A short title for the cinematic sequence, e.g. 'Hero reveal'.",
        },
        "shots": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Shot name, e.g. 'Wide establishing'."},
                    "position": {"type": "array", "items": {"type": "number"}, "description": "Camera position [x, y, z]."},
                    "target": {"type": "array", "items": {"type": "number"}, "description": "Look-at target [x, y, z]."},
                    "fov": {"type": "number", "description": "Field of view in degrees."},
                    "duration": {"type": "number", "description": "Shot duration in seconds."},
                    "easing": {"type": "string", "enum": list(EASINGS), "description": "Camera easing between shots."},
                    "description": {"type": "string", "description": "Optional shot description."},
                },
            },
            "description": "Ordered list of shot dictionaries composing the sequence.",
        },
        "loop": {"type": "boolean", "description": "Loop the sequence forever (default true)."},
    },
    "required": ["shots"],
}


class ComposeStoryTool(ToolBase):
    """Create or replace the cinematic storyboard from a shot list."""

    name = "compose_story"
    description = (
        "Compose a cinematic storyboard: an ordered sequence of camera shots "
        "(position, look-at target, fov, duration, easing) that plays as a "
        "scripted camera tour of the scene. Use this to plan a film-like "
        "reveal, flythrough, or product showcase. Replaces any existing "
        "storyboard. Provide a title and at least one shot."
    )

    def schema(self) -> Dict[str, Any]:
        return _COMPOSE_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        raw_shots = arguments.get("shots")
        if not isinstance(raw_shots, list) or len(raw_shots) == 0:
            return ToolResult(
                success=False,
                message="compose_story requires at least one shot.",
                deltas=[],
                data={},
            )
        title = str(arguments.get("title") or "Untitled scene")
        loop = bool(arguments.get("loop", True))
        storyboard = new_storyboard(title, raw_shots, loop=loop)
        scene.storyboard = storyboard
        return ToolResult(
            success=True,
            message=(
                f"Composed storyboard '{title}' with {len(storyboard['shots'])} shot(s), "
                f"~{total_duration(storyboard):.1f}s total."
            ),
            deltas=[_story_delta("update_storyboard", storyboard)],
            data={"storyboard": storyboard},
        )


_ADD_SHOT_PARAMS = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "description": "Shot name."},
        "position": {"type": "array", "items": {"type": "number"}, "description": "Camera position [x, y, z]."},
        "target": {"type": "array", "items": {"type": "number"}, "description": "Look-at target [x, y, z]."},
        "fov": {"type": "number", "description": "Field of view in degrees."},
        "duration": {"type": "number", "description": "Shot duration in seconds (default 3)."},
        "easing": {"type": "string", "enum": list(EASINGS), "description": "Easing between shots."},
        "description": {"type": "string", "description": "Optional description."},
    },
    "required": [],
}


class AddShotTool(ToolBase):
    """Append a shot to the current storyboard."""

    name = "add_shot"
    description = (
        "Append a camera shot to the scene's cinematic storyboard. Creates "
        "the storyboard if none exists. Use this to extend an existing "
        "sequence one shot at a time (e.g. 'add a close-up shot of the "
        "tower')."
    )

    def schema(self) -> Dict[str, Any]:
        return _ADD_SHOT_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        storyboard = _ensure(scene)
        shot = new_shot(
            name=str(arguments.get("name") or f"Shot {len(storyboard['shots']) + 1}"),
            position=arguments.get("position"),
            target=arguments.get("target"),
            fov=arguments.get("fov"),
            duration=arguments.get("duration"),
            easing=arguments.get("easing"),
            description=str(arguments.get("description") or ""),
        )
        storyboard["shots"].append(shot)
        return ToolResult(
            success=True,
            message=f"Added shot '{shot['name']}' to storyboard '{storyboard['title']}'.",
            deltas=[_story_delta("update_storyboard", storyboard)],
            data={"shot": shot, "storyboard": storyboard},
        )


_UPDATE_SHOT_PARAMS = {
    "type": "object",
    "properties": {
        "shot_id": {"type": "string", "description": "Id of the shot to edit."},
        "name": {"type": "string", "description": "New shot name."},
        "position": {"type": "array", "items": {"type": "number"}, "description": "New camera position [x, y, z]."},
        "target": {"type": "array", "items": {"type": "number"}, "description": "New look-at target [x, y, z]."},
        "fov": {"type": "number", "description": "New field of view."},
        "duration": {"type": "number", "description": "New duration in seconds."},
        "easing": {"type": "string", "enum": list(EASINGS), "description": "New easing."},
        "description": {"type": "string", "description": "New description."},
    },
    "required": ["shot_id"],
}


class UpdateShotTool(ToolBase):
    """Edit a shot in the storyboard."""

    name = "update_shot"
    description = (
        "Edit one shot in the scene's cinematic storyboard by id. You can "
        "change its name, camera position, look-at target, fov, duration, "
        "easing, or description. Use list_story to get shot ids."
    )

    def schema(self) -> Dict[str, Any]:
        return _UPDATE_SHOT_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        storyboard = _story(scene)
        if not storyboard:
            return ToolResult(
                success=False,
                message="No storyboard exists yet. Use compose_story first.",
                deltas=[],
                data={},
            )
        shot_id = arguments.get("shot_id")
        shot = next((s for s in storyboard["shots"] if s.get("id") == shot_id), None)
        if shot is None:
            return ToolResult(
                success=False,
                message=(
                    f"Shot '{shot_id}' not found. "
                    f"Available: {[s.get('id') for s in storyboard['shots']]}"
                ),
                deltas=[],
                data={},
            )
        changed = update_shot_fields(shot, arguments)
        if not changed:
            return ToolResult(
                success=False,
                message="No valid shot fields provided to update.",
                deltas=[],
                data={},
            )
        return ToolResult(
            success=True,
            message=f"Updated shot '{shot['name']}': {', '.join(changed)}.",
            deltas=[_story_delta("update_storyboard", storyboard)],
            data={"shot": shot, "storyboard": storyboard},
        )


_REMOVE_SHOT_PARAMS = {
    "type": "object",
    "properties": {
        "shot_id": {"type": "string", "description": "Id of the shot to remove."},
    },
    "required": ["shot_id"],
}


class RemoveShotTool(ToolBase):
    """Remove a shot from the storyboard."""

    name = "remove_shot"
    description = (
        "Remove a shot from the scene's cinematic storyboard by id. "
        "Use list_story to get shot ids."
    )

    def schema(self) -> Dict[str, Any]:
        return _REMOVE_SHOT_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        storyboard = _story(scene)
        if not storyboard:
            return ToolResult(success=False, message="No storyboard exists.", deltas=[], data={})
        shot_id = arguments.get("shot_id")
        before = len(storyboard["shots"])
        storyboard["shots"] = [s for s in storyboard["shots"] if s.get("id") != shot_id]
        if len(storyboard["shots"]) == before:
            return ToolResult(
                success=False,
                message=f"Shot '{shot_id}' not found.",
                deltas=[],
                data={},
            )
        return ToolResult(
            success=True,
            message=f"Removed shot '{shot_id}'. {len(storyboard['shots'])} shot(s) remain.",
            deltas=[_story_delta("update_storyboard", storyboard)],
            data={"storyboard": storyboard},
        )


class ListStoryTool(ToolBase):
    """Read the current storyboard."""

    name = "list_story"
    description = (
        "List the scene's cinematic storyboard: its title, total duration, "
        "and every shot (name, camera position, look-at target, fov, "
        "duration, easing). Does not mutate the scene."
    )

    def schema(self) -> Dict[str, Any]:
        return {"type": "object", "properties": {}, "required": []}

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        storyboard = _story(scene)
        if not storyboard:
            return ToolResult(
                success=True,
                message="No storyboard composed yet.",
                deltas=[],
                data={"storyboard": None, "shots": [], "total_duration": 0.0},
            )
        return ToolResult(
            success=True,
            message=(
                f"Storyboard '{storyboard['title']}': {len(storyboard['shots'])} shot(s), "
                f"~{total_duration(storyboard):.1f}s total."
            ),
            deltas=[],
            data={
                "storyboard": storyboard,
                "shots": storyboard["shots"],
                "total_duration": total_duration(storyboard),
            },
        )


class ClearStoryTool(ToolBase):
    """Remove the storyboard from the scene."""

    name = "clear_story"
    description = (
        "Remove the scene's cinematic storyboard entirely. The viewport "
        "returns to free-orbit control."
    )

    def schema(self) -> Dict[str, Any]:
        return {"type": "object", "properties": {}, "required": []}

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        if scene.storyboard is None:
            return ToolResult(
                success=True,
                message="No storyboard to clear.",
                deltas=[],
                data={"storyboard": None},
            )
        scene.storyboard = None
        return ToolResult(
            success=True,
            message="Cleared the cinematic storyboard.",
            deltas=[SceneDelta(action="clear_storyboard", payload={})],
            data={"storyboard": None},
        )


_PLAY_PARAMS = {
    "type": "object",
    "properties": {
        "mode": {
            "type": "string",
            "enum": ["play", "pause", "stop"],
            "description": "Playback action: play starts/resumes, pause holds, stop resets to the first shot.",
        },
        "speed": {"type": "number", "description": "Playback speed multiplier (0.25 - 4.0)."},
        "index": {"type": "integer", "description": "The shot to jump to before playing (0-based)."},
    },
    "required": ["mode"],
}


class PlayStoryTool(ToolBase):
    """Control storyboard playback."""

    name = "play_story"
    description = (
        "Start, pause, or stop the scene's cinematic storyboard playback. "
        "When playing, the viewport camera glides through the shot sequence. "
        "Optionally set the playback speed and the starting shot index."
    )

    def schema(self) -> Dict[str, Any]:
        return _PLAY_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        storyboard = _story(scene)
        if not storyboard:
            return ToolResult(
                success=False,
                message="No storyboard to play. Use compose_story first.",
                deltas=[],
                data={},
            )
        mode = str(arguments.get("mode") or "play")
        if mode == "play":
            storyboard["playing"] = True
        elif mode == "pause":
            storyboard["playing"] = False
        elif mode == "stop":
            storyboard["playing"] = False
            storyboard["index"] = 0
        else:
            return ToolResult(
                success=False,
                message=f"Unknown mode '{mode}' (expected play/pause/stop).",
                deltas=[],
                data={},
            )
        if "speed" in arguments:
            storyboard["speed"] = max(0.25, min(4.0, float(arguments["speed"])))
        if "index" in arguments:
            idx = int(arguments["index"])
            if 0 <= idx < len(storyboard["shots"]):
                storyboard["index"] = idx
        return ToolResult(
            success=True,
            message=f"Storyboard {mode}.",
            deltas=[_story_delta("update_storyboard", storyboard)],
            data={"storyboard": storyboard, "playing": storyboard["playing"]},
        )