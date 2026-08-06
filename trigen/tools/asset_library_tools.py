"""Asset library, scatter paint, and surface snap tools.

Three creation-category tools that build on the primitive ``create_object``
foundation but raise the abstraction level so the Agent can populate a
scene the way a level designer would:

* ``AssetLibraryTool`` (``place_asset``) — drop a pre-built asset from a
  curated library (cube, sphere, cylinder, tree, rock, lamp, chair,
  table) with sensible material/geometry defaults. Internally derives
  the right ``create_object`` arguments; no new mesh data is required.

* ``ScatterPaintTool`` (``scatter_paint``) — scatter N copies of an
  asset across a horizontal plane region with per-instance jitter.
  Returns the list of created object names so the caller can address
  them as a group afterwards.

* ``SnapToSurfaceTool`` (``snap_to_surface``) — raycast snap an object
  to the highest surface below it (ground plane or top of another
  object). Useful for "drop to floor" / "place on table" semantics
  without forcing the user to compute Y by hand.
"""

from __future__ import annotations

import math
import uuid
from typing import Any, Dict, List, Optional

from trigen.scene import Scene, SceneObject, Geometry, Material, Transform
from trigen.tools.base import SceneDelta, ToolBase, ToolResult


# Curated asset library. Each entry bundles the geometry_type, default
# params, default material, and an auto-name prefix. Values are chosen
# so a single ``place_asset`` call produces a recognizable object the
# user can immediately identify in the outliner.
_ASSET_LIBRARY: Dict[str, Dict[str, Any]] = {
    "cube": {
        "geometry_type": "box",
        "params": {"width": 1.0, "height": 1.0, "depth": 1.0},
        "color": "#cccccc",
        "name_prefix": "Cube",
    },
    "sphere": {
        "geometry_type": "sphere",
        "params": {"radius": 0.6},
        "color": "#cccccc",
        "name_prefix": "Sphere",
    },
    "cylinder": {
        "geometry_type": "cylinder",
        "params": {"radiusTop": 0.5, "radiusBottom": 0.5, "height": 1.2},
        "color": "#cccccc",
        "name_prefix": "Cylinder",
    },
    "tree": {
        # Tree = brown cylinder trunk + green sphere canopy. Materialized
        # as a single sphere-on-cylinder composite via two create_object
        # calls; the canopy is parented visually by position.
        "geometry_type": "cylinder",
        "params": {"radiusTop": 0.15, "radiusBottom": 0.2, "height": 1.6},
        "color": "#6b3f1a",  # bark brown
        "name_prefix": "Tree",
        "canopy": {
            "geometry_type": "sphere",
            "params": {"radius": 0.8},
            "color": "#2f6b2f",  # leaf green
            "y_offset": 1.2,
        },
    },
    "rock": {
        # Rock = grey dodecahedron for an angular look.
        "geometry_type": "dodecahedron",
        "params": {"radius": 0.5},
        "color": "#7d7d7d",
        "name_prefix": "Rock",
    },
    "lamp": {
        # Lamp = emissive sphere on a thin cylinder.
        "geometry_type": "cylinder",
        "params": {"radiusTop": 0.05, "radiusBottom": 0.05, "height": 1.4},
        "color": "#222222",
        "name_prefix": "Lamp",
        "canopy": {
            "geometry_type": "sphere",
            "params": {"radius": 0.25},
            "color": "#ffe082",
            "emissive": "#ffd54f",
            "emissive_intensity": 1.5,
            "y_offset": 0.85,
        },
    },
    "chair": {
        # Chair = box seat + thin box back. Simple blocky silhouette.
        "geometry_type": "box",
        "params": {"width": 0.5, "height": 0.1, "depth": 0.5},
        "color": "#8a5a3b",
        "name_prefix": "Chair",
        "canopy": {
            "geometry_type": "box",
            "params": {"width": 0.5, "height": 0.6, "depth": 0.08},
            "color": "#8a5a3b",
            "y_offset": 0.35,
            "z_offset": -0.21,
        },
    },
    "table": {
        # Table = box top + 4 cylinder legs (legs approximated by a
        # single thick cylinder for a clean silhouette).
        "geometry_type": "cylinder",
        "params": {"radiusTop": 0.05, "radiusBottom": 0.05, "height": 0.7},
        "color": "#5a3a22",
        "name_prefix": "Table",
        "canopy": {
            "geometry_type": "box",
            "params": {"width": 1.2, "height": 0.08, "depth": 0.8},
            "color": "#5a3a22",
            "y_offset": 0.4,
        },
    },
}


_PLACE_ASSET_PARAMS = {
    "type": "object",
    "properties": {
        "asset_id": {
            "type": "string",
            "enum": list(_ASSET_LIBRARY.keys()),
            "description": (
                "Asset to place from the library. One of: "
                + ", ".join(_ASSET_LIBRARY.keys()) + "."
            ),
        },
        "position": {
            "type": "array",
            "items": {"type": "number"},
            "description": "Position [x, y, z] for the placed asset (default [0, 0, 0]).",
        },
        "scale": {
            "type": "number",
            "description": "Uniform scale multiplier applied to the asset (default 1.0).",
        },
        "name": {
            "type": "string",
            "description": "Optional override name. When omitted, the asset's name_prefix is used with an auto-increment suffix.",
        },
    },
    "required": ["asset_id"],
}


_SCATTER_PAINT_PARAMS = {
    "type": "object",
    "properties": {
        "asset_id": {
            "type": "string",
            "enum": list(_ASSET_LIBRARY.keys()),
            "description": "Asset to scatter.",
        },
        "count": {
            "type": "integer",
            "description": "Number of copies to scatter (default 8, capped at 50).",
            "minimum": 1,
            "maximum": 50,
        },
        "center": {
            "type": "array",
            "items": {"type": "number"},
            "description": "Center of the scatter region [x, y, z] (default [0, 0, 0]). The y coordinate is the placement plane.",
        },
        "radius": {
            "type": "number",
            "description": "Radius of the scatter region on the XZ plane (default 5).",
            "minimum": 0,
        },
        "jitter": {
            "type": "number",
            "description": "Per-instance scale jitter multiplier (default 0.2 = ±20%). 0 = uniform scale.",
            "minimum": 0,
            "maximum": 1,
        },
        "scale": {
            "type": "number",
            "description": "Base uniform scale applied to every scattered copy (default 1.0).",
        },
    },
    "required": ["asset_id"],
}


_SNAP_TO_SURFACE_PARAMS = {
    "type": "object",
    "properties": {
        "target": {
            "type": "string",
            "description": "Object id or name to snap.",
        },
        "surface": {
            "type": "string",
            "description": (
                "Surface to snap onto. 'ground' (default) snaps to the y=0 plane. "
                "Any other string is interpreted as an object name/id whose top "
                "becomes the snap surface."
            ),
        },
    },
    "required": ["target"],
}


def _make_material(color: str, emissive: Optional[str] = None, emissive_intensity: float = 0.0) -> Material:
    """Build a Material with optional emissive fields populated."""
    mat = Material(color=color)
    if emissive:
        mat.emissive = emissive
        mat.emissive_intensity = float(emissive_intensity)
    return mat


def _bbox_top_y(obj: SceneObject) -> float:
    """Return the world-space Y of the top of an object's bounding box.

    Uses the same geometry-aware half-extent heuristic as
    ``composite_tools._bbox_of`` so the snap target matches what the
    user sees in the viewport. Returns 0.0 for unknown geometry types.
    """
    g = obj.geometry
    p = g.params or {}
    t = g.type
    hy = 0.5
    if t == "box":
        hy = float(p.get("height", 1.0)) / 2
    elif t in ("sphere", "icosahedron", "dodecahedron", "octahedron", "tetrahedron"):
        hy = float(p.get("radius", 0.6))
    elif t in ("cylinder", "cone"):
        hy = float(p.get("height", 1.2)) / 2
    elif t == "torus":
        hy = float(p.get("tube", 0.2))
    elif t == "capsule":
        hy = float(p.get("radius", 0.4)) + float(p.get("length", 0.8)) / 2
    elif t == "plane":
        hy = 0.0
    sy = obj.transform.scale[1] if len(obj.transform.scale) == 3 else 1.0
    py = obj.transform.position[1] if len(obj.transform.position) == 3 else 0.0
    return py + hy * abs(sy)


def _bbox_bottom_y(obj: SceneObject) -> float:
    """Return the world-space Y of the bottom of an object's bounding box."""
    g = obj.geometry
    p = g.params or {}
    t = g.type
    hy = 0.5
    if t == "box":
        hy = float(p.get("height", 1.0)) / 2
    elif t in ("sphere", "icosahedron", "dodecahedron", "octahedron", "tetrahedron"):
        hy = float(p.get("radius", 0.6))
    elif t in ("cylinder", "cone"):
        hy = float(p.get("height", 1.2)) / 2
    elif t == "torus":
        hy = float(p.get("tube", 0.2))
    elif t == "capsule":
        hy = float(p.get("radius", 0.4)) + float(p.get("length", 0.8)) / 2
    elif t == "plane":
        hy = 0.0
    sy = obj.transform.scale[1] if len(obj.transform.scale) == 3 else 1.0
    py = obj.transform.position[1] if len(obj.transform.position) == 3 else 0.0
    return py - hy * abs(sy)


class AssetLibraryTool(ToolBase):
    """Place a pre-built asset from the curated library.

    Each asset bundles sensible geometry defaults, a starting material,
    and an auto-name prefix. Composite assets (tree, lamp, chair, table)
    emit a primary mesh plus an optional secondary mesh positioned on top
    so the user sees a recognizable silhouette without manual assembly.
    """

    name = "place_asset"
    description = (
        "Place a pre-built asset from the Trigen asset library "
        "(cube, sphere, cylinder, tree, rock, lamp, chair, table). "
        "Composite assets (tree, lamp, chair, table) auto-assemble their "
        "secondary parts so a single call produces a recognizable object."
    )

    def schema(self) -> Dict[str, Any]:
        return _PLACE_ASSET_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        asset_id = str(arguments.get("asset_id", "")).strip().lower()
        if asset_id not in _ASSET_LIBRARY:
            return ToolResult(
                success=False,
                message=(
                    f"Unknown asset_id: {asset_id!r}. Available: "
                    f"{', '.join(_ASSET_LIBRARY.keys())}"
                ),
            )
        spec = _ASSET_LIBRARY[asset_id]
        position = arguments.get("position", [0.0, 0.0, 0.0])
        if not isinstance(position, list) or len(position) != 3:
            position = [0.0, 0.0, 0.0]
        try:
            position = [float(v) for v in position]
        except (TypeError, ValueError):
            return ToolResult(success=False, message=f"Invalid position: {position!r}")
        try:
            scale = float(arguments.get("scale", 1.0))
        except (TypeError, ValueError):
            scale = 1.0
        if scale <= 0:
            return ToolResult(success=False, message=f"scale must be positive, got {scale}")

        # Build the primary mesh.
        primary_name = scene.next_auto_name(
            arguments.get("name") or spec["name_prefix"]
        )
        primary = SceneObject(
            name=primary_name,
            geometry=Geometry(type=spec["geometry_type"], params=dict(spec.get("params", {}))),
            material=_make_material(spec["color"]),
            transform=Transform(
                position=list(position),
                rotation=[0.0, 0.0, 0.0],
                scale=[scale, scale, scale],
            ),
        )
        scene.objects.append(primary)
        deltas: List[SceneDelta] = [SceneDelta(action="create", target_id=primary.id, payload=primary.to_dict())]
        created_names: List[str] = [primary.name]

        # Composite assets: emit the secondary mesh positioned on top of
        # the primary. The canopy spec describes the secondary geometry.
        canopy_spec = spec.get("canopy")
        if canopy_spec:
            y_off = float(canopy_spec.get("y_offset", 0.0))
            z_off = float(canopy_spec.get("z_offset", 0.0))
            canopy_pos = [
                position[0],
                position[1] + y_off * scale,
                position[2] + z_off * scale,
            ]
            canopy_name = scene.next_auto_name(f"{primary_name}_Top")
            canopy_mat = _make_material(
                canopy_spec["color"],
                emissive=canopy_spec.get("emissive"),
                emissive_intensity=canopy_spec.get("emissive_intensity", 0.0),
            )
            canopy = SceneObject(
                name=canopy_name,
                geometry=Geometry(type=canopy_spec["geometry_type"], params=dict(canopy_spec.get("params", {}))),
                material=canopy_mat,
                transform=Transform(
                    position=canopy_pos,
                    rotation=[0.0, 0.0, 0.0],
                    scale=[scale, scale, scale],
                ),
            )
            scene.objects.append(canopy)
            deltas.append(SceneDelta(action="create", target_id=canopy.id, payload=canopy.to_dict()))
            created_names.append(canopy.name)

        return ToolResult(
            success=True,
            message=f"Placed {asset_id} -> {primary.name}"
            + (f" (+{len(created_names) - 1} part(s))" if len(created_names) > 1 else ""),
            deltas=deltas,
            data={
                "asset_id": asset_id,
                "created": created_names,
                "position": position,
                "scale": scale,
            },
        )


class ScatterPaintTool(ToolBase):
    """Scatter N copies of an asset across a horizontal plane region.

    The scatter region is a disc of ``radius`` centered at ``center`` on
    the XZ plane. Each copy receives a per-instance scale jitter so the
    result reads as a natural cluster (rocks, trees, grass tufts) rather
    than a uniform grid.
    """

    name = "scatter_paint"
    description = (
        "Scatter N copies of a library asset across a horizontal disc "
        "with per-instance position and scale jitter. Useful for populating "
        "forests, rock fields, or crowd clusters in a single call."
    )

    def schema(self) -> Dict[str, Any]:
        return _SCATTER_PAINT_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        asset_id = str(arguments.get("asset_id", "")).strip().lower()
        if asset_id not in _ASSET_LIBRARY:
            return ToolResult(
                success=False,
                message=f"Unknown asset_id: {asset_id!r}. Available: {', '.join(_ASSET_LIBRARY.keys())}",
            )
        try:
            count = int(arguments.get("count", 8))
        except (TypeError, ValueError):
            count = 8
        count = max(1, min(50, count))

        center = arguments.get("center", [0.0, 0.0, 0.0])
        if not isinstance(center, list) or len(center) != 3:
            center = [0.0, 0.0, 0.0]
        try:
            center = [float(v) for v in center]
        except (TypeError, ValueError):
            return ToolResult(success=False, message=f"Invalid center: {center!r}")

        try:
            radius = float(arguments.get("radius", 5.0))
        except (TypeError, ValueError):
            radius = 5.0
        if radius < 0:
            return ToolResult(success=False, message=f"radius must be ≥ 0, got {radius}")

        try:
            jitter = float(arguments.get("jitter", 0.2))
        except (TypeError, ValueError):
            jitter = 0.2
        jitter = max(0.0, min(1.0, jitter))

        try:
            base_scale = float(arguments.get("scale", 1.0))
        except (TypeError, ValueError):
            base_scale = 1.0
        if base_scale <= 0:
            return ToolResult(success=False, message=f"scale must be positive, got {base_scale}")

        spec = _ASSET_LIBRARY[asset_id]
        deltas: List[SceneDelta] = []
        created_names: List[str] = []
        # Use uuid-seeded pseudo-randomness derived from the call so the
        # scatter is deterministic per invocation (easier to test). We
        # pull values from a simple LCG seeded from the asset name + count.
        seed_str = f"{asset_id}:{count}:{center[0]:.3f}:{center[2]:.3f}:{radius:.3f}"
        seed = abs(hash(seed_str)) % (2 ** 31)
        rng_state = [seed]

        def _rand() -> float:
            # Numerical Recipes LCG constants.
            rng_state[0] = (1664525 * rng_state[0] + 1013904223) % (2 ** 32)
            return rng_state[0] / float(2 ** 32)

        for i in range(count):
            # Uniformly sample a point inside the disc.
            r = radius * math.sqrt(_rand())
            theta = 2.0 * math.pi * _rand()
            px = center[0] + r * math.cos(theta)
            pz = center[2] + r * math.sin(theta)
            py = center[1]
            # Per-instance scale jitter: base * (1 ± jitter).
            j = 1.0 + (2.0 * _rand() - 1.0) * jitter
            inst_scale = max(0.05, base_scale * j)

            name = scene.next_auto_name(spec["name_prefix"])
            obj = SceneObject(
                name=name,
                geometry=Geometry(type=spec["geometry_type"], params=dict(spec.get("params", {}))),
                material=_make_material(spec["color"]),
                transform=Transform(
                    position=[px, py, pz],
                    rotation=[0.0, 2.0 * math.pi * _rand(), 0.0],
                    scale=[inst_scale, inst_scale, inst_scale],
                ),
            )
            scene.objects.append(obj)
            deltas.append(SceneDelta(action="create", target_id=obj.id, payload=obj.to_dict()))
            created_names.append(name)

        return ToolResult(
            success=True,
            message=f"Scattered {count} {asset_id}(s) within radius {radius} at {center}",
            deltas=deltas,
            data={
                "asset_id": asset_id,
                "count": count,
                "center": center,
                "radius": radius,
                "jitter": jitter,
                "created": created_names,
            },
        )


class SnapToSurfaceTool(ToolBase):
    """Raycast snap an object to the highest surface below it.

    The snap is a vertical drop: the target's bottom Y is set to either
    the y=0 ground plane (when ``surface='ground'``) or the top Y of
    another object whose AABB is below the target. The X/Z position is
    preserved.
    """

    name = "snap_to_surface"
    description = (
        "Snap an object to the highest surface below it (the y=0 ground "
        "plane or the top of another named object). Use to 'drop to floor' "
        "or 'place on table' without computing Y by hand."
    )

    def schema(self) -> Dict[str, Any]:
        return _SNAP_TO_SURFACE_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        target_id = str(arguments.get("target", "")).strip()
        if not target_id:
            return ToolResult(success=False, message="snap_to_surface requires a 'target'.")
        obj = scene.find_object(target_id)
        if obj is None:
            return ToolResult(success=False, message=f"Object not found: {target_id}")

        surface_arg = str(arguments.get("surface", "ground") or "ground").strip()
        old_pos = list(obj.transform.position)
        old_bottom = _bbox_bottom_y(obj)

        if surface_arg.lower() == "ground":
            new_bottom = 0.0
        else:
            surface_obj = scene.find_object(surface_arg)
            if surface_obj is None:
                return ToolResult(
                    success=False,
                    message=f"Surface object not found: {surface_arg}"
                )
            new_bottom = _bbox_top_y(surface_obj)

        # Shift the object so its bottom rests on the chosen surface.
        delta_y = new_bottom - old_bottom
        new_pos = [old_pos[0], old_pos[1] + delta_y, old_pos[2]]
        obj.transform.position = new_pos

        return ToolResult(
            success=True,
            message=(
                f"Snapped {obj.name} bottom from y={old_bottom:.3f} to y={new_bottom:.3f} "
                f"on {surface_arg}; new position {new_pos}"
            ),
            deltas=[SceneDelta(action="update", target_id=obj.id, payload=obj.to_dict())],
            data={
                "object": obj.to_dict(),
                "old_position": old_pos,
                "new_position": new_pos,
                "old_bottom_y": old_bottom,
                "new_bottom_y": new_bottom,
                "surface": surface_arg,
            },
        )


__all__ = [
    "AssetLibraryTool",
    "ScatterPaintTool",
    "SnapToSurfaceTool",
    "_ASSET_LIBRARY",
]
