"""Mesh surface-detail tools: shell/bevel/inflate + UV/texture mapping + LOD bake.

Each tool is a non-destructive surface operator: instead of mutating the
raw vertex buffers (which would require shipping heavy mesh-processing
dependencies), it annotates the SceneObject with a ``surface_ops`` dict
that the frontend ModifierRenderer component consumes at render time.

Supported operators:

  * ``shell``      — hollow / offset surface (positive shell = inflated outer
                     hull, negative shell = carved inner cavity)
  * ``bevel``      — round the edges / corners of hard-surface geometry.
                     Controls radius, segments, and profile shape.
  * ``inflate``    — push the mesh along vertex normals by a signed amount.
  * ``uv_map``     — specify a projection mode for UVs (box / planar /
                     spherical / cylindrical) so procedurally generated
                     textures line up correctly.
  * ``texture_tile`` — scale / rotate / offset a material's UV transform.
  * ``bake_lod``   — annotate the object with up to 4 LOD levels. The
                     viewport swaps geometry detail based on camera distance.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from trigen.scene import Scene
from trigen.tools.base import ToolBase, ToolResult, SceneDelta


def _find_object(scene: Scene, target: str) -> Optional[Any]:
    """Look up an object by id or case-insensitive name prefix."""
    if not target:
        return scene.most_recent_object() if scene.objects else None
    low = target.lower()
    for obj in scene.objects:
        if obj.id == target or obj.name.lower() == low or obj.name.lower().startswith(low):
            return obj
    return scene.most_recent_object() if scene.objects else None


class ShellModifierTool(ToolBase):
    """Apply a hollow shell / offset-surface modifier to a mesh."""

    name = "shell_modifier"
    description = (
        "Hollow or thicken a mesh using an offset-surface shell. Positive "
        "thickness creates an inflated outer hull; negative thickness carves "
        "an inner cavity. The result is non-destructive and can be adjusted "
        "or cleared later."
    )
    category = "detail"

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "Object id or name. Uses the most recent object when omitted."},
                "thickness": {"type": "number", "description": "Signed shell offset. 0.05 = outer hull, -0.05 = inner cavity.", "default": 0.05},
                "inner_material": {"type": "string", "description": "Optional color hex applied to the inner surface. When omitted the outer material is reused.", "default": ""},
                "flip_normals": {"type": "boolean", "description": "True to show the inside of the shell instead of the outside (for hollow containers).", "default": False},
            },
            "required": [],
        }

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        target = str(arguments.get("target", "") or "")
        thickness = float(arguments.get("thickness", 0.05))
        inner_material = str(arguments.get("inner_material", "") or "")
        flip_normals = bool(arguments.get("flip_normals", False))
        obj = _find_object(scene, target)
        if obj is None:
            return ToolResult(success=False, message=f"shell_modifier: Object '{target}' not found")
        existing = dict(getattr(obj, "surface_ops", None) or {})
        existing["shell"] = {
            "thickness": thickness,
            "inner_material": inner_material,
            "flip_normals": flip_normals,
        }
        obj.surface_ops = existing
        summary = (
            f"Applied {thickness:+.3f} shell modifier to '{obj.name}' "
            f"{'with custom inner surface' if inner_material else 'reusing outer material'}"
        )
        return ToolResult(
            success=True,
            message=summary,
            deltas=[SceneDelta(action="update", target_id=obj.id, payload=obj.to_dict())],
            data={"surface_op": "shell", "object_id": obj.id, "params": existing["shell"]},
        )


class BevelModifierTool(ToolBase):
    """Round the edges / corners of a mesh (non-destructive shader bevel)."""

    name = "bevel_modifier"
    description = (
        "Apply a soft-edge / bevel modifier to an object. Controls radius, "
        "segment count, and the corner profile so hard-surface models read "
        "as physically believable without adding heavy geometry."
    )
    category = "detail"

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "Object id or name."},
                "radius": {"type": "number", "description": "Bevel radius in world units (typically 0.01..0.1).", "default": 0.03},
                "segments": {"type": "integer", "description": "Bevel sample segments (1 = cheap chamfer, 4 = smooth round).", "default": 3, "minimum": 1, "maximum": 8},
                "profile": {"type": "string", "description": "Corner profile shape: 'round' | 'chamfer' | 'concave' | 'convex'.", "default": "round"},
                "angle": {"type": "number", "description": "Only bevel edges whose dihedral angle exceeds this threshold (degrees). 0 = all edges.", "default": 25.0},
            },
            "required": [],
        }

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        target = str(arguments.get("target", "") or "")
        radius = max(0.0, float(arguments.get("radius", 0.03)))
        segments = max(1, min(8, int(arguments.get("segments", 3))))
        profile = str(arguments.get("profile", "round") or "round")
        if profile not in {"round", "chamfer", "concave", "convex"}:
            profile = "round"
        angle = float(arguments.get("angle", 25.0))
        obj = _find_object(scene, target)
        if obj is None:
            return ToolResult(success=False, message=f"bevel_modifier: Object '{target}' not found")
        existing = dict(getattr(obj, "surface_ops", None) or {})
        existing["bevel"] = {
            "radius": radius,
            "segments": segments,
            "profile": profile,
            "angle": angle,
        }
        obj.surface_ops = existing
        summary = f"Applied {profile}-profile bevel (r={radius:.3f}, segs={segments}) to '{obj.name}'"
        return ToolResult(
            success=True,
            message=summary,
            deltas=[SceneDelta(action="update", target_id=obj.id, payload=obj.to_dict())],
            data={"surface_op": "bevel", "object_id": obj.id, "params": existing["bevel"]},
        )


class InflateModifierTool(ToolBase):
    """Push a mesh along its vertex normals (puff / deflate / inflate)."""

    name = "inflate_modifier"
    description = (
        "Uniformly inflate or deflate a mesh along its vertex normals. "
        "Positive values puff the mesh outward; negative values shrink it "
        "along its surface. Works as a quick sculpting pass or for adding "
        "a 'buffer' layer around geometry."
    )
    category = "detail"

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "Object id or name."},
                "amount": {"type": "number", "description": "Signed displacement along normals (e.g. 0.05 puff, -0.03 deflate).", "default": 0.05},
                "preserve_volume": {"type": "boolean", "description": "When true, counteract scale shrinkage from inward normals for organic-looking puff.", "default": True},
            },
            "required": [],
        }

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        target = str(arguments.get("target", "") or "")
        amount = float(arguments.get("amount", 0.05))
        preserve_volume = bool(arguments.get("preserve_volume", True))
        obj = _find_object(scene, target)
        if obj is None:
            return ToolResult(success=False, message=f"inflate_modifier: Object '{target}' not found")
        existing = dict(getattr(obj, "surface_ops", None) or {})
        existing["inflate"] = {"amount": amount, "preserve_volume": preserve_volume}
        obj.surface_ops = existing
        summary = f"Inflated '{obj.name}' along normals by {amount:+.3f}"
        return ToolResult(
            success=True,
            message=summary,
            deltas=[SceneDelta(action="update", target_id=obj.id, payload=obj.to_dict())],
            data={"surface_op": "inflate", "object_id": obj.id, "params": existing["inflate"]},
        )


class ClearSurfaceOpsTool(ToolBase):
    """Strip all shell / bevel / inflate modifiers from an object."""

    name = "clear_surface_ops"
    description = (
        "Remove every non-destructive surface operator (shell, bevel, inflate) "
        "from the target object, restoring its raw geometry appearance."
    )
    category = "detail"

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "Object id or name. Clears the most recent object when omitted."},
            },
            "required": [],
        }

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        target = str(arguments.get("target", "") or "")
        obj = _find_object(scene, target)
        if obj is None:
            return ToolResult(success=False, message=f"clear_surface_ops: Object '{target}' not found")
        obj.surface_ops = {}
        return ToolResult(
            success=True,
            message=f"Cleared surface operators from '{obj.name}'",
            deltas=[SceneDelta(action="update", target_id=obj.id, payload=obj.to_dict())],
        )


class UvMapTool(ToolBase):
    """Specify a UV projection mode for texture mapping."""

    name = "uv_map"
    description = (
        "Choose a UV projection (box / planar / spherical / cylindrical / triplanar) "
        "and set the tile/offset/rotation. Applies procedurally at render time "
        "so generated textures line up correctly with the object shape."
    )
    category = "texture"

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "Object id or name."},
                "projection": {"type": "string", "description": "Projection mode: box | planar | spherical | cylindrical | triplanar.", "default": "box"},
                "scale": {"type": "array", "items": {"type": "number"}, "description": "[u, v] tiling scale.", "default": [1.0, 1.0]},
                "offset": {"type": "array", "items": {"type": "number"}, "description": "[u, v] offset in normalized UV space.", "default": [0.0, 0.0]},
                "rotation": {"type": "number", "description": "UV rotation in degrees around the projection center.", "default": 0.0},
                "axis": {"type": "string", "description": "Primary projection axis for planar/triplanar: x | y | z.", "default": "y"},
            },
            "required": [],
        }

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        target = str(arguments.get("target", "") or "")
        projection = str(arguments.get("projection", "box") or "box").lower()
        if projection not in {"box", "planar", "spherical", "cylindrical", "triplanar"}:
            projection = "box"
        scale_raw = arguments.get("scale", [1.0, 1.0])
        offset_raw = arguments.get("offset", [0.0, 0.0])
        scale = (
            [float(scale_raw[0]), float(scale_raw[1])]
            if isinstance(scale_raw, list) and len(scale_raw) >= 2
            else [1.0, 1.0]
        )
        offset = (
            [float(offset_raw[0]), float(offset_raw[1])]
            if isinstance(offset_raw, list) and len(offset_raw) >= 2
            else [0.0, 0.0]
        )
        rotation = float(arguments.get("rotation", 0.0))
        axis = str(arguments.get("axis", "y") or "y").lower()
        if axis not in {"x", "y", "z"}:
            axis = "y"
        obj = _find_object(scene, target)
        if obj is None:
            return ToolResult(success=False, message=f"uv_map: Object '{target}' not found")
        existing = dict(getattr(obj, "texture_ops", None) or {})
        existing["uv"] = {
            "projection": projection,
            "scale": scale,
            "offset": offset,
            "rotation": rotation,
            "axis": axis,
        }
        obj.texture_ops = existing
        summary = (
            f"UV projection for '{obj.name}' set to {projection} "
            f"(tiling {scale[0]}x{scale[1]}, axis={axis})"
        )
        return ToolResult(
            success=True,
            message=summary,
            deltas=[SceneDelta(action="update", target_id=obj.id, payload=obj.to_dict())],
            data={"texture_op": "uv", "object_id": obj.id, "params": existing["uv"]},
        )


class TextureTileTool(ToolBase):
    """Quickly scale / offset / rotate the UV tiling of an object's material."""

    name = "texture_tile"
    description = (
        "Adjust how a texture repeats across an object's surface by "
        "scaling, offsetting, and rotating the UV transform. A lightweight "
        "companion to the full uv_map tool — useful for texture-material tweaks."
    )
    category = "texture"

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "Object id or name."},
                "tile": {"type": "number", "description": "Uniform tiling multiplier (2 = 2x more repeats).", "default": 1.0},
                "offset_u": {"type": "number", "description": "Horizontal offset in UV space.", "default": 0.0},
                "offset_v": {"type": "number", "description": "Vertical offset in UV space.", "default": 0.0},
                "rotation": {"type": "number", "description": "Rotation in degrees.", "default": 0.0},
            },
            "required": [],
        }

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        target = str(arguments.get("target", "") or "")
        tile = max(0.001, float(arguments.get("tile", 1.0)))
        offset_u = float(arguments.get("offset_u", 0.0))
        offset_v = float(arguments.get("offset_v", 0.0))
        rotation = float(arguments.get("rotation", 0.0))
        obj = _find_object(scene, target)
        if obj is None:
            return ToolResult(success=False, message=f"texture_tile: Object '{target}' not found")
        existing = dict(getattr(obj, "texture_ops", None) or {})
        uv = dict(existing.get("uv") or {})
        uv.setdefault("projection", uv.get("projection") or "box")
        uv["scale"] = [tile, tile]
        uv["offset"] = [offset_u, offset_v]
        uv["rotation"] = rotation
        existing["uv"] = uv
        obj.texture_ops = existing
        return ToolResult(
            success=True,
            message=f"Tiled texture on '{obj.name}' at {tile:.2f}x (rotation {rotation:.0f}°)",
            deltas=[SceneDelta(action="update", target_id=obj.id, payload=obj.to_dict())],
        )


class BakeLodTool(ToolBase):
    """Annotate an object with a level-of-detail chain for the viewport."""

    name = "bake_lod"
    description = (
        "Define up to 4 view-distance LOD levels so distant objects draw with "
        "simpler geometry. Each level carries a distance threshold and a "
        "segment count multiplier (lower = less detail). The viewport picks "
        "the coarsest level whose threshold the camera is past."
    )
    category = "quality"

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "Object id or name."},
                "levels": {
                    "type": "array",
                    "description": "LOD levels. Each item: {distance, detail}. detail in (0,1] where 1.0 = full detail.",
                    "items": {"type": "object"},
                    "default": [
                        {"distance": 8.0, "detail": 1.0},
                        {"distance": 20.0, "detail": 0.6},
                        {"distance": 50.0, "detail": 0.3},
                        {"distance": 120.0, "detail": 0.1},
                    ],
                },
            },
            "required": [],
        }

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        target = str(arguments.get("target", "") or "")
        levels_raw = arguments.get("levels") or [
            {"distance": 8.0, "detail": 1.0},
            {"distance": 20.0, "detail": 0.6},
            {"distance": 50.0, "detail": 0.3},
            {"distance": 120.0, "detail": 0.1},
        ]
        levels: List[Dict[str, float]] = []
        for lvl in list(levels_raw)[:4]:
            try:
                d = float(lvl.get("distance", 8.0))
                det = max(0.01, min(1.0, float(lvl.get("detail", 1.0))))
                levels.append({"distance": d, "detail": det})
            except Exception:
                continue
        levels.sort(key=lambda x: x["distance"])
        obj = _find_object(scene, target)
        if obj is None:
            return ToolResult(success=False, message=f"bake_lod: Object '{target}' not found")
        lod: Dict[str, Any] = {"levels": levels, "enabled": True}
        obj.lod = lod
        return ToolResult(
            success=True,
            message=f"Baked {len(levels)} LOD levels for '{obj.name}'",
            deltas=[SceneDelta(action="update", target_id=obj.id, payload=obj.to_dict())],
            data={"object_id": obj.id, "lod": lod},
        )
