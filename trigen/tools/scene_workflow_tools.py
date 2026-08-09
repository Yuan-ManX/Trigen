"""Scene workflow intelligence tools.

Higher-level scene-authoring tools that complement the primitive-level
editing surface with bulk, query, and stylization capabilities:

1. ``QuerySceneTool`` — filter scene objects by attribute (color, geometry
   type, name regex, tag, layer, visibility, metalness range) and return
   compact summaries for downstream reasoning.
2. ``StyleSceneTool`` — apply a named thematic style preset (cyberpunk,
   minimalist, photoreal, noir, sunset, oceanic) by mutating the scene
   background, fog, ambient light, and per-object materials in one call.
3. ``BatchTransformTool`` — apply the same translate / rotate / scale
   operation to many targets at once, more efficient than chaining
   ``transform_object`` calls.
4. ``SceneStatisticsTool`` — read-only stats: object counts by geometry
   type and material color, polygon estimate, scene bounding box, light /
   camera / group / annotation totals.
5. ``ListAnnotationsTool`` — list every on-canvas annotation in the
   scene with its anchor and text payload.
6. ``CameraFlythroughTool`` — animate a camera along a waypoint path
   with per-waypoint look-at targets, speed, and loop options. Emits a
   dedicated ``editor_camera_flythrough`` delta so the frontend can
   preview the cinematic without re-deriving the descriptor.

All tools follow the standard ``ToolBase`` contract: declare ``name``,
``description``, ``schema()``, and ``async def execute(scene, arguments)``.
Mutating tools return ``SceneDelta`` entries so the frontend can apply
incremental updates; read-only tools return ``data`` only.
"""

from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Optional

from trigen.scene import CameraObject, Scene, SceneObject
from trigen.tools.base import SceneDelta, ToolBase, ToolResult


# ---------------------------------------------------------------------------
# Helpers shared by QueryScene and SceneStatistics
# ---------------------------------------------------------------------------

# Rough triangle estimate per geometry type at default segment counts.
# Used by SceneStatisticsTool to surface a polygon estimate without
# requiring the actual mesh data. Values are approximate.
_POLY_ESTIMATE: Dict[str, int] = {
    "box": 12,
    "sphere": 32 * 16 * 2,
    "cylinder": 32 * 4,
    "cone": 32 * 3,
    "torus": 12 * 48 * 2,
    "plane": 2,
    "torusKnot": 64 * 8 * 2,
    "dodecahedron": 36,
    "icosahedron": 20,
    "octahedron": 8,
    "tetrahedron": 4,
    "ring": 24 * 2,
    "capsule": 12 * 16 * 2,
    "tube": 64 * 8 * 2,
    "lathe": 32 * 6 * 2,
    "extrude": 24,
    "text": 200,
    "spline": 64 * 8 * 2,
}


def _estimate_polygons(obj: SceneObject) -> int:
    """Return a rough triangle estimate for an object based on its geometry
    type and params. Falls back to the default table when params are
    missing."""
    geo_type = obj.geometry.type
    params = obj.geometry.params or {}
    if geo_type == "box":
        ws = int(params.get("widthSegments", 1))
        hs = int(params.get("heightSegments", 1))
        ds = int(params.get("depthSegments", 1))
        return 12 * max(1, ws) * max(1, hs) * max(1, ds)
    if geo_type == "sphere":
        ws = int(params.get("widthSegments", 32))
        hs = int(params.get("heightSegments", 16))
        return ws * hs * 2
    if geo_type == "cylinder":
        rs = int(params.get("radialSegments", 32))
        return rs * 4
    if geo_type == "cone":
        rs = int(params.get("radialSegments", 32))
        return rs * 3
    if geo_type == "torus":
        rs = int(params.get("radialSegments", 12))
        ts = int(params.get("tubularSegments", 48))
        return rs * ts * 2
    if geo_type == "plane":
        ws = int(params.get("widthSegments", 1))
        hs = int(params.get("heightSegments", 1))
        return ws * hs * 2
    if geo_type == "torusKnot":
        ts = int(params.get("tubularSegments", 64))
        rs = int(params.get("radialSegments", 8))
        return ts * rs * 2
    if geo_type == "ring":
        ts = int(params.get("thetaSegments", 24))
        return ts * 2
    if geo_type == "capsule":
        cs = int(params.get("capSegments", 12))
        rs = int(params.get("radialSegments", 16))
        return (cs * 2 + rs) * rs
    if geo_type == "tube":
        ts = int(params.get("tubularSegments", 64))
        rs = int(params.get("radialSegments", 8))
        return ts * rs * 2
    if geo_type == "lathe":
        seg = int(params.get("segments", 32))
        pts = params.get("points", [])
        n = len(pts) if isinstance(pts, list) else 4
        return seg * max(1, n - 1) * 2
    return _POLY_ESTIMATE.get(geo_type, 0)


def _layer_of(obj: SceneObject) -> str:
    """Return the layer name tagged on an object (default 'default')."""
    for t in obj.tags:
        if t.startswith("layer:"):
            return t[len("layer:"):]
    return "default"


def _object_summary(obj: SceneObject) -> Dict[str, Any]:
    """Compact object summary returned by QuerySceneTool."""
    return {
        "id": obj.id,
        "name": obj.name,
        "geometry_type": obj.geometry.type,
        "color": obj.material.color,
        "metalness": obj.material.metalness,
        "roughness": obj.material.roughness,
        "position": list(obj.transform.position),
        "visible": obj.visible,
        "layer": _layer_of(obj),
        "tags": list(obj.tags),
        "group_id": obj.group_id,
    }


# --- QuerySceneTool — read-only attribute filter over scene objects ---

_QUERY_SCENE_PARAMS = {
    "type": "object",
    "properties": {
        "geometry_type": {
            "type": "string",
            "description": "(Optional) filter by geometry type: box/sphere/cylinder/cone/torus/plane/torusKnot/dodecahedron/icosahedron/octahedron/tetrahedron/ring/capsule/tube/lathe/extrude/text/spline.",
        },
        "color": {
            "type": "string",
            "description": "(Optional) filter by exact material color hex (case-insensitive), e.g. '#ff0000'.",
        },
        "name_regex": {
            "type": "string",
            "description": "(Optional) case-insensitive regex matched against object names.",
        },
        "tag": {
            "type": "string",
            "description": "(Optional) only return objects whose tags contain this exact tag.",
        },
        "layer": {
            "type": "string",
            "description": "(Optional) only return objects on this named layer.",
        },
        "visible": {
            "type": "boolean",
            "description": "(Optional) filter by visibility flag.",
        },
        "metalness_min": {
            "type": "number",
            "description": "(Optional) minimum metalness (0-1) inclusive.",
        },
        "metalness_max": {
            "type": "number",
            "description": "(Optional) maximum metalness (0-1) inclusive.",
        },
        "limit": {
            "type": "integer",
            "description": "(Optional) cap on the number of returned objects (default 200).",
        },
    },
}


class QuerySceneTool(ToolBase):
    """Filter scene objects by attribute and return compact summaries."""

    name = "query_scene"
    description = (
        "Query the scene for objects matching one or more attribute filters "
        "(geometry type, color, name regex, tag, layer, visibility, metalness "
        "range). Returns compact summaries (id, name, geometry, color, "
        "position, layer, tags) for downstream reasoning. Read-only — does "
        "not mutate the scene."
    )

    def schema(self) -> Dict[str, Any]:
        return _QUERY_SCENE_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        geometry_type = str(arguments.get("geometry_type") or "").lower() or None
        color = str(arguments.get("color") or "").lower() or None
        name_regex = arguments.get("name_regex")
        name_pattern: Optional[re.Pattern] = None
        if name_regex:
            try:
                name_pattern = re.compile(str(name_regex), re.IGNORECASE)
            except re.error as e:
                return ToolResult(success=False, message=f"Invalid name_regex: {e}")
        tag = str(arguments.get("tag") or "") or None
        layer = str(arguments.get("layer") or "") or None
        visible_filter = arguments.get("visible")
        if visible_filter is not None:
            visible_filter = bool(visible_filter)
        m_min = arguments.get("metalness_min")
        m_max = arguments.get("metalness_max")
        try:
            m_min = float(m_min) if m_min is not None else None
            m_max = float(m_max) if m_max is not None else None
        except (TypeError, ValueError):
            return ToolResult(success=False, message="metalness_min/max must be numbers")
        limit = int(arguments.get("limit", 200))
        if limit <= 0:
            limit = 200

        matches: List[Dict[str, Any]] = []
        for obj in scene.objects:
            if geometry_type and obj.geometry.type.lower() != geometry_type:
                continue
            if color and obj.material.color.lower() != color:
                continue
            if name_pattern and not name_pattern.search(obj.name):
                continue
            if tag and tag not in obj.tags:
                continue
            if layer and _layer_of(obj) != layer:
                continue
            if visible_filter is not None and obj.visible != visible_filter:
                continue
            if m_min is not None and obj.material.metalness < m_min:
                continue
            if m_max is not None and obj.material.metalness > m_max:
                continue
            matches.append(_object_summary(obj))
            if len(matches) >= limit:
                break

        return ToolResult(
            success=True,
            message=f"Matched {len(matches)} object(s)" + (f" (capped at {limit})" if len(matches) >= limit else ""),
            deltas=[],
            data={"matches": matches, "count": len(matches), "total_scene_objects": len(scene.objects)},
        )


# --- StyleSceneTool — apply a named thematic style preset to the scene ---

# Each preset defines: background hex, optional fog descriptor, ambient
# light color + intensity, and a material override applied to every
# object (color/metalness/roughness/emissive). Geometry-type-specific
# overrides layer on top of the base material override.
_STYLE_PRESETS: Dict[str, Dict[str, Any]] = {
    "cyberpunk": {
        "background": "#0a0418",
        "fog": {"color": "#1a0438", "near": 18, "far": 60},
        "ambient": {"color": "#3a0a5a", "intensity": 0.5},
        "material": {
            "metalness": 0.85, "roughness": 0.25,
            "emissive": "#ff00aa", "emissive_intensity": 0.4,
        },
        "by_type": {
            "box": {"color": "#1a0a2e", "emissive": "#ff00aa", "emissive_intensity": 0.6},
            "sphere": {"color": "#00F0FF", "emissive": "#00F0FF", "emissive_intensity": 0.8},
            "torus": {"color": "#FFB800", "emissive": "#FFB800", "emissive_intensity": 1.0},
            "plane": {"color": "#0a0418", "emissive": "#000000", "emissive_intensity": 0.0},
        },
    },
    "minimalist": {
        "background": "#f5f5f5",
        "fog": None,
        "ambient": {"color": "#ffffff", "intensity": 0.7},
        "material": {
            "metalness": 0.0, "roughness": 0.6,
            "emissive": "#000000", "emissive_intensity": 0.0,
        },
        "by_type": {
            "box": {"color": "#ffffff"},
            "sphere": {"color": "#222222"},
            "plane": {"color": "#eeeeee"},
            "cylinder": {"color": "#cccccc"},
        },
    },
    "photoreal": {
        "background": "#10141a",
        "fog": {"color": "#10141a", "near": 25, "far": 80},
        "ambient": {"color": "#ffffff", "intensity": 0.35},
        "material": {
            "metalness": 0.4, "roughness": 0.45,
            "emissive": "#000000", "emissive_intensity": 0.0,
        },
        "by_type": {
            "sphere": {"metalness": 0.9, "roughness": 0.15},
            "box": {"metalness": 0.2, "roughness": 0.7},
            "plane": {"metalness": 0.0, "roughness": 0.9},
        },
    },
    "noir": {
        "background": "#050505",
        "fog": {"color": "#050505", "near": 15, "far": 55},
        "ambient": {"color": "#202024", "intensity": 0.3},
        "material": {
            "metalness": 0.6, "roughness": 0.35,
            "emissive": "#000000", "emissive_intensity": 0.0,
        },
        "by_type": {
            "sphere": {"color": "#1a1a1a", "metalness": 1.0, "roughness": 0.1},
            "box": {"color": "#2a2a2a"},
            "plane": {"color": "#0a0a0a"},
        },
    },
    "sunset": {
        "background": "#2a1a2e",
        "fog": {"color": "#5a2a3a", "near": 20, "far": 70},
        "ambient": {"color": "#ff8a5a", "intensity": 0.6},
        "material": {
            "metalness": 0.3, "roughness": 0.5,
            "emissive": "#3a1a1a", "emissive_intensity": 0.2,
        },
        "by_type": {
            "sphere": {"color": "#ffb86a", "emissive": "#ff7a3a", "emissive_intensity": 0.4},
            "box": {"color": "#5a2a3a"},
            "plane": {"color": "#2a1a2e"},
            "torus": {"color": "#ffd86a", "emissive": "#ffaa5a", "emissive_intensity": 0.5},
        },
    },
    "oceanic": {
        "background": "#021a2a",
        "fog": {"color": "#04304a", "near": 18, "far": 60},
        "ambient": {"color": "#3a8aff", "intensity": 0.5},
        "material": {
            "metalness": 0.5, "roughness": 0.3,
            "emissive": "#001a3a", "emissive_intensity": 0.15,
        },
        "by_type": {
            "sphere": {"color": "#1a6aff", "transmission": 0.4, "ior": 1.4, "opacity": 0.85},
            "box": {"color": "#0a3a6a"},
            "plane": {"color": "#021a2a"},
            "torus": {"color": "#3aaaff", "emissive": "#00F0FF", "emissive_intensity": 0.3},
        },
    },
}


_STYLE_SCENE_PARAMS = {
    "type": "object",
    "properties": {
        "preset": {
            "type": "string",
            "enum": list(_STYLE_PRESETS.keys()),
            "description": "Thematic style preset applied to the whole scene.",
        },
        "include_objects": {
            "type": "boolean",
            "description": "If true (default), apply the preset's material overrides to every object. If false, only update background/fog/ambient.",
        },
    },
    "required": ["preset"],
}


def _apply_material_override(obj: SceneObject, override: Dict[str, Any]) -> None:
    """Apply a material override dict to an object. Only known Material
    fields are set; unknown keys are ignored silently."""
    for key, value in override.items():
        if hasattr(obj.material, key):
            try:
                setattr(obj.material, key, value)
            except (TypeError, ValueError):
                continue


class StyleSceneTool(ToolBase):
    """Apply a named thematic style preset to the whole scene at once."""

    name = "style_scene"
    description = (
        "Apply a named thematic style preset (cyberpunk, minimalist, "
        "photoreal, noir, sunset, oceanic) to the whole scene in one call. "
        "Updates the background, fog, ambient light, and per-object "
        "materials with geometry-type-specific overrides. Faster than "
        "calling apply_material on each object individually."
    )

    def schema(self) -> Dict[str, Any]:
        return _STYLE_SCENE_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        preset_name = str(arguments.get("preset", "")).lower()
        if preset_name not in _STYLE_PRESETS:
            return ToolResult(
                success=False,
                message=f"Unknown style preset: {preset_name}. Available: {', '.join(sorted(_STYLE_PRESETS))}",
            )
        include_objects = bool(arguments.get("include_objects", True))
        preset = _STYLE_PRESETS[preset_name]
        deltas: List[SceneDelta] = []

        # Background
        old_bg = scene.background
        scene.background = preset["background"]
        deltas.append(SceneDelta(action="set_background", payload={"background": scene.background, "previous": old_bg}))

        # Fog
        old_fog = scene.fog
        scene.fog = dict(preset["fog"]) if preset["fog"] else None
        deltas.append(SceneDelta(action="set_fog", payload={"fog": scene.fog, "previous": old_fog}))

        # Ambient light — find an existing ambient light and update it; if
        # none exists, leave a note in the message (creating a new light
        # would change light count which can surprise callers).
        ambient_spec = preset.get("ambient")
        ambient_updated = False
        if ambient_spec:
            for light in scene.lights:
                if light.type == "ambient":
                    light.color = ambient_spec["color"]
                    light.intensity = float(ambient_spec["intensity"])
                    deltas.append(SceneDelta(action="update_light", target_id=light.id, payload=light.to_dict()))
                    ambient_updated = True
                    break

        # Per-object materials
        applied_count = 0
        if include_objects:
            base_override = preset.get("material", {})
            by_type = preset.get("by_type", {})
            for obj in scene.objects:
                override = {**base_override, **by_type.get(obj.geometry.type, {})}
                if not override:
                    continue
                _apply_material_override(obj, override)
                deltas.append(SceneDelta(action="update", target_id=obj.id, payload={"material": obj.material.to_dict()}))
                applied_count += 1

        msg = f"Applied '{preset_name}' style preset (background + fog"
        if ambient_updated:
            msg += " + ambient"
        if include_objects:
            msg += f" + {applied_count} object material(s)"
        msg += ")."
        return ToolResult(
            success=True,
            message=msg,
            deltas=deltas,
            data={
                "preset": preset_name,
                "background": scene.background,
                "fog": scene.fog,
                "ambient_updated": ambient_updated,
                "objects_styled": applied_count,
            },
        )


# --- BatchTransformTool — apply same transform op to many targets at once ---

_BATCH_TRANSFORM_PARAMS = {
    "type": "object",
    "properties": {
        "targets": {
            "type": "array",
            "items": {"type": "string"},
            "description": "List of object ids or names to transform.",
        },
        "operation": {
            "type": "string",
            "enum": ["translate", "rotate", "scale", "set_position", "set_rotation", "set_scale"],
            "description": (
                "translate: add delta to current position. "
                "rotate: add delta to current rotation (radians). "
                "scale: multiply current scale by factor. "
                "set_position/set_rotation/set_scale: replace the field entirely."
            ),
        },
        "values": {
            "type": "array",
            "items": {"type": "number"},
            "description": "[x, y, z] vector for the operation.",
        },
    },
    "required": ["targets", "operation", "values"],
}


class BatchTransformTool(ToolBase):
    """Apply the same transform operation to multiple objects at once."""

    name = "batch_transform"
    description = (
        "Apply the same translate/rotate/scale (or set_position/set_rotation/"
        "set_scale) operation to many targets in one call. More efficient "
        "than chaining transform_object calls when several objects should "
        "move/rotate/scale identically — e.g. shifting a group of objects "
        "up by 1 unit, or scaling every selected object by 1.5."
    )

    def schema(self) -> Dict[str, Any]:
        return _BATCH_TRANSFORM_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        targets = arguments.get("targets", [])
        if not isinstance(targets, list) or not targets:
            return ToolResult(success=False, message="targets must be a non-empty array")
        operation = str(arguments.get("operation", "")).lower()
        if operation not in ("translate", "rotate", "scale", "set_position", "set_rotation", "set_scale"):
            return ToolResult(success=False, message=f"Unknown operation: {operation}")
        raw_values = arguments.get("values")
        if not isinstance(raw_values, list) or len(raw_values) != 3:
            return ToolResult(success=False, message="values must be a 3-element array [x,y,z]")
        try:
            values = [float(raw_values[0]), float(raw_values[1]), float(raw_values[2])]
        except (TypeError, ValueError):
            return ToolResult(success=False, message="values must contain numbers")

        deltas: List[SceneDelta] = []
        applied = 0
        missing = 0
        for tgt in targets:
            obj = scene.find_object(str(tgt))
            if not obj:
                missing += 1
                continue
            tf = obj.transform
            if operation == "translate":
                tf.position = [tf.position[i] + values[i] for i in range(3)]
            elif operation == "rotate":
                tf.rotation = [tf.rotation[i] + values[i] for i in range(3)]
            elif operation == "scale":
                tf.scale = [max(1e-6, tf.scale[i] * values[i]) for i in range(3)]
            elif operation == "set_position":
                tf.position = list(values)
            elif operation == "set_rotation":
                tf.rotation = list(values)
            elif operation == "set_scale":
                # Guard against zero scale to avoid degenerate transforms.
                tf.scale = [max(1e-6, v) for v in values]
            deltas.append(SceneDelta(action="update", target_id=obj.id, payload={"transform": tf.to_dict()}))
            applied += 1

        if applied == 0:
            return ToolResult(success=False, message="None of the targets were found in the scene.")
        msg = f"Applied {operation} by [{values[0]:.3f}, {values[1]:.3f}, {values[2]:.3f}] to {applied} object(s)"
        if missing:
            msg += f"; {missing} target(s) not found"
        return ToolResult(
            success=True,
            message=msg,
            deltas=deltas,
            data={"operation": operation, "values": values, "applied_count": applied, "missing_count": missing},
        )


# --- SceneStatisticsTool — read-only detailed scene stats ---


def _scene_bbox(scene: Scene) -> Dict[str, Any]:
    """Compute the axis-aligned bounding box across all visible objects.

    Uses each object's position as the box center and a per-geometry-type
    half-extent approximation derived from transform scale. Returns
    {min, max, size, center}; all zeros when the scene is empty.
    """
    if not scene.objects:
        return {
            "min": [0.0, 0.0, 0.0],
            "max": [0.0, 0.0, 0.0],
            "size": [0.0, 0.0, 0.0],
            "center": [0.0, 0.0, 0.0],
            "empty": True,
        }
    mins = [math.inf, math.inf, math.inf]
    maxs = [-math.inf, -math.inf, -math.inf]
    for obj in scene.objects:
        px, py, pz = (float(v) for v in obj.transform.position)
        sx, sy, sz = (float(v) for v in obj.transform.scale)
        # Per-type half-extent approximation.
        geo = obj.geometry.type
        if geo == "box":
            hx, hy, hz = 0.5 * sx, 0.5 * sy, 0.5 * sz
        elif geo in ("sphere", "icosahedron", "dodecahedron", "octahedron", "tetrahedron"):
            r = 0.6 * max(sx, sy, sz)
            hx = hy = hz = r
        elif geo in ("cylinder", "cone", "capsule"):
            r = 0.5 * max(sx, sz)
            hx = hz = r
            hy = 0.6 * sy
        elif geo == "torus":
            r = 0.8 * max(sx, sz)
            hx = hz = r
            hy = 0.2 * sy
        elif geo == "plane":
            hx = 1.0 * sx
            hy = 0.0
            hz = 1.0 * sz
        else:
            hx = hy = hz = 0.6 * max(sx, sy, sz)
        for i, (p, h) in enumerate(zip((px, py, pz), (hx, hy, hz))):
            if p - h < mins[i]:
                mins[i] = p - h
            if p + h > maxs[i]:
                maxs[i] = p + h
    size = [maxs[i] - mins[i] for i in range(3)]
    center = [(mins[i] + maxs[i]) / 2.0 for i in range(3)]
    return {
        "min": mins,
        "max": maxs,
        "size": size,
        "center": center,
        "empty": False,
    }


class SceneStatisticsTool(ToolBase):
    """Return detailed statistics about the current scene."""

    name = "scene_statistics"
    description = (
        "Return detailed statistics about the current scene: object count, "
        "object counts by geometry type and by material color, polygon "
        "estimate, scene bounding box (min/max/size/center), light/camera/"
        "group/annotation counts. Read-only — does not mutate the scene."
    )

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "include_bbox": {
                    "type": "boolean",
                    "description": "If true (default), include the scene bounding box in the result.",
                },
                "include_polygon_estimate": {
                    "type": "boolean",
                    "description": "If true (default), include the polygon estimate per object and total.",
                },
            },
        }

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        include_bbox = bool(arguments.get("include_bbox", True))
        include_polys = bool(arguments.get("include_polygon_estimate", True))

        by_geometry: Dict[str, int] = {}
        by_color: Dict[str, int] = {}
        by_layer: Dict[str, int] = {}
        by_visibility = {"visible": 0, "hidden": 0}
        by_lock = {"locked": 0, "unlocked": 0}
        polygon_total = 0
        polygon_per_object: List[Dict[str, Any]] = []
        for obj in scene.objects:
            by_geometry[obj.geometry.type] = by_geometry.get(obj.geometry.type, 0) + 1
            by_color[obj.material.color] = by_color.get(obj.material.color, 0) + 1
            layer = _layer_of(obj)
            by_layer[layer] = by_layer.get(layer, 0) + 1
            if obj.visible:
                by_visibility["visible"] += 1
            else:
                by_visibility["hidden"] += 1
            if obj.locked:
                by_lock["locked"] += 1
            else:
                by_lock["unlocked"] += 1
            if include_polys:
                polys = _estimate_polygons(obj)
                polygon_total += polys
                polygon_per_object.append({"id": obj.id, "name": obj.name, "geometry": obj.geometry.type, "polygons": polys})

        stats: Dict[str, Any] = {
            "object_count": len(scene.objects),
            "by_geometry_type": by_geometry,
            "by_color": by_color,
            "by_layer": by_layer,
            "by_visibility": by_visibility,
            "by_lock": by_lock,
            "light_count": len(scene.lights),
            "camera_count": len(scene.cameras),
            "group_count": len(scene.groups),
            "annotation_count": len(scene.annotations),
            "background": scene.background,
            "environment": scene.environment,
            "fog": scene.fog,
            "grid_visible": scene.grid_visible,
            "grid_size": scene.grid_size,
        }
        if include_polys:
            stats["polygon_estimate"] = {
                "total": polygon_total,
                "per_object": polygon_per_object,
            }
        if include_bbox:
            stats["bounding_box"] = _scene_bbox(scene)

        # Compose a brief human-facing summary.
        msg_parts = [
            f"{len(scene.objects)} object(s)",
            f"{len(scene.lights)} light(s)",
            f"{len(scene.cameras)} camera(s)",
            f"{len(scene.groups)} group(s)",
            f"{len(scene.annotations)} annotation(s)",
        ]
        if include_polys and polygon_total > 0:
            msg_parts.append(f"~{polygon_total} triangles")
        return ToolResult(
            success=True,
            message="Scene stats: " + ", ".join(msg_parts) + ".",
            deltas=[],
            data=stats,
        )


# --- ListAnnotationsTool — read-only listing of all annotations ---


class ListAnnotationsTool(ToolBase):
    """List every on-canvas annotation currently in the scene."""

    name = "list_annotations"
    description = (
        "List every on-canvas annotation in the scene with its id, anchor "
        "object id, world-space position, text, title, color, and visibility. "
        "Read-only — does not mutate the scene. Use this before "
        "remove_annotation when you need to discover annotation ids."
    )

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "visible_only": {
                    "type": "boolean",
                    "description": "If true, only return annotations whose visible flag is true (default false).",
                },
            },
        }

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        visible_only = bool(arguments.get("visible_only", False))
        items: List[Dict[str, Any]] = []
        for ann in scene.annotations:
            if visible_only and not ann.get("visible", True):
                continue
            items.append({
                "id": ann.get("id"),
                "object_id": ann.get("object_id"),
                "position": ann.get("position"),
                "text": ann.get("text", ""),
                "title": ann.get("title"),
                "color": ann.get("color", "#22d3ee"),
                "visible": ann.get("visible", True),
            })
        return ToolResult(
            success=True,
            message=f"Scene has {len(items)} annotation(s)" + (" (visible only)" if visible_only else "") + ".",
            deltas=[],
            data={"annotations": items, "count": len(items), "total_in_scene": len(scene.annotations)},
        )


# --- CameraFlythroughTool — animate a camera along a waypoint path ---

_CAMERA_FLYTHROUGH_PARAMS = {
    "type": "object",
    "properties": {
        "camera": {
            "type": "string",
            "description": "(Optional) camera id or name. Defaults to the first camera in the scene.",
        },
        "waypoints": {
            "type": "array",
            "description": (
                "Ordered list of waypoints. Each waypoint is an object with "
                "`position` [x,y,z] (required) and optional `target` [x,y,z] "
                "(look-at point during that segment, defaults to the next "
                "waypoint's position or the camera's current target for the "
                "last waypoint), `dwell` (seconds to hold at this waypoint "
                "before continuing, default 0), and `speed` (m/s for the "
                "segment leaving this waypoint, optional)."
            ),
            "items": {
                "type": "object",
                "properties": {
                    "position": {
                        "type": "array",
                        "items": {"type": "number"},
                        "description": "Camera position at this waypoint [x, y, z].",
                    },
                    "target": {
                        "type": "array",
                        "items": {"type": "number"},
                        "description": "(Optional) look-at target during the segment leaving this waypoint.",
                    },
                    "dwell": {
                        "type": "number",
                        "description": "(Optional) seconds to hold at this waypoint before continuing (default 0).",
                    },
                    "speed": {
                        "type": "number",
                        "description": "(Optional) segment speed in m/s; overrides the global speed for this leg.",
                    },
                },
                "required": ["position"],
            },
            "minItems": 2,
        },
        "speed": {
            "type": "number",
            "description": "Default segment speed in m/s when a waypoint does not override it (default 2.0).",
        },
        "loop": {
            "type": "boolean",
            "description": "If true, the flythrough loops back to the first waypoint after the last (default false).",
        },
        "smooth": {
            "type": "boolean",
            "description": "If true (default), use spline interpolation between waypoints; false = linear.",
        },
    },
    "required": ["waypoints"],
}


class CameraFlythroughTool(ToolBase):
    """Attach a waypoint-based cinematic flythrough animation to a camera."""

    name = "camera_flythrough"
    description = (
        "Animate a camera along an ordered waypoint path with per-waypoint "
        "look-at targets, dwell time, and speed overrides. More expressive "
        "than the basic animate_camera flythrough: each leg can look at a "
        "different target, pause at waypoints, and travel at a different "
        "speed. Emits an editor_camera_flythrough delta so the frontend can "
        "preview the cinematic immediately, and stores the descriptor on the "
        "camera for replay."
    )

    def schema(self) -> Dict[str, Any]:
        return _CAMERA_FLYTHROUGH_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        raw_waypoints = arguments.get("waypoints")
        if not isinstance(raw_waypoints, list) or len(raw_waypoints) < 2:
            return ToolResult(success=False, message="waypoints must be a list of at least 2 entries")

        # Resolve the target camera.
        cam_id = arguments.get("camera")
        camera: Optional[CameraObject] = None
        if cam_id:
            for c in scene.cameras:
                if c.id == str(cam_id) or c.name.lower() == str(cam_id).lower():
                    camera = c
                    break
        if camera is None and scene.cameras:
            camera = scene.cameras[0]
        if camera is None:
            return ToolResult(success=False, message="No camera available in the scene")

        # Normalize waypoints.
        default_target = list(camera.target)
        default_speed = float(arguments.get("speed", 2.0))
        if default_speed <= 0:
            return ToolResult(success=False, message="speed must be positive")
        waypoints: List[Dict[str, Any]] = []
        for idx, wp in enumerate(raw_waypoints):
            if not isinstance(wp, dict):
                return ToolResult(success=False, message=f"waypoint[{idx}] must be an object")
            pos = wp.get("position")
            if not isinstance(pos, list) or len(pos) != 3:
                return ToolResult(success=False, message=f"waypoint[{idx}].position must be [x,y,z]")
            try:
                position = [float(pos[0]), float(pos[1]), float(pos[2])]
            except (TypeError, ValueError):
                return ToolResult(success=False, message=f"waypoint[{idx}].position must contain numbers")
            tgt = wp.get("target")
            if tgt is None:
                # Look at the next waypoint's position, or the camera's
                # current target for the last waypoint.
                if idx + 1 < len(raw_waypoints) and isinstance(raw_waypoints[idx + 1], dict):
                    next_pos = raw_waypoints[idx + 1].get("position")
                    if isinstance(next_pos, list) and len(next_pos) == 3:
                        target = [float(next_pos[0]), float(next_pos[1]), float(next_pos[2])]
                    else:
                        target = list(default_target)
                else:
                    target = list(default_target)
            else:
                if not isinstance(tgt, list) or len(tgt) != 3:
                    return ToolResult(success=False, message=f"waypoint[{idx}].target must be [x,y,z]")
                target = [float(tgt[0]), float(tgt[1]), float(tgt[2])]
            dwell = float(wp.get("dwell", 0.0))
            if dwell < 0:
                dwell = 0.0
            seg_speed = float(wp.get("speed", default_speed))
            if seg_speed <= 0:
                seg_speed = default_speed
            waypoints.append({
                "position": position,
                "target": target,
                "dwell": dwell,
                "speed": seg_speed,
            })

        loop = bool(arguments.get("loop", False))
        smooth = bool(arguments.get("smooth", True))

        # Compute total duration by summing per-leg travel time (distance / speed) + dwell.
        total_distance = 0.0
        total_time = 0.0
        n = len(waypoints)
        for i in range(n):
            wp = waypoints[i]
            total_time += wp["dwell"]
            if i < n - 1:
                nxt = waypoints[i + 1]
                dist = math.sqrt(sum((wp["position"][k] - nxt["position"][k]) ** 2 for k in range(3)))
                total_distance += dist
                total_time += dist / wp["speed"]
            elif loop:
                # Loop leg returns to start.
                first = waypoints[0]
                dist = math.sqrt(sum((wp["position"][k] - first["position"][k]) ** 2 for k in range(3)))
                total_distance += dist
                total_time += dist / wp["speed"]

        descriptor: Dict[str, Any] = {
            "type": "flythrough",
            "waypoints": waypoints,
            "loop": loop,
            "smooth": smooth,
            "speed": default_speed,
            "duration": total_time,
            "distance": total_distance,
        }
        camera.animation = descriptor
        return ToolResult(
            success=True,
            message=(
                f"Attached flythrough animation to camera '{camera.name}' "
                f"({len(waypoints)} waypoints, ~{total_time:.2f}s, "
                f"~{total_distance:.2f}m{' loop' if loop else ''})."
            ),
            deltas=[
                # Update the camera model so the frontend persists the descriptor.
                SceneDelta(action="update_camera", target_id=camera.id, payload=camera.to_dict()),
                # Dedicated editor delta so the frontend can trigger a
                # cinematic preview player without re-deriving the descriptor
                # from the camera object.
                SceneDelta(action="editor_camera_flythrough", target_id=camera.id, payload=descriptor),
            ],
            data={"camera_id": camera.id, "camera_name": camera.name, "descriptor": descriptor},
        )


__all__ = [
    "QuerySceneTool",
    "StyleSceneTool",
    "BatchTransformTool",
    "SceneStatisticsTool",
    "ListAnnotationsTool",
    "CameraFlythroughTool",
]
