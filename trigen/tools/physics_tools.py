"""Rigid-body physics tools.

These tools attach a lightweight physics descriptor to scene objects so
the viewport simulation can apply gravity, bouncing, friction, and a
resting floor. They close the gap between the Agent's conversational
control and dynamic scene behavior — a user can say "drop the sphere and
let it bounce" and the Agent materializes that as a physics descriptor on
the sphere.

The descriptor is stored on ``SceneObject.physics`` as a plain dict:
``{enabled, gravity, bounciness, friction, shape, floor, mass}``. The
frontend scene renderer reads it and advances a per-object simulation
each frame, so no backend engine or external physics dependency is
required — the whole capability is self-contained and offline-safe.
"""

from __future__ import annotations

from typing import Any, Dict, List

from trigen.scene import Scene
from trigen.tools.base import SceneDelta, ToolBase, ToolResult


def _clamp(v: float, lo: float, hi: float) -> float:
    """Clamp a numeric value to the inclusive [lo, hi] range."""
    return max(lo, min(hi, v))


# ---------------------------------------------------------------------------
# apply_physics
# ---------------------------------------------------------------------------
_APPLY_PHYSICS_PARAMS = {
    "type": "object",
    "properties": {
        "target": {
            "type": "string",
            "description": "Object id or name to apply physics to.",
        },
        "gravity": {
            "type": "number",
            "description": "Downward acceleration in units/s^2 (default 9.8). Set 0 to hover.",
        },
        "bounciness": {
            "type": "number",
            "description": "Restitution 0-1 controlling how much energy is kept on impact (default 0.3).",
        },
        "friction": {
            "type": "number",
            "description": "Horizontal damping 0-1 controlling slide (default 0.2).",
        },
        "shape": {
            "type": "string",
            "enum": ["auto", "sphere", "box"],
            "description": "Collision shape used to size the resting offset (default auto).",
        },
        "floor": {
            "type": "number",
            "description": "Resting floor Y level (default 0 = grid plane).",
        },
        "mass": {
            "type": "number",
            "description": "Relative mass affecting bounce height (default 1).",
        },
    },
    "required": ["target"],
}


class ApplyPhysicsTool(ToolBase):
    """Attach a rigid-body physics descriptor to a scene object.

    When physics is enabled the viewport simulation applies gravity so the
    object falls to the configured floor and bounces with the given
    restitution. The descriptor does not conflict with keyframe animation:
    a physics-enabled object ignores its authored static transform while it
    is active. Read/write — mutates the target object.
    """

    name = "apply_physics"
    description = (
        "Enable or configure rigid-body physics on an object: gravity pulls it "
        "down to the floor and bounciness makes it rebound. Pass only the fields "
        "you want to change; unspecified fields keep their current values. "
        "Use clear_physics to remove physics again."
    )

    def schema(self) -> Dict[str, Any]:
        return _APPLY_PHYSICS_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        target = str(arguments.get("target", "")).strip()
        obj = scene.find_object(target)
        if not obj:
            return ToolResult(
                success=False,
                message=f"Object '{target}' not found",
                deltas=[],
                data={},
            )

        current: Dict[str, Any] = dict(obj.physics or {})
        updated: Dict[str, Any] = {}
        try:
            if "gravity" in arguments:
                updated["gravity"] = _clamp(float(arguments["gravity"]), 0.0, 60.0)
            if "bounciness" in arguments:
                updated["bounciness"] = _clamp(float(arguments["bounciness"]), 0.0, 1.0)
            if "friction" in arguments:
                updated["friction"] = _clamp(float(arguments["friction"]), 0.0, 1.0)
            if "mass" in arguments:
                updated["mass"] = _clamp(float(arguments["mass"]), 0.1, 20.0)
        except (TypeError, ValueError):
            return ToolResult(
                success=False,
                message="Invalid numeric value in physics arguments",
                deltas=[],
                data={},
            )

        if "shape" in arguments:
            shape = str(arguments["shape"])
            updated["shape"] = shape if shape in ("auto", "sphere", "box") else "auto"
        if "floor" in arguments:
            updated["floor"] = float(arguments["floor"])

        merged = dict(current)
        merged.update(updated)
        merged["enabled"] = True
        merged["applied_at"] = True
        obj.physics = merged

        return ToolResult(
            success=True,
            message=(
                f"Physics enabled on '{obj.name}': "
                f"gravity={merged.get('gravity', 9.8)}, "
                f"bounciness={merged.get('bounciness', 0.3)}, "
                f"floor={merged.get('floor', 0.0)}"
            ),
            deltas=[
                SceneDelta(
                    action="update_object",
                    target_id=obj.id,
                    payload=obj.to_dict(),
                )
            ],
            data={"id": obj.id, "physics": merged},
        )


# ---------------------------------------------------------------------------
# clear_physics
# ---------------------------------------------------------------------------
_CLEAR_PHYSICS_PARAMS = {
    "type": "object",
    "properties": {
        "target": {
            "type": "string",
            "description": "Object id or name to remove physics from.",
        },
    },
    "required": ["target"],
}


class ClearPhysicsTool(ToolBase):
    """Remove the physics descriptor from an object, restoring its static
    authored transform in the viewport."""

    name = "clear_physics"
    description = (
        "Remove rigid-body physics from an object so it stops falling and returns "
        "to its authored static transform."
    )

    def schema(self) -> Dict[str, Any]:
        return _CLEAR_PHYSICS_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        target = str(arguments.get("target", "")).strip()
        obj = scene.find_object(target)
        if not obj:
            return ToolResult(
                success=False,
                message=f"Object '{target}' not found",
                deltas=[],
                data={},
            )
        if not obj.physics:
            return ToolResult(
                success=True,
                message=f"Object '{obj.name}' has no physics to clear",
                deltas=[],
                data={"id": obj.id, "physics": None},
            )
        obj.physics = None
        return ToolResult(
            success=True,
            message=f"Physics removed from '{obj.name}'",
            deltas=[
                SceneDelta(
                    action="update_object",
                    target_id=obj.id,
                    payload=obj.to_dict(),
                )
            ],
            data={"id": obj.id, "physics": None},
        )


# ---------------------------------------------------------------------------
# list_physics
# ---------------------------------------------------------------------------
_LIST_PHYSICS_PARAMS = {
    "type": "object",
    "properties": {
        "enabled_only": {
            "type": "boolean",
            "description": "When true, only return objects with physics enabled.",
        },
    },
    "required": [],
}


class ListPhysicsTool(ToolBase):
    """List which objects carry physics descriptors and their current values."""

    name = "list_physics"
    description = (
        "List every object that has physics enabled, with its gravity, bounciness, "
        "friction, and floor. Read-only."
    )

    def schema(self) -> Dict[str, Any]:
        return _LIST_PHYSICS_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        enabled_only = bool(arguments.get("enabled_only", True))
        items: List[Dict[str, Any]] = []
        for obj in scene.objects:
            if not obj.physics:
                continue
            if enabled_only and not obj.physics.get("enabled"):
                continue
            items.append(
                {
                    "id": obj.id,
                    "name": obj.name,
                    "physics": obj.physics,
                }
            )
        return ToolResult(
            success=True,
            message=f"{len(items)} object(s) have physics",
            deltas=[],
            data={"objects": items, "count": len(items)},
        )


__all__ = [
    "ApplyPhysicsTool",
    "ClearPhysicsTool",
    "ListPhysicsTool",
]
