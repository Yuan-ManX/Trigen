"""Object animation tools.

Attaches animation descriptors to scene objects, mirroring the camera
animation pattern. The frontend renderer interprets the ``animation``
field on SceneObject to drive per-frame transforms (keyframe interpolation,
circular orbits, sine wave drift, vertical bounce).

All animation descriptors share the common shape:
    {
        "type": "keyframe" | "orbit" | "wave" | "bounce",
        "duration": float,            # seconds for one loop
        "loop": bool,
        ... type-specific fields ...
    }
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

from trigen.scene import Scene, SceneObject
from trigen.tools.base import SceneDelta, ToolBase, ToolResult


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

_KEYFRAME_PARAMS = {
    "type": "object",
    "properties": {
        "target": {"type": "string", "description": "Target object id or name"},
        "keyframes": {
            "type": "array",
            "description": "Ordered keyframes; each entry has 't' in [0,1] and any of position/rotation/scale",
            "items": {
                "type": "object",
                "properties": {
                    "t": {"type": "number", "description": "Normalized time 0..1"},
                    "position": {"type": "array", "items": {"type": "number"}, "description": "[x, y, z] position"},
                    "rotation": {"type": "array", "items": {"type": "number"}, "description": "[rx, ry, rz] Euler radians"},
                    "scale": {"type": "array", "items": {"type": "number"}, "description": "[sx, sy, sz] scale"},
                },
            },
        },
        "duration": {"type": "number", "description": "Total duration in seconds (default 4)"},
        "loop": {"type": "boolean", "description": "Loop the animation (default true)"},
        "easing": {
            "type": "string",
            "enum": ["linear", "easeIn", "easeOut", "easeInOut"],
            "description": "Interpolation easing (default linear)",
        },
    },
    "required": ["target", "keyframes"],
}

_ORBIT_PARAMS = {
    "type": "object",
    "properties": {
        "target": {"type": "string", "description": "Target object id or name"},
        "center": {
            "type": "array",
            "items": {"type": "number"},
            "description": "Orbit center [x, y, z] (default scene origin)",
        },
        "radius": {"type": "number", "description": "Orbit radius in XZ plane (default 3)"},
        "height": {"type": "number", "description": "Constant orbit height (default current y)"},
        "duration": {"type": "number", "description": "Seconds per revolution (default 6)"},
        "loop": {"type": "boolean", "description": "Loop the orbit (default true)"},
        "axis": {
            "type": "string",
            "enum": ["y", "x", "z"],
            "description": "Rotation axis (default y, orbit in XZ plane)",
        },
        "face_center": {"type": "boolean", "description": "Rotate the object to face the orbit center (default true)"},
    },
    "required": ["target"],
}

_WAVE_PARAMS = {
    "type": "object",
    "properties": {
        "target": {"type": "string", "description": "Target object id or name"},
        "amplitude": {"type": "number", "description": "Wave amplitude (default 1.0)"},
        "frequency": {"type": "number", "description": "Wave frequency in Hz (default 0.5)"},
        "axis": {
            "type": "string",
            "enum": ["x", "y", "z"],
            "description": "Axis along which the wave displacement happens (default y)",
        },
        "duration": {"type": "number", "description": "Animation duration in seconds (default 4)"},
        "loop": {"type": "boolean", "description": "Loop the wave (default true)"},
    },
    "required": ["target"],
}

_BOUNCE_PARAMS = {
    "type": "object",
    "properties": {
        "target": {"type": "string", "description": "Target object id or name"},
        "height": {"type": "number", "description": "Peak bounce height above current position (default 1.5)"},
        "bounces": {"type": "integer", "description": "Number of bounces per loop (default 3)", "minimum": 1, "maximum": 10},
        "squash": {"type": "boolean", "description": "Apply squash-and-stretch on landing (default true)"},
        "duration": {"type": "number", "description": "Total duration in seconds (default 3)"},
        "loop": {"type": "boolean", "description": "Loop the bounce (default true)"},
    },
    "required": ["target"],
}


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

class KeyframeAnimationTool(ToolBase):
    """Attach a keyframe-based animation descriptor to an object."""

    name = "keyframe_animation"
    description = "Attach a keyframe animation to an object, interpolating position/rotation/scale across timed keyframes."

    def schema(self) -> Dict[str, Any]:
        return _KEYFRAME_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        target_id = arguments.get("target", "")
        obj = scene.find_object(target_id)
        if not obj:
            return ToolResult(success=False, message=f"Object not found: {target_id}")

        raw_keyframes = arguments.get("keyframes")
        if not isinstance(raw_keyframes, list) or len(raw_keyframes) < 2:
            return ToolResult(success=False, message="At least 2 keyframes are required")

        # Normalize and sort keyframes by time
        cleaned: List[Dict[str, Any]] = []
        for kf in raw_keyframes:
            if not isinstance(kf, dict):
                continue
            t = float(kf.get("t", 0.0))
            t = max(0.0, min(1.0, t))
            entry: Dict[str, Any] = {"t": t}
            for field in ("position", "rotation", "scale"):
                val = kf.get(field)
                if isinstance(val, list) and len(val) == 3:
                    entry[field] = [float(val[0]), float(val[1]), float(val[2])]
            cleaned.append(entry)
        if len(cleaned) < 2:
            return ToolResult(success=False, message="At least 2 valid keyframes are required")
        cleaned.sort(key=lambda k: k["t"])

        descriptor = {
            "type": "keyframe",
            "keyframes": cleaned,
            "duration": float(arguments.get("duration", 4.0)),
            "loop": bool(arguments.get("loop", True)),
            "easing": str(arguments.get("easing", "linear")),
        }
        obj.animation = descriptor
        return ToolResult(
            success=True,
            message=f"Attached keyframe animation ({len(cleaned)} keyframes) to {obj.name}",
            deltas=[SceneDelta(action="update", target_id=obj.id, payload=obj.to_dict())],
            data={"object": obj.to_dict(), "animation": descriptor},
        )


class OrbitAnimationTool(ToolBase):
    """Attach an orbit animation so an object circles a center point."""

    name = "orbit_animation"
    description = "Attach an orbit animation to an object so it revolves around a center point on a chosen axis."

    def schema(self) -> Dict[str, Any]:
        return _ORBIT_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        target_id = arguments.get("target", "")
        obj = scene.find_object(target_id)
        if not obj:
            return ToolResult(success=False, message=f"Object not found: {target_id}")

        center = arguments.get("center")
        if not isinstance(center, list) or len(center) != 3:
            center = [0.0, 0.0, 0.0]
        center = [float(center[0]), float(center[1]), float(center[2])]

        radius_arg = arguments.get("radius")
        if radius_arg is None:
            # Compute current radius in the XZ plane (default orbit axis = y)
            cx, _, cz = center
            ox, _, oz = obj.transform.position
            radius = math.sqrt((ox - cx) ** 2 + (oz - cz) ** 2)
            if radius < 1e-3:
                radius = 3.0
        else:
            radius = float(radius_arg)

        height_arg = arguments.get("height")
        if height_arg is None:
            height = float(obj.transform.position[1])
        else:
            height = float(height_arg)

        axis = str(arguments.get("axis", "y")).lower()
        if axis not in ("x", "y", "z"):
            axis = "y"

        descriptor = {
            "type": "orbit",
            "center": center,
            "radius": radius,
            "height": height,
            "axis": axis,
            "duration": float(arguments.get("duration", 6.0)),
            "loop": bool(arguments.get("loop", True)),
            "face_center": bool(arguments.get("face_center", True)),
            "start_position": list(obj.transform.position),
        }
        obj.animation = descriptor
        return ToolResult(
            success=True,
            message=f"Attached orbit animation to {obj.name} (radius {radius:.2f}, axis {axis})",
            deltas=[SceneDelta(action="update", target_id=obj.id, payload=obj.to_dict())],
            data={"object": obj.to_dict(), "animation": descriptor},
        )


class WaveAnimationTool(ToolBase):
    """Attach a sine-wave drift animation along an axis."""

    name = "wave_animation"
    description = "Attach a sinusoidal wave motion to an object along the X/Y/Z axis."

    def schema(self) -> Dict[str, Any]:
        return _WAVE_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        target_id = arguments.get("target", "")
        obj = scene.find_object(target_id)
        if not obj:
            return ToolResult(success=False, message=f"Object not found: {target_id}")

        axis = str(arguments.get("axis", "y")).lower()
        if axis not in ("x", "y", "z"):
            axis = "y"
        amplitude = float(arguments.get("amplitude", 1.0))
        frequency = float(arguments.get("frequency", 0.5))

        descriptor = {
            "type": "wave",
            "axis": axis,
            "amplitude": amplitude,
            "frequency": frequency,
            "duration": float(arguments.get("duration", 4.0)),
            "loop": bool(arguments.get("loop", True)),
            "start_position": list(obj.transform.position),
        }
        obj.animation = descriptor
        return ToolResult(
            success=True,
            message=f"Attached wave animation to {obj.name} (axis {axis}, amp {amplitude:.2f})",
            deltas=[SceneDelta(action="update", target_id=obj.id, payload=obj.to_dict())],
            data={"object": obj.to_dict(), "animation": descriptor},
        )


class BounceAnimationTool(ToolBase):
    """Attach a vertical bounce animation with optional squash-and-stretch."""

    name = "bounce_animation"
    description = "Attach a vertical bounce animation to an object with optional squash-and-stretch deformation on landing."

    def schema(self) -> Dict[str, Any]:
        return _BOUNCE_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        target_id = arguments.get("target", "")
        obj = scene.find_object(target_id)
        if not obj:
            return ToolResult(success=False, message=f"Object not found: {target_id}")

        descriptor = {
            "type": "bounce",
            "height": float(arguments.get("height", 1.5)),
            "bounces": max(1, min(10, int(arguments.get("bounces", 3)))),
            "squash": bool(arguments.get("squash", True)),
            "duration": float(arguments.get("duration", 3.0)),
            "loop": bool(arguments.get("loop", True)),
            "start_position": list(obj.transform.position),
            "start_scale": list(obj.transform.scale),
        }
        obj.animation = descriptor
        return ToolResult(
            success=True,
            message=f"Attached bounce animation to {obj.name} ({descriptor['bounces']} bounces)",
            deltas=[SceneDelta(action="update", target_id=obj.id, payload=obj.to_dict())],
            data={"object": obj.to_dict(), "animation": descriptor},
        )
