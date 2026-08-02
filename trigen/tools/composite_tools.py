"""Composite geometry tools.

Builds higher-order modelling operations on top of the base scene model:
linear/grid/radial patterning, mirroring, bounding-box boolean ops, and
grid snapping. Each tool emits the standard scene deltas so the frontend
updates incrementally.
"""

from __future__ import annotations

import json
import math
import uuid
from typing import Any, Dict, List

from trigen.scene import Scene, SceneObject
from trigen.tools.base import SceneDelta, ToolBase, ToolResult


_AXIS_INDEX = {"x": 0, "y": 1, "z": 2}


_ARRAY_PARAMS = {
    "type": "object",
    "properties": {
        "target": {"type": "string", "description": "Source object id or name to replicate"},
        "pattern": {
            "type": "string",
            "enum": ["linear", "grid", "radial"],
            "description": "Array pattern type",
        },
        "count": {"type": "integer", "description": "Total number of clones (linear/radial, default 5)", "minimum": 1, "maximum": 100},
        "axis": {"type": "string", "enum": ["x", "y", "z"], "description": "Linear axis (default x) or radial rotation plane normal (default y)"},
        "spacing": {"type": "number", "description": "Linear spacing between clones (default 2)"},
        "rows": {"type": "integer", "description": "Grid rows (default 3)", "minimum": 1, "maximum": 20},
        "cols": {"type": "integer", "description": "Grid columns (default 3)", "minimum": 1, "maximum": 20},
        "spacing_x": {"type": "number", "description": "Grid column spacing (default 2)"},
        "spacing_z": {"type": "number", "description": "Grid row spacing (default 2)"},
        "radius": {"type": "number", "description": "Radial pattern radius (default 3)"},
        "name_prefix": {"type": "string", "description": "Naming prefix for clones (default source name)"},
    },
    "required": ["target", "pattern"],
}


_MIRROR_PARAMS = {
    "type": "object",
    "properties": {
        "target": {"type": "string", "description": "Source object id or name"},
        "axis": {"type": "string", "enum": ["x", "y", "z"], "description": "Mirror axis (default x)"},
        "name": {"type": "string", "description": "Optional name for the mirrored copy"},
    },
    "required": ["target"],
}


_BOOLEAN_PARAMS = {
    "type": "object",
    "properties": {
        "target_a": {"type": "string", "description": "First operand object id or name"},
        "target_b": {"type": "string", "description": "Second operand object id or name"},
        "operation": {
            "type": "string",
            "enum": ["union", "difference", "intersection"],
            "description": "Boolean operation",
        },
        "name": {"type": "string", "description": "Optional name for the result object"},
        "delete_inputs": {"type": "boolean", "description": "Remove the two operand objects after computing the result (default false)"},
    },
    "required": ["target_a", "target_b", "operation"],
}


_SNAP_PARAMS = {
    "type": "object",
    "properties": {
        "target": {"type": "string", "description": "Target object id or name"},
        "grid_size": {"type": "number", "description": "Grid cell size (default 1.0)"},
        "axes": {
            "type": "array",
            "items": {"type": "string", "enum": ["x", "y", "z"]},
            "description": "Axes to snap (default all three)",
        },
    },
    "required": ["target"],
}


def _clone_object(obj: SceneObject) -> SceneObject:
    """Deep-copy an object with a fresh id."""
    new_obj = SceneObject.from_dict(json.loads(json.dumps(obj.to_dict())))
    new_obj.id = f"obj_{uuid.uuid4().hex[:8]}"
    return new_obj


def _bbox_of(obj: SceneObject) -> tuple:
    """Return (min_xyz, max_xyz) bounding box of an object from geometry params."""
    g = obj.geometry
    p = g.params or {}
    t = g.type
    hx = hy = hz = 0.5
    if t == "box":
        hx = float(p.get("width", 1.0)) / 2
        hy = float(p.get("height", 1.0)) / 2
        hz = float(p.get("depth", 1.0)) / 2
    elif t in ("sphere", "icosahedron", "dodecahedron", "octahedron", "tetrahedron"):
        r = float(p.get("radius", 0.6))
        hx = hy = hz = r
    elif t == "cylinder":
        r = float(p.get("radiusTop", p.get("radiusBottom", 0.5)))
        hy = float(p.get("height", 1.2)) / 2
        hx = hz = r
    elif t == "cone":
        r = float(p.get("radius", 0.6))
        hy = float(p.get("height", 1.2)) / 2
        hx = hz = r
    elif t == "torus":
        r = float(p.get("radius", 0.6)) + float(p.get("tube", 0.2))
        hy = float(p.get("tube", 0.2))
        hx = hz = r
    elif t == "plane":
        hx = float(p.get("width", 2.0)) / 2
        hz = float(p.get("height", 2.0)) / 2
        hy = 0.0
    elif t == "capsule":
        r = float(p.get("radius", 0.4))
        hy = r + float(p.get("length", 0.8)) / 2
        hx = hz = r
    sx, sy, sz = obj.transform.scale
    px, py, pz = obj.transform.position
    ext = [hx * sx, hy * sy, hz * sz]
    mins = [px - ext[0], py - ext[1], pz - ext[2]]
    maxs = [px + ext[0], py + ext[1], pz + ext[2]]
    return mins, maxs


class ArrayPatternTool(ToolBase):
    """Replicate an object along a linear, grid, or radial pattern."""

    name = "array_pattern"
    description = "Replicate an object along a linear, grid, or radial pattern, creating a clone array."

    def schema(self) -> Dict[str, Any]:
        return _ARRAY_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        target_id = arguments.get("target", "")
        src = scene.find_object(target_id)
        if not src:
            return ToolResult(success=False, message=f"Object not found: {target_id}")

        pattern = str(arguments.get("pattern", "linear")).lower()
        name_prefix = arguments.get("name_prefix") or src.name
        created: List[SceneObject] = []
        deltas: List[SceneDelta] = []

        if pattern == "linear":
            count = max(1, min(100, int(arguments.get("count", 5))))
            axis = str(arguments.get("axis", "x")).lower()
            if axis not in _AXIS_INDEX:
                return ToolResult(success=False, message=f"Invalid axis: {axis}")
            spacing = float(arguments.get("spacing", 2.0))
            idx = _AXIS_INDEX[axis]
            base_pos = list(src.transform.position)
            for i in range(1, count):
                clone = _clone_object(src)
                clone.name = scene.next_auto_name(name_prefix)
                new_pos = list(base_pos)
                new_pos[idx] = base_pos[idx] + spacing * i
                clone.transform.position = new_pos
                scene.objects.append(clone)
                created.append(clone)
                deltas.append(SceneDelta(action="create", target_id=clone.id, payload=clone.to_dict()))
            msg = f"Arrayed {len(created)} clones along {axis} (spacing {spacing})"

        elif pattern == "grid":
            rows = max(1, min(20, int(arguments.get("rows", 3))))
            cols = max(1, min(20, int(arguments.get("cols", 3))))
            sx = float(arguments.get("spacing_x", 2.0))
            sz = float(arguments.get("spacing_z", 2.0))
            base_pos = list(src.transform.position)
            for r in range(rows):
                for c in range(cols):
                    if r == 0 and c == 0:
                        continue
                    clone = _clone_object(src)
                    clone.name = scene.next_auto_name(name_prefix)
                    clone.transform.position = [
                        base_pos[0] + sx * c,
                        base_pos[1],
                        base_pos[2] + sz * r,
                    ]
                    scene.objects.append(clone)
                    created.append(clone)
                    deltas.append(SceneDelta(action="create", target_id=clone.id, payload=clone.to_dict()))
            msg = f"Arrayed {len(created)} clones in {rows}x{cols} grid"

        elif pattern == "radial":
            count = max(1, min(100, int(arguments.get("count", 6))))
            radius = float(arguments.get("radius", 3.0))
            axis = str(arguments.get("axis", "y")).lower()
            if axis not in _AXIS_INDEX:
                return ToolResult(success=False, message=f"Invalid axis: {axis}")
            center = list(src.transform.position)
            for i in range(1, count):
                angle = (2.0 * math.pi * i) / count
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
                # Rotate clone to face outward (yaw around the pattern axis)
                clone.transform.rotation = list(clone.transform.rotation)
                if axis == "y":
                    clone.transform.rotation[1] = clone.transform.rotation[1] + angle
                elif axis == "x":
                    clone.transform.rotation[0] = clone.transform.rotation[0] + angle
                else:
                    clone.transform.rotation[2] = clone.transform.rotation[2] + angle
                scene.objects.append(clone)
                created.append(clone)
                deltas.append(SceneDelta(action="create", target_id=clone.id, payload=clone.to_dict()))
            msg = f"Arrayed {len(created)} clones radially (radius {radius}, axis {axis})"

        else:
            return ToolResult(success=False, message=f"Unknown pattern: {pattern}")

        return ToolResult(
            success=True,
            message=msg,
            deltas=deltas,
            data={"created": [o.to_dict() for o in created], "count": len(created)},
        )


class MirrorObjectTool(ToolBase):
    """Create a mirrored copy of an object across a plane on the given axis."""

    name = "mirror_object"
    description = "Create a mirrored copy of an object across the X/Y/Z plane through the origin."

    def schema(self) -> Dict[str, Any]:
        return _MIRROR_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        target_id = arguments.get("target", "")
        src = scene.find_object(target_id)
        if not src:
            return ToolResult(success=False, message=f"Object not found: {target_id}")

        axis = str(arguments.get("axis", "x")).lower()
        if axis not in _AXIS_INDEX:
            return ToolResult(success=False, message=f"Invalid axis: {axis}")
        idx = _AXIS_INDEX[axis]

        clone = _clone_object(src)
        clone.name = scene.next_auto_name(arguments.get("name") or f"{src.name}_Mirror")
        # Mirror position coordinate on the chosen axis
        clone.transform.position = list(clone.transform.position)
        clone.transform.position[idx] = -clone.transform.position[idx]
        # Mirror scale on the chosen axis to flip geometry orientation
        clone.transform.scale = list(clone.transform.scale)
        clone.transform.scale[idx] = -abs(clone.transform.scale[idx]) if clone.transform.scale[idx] >= 0 else clone.transform.scale[idx]
        scene.objects.append(clone)

        return ToolResult(
            success=True,
            message=f"Mirrored {src.name} across {axis} plane -> {clone.name}",
            deltas=[SceneDelta(action="create", target_id=clone.id, payload=clone.to_dict())],
            data={"object": clone.to_dict()},
        )


class BooleanOperationTool(ToolBase):
    """Approximate boolean union/difference/intersection via bounding boxes.

    Produces a new box mesh whose dimensions enclose the boolean result of
    the two operands' bounding boxes. The original operands are retained
    unless ``delete_inputs`` is set.
    """

    name = "boolean_operation"
    description = "Compute a boolean union/difference/intersection of two objects, approximated by their bounding boxes, producing a new box mesh."
    requires_approval = True  # Destructive: may delete input operands

    def schema(self) -> Dict[str, Any]:
        return _BOOLEAN_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        a_id = str(arguments.get("target_a", ""))
        b_id = str(arguments.get("target_b", ""))
        a = scene.find_object(a_id)
        b = scene.find_object(b_id)
        if a is None:
            return ToolResult(success=False, message=f"Object not found: {a_id}")
        if b is None:
            return ToolResult(success=False, message=f"Object not found: {b_id}")

        op = str(arguments.get("operation", "union")).lower()
        if op not in ("union", "difference", "intersection"):
            return ToolResult(success=False, message=f"Unknown operation: {op}")

        a_min, a_max = _bbox_of(a)
        b_min, b_max = _bbox_of(b)

        if op == "union":
            r_min = [min(a_min[i], b_min[i]) for i in range(3)]
            r_max = [max(a_max[i], b_max[i]) for i in range(3)]
        elif op == "intersection":
            r_min = [max(a_min[i], b_min[i]) for i in range(3)]
            r_max = [min(a_max[i], b_max[i]) for i in range(3)]
            if any(r_max[i] < r_min[i] for i in range(3)):
                return ToolResult(success=False, message="Operands do not overlap; intersection is empty")
        else:  # difference: A minus B — bbox encloses A minus the overlap region
            # Approximate as A's bbox; a tighter box would require splitting.
            r_min, r_max = list(a_min), list(a_max)

        size = [max(1e-3, r_max[i] - r_min[i]) for i in range(3)]
        center = [(r_min[i] + r_max[i]) / 2.0 for i in range(3)]

        result = SceneObject.from_dict({
            "name": arguments.get("name") or f"{a.name}_{op}_{b.name}",
            "type": "mesh",
            "geometry": {"type": "box", "params": {"width": size[0], "height": size[1], "depth": size[2]}},
            "material": a.material.to_dict(),
            "transform": {"position": center, "rotation": [0.0, 0.0, 0.0], "scale": [1.0, 1.0, 1.0]},
            "visible": True,
            "locked": False,
            "group_id": None,
            "tags": [f"boolean:{op}", f"src:{a.id}", f"src:{b.id}"],
        })
        result.name = scene.next_auto_name(result.name)
        scene.objects.append(result)

        deltas: List[SceneDelta] = [SceneDelta(action="create", target_id=result.id, payload=result.to_dict())]
        deleted_names: List[str] = []
        if bool(arguments.get("delete_inputs", False)):
            for src in (a, b):
                if src in scene.objects:
                    scene.objects.remove(src)
                    deltas.append(SceneDelta(action="delete", target_id=src.id))
                    deleted_names.append(src.name)

        note = " (inputs removed)" if deleted_names else ""
        return ToolResult(
            success=True,
            message=f"Boolean {op} of {a.name} and {b.name} -> {result.name} (bbox approx{note})",
            deltas=deltas,
            data={"object": result.to_dict(), "operation": op, "size": size, "center": center, "deleted": deleted_names},
        )


class SnapToGridTool(ToolBase):
    """Snap an object's position to the nearest grid increment."""

    name = "snap_to_grid"
    description = "Snap an object's position to the nearest grid increment along specified axes."

    def schema(self) -> Dict[str, Any]:
        return _SNAP_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        target_id = arguments.get("target", "")
        obj = scene.find_object(target_id)
        if not obj:
            return ToolResult(success=False, message=f"Object not found: {target_id}")

        grid = float(arguments.get("grid_size", 1.0))
        if grid <= 0:
            return ToolResult(success=False, message="grid_size must be positive")

        axes_arg = arguments.get("axes", ["x", "y", "z"])
        if not isinstance(axes_arg, list) or not axes_arg:
            axes = {"x", "y", "z"}
        else:
            axes = {str(ax).lower() for ax in axes_arg if str(ax).lower() in _AXIS_INDEX}
        if not axes:
            return ToolResult(success=False, message="No valid axes specified")

        old_pos = list(obj.transform.position)
        new_pos = list(obj.transform.position)
        for ax in axes:
            idx = _AXIS_INDEX[ax]
            new_pos[idx] = round(old_pos[idx] / grid) * grid
        obj.transform.position = new_pos

        return ToolResult(
            success=True,
            message=f"Snapped {obj.name} to grid {grid}: {old_pos} -> {new_pos}",
            deltas=[SceneDelta(action="update", target_id=obj.id, payload=obj.to_dict())],
            data={"object": obj.to_dict(), "old_position": old_pos, "new_position": new_pos, "grid_size": grid},
        )
