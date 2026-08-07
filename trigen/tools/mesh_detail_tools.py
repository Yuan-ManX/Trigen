"""Mesh detail control tools.

Two Agent-callable tools that fill remaining gaps in geometry editing:

  * ``convert_geometry`` — swap an existing object's geometry type while
    preserving its transform, material, and parent assignment. Useful for
    iterative design ("turn this cube into a sphere") without re-creating
    the object and losing its place in the scene graph.
  * ``subdivide_mesh`` — raise the segment counts of a parametric
    geometry so its surface becomes smoother. Distinct from
    ``set_geometry_params`` (which sets arbitrary params): subdivide is a
    one-call "make this smoother / lower-poly" intent with a single
    ``factor`` argument and safe clamping per geometry type.
"""

from __future__ import annotations

from typing import Any, Dict, List

from trigen.scene import GEOMETRY_DEFAULTS, Scene
from trigen.tools.base import SceneDelta, ToolBase, ToolResult


# ---------------------------------------------------------------------------
# 1. convert_geometry — swap geometry type preserving transform/material
# ---------------------------------------------------------------------------

_CONVERT_PARAMS = {
    "type": "object",
    "properties": {
        "target": {
            "type": "string",
            "description": "Object id or name whose geometry type should be converted.",
        },
        "geometry_type": {
            "type": "string",
            "enum": list(GEOMETRY_DEFAULTS.keys()),
            "description": "New geometry type to apply.",
        },
        "params": {
            "type": "object",
            "description": (
                "Optional geometry parameters for the new type. Defaults are "
                "used for any unspecified field."
            ),
            "additionalProperties": True,
        },
    },
    "required": ["target", "geometry_type"],
}


class ConvertGeometryTool(ToolBase):
    """Convert an object's geometry type, preserving transform and material."""

    name = "convert_geometry"
    description = (
        "Convert an existing object's geometry type (e.g. box -> sphere) while "
        "preserving its transform, material, layer, and parent. Faster than "
        "delete + create when iterating on a shape that already has the right "
        "placement and styling."
    )

    def schema(self) -> Dict[str, Any]:
        return _CONVERT_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        target_id = str(arguments.get("target", ""))
        new_type = str(arguments.get("geometry_type", ""))
        if new_type not in GEOMETRY_DEFAULTS:
            return ToolResult(
                success=False,
                message=(
                    f"Unsupported geometry type: {new_type}. Available: "
                    f"{', '.join(GEOMETRY_DEFAULTS.keys())}"
                ),
            )
        obj = scene.find_object(target_id)
        if obj is None:
            return ToolResult(success=False, message=f"Object not found: {target_id}")

        old_type = obj.geometry.type
        if old_type == new_type:
            return ToolResult(
                success=True,
                message=f"'{obj.name}' is already {new_type}; no change.",
                data={"target": obj.id, "geometry_type": new_type, "unchanged": True},
            )

        # Build new params: defaults for the target type, merged with caller
        # overrides. Existing params are intentionally NOT carried over
        # because they are type-specific (sphere radius vs box width) and
        # would produce invalid geometry.
        new_params = dict(GEOMETRY_DEFAULTS[new_type])
        user_params = arguments.get("params", {})
        if isinstance(user_params, dict):
            new_params.update(user_params)

        obj.geometry.type = new_type
        obj.geometry.params = new_params

        return ToolResult(
            success=True,
            message=f"Converted '{obj.name}' from {old_type} to {new_type}.",
            deltas=[SceneDelta(
                action="update",
                target_id=obj.id,
                payload={"geometry": obj.geometry.to_dict()},
            )],
            data={
                "target": obj.id,
                "name": obj.name,
                "old_type": old_type,
                "new_type": new_type,
                "params": new_params,
            },
        )


# ---------------------------------------------------------------------------
# 2. subdivide_mesh — raise / lower segment counts for smoother surfaces
# ---------------------------------------------------------------------------

# Per-geometry segment keys and sane bounds. Geometries without segment
# params (lathe/extrude/text/spline/tube) are handled with their own
# resolution keys where applicable.
_SEGMENT_KEYS: Dict[str, List[str]] = {
    "box": ["widthSegments", "heightSegments", "depthSegments"],
    "sphere": ["widthSegments", "heightSegments"],
    "cylinder": ["radialSegments"],
    "cone": ["radialSegments"],
    "torus": ["radialSegments", "tubularSegments"],
    "torusKnot": ["tubularSegments", "radialSegments"],
    "plane": ["widthSegments", "heightSegments"],
    "capsule": ["capSegments", "radialSegments"],
    "ring": ["thetaSegments"],
    "tube": ["tubularSegments", "radialSegments"],
    "lathe": ["segments"],
    "extrude": ["curveSegments"],
    "spline": ["tubularSegments", "radialSegments"],
}

# Hard caps per segment key to keep geometry renderable. Matches the
# upper bounds the frontend tolerates without frame drops.
_SEG_CAPS: Dict[str, int] = {
    "widthSegments": 64,
    "heightSegments": 64,
    "depthSegments": 64,
    "radialSegments": 128,
    "tubularSegments": 256,
    "capSegments": 64,
    "thetaSegments": 128,
    "segments": 256,
    "curveSegments": 64,
}

_SUBDIVIDE_PARAMS = {
    "type": "object",
    "properties": {
        "target": {
            "type": "string",
            "description": "Object id or name to subdivide or simplify.",
        },
        "factor": {
            "type": "number",
            "description": (
                "Multiplier applied to every segment count. >1 increases "
                "detail (smoother); <1 decreases detail (lower-poly). "
                "Clamped to [0.1, 8.0]. Default 2.0 (double resolution)."
            ),
            "minimum": 0.1,
            "maximum": 8.0,
        },
    },
    "required": ["target"],
}


class SubdivideMeshTool(ToolBase):
    """Raise or lower a parametric geometry's segment counts in one call."""

    name = "subdivide_mesh"
    description = (
        "Scale an object's mesh resolution by a single factor. factor >1 "
        "increases segment counts for a smoother surface; factor <1 reduces "
        "them for a lower-poly look. Faster than calling set_geometry_params "
        "for each segment field separately."
    )

    def schema(self) -> Dict[str, Any]:
        return _SUBDIVIDE_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        target_id = str(arguments.get("target", ""))
        obj = scene.find_object(target_id)
        if obj is None:
            return ToolResult(success=False, message=f"Object not found: {target_id}")

        try:
            factor = float(arguments.get("factor", 2.0))
        except (TypeError, ValueError):
            return ToolResult(success=False, message="factor must be a number")
        # Clamp to the schema-declared bounds.
        factor = max(0.1, min(8.0, factor))

        geo_type = obj.geometry.type
        seg_keys = _SEGMENT_KEYS.get(geo_type)
        if not seg_keys:
            return ToolResult(
                success=False,
                message=(
                    f"Geometry '{geo_type}' has no tunable segment counts. "
                    f"Supported types: {', '.join(sorted(_SEGMENT_KEYS))}"
                ),
            )

        params = dict(obj.geometry.params or {})
        changes: List[Dict[str, Any]] = []
        for key in seg_keys:
            cur = params.get(key)
            if not isinstance(cur, (int, float)) or cur <= 0:
                continue
            new_val = int(round(float(cur) * factor))
            new_val = max(1, min(_SEG_CAPS.get(key, 128), new_val))
            if new_val != cur:
                params[key] = new_val
                changes.append({"key": key, "from": cur, "to": new_val})

        if not changes:
            return ToolResult(
                success=True,
                message=(
                    f"'{obj.name}' ({geo_type}) segment counts unchanged at "
                    f"factor {factor}."
                ),
                data={"target": obj.id, "factor": factor, "unchanged": True},
            )

        obj.geometry.params = params
        direction = "smoother" if factor > 1 else "lower-poly"
        summary = ", ".join(f"{c['key']}: {c['from']}->{c['to']}" for c in changes[:4])
        if len(changes) > 4:
            summary += f" (+{len(changes) - 4} more)"
        return ToolResult(
            success=True,
            message=f"Subdivided '{obj.name}' ({geo_type}, {direction}): {summary}.",
            deltas=[SceneDelta(
                action="update",
                target_id=obj.id,
                payload={"geometry": obj.geometry.to_dict()},
            )],
            data={
                "target": obj.id,
                "name": obj.name,
                "geometry_type": geo_type,
                "factor": factor,
                "changes": changes,
            },
        )
