"""Scene inspection tool.

Returns a detailed summary of the current scene: object/light/camera/group
counts, bounding box, material color distribution, and geometry type
distribution. Read-only — does not mutate the scene.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

from trigen.scene import Scene, SceneObject
from trigen.tools.base import ToolBase, ToolResult


_SCENE_INFO_PARAMS = {
    "type": "object",
    "properties": {
        "include_object_list": {
            "type": "boolean",
            "description": "Whether to include the full object/light/camera list in the result (default false, returns summary only)",
        },
    },
    "required": [],
}


def _estimate_half_extents(obj: SceneObject) -> List[float]:
    """Estimate half-extents of an object in local space, then apply scale."""
    geo = obj.geometry
    p = geo.params
    t = geo.type
    if t == "box":
        he = [p.get("width", 1.0) / 2, p.get("height", 1.0) / 2, p.get("depth", 1.0) / 2]
    elif t == "sphere":
        r = p.get("radius", 0.6)
        he = [r, r, r]
    elif t == "cylinder":
        r = max(p.get("radiusTop", 0.5), p.get("radiusBottom", 0.5))
        h = p.get("height", 1.2)
        he = [r, h / 2, r]
    elif t == "cone":
        r = p.get("radius", 0.6)
        h = p.get("height", 1.2)
        he = [r, h / 2, r]
    elif t == "torus":
        R = p.get("radius", 0.6)
        tube = p.get("tube", 0.2)
        he = [R + tube, tube, R + tube]
    elif t == "plane":
        he = [p.get("width", 2.0) / 2, 0.001, p.get("height", 2.0) / 2]
    elif t in ("icosahedron", "dodecahedron", "octahedron", "tetrahedron"):
        r = p.get("radius", 0.6)
        he = [r, r, r]
    elif t == "torusKnot":
        R = p.get("radius", 0.6)
        tube = p.get("tube", 0.2)
        he = [R + tube, R + tube, R + tube]
    elif t == "ring":
        outer = p.get("outerRadius", 0.7)
        he = [outer, 0.001, outer]
    elif t == "capsule":
        r = p.get("radius", 0.4)
        length = p.get("length", 0.8)
        he = [r, length / 2 + r, r]
    elif t == "tube":
        r = p.get("radius", 0.3)
        he = [r, r, r]
    else:
        he = [0.5, 0.5, 0.5]
    s = obj.transform.scale
    return [he[i] * s[i] for i in range(3)]


def _compute_bbox(scene: Scene) -> Optional[Tuple[List[float], List[float]]]:
    """Compute scene bounding box as (min, max). Returns None if no visible objects."""
    if not scene.objects:
        return None
    minp = [float("inf")] * 3
    maxp = [float("-inf")] * 3
    found = False
    for obj in scene.objects:
        if not obj.visible:
            continue
        pos = obj.transform.position
        he = _estimate_half_extents(obj)
        for i in range(3):
            minp[i] = min(minp[i], pos[i] - he[i])
            maxp[i] = max(maxp[i], pos[i] + he[i])
        found = True
    if not found:
        return None
    return minp, maxp


class SceneInfoTool(ToolBase):
    """Scene info tool."""

    name = "scene_info"
    description = (
        "Return a detailed summary of the current scene: object count, light count, "
        "camera count, group count, bounding box, material color distribution, "
        "and geometry type distribution."
    )

    def schema(self) -> Dict[str, Any]:
        return _SCENE_INFO_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        obj_count = len(scene.objects)
        light_count = len(scene.lights)
        camera_count = len(scene.cameras)
        group_count = len(scene.groups)

        # Geometry type distribution
        geo_dist = Counter(o.geometry.type for o in scene.objects)
        # Material color distribution
        color_dist = Counter(o.material.color for o in scene.objects)
        # Light type distribution
        light_type_dist = Counter(l.type for l in scene.lights)

        # Bounding box
        bbox = _compute_bbox(scene)

        lines: List[str] = []
        lines.append("=== Scene Info ===")
        lines.append(f"Objects: {obj_count}")
        lines.append(f"Lights: {light_count}")
        lines.append(f"Cameras: {camera_count}")
        lines.append(f"Groups: {group_count}")
        lines.append(f"Background: {scene.background}")
        if scene.fog:
            lines.append(f"Fog: {scene.fog}")
        else:
            lines.append("Fog: off")
        lines.append(f"Grid: visible={scene.grid_visible}, size={scene.grid_size}")

        if bbox:
            minp, maxp = bbox
            size = [maxp[i] - minp[i] for i in range(3)]
            lines.append(
                f"BBox: min=[{minp[0]:.2f}, {minp[1]:.2f}, {minp[2]:.2f}], "
                f"max=[{maxp[0]:.2f}, {maxp[1]:.2f}, {maxp[2]:.2f}], "
                f"size=[{size[0]:.2f}, {size[1]:.2f}, {size[2]:.2f}]"
            )
        else:
            lines.append("BBox: (no visible objects in scene)")

        if geo_dist:
            geo_str = ", ".join(f"{k}:{v}" for k, v in geo_dist.most_common())
            lines.append(f"Geometry: {geo_str}")
        else:
            lines.append("Geometry: (empty)")
        if color_dist:
            color_str = ", ".join(f"{k}:{v}" for k, v in color_dist.most_common())
            lines.append(f"Material colors: {color_str}")
        if light_type_dist:
            light_str = ", ".join(f"{k}:{v}" for k, v in light_type_dist.most_common())
            lines.append(f"Light types: {light_str}")

        message = "\n".join(lines)

        data: Dict[str, Any] = {
            "object_count": obj_count,
            "light_count": light_count,
            "camera_count": camera_count,
            "group_count": group_count,
            "background": scene.background,
            "fog": scene.fog,
            "grid_visible": scene.grid_visible,
            "grid_size": scene.grid_size,
            "geometry_distribution": dict(geo_dist),
            "material_color_distribution": dict(color_dist),
            "light_type_distribution": dict(light_type_dist),
            "bounding_box": {
                "min": bbox[0] if bbox else None,
                "max": bbox[1] if bbox else None,
                "size": [bbox[1][i] - bbox[0][i] for i in range(3)] if bbox else None,
            },
        }

        # Optionally include full lists
        if arguments.get("include_object_list"):
            data["objects"] = [o.to_dict() for o in scene.objects]
            data["lights"] = [l.to_dict() for l in scene.lights]
            data["cameras"] = [c.to_dict() for c in scene.cameras]
            data["groups"] = [g.to_dict() for g in scene.groups]

        return ToolResult(
            success=True,
            message=message,
            deltas=[],
            data=data,
        )
