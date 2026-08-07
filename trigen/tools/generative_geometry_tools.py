"""Generative geometry tools — radial symmetry + clone-with-jitter.

These two tools fill real authoring gaps that the existing primitive
/ array / boolean tools do not cover:

* ``radial_symmetry`` places N copies of a target around a chosen axis
  at a given radius, optionally rotating each clone to face outward and
  optionally mirroring alternate clones so the result reads as a true
  radial symmetry (petals, propeller blades, clock numerals). Distinct
  from ``array_pattern`` (radial) which only rotates clones around the
  ring without the mirror-alternate option and without the
  per-instance angular offset knob.

* ``clone_with_jitter`` duplicates a target ``count`` times, applying
  random per-instance offsets to position / rotation / scale / color
  so the agent can scatter organic variation (forests, crowds, rubble)
  in a single call. Distinct from ``randomize_variant`` which jitters
  an existing scene in place; this tool produces fresh clones.

Both tools emit standard ``create`` SceneDeltas using the existing
SceneObject shape, so the frontend renders them without any changes.
"""

from __future__ import annotations

import colorsys
import json
import math
import random
import uuid
from typing import Any, Dict, List, Optional, Tuple

from trigen.scene import Scene, SceneObject
from trigen.tools.base import SceneDelta, ToolBase, ToolResult


_AXIS_INDEX = {"x": 0, "y": 1, "z": 2}


_RADIAL_SYMMETRY_PARAMS = {
    "type": "object",
    "properties": {
        "target": {"type": "string", "description": "Source object id or name to replicate"},
        "count": {
            "type": "integer",
            "description": "Number of clones around the ring (2-100, default 6)",
            "minimum": 2,
            "maximum": 100,
        },
        "axis": {
            "type": "string",
            "enum": ["x", "y", "z"],
            "description": "Ring rotation axis (default y)",
        },
        "radius": {"type": "number", "description": "Ring radius (default 3.0)", "minimum": 0.0},
        "angle_offset_deg": {
            "type": "number",
            "description": "Starting angular offset in degrees (default 0)",
        },
        "face_outward": {
            "type": "boolean",
            "description": "Rotate each clone to face outward along the ring tangent (default true)",
        },
        "mirror_alternate": {
            "type": "boolean",
            "description": "Mirror every other clone so the ring reads as a true symmetry (default false)",
        },
        "name_prefix": {"type": "string", "description": "Naming prefix for clones (default source name)"},
    },
    "required": ["target"],
}


_CLONE_JITTER_PARAMS = {
    "type": "object",
    "properties": {
        "target": {"type": "string", "description": "Source object id or name to replicate"},
        "count": {
            "type": "integer",
            "description": "Number of jittered clones to create (1-100, default 5)",
            "minimum": 1,
            "maximum": 100,
        },
        "pos_jitter": {
            "type": "number",
            "description": "Maximum random offset on each position axis (default 0.0 = no position jitter)",
            "minimum": 0.0,
        },
        "rot_jitter": {
            "type": "number",
            "description": "Maximum random rotation in radians on each axis (default 0.0 = no rotation jitter)",
            "minimum": 0.0,
        },
        "scale_jitter": {
            "type": "number",
            "description": "Maximum random scale delta per axis (default 0.0 = no scale jitter). e.g. 0.2 means ±20%",
            "minimum": 0.0,
        },
        "hue_jitter": {
            "type": "number",
            "description": "Maximum random hue rotation in degrees (default 0.0 = no color jitter)",
            "minimum": 0.0,
            "maximum": 360.0,
        },
        "seed": {"type": "integer", "description": "Optional random seed for reproducibility"},
        "name_prefix": {"type": "string", "description": "Naming prefix for clones (default source name)"},
    },
    "required": ["target"],
}


def _clone_object(obj: SceneObject) -> SceneObject:
    """Deep-copy an object with a fresh id."""
    new_obj = SceneObject.from_dict(json.loads(json.dumps(obj.to_dict())))
    new_obj.id = f"obj_{uuid.uuid4().hex[:8]}"
    return new_obj


def _hex_to_rgb(hex_str: str) -> Tuple[float, float, float]:
    h = str(hex_str).lstrip("#")
    if len(h) != 6:
        return (0.8, 0.8, 0.8)
    try:
        return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    except ValueError:
        return (0.8, 0.8, 0.8)


def _rgb_to_hex(rgb: Tuple[float, float, float]) -> str:
    r, g, b = rgb
    return "#{:02x}{:02x}{:02x}".format(
        max(0, min(255, int(r * 255))),
        max(0, min(255, int(g * 255))),
        max(0, min(255, int(b * 255))),
    )


def _jitter_color(hex_str: str, max_hue_deg: float, rng: random.Random) -> str:
    """Rotate the HSV hue of a hex color by a random amount up to max_hue_deg."""
    r, g, b = _hex_to_rgb(hex_str)
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    delta = rng.uniform(-max_hue_deg, max_hue_deg) / 360.0
    h = (h + delta) % 1.0
    nr, ng, nb = colorsys.hsv_to_rgb(h, s, v)
    return _rgb_to_hex((nr, ng, nb))


class RadialSymmetryTool(ToolBase):
    """Place N copies of a target around an axis to form a radial symmetry."""

    name = "radial_symmetry"
    description = (
        "Place N copies of a target object around a chosen axis at a given "
        "radius to form a radial symmetry (petals, blades, spokes)."
    )

    def schema(self) -> Dict[str, Any]:
        return _RADIAL_SYMMETRY_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        target_id = str(arguments.get("target", ""))
        src = scene.find_object(target_id)
        if src is None:
            return ToolResult(success=False, message=f"Object not found: {target_id}")

        count = max(2, min(100, int(arguments.get("count", 6))))
        axis = str(arguments.get("axis", "y")).lower()
        if axis not in _AXIS_INDEX:
            return ToolResult(success=False, message=f"Invalid axis: {axis}")
        radius = max(0.0, float(arguments.get("radius", 3.0)))
        angle_offset = math.radians(float(arguments.get("angle_offset_deg", 0.0)))
        face_outward = bool(arguments.get("face_outward", True))
        mirror_alternate = bool(arguments.get("mirror_alternate", False))
        name_prefix = arguments.get("name_prefix") or src.name

        center = list(src.transform.position)
        # The ring lives in the plane perpendicular to the chosen axis:
        # axis=y -> plane (x,z); axis=x -> plane (y,z); axis=z -> plane (x,y).
        created: List[SceneObject] = []
        deltas: List[SceneDelta] = []

        for i in range(count):
            angle = angle_offset + (2.0 * math.pi * i) / count
            clone = _clone_object(src)
            clone.name = scene.next_auto_name(name_prefix)
            if axis == "y":
                clone.transform.position = [
                    center[0] + radius * math.cos(angle),
                    center[1],
                    center[2] + radius * math.sin(angle),
                ]
            elif axis == "x":
                clone.transform.position = [
                    center[0],
                    center[1] + radius * math.sin(angle),
                    center[2] + radius * math.cos(angle),
                ]
            else:  # z
                clone.transform.position = [
                    center[0] + radius * math.cos(angle),
                    center[1] + radius * math.sin(angle),
                    center[2],
                ]

            rot = list(clone.transform.rotation)
            if face_outward:
                # Yaw the clone around the chosen axis so it faces outward
                # along the ring tangent.
                idx = _AXIS_INDEX[axis]
                rot[idx] = rot[idx] + angle
            if mirror_alternate and (i % 2 == 1):
                # Flip scale on the ring's primary horizontal axis to mirror
                # alternate instances, producing true radial symmetry.
                mirror_idx = 0 if axis != "x" else 1
                clone.transform.scale = list(clone.transform.scale)
                clone.transform.scale[mirror_idx] = -abs(clone.transform.scale[mirror_idx])
            clone.transform.rotation = rot

            clone.tags = list(clone.tags) + [f"radial_symmetry:{count}"]
            scene.objects.append(clone)
            created.append(clone)
            deltas.append(SceneDelta(action="create", target_id=clone.id, payload=clone.to_dict()))

        msg = (
            f"Radial symmetry: {count} copies of {src.name} around {axis} "
            f"(radius {radius}, face_outward={face_outward}, mirror_alternate={mirror_alternate})"
        )
        return ToolResult(
            success=True,
            message=msg,
            deltas=deltas,
            data={"created": [o.to_dict() for o in created], "count": len(created)},
        )


class CloneWithJitterTool(ToolBase):
    """Duplicate a target ``count`` times with random per-instance variation."""

    name = "clone_with_jitter"
    description = (
        "Duplicate a target object count times, applying random per-instance "
        "offsets to position, rotation, scale, and color so the agent can "
        "scatter organic variation (forests, crowds, rubble) in one call."
    )

    def schema(self) -> Dict[str, Any]:
        return _CLONE_JITTER_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        target_id = str(arguments.get("target", ""))
        src = scene.find_object(target_id)
        if src is None:
            return ToolResult(success=False, message=f"Object not found: {target_id}")

        count = max(1, min(100, int(arguments.get("count", 5))))
        pos_jitter = max(0.0, float(arguments.get("pos_jitter", 0.0)))
        rot_jitter = max(0.0, float(arguments.get("rot_jitter", 0.0)))
        scale_jitter = max(0.0, float(arguments.get("scale_jitter", 0.0)))
        hue_jitter = max(0.0, min(360.0, float(arguments.get("hue_jitter", 0.0))))
        seed = arguments.get("seed")
        rng = random.Random(int(seed)) if isinstance(seed, int) else random.Random()
        name_prefix = arguments.get("name_prefix") or src.name

        base_pos = list(src.transform.position)
        base_rot = list(src.transform.rotation)
        base_scale = list(src.transform.scale)

        created: List[SceneObject] = []
        deltas: List[SceneDelta] = []

        for _ in range(count):
            clone = _clone_object(src)
            clone.name = scene.next_auto_name(name_prefix)

            if pos_jitter > 0.0:
                clone.transform.position = [
                    base_pos[0] + rng.uniform(-pos_jitter, pos_jitter),
                    base_pos[1] + rng.uniform(-pos_jitter, pos_jitter),
                    base_pos[2] + rng.uniform(-pos_jitter, pos_jitter),
                ]
            if rot_jitter > 0.0:
                clone.transform.rotation = [
                    base_rot[0] + rng.uniform(-rot_jitter, rot_jitter),
                    base_rot[1] + rng.uniform(-rot_jitter, rot_jitter),
                    base_rot[2] + rng.uniform(-rot_jitter, rot_jitter),
                ]
            if scale_jitter > 0.0:
                clone.transform.scale = [
                    max(1e-3, base_scale[0] * (1.0 + rng.uniform(-scale_jitter, scale_jitter))),
                    max(1e-3, base_scale[1] * (1.0 + rng.uniform(-scale_jitter, scale_jitter))),
                    max(1e-3, base_scale[2] * (1.0 + rng.uniform(-scale_jitter, scale_jitter))),
                ]
            if hue_jitter > 0.0:
                clone.material.color = _jitter_color(clone.material.color, hue_jitter, rng)
                if clone.material.emissive and clone.material.emissive.lower() != "#000000":
                    clone.material.emissive = _jitter_color(clone.material.emissive, hue_jitter, rng)

            clone.tags = list(clone.tags) + ["clone_with_jitter"]
            scene.objects.append(clone)
            created.append(clone)
            deltas.append(SceneDelta(action="create", target_id=clone.id, payload=clone.to_dict()))

        jitter_summary = []
        if pos_jitter > 0.0:
            jitter_summary.append(f"pos±{pos_jitter}")
        if rot_jitter > 0.0:
            jitter_summary.append(f"rot±{rot_jitter}")
        if scale_jitter > 0.0:
            jitter_summary.append(f"scale±{scale_jitter}")
        if hue_jitter > 0.0:
            jitter_summary.append(f"hue±{hue_jitter}°")
        jitter_str = ", ".join(jitter_summary) if jitter_summary else "no jitter"
        msg = f"Cloned {src.name} x{count} with jitter ({jitter_str})"
        return ToolResult(
            success=True,
            message=msg,
            deltas=deltas,
            data={
                "created": [o.to_dict() for o in created],
                "count": len(created),
                "pos_jitter": pos_jitter,
                "rot_jitter": rot_jitter,
                "scale_jitter": scale_jitter,
                "hue_jitter": hue_jitter,
                "seed": seed,
            },
        )
