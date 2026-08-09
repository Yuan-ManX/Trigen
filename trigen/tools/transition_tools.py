"""Scene transition tools — AI-native motion choreography.

These tools author and drive smooth animated morphs between scene states.
A transition is a scene-level descriptor that tells the viewport to
interpolate a set of objects from their current transform to a described
target transform over a duration, with an easing curve. This is the
platform's "motion choreography" layer: a user can say "gently float the
sphere up and slide the box to the right over two seconds" and the Agent
materializes that as a reusable transition.

Transitions are stored on ``Scene.transitions`` (a plain dict list for
forward compatibility) and ``Scene.active_transition`` names the one the
viewport is currently playing. No external animation engine is required —
the renderer interpolates transforms each frame, so the capability is
self-contained and offline-safe.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from trigen.scene import Scene
from trigen.tools.base import SceneDelta, ToolBase, ToolResult

_TRANSITION_EASINGS = ["linear", "easeIn", "easeOut", "easeInOut"]


def _gen_id() -> str:
    return f"tr_{uuid.uuid4().hex[:8]}"


def _vec(arg: Any, default: List[float]) -> Optional[List[float]]:
    """Coerce an argument into a 3-float vector, or None when invalid."""
    if isinstance(arg, (list, tuple)) and len(arg) >= 3:
        try:
            return [float(arg[0]), float(arg[1]), float(arg[2])]
        except (TypeError, ValueError):
            return None
    return None


def _find_transition(scene: Scene, identifier: str) -> Optional[Dict[str, Any]]:
    """Look up a transition by id or name."""
    for tr in scene.transitions:
        if tr.get("id") == identifier or tr.get("name", "").lower() == identifier.lower():
            return tr
    return None


# ---------------------------------------------------------------------------
# create_scene_transition
# ---------------------------------------------------------------------------
_CREATE_TRANSITION_PARAMS = {
    "type": "object",
    "properties": {
        "name": {
            "type": "string",
            "description": "A short name for the transition (default 'transition').",
        },
        "targets": {
            "type": "array",
            "description": (
                "Target states to morph to. Each entry: {target: object id/name, "
                "position: [x,y,z], rotation: [rx,ry,rz], scale: [sx,sy,sz]}. "
                "Any field omitted is left unchanged."
            ),
            "items": {
                "type": "object",
                "properties": {
                    "target": {"type": "string", "description": "Object id or name."},
                    "position": {
                        "type": "array",
                        "items": {"type": "number"},
                        "description": "Target position [x, y, z].",
                    },
                    "rotation": {
                        "type": "array",
                        "items": {"type": "number"},
                        "description": "Target Euler rotation [rx, ry, rz].",
                    },
                    "scale": {
                        "type": "array",
                        "items": {"type": "number"},
                        "description": "Target scale [sx, sy, sz].",
                    },
                },
                "required": ["target"],
            },
        },
        "duration": {
            "type": "number",
            "description": "Transition duration in seconds (default 2.0).",
        },
        "easing": {
            "type": "string",
            "enum": _TRANSITION_EASINGS,
            "description": "Easing curve (default easeInOut).",
        },
        "loop": {
            "type": "boolean",
            "description": "Loop the transition (default false).",
        },
        "scope": {
            "type": "string",
            "enum": ["targets", "all", "selected"],
            "description": "When 'all', targets morph every object (targets ignored).",
        },
    },
    "required": [],
}


class CreateSceneTransitionTool(ToolBase):
    """Author a reusable scene transition between object states.

    Snapshots the current transform of each target as the 'from' state and
    records the described 'to' state. The viewport interpolates between
    them when the transition is played. Read/write — adds a transition.
    """

    name = "create_scene_transition"
    description = (
        "Create a smooth animated transition that morphs one or more objects "
        "from their current state to a described target state over a duration. "
        "Use it to choreograph motion — slide, lift, rotate, or scale objects "
        "as a coordinated scene move."
    )

    def schema(self) -> Dict[str, Any]:
        return _CREATE_TRANSITION_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        name = str(arguments.get("name", "")).strip() or "transition"
        duration = float(arguments.get("duration", 2.0))
        if duration <= 0:
            duration = 2.0
        easing = str(arguments.get("easing", "easeInOut"))
        if easing not in _TRANSITION_EASINGS:
            easing = "easeInOut"
        loop = bool(arguments.get("loop", False))
        scope = str(arguments.get("scope", "targets"))

        # Resolve which objects participate.
        targets: List[Dict[str, Any]] = []
        if scope == "all":
            for obj in scene.objects:
                targets.append({"target": obj.id, "position": obj.transform.position})
        elif scope == "selected":
            selected = [o for o in scene.objects if getattr(o, "selected", False)]
            for obj in (selected or scene.objects):
                targets.append({"target": obj.id, "position": obj.transform.position})
        else:
            raw = arguments.get("targets", [])
            if not isinstance(raw, list):
                raw = []
            for entry in raw:
                if not isinstance(entry, dict):
                    continue
                target_id = str(entry.get("target", "")).strip()
                obj = scene.find_object(target_id)
                if not obj:
                    continue
                target_state: Dict[str, Any] = {"target": obj.id}
                pos = _vec(entry.get("position"), obj.transform.position)
                rot = _vec(entry.get("rotation"), obj.transform.rotation)
                scl = _vec(entry.get("scale"), obj.transform.scale)
                if pos is not None:
                    target_state["position"] = pos
                if rot is not None:
                    target_state["rotation"] = rot
                if scl is not None:
                    target_state["scale"] = scl
                targets.append(target_state)

        if not targets:
            return ToolResult(
                success=False,
                message="No valid targets resolved for the transition",
                deltas=[],
                data={},
            )

        transition: Dict[str, Any] = {
            "id": _gen_id(),
            "name": name,
            "duration": duration,
            "easing": easing,
            "loop": loop,
            "targets": targets,
        }
        scene.transitions.append(transition)

        return ToolResult(
            success=True,
            message=f"Created transition '{name}' morphing {len(targets)} object(s) over {duration}s",
            deltas=[
                SceneDelta(
                    action="update_scene",
                    target_id=scene.id if hasattr(scene, "id") else "",
                    payload={"transitions": list(scene.transitions)},
                )
            ],
            data={"id": transition["id"], "name": name, "target_count": len(targets)},
        )


# ---------------------------------------------------------------------------
# play_scene_transition
# ---------------------------------------------------------------------------
_PLAY_TRANSITION_PARAMS = {
    "type": "object",
    "properties": {
        "transition": {
            "type": "string",
            "description": "Transition id or name to play.",
        },
    },
    "required": ["transition"],
}


class PlaySceneTransitionTool(ToolBase):
    """Activate a scene transition so the viewport plays it."""

    name = "play_scene_transition"
    description = (
        "Play a named scene transition, smoothly morphing its objects to the "
        "described target state over the transition's duration."
    )

    def schema(self) -> Dict[str, Any]:
        return _PLAY_TRANSITION_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        identifier = str(arguments.get("transition", "")).strip()
        transition = _find_transition(scene, identifier)
        if not transition:
            return ToolResult(
                success=False,
                message=f"Transition not found: {identifier}",
                deltas=[],
                data={},
            )
        scene.active_transition = transition["id"]
        return ToolResult(
            success=True,
            message=f"Playing transition '{transition['name']}'",
            deltas=[
                SceneDelta(
                    action="update_scene",
                    target_id="",
                    payload={"active_transition": transition["id"]},
                )
            ],
            data={"id": transition["id"], "name": transition["name"]},
        )


# ---------------------------------------------------------------------------
# list_scene_transitions
# ---------------------------------------------------------------------------
class ListSceneTransitionsTool(ToolBase):
    """List all authored scene transitions."""

    name = "list_scene_transitions"
    description = (
        "List every scene transition that has been authored, with its id, "
        "name, duration, easing, and target object count."
    )

    def schema(self) -> Dict[str, Any]:
        return {"type": "object", "properties": {}}

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        summary = [
            {
                "id": t.get("id"),
                "name": t.get("name"),
                "duration": t.get("duration"),
                "easing": t.get("easing"),
                "target_count": len(t.get("targets", [])),
            }
            for t in scene.transitions
        ]
        return ToolResult(
            success=True,
            message=f"{len(scene.transitions)} transition(s)",
            deltas=[],
            data={"transitions": summary, "active_transition": scene.active_transition},
        )


# ---------------------------------------------------------------------------
# remove_scene_transition
# ---------------------------------------------------------------------------
_REMOVE_TRANSITION_PARAMS = {
    "type": "object",
    "properties": {
        "transition": {
            "type": "string",
            "description": "Transition id or name to remove.",
        },
    },
    "required": ["transition"],
}


class RemoveSceneTransitionTool(ToolBase):
    """Remove a scene transition by id or name."""

    name = "remove_scene_transition"
    description = (
        "Remove a previously authored scene transition. If it is the active "
        "transition, playback stops."
    )

    def schema(self) -> Dict[str, Any]:
        return _REMOVE_TRANSITION_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        identifier = str(arguments.get("transition", "")).strip()
        transition = _find_transition(scene, identifier)
        if not transition:
            return ToolResult(
                success=False,
                message=f"Transition not found: {identifier}",
                deltas=[],
                data={},
            )
        scene.transitions = [t for t in scene.transitions if t.get("id") != transition["id"]]
        if scene.active_transition == transition["id"]:
            scene.active_transition = None
        return ToolResult(
            success=True,
            message=f"Removed transition '{transition['name']}'",
            deltas=[
                SceneDelta(
                    action="update_scene",
                    target_id="",
                    payload={"transitions": list(scene.transitions), "active_transition": scene.active_transition},
                )
            ],
            data={"id": transition["id"]},
        )


__all__ = [
    "CreateSceneTransitionTool",
    "PlaySceneTransitionTool",
    "ListSceneTransitionsTool",
    "RemoveSceneTransitionTool",
]
