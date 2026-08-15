"""Viewport presentation and batch authoring tools.

Provides viewport shading mode, procedural curve creation, batch object
spawning, material texture mapping, and viewport background configuration.
These tools follow the same ToolBase / ToolResult / SceneDelta contract as
the rest of the trigen.tools package.
"""

from __future__ import annotations

from typing import Any, Dict, List

from trigen.scene import (
    GEOMETRY_DEFAULTS,
    GEOMETRY_DISPLAY_NAMES,
    Geometry,
    Material,
    Scene,
    SceneObject,
    Transform,
)
from trigen.tools.base import SceneDelta, ToolBase, ToolResult


def _ensure_scene_metadata(scene: Scene) -> Dict[str, Any]:
    """Return the scene's metadata dict, initializing it on first use.

    The base Scene dataclass does not declare a ``metadata`` field, so
    viewport presentation state (shading mode, background, etc.) is attached
    dynamically for forward-compatible storage without schema migration.
    """
    metadata = getattr(scene, "metadata", None)
    if not isinstance(metadata, dict):
        metadata = {}
        scene.metadata = metadata  # type: ignore[attr-defined]
    return metadata


def _ensure_material_params(material: Material) -> Dict[str, Any]:
    """Return a material's params dict, initializing it on first use.

    The base Material dataclass does not declare a ``params`` field; texture
    descriptors are attached dynamically so they travel with the material
    without requiring a schema change.
    """
    params = getattr(material, "params", None)
    if not isinstance(params, dict):
        params = {}
        material.params = params  # type: ignore[attr-defined]
    return params


# --- SetViewportShadingTool -------------------------------------------------

_SET_VIEWPORT_SHADING_PARAMS = {
    "type": "object",
    "properties": {
        "mode": {
            "type": "string",
            "enum": ["wireframe", "solid", "material", "rendered"],
            "description": "Viewport rendering mode",
        },
    },
    "required": ["mode"],
}


class SetViewportShadingTool(ToolBase):
    """Set the viewport rendering mode (wireframe / solid / material / rendered)."""

    name = "set_viewport_shading"
    description = (
        "Set the viewport rendering mode: wireframe, solid, material, or rendered. "
        "Controls how the active viewport shades scene geometry."
    )

    def schema(self) -> Dict[str, Any]:
        return _SET_VIEWPORT_SHADING_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        mode = str(arguments.get("mode", "")).strip().lower()
        valid = {"wireframe", "solid", "material", "rendered"}
        if mode not in valid:
            return ToolResult(
                success=False,
                message=f"Invalid shading mode '{mode}'. Valid modes: {', '.join(sorted(valid))}",
            )

        metadata = _ensure_scene_metadata(scene)
        previous = metadata.get("viewport_shading")
        metadata["viewport_shading"] = mode

        return ToolResult(
            success=True,
            message=f"Viewport shading set to '{mode}'" + (
                f" (was '{previous}')" if previous else ""
            ),
            deltas=[SceneDelta(action="update", payload={"viewport_shading": mode})],
            data={"viewport_shading": mode, "previous": previous},
        )


# --- CreateCurveTool --------------------------------------------------------

_CREATE_CURVE_PARAMS = {
    "type": "object",
    "properties": {
        "points": {
            "type": "array",
            "items": {
                "type": "array",
                "items": {"type": "number"},
                "description": "Control point [x, y, z]",
            },
            "description": "Bezier control points (at least 2 required)",
        },
        "name": {"type": "string", "description": "Curve object name (default 'Curve')"},
        "closed": {"type": "boolean", "description": "Whether the curve is closed (default false)"},
        "color": {"type": "string", "description": "Curve material color (hex, default '#ffffff')"},
    },
    "required": ["points"],
}


class CreateCurveTool(ToolBase):
    """Create a bezier curve object in the scene."""

    name = "create_curve"
    description = (
        "Create a bezier curve object from a list of [x, y, z] control points "
        "(minimum 2 points). Supports open/closed curves and a material color."
    )

    def schema(self) -> Dict[str, Any]:
        return _CREATE_CURVE_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        raw_points = arguments.get("points")
        if not isinstance(raw_points, list) or len(raw_points) < 2:
            return ToolResult(
                success=False,
                message="At least 2 control points are required to create a curve",
            )

        # Normalize and validate each control point to [x, y, z].
        points: List[List[float]] = []
        for idx, pt in enumerate(raw_points):
            if not isinstance(pt, (list, tuple)) or len(pt) != 3:
                return ToolResult(
                    success=False,
                    message=f"Point #{idx} must be a [x, y, z] array",
                )
            try:
                points.append([float(pt[0]), float(pt[1]), float(pt[2])])
            except (TypeError, ValueError):
                return ToolResult(
                    success=False,
                    message=f"Point #{idx} contains non-numeric values",
                )

        closed = bool(arguments.get("closed", False))
        color = str(arguments.get("color", "#ffffff")) or "#ffffff"
        base_name = str(arguments.get("name", "Curve")) or "Curve"
        name = scene.next_auto_name(base_name)

        obj = SceneObject(
            name=name,
            type="mesh",
            geometry=Geometry(
                type="curve",
                params={
                    "points": points,
                    "closed": closed,
                },
            ),
            material=Material(color=color),
            transform=Transform(),
        )
        scene.objects.append(obj)

        return ToolResult(
            success=True,
            message=f"Created curve '{name}' with {len(points)} control point(s), color {color}",
            deltas=[SceneDelta(action="create", target_id=obj.id, payload=obj.to_dict())],
            data={"object": obj.to_dict()},
        )


# --- BatchCreateObjectsTool -------------------------------------------------

_BATCH_CREATE_PARAMS = {
    "type": "object",
    "properties": {
        "objects": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "geometry_type": {
                        "type": "string",
                        "description": "Geometry type (e.g. box, sphere, cylinder, cone, torus, plane)",
                    },
                    "name": {"type": "string", "description": "Object name"},
                    "position": {
                        "type": "array",
                        "items": {"type": "number"},
                        "description": "Initial position [x, y, z]",
                    },
                    "color": {"type": "string", "description": "Material color (hex)"},
                    "size": {"type": "number", "description": "Uniform scale factor (default 1.0)"},
                },
                "required": ["geometry_type"],
            },
            "description": "List of object specs to create",
        },
    },
    "required": ["objects"],
}


class BatchCreateObjectsTool(ToolBase):
    """Create multiple objects in a single call."""

    name = "batch_create_objects"
    description = (
        "Create multiple 3D objects in one call. Each spec accepts geometry_type, "
        "name, position, color, and a uniform size. Returns one create delta per object."
    )

    def schema(self) -> Dict[str, Any]:
        return _BATCH_CREATE_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        specs = arguments.get("objects")
        if not isinstance(specs, list) or not specs:
            return ToolResult(
                success=False,
                message="No object specs provided",
            )

        deltas: List[SceneDelta] = []
        errors: List[str] = []
        created: List[Dict[str, Any]] = []

        for i, spec in enumerate(specs):
            if not isinstance(spec, dict):
                errors.append(f"Spec #{i}: not an object")
                continue

            geo_type = str(spec.get("geometry_type", "")).strip()
            if geo_type not in GEOMETRY_DEFAULTS:
                errors.append(
                    f"Spec #{i}: unsupported geometry_type '{geo_type}'"
                )
                continue

            # Merge geometry defaults with any user-supplied params.
            params = dict(GEOMETRY_DEFAULTS[geo_type])

            position = spec.get("position", [0.0, 0.0, 0.0])
            if not isinstance(position, list) or len(position) != 3:
                position = [0.0, 0.0, 0.0]

            try:
                size = float(spec.get("size", 1.0))
            except (TypeError, ValueError):
                size = 1.0
            scale = [size, size, size]

            color = str(spec.get("color", "#cccccc")) or "#cccccc"

            base_name = str(spec.get("name", "")) or GEOMETRY_DISPLAY_NAMES.get(geo_type, "Object")
            name = scene.next_auto_name(base_name)

            obj = SceneObject(
                name=name,
                type="mesh",
                geometry=Geometry(type=geo_type, params=params),
                material=Material(color=color),
                transform=Transform(
                    position=[float(p) for p in position],
                    scale=scale,
                ),
            )
            scene.objects.append(obj)

            deltas.append(SceneDelta(action="create", target_id=obj.id, payload=obj.to_dict()))
            created.append(obj.to_dict())

        if not created:
            return ToolResult(
                success=False,
                message="No objects were created. " + "; ".join(errors),
            )

        message = f"Created {len(created)} object(s)"
        if errors:
            message += f"; skipped {len(errors)} invalid spec(s)"

        return ToolResult(
            success=True,
            message=message,
            deltas=deltas,
            data={"objects": created, "errors": errors},
        )


# --- SetMaterialTextureTool -------------------------------------------------

_SET_MATERIAL_TEXTURE_PARAMS = {
    "type": "object",
    "properties": {
        "target": {
            "type": "string",
            "description": "Object id or name whose material will receive the texture",
        },
        "texture_type": {
            "type": "string",
            "enum": ["none", "checker", "noise", "grid", "brick"],
            "description": "Procedural texture type",
        },
        "scale": {"type": "number", "description": "Texture scale factor (default 1.0)"},
        "repeat": {
            "type": "array",
            "items": {"type": "number"},
            "description": "Texture repeat [x, y] (default [1, 1])",
        },
    },
    "required": ["target", "texture_type"],
}


class SetMaterialTextureTool(ToolBase):
    """Apply a procedural texture mapping to an object's material."""

    name = "set_material_texture"
    description = (
        "Apply a procedural texture (checker, noise, grid, brick, or none) to an "
        "object's material with optional scale and repeat."
    )

    def schema(self) -> Dict[str, Any]:
        return _SET_MATERIAL_TEXTURE_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        target = str(arguments.get("target", "")).strip()
        if not target:
            return ToolResult(success=False, message="No target object provided")

        obj = scene.find_object(target)
        if obj is None:
            return ToolResult(success=False, message=f"Object not found: {target}")

        texture_type = str(arguments.get("texture_type", "none")).strip().lower()
        valid = {"none", "checker", "noise", "grid", "brick"}
        if texture_type not in valid:
            return ToolResult(
                success=False,
                message=f"Invalid texture_type '{texture_type}'. Valid types: {', '.join(sorted(valid))}",
            )

        try:
            scale = float(arguments.get("scale", 1.0))
        except (TypeError, ValueError):
            scale = 1.0

        repeat_raw = arguments.get("repeat", [1, 1])
        if not isinstance(repeat_raw, (list, tuple)) or len(repeat_raw) != 2:
            repeat = [1, 1]
        else:
            try:
                repeat = [int(repeat_raw[0]), int(repeat_raw[1])]
            except (TypeError, ValueError):
                repeat = [1, 1]

        texture: Dict[str, Any] = {
            "type": texture_type,
            "scale": scale,
            "repeat": repeat,
        }

        params = _ensure_material_params(obj.material)
        params["texture"] = texture

        # Build payload from the object dict and surface the texture
        # explicitly so the frontend receives it even though the dynamic
        # material.params attribute is not serialized by Material.to_dict().
        payload = obj.to_dict()
        payload["texture"] = texture

        return ToolResult(
            success=True,
            message=f"Set material texture '{texture_type}' on '{obj.name}' (scale {scale}, repeat {repeat})",
            deltas=[SceneDelta(action="update", target_id=obj.id, payload=payload)],
            data={"texture": texture, "object_id": obj.id},
        )


# --- SetViewportBackgroundTool ----------------------------------------------

_SET_VIEWPORT_BACKGROUND_PARAMS = {
    "type": "object",
    "properties": {
        "type": {
            "type": "string",
            "enum": ["solid", "gradient", "skybox"],
            "description": "Background type",
        },
        "top_color": {
            "type": "string",
            "description": "Top color for gradient backgrounds (hex)",
        },
        "bottom_color": {
            "type": "string",
            "description": "Bottom color for gradient backgrounds (hex)",
        },
    },
    "required": ["type"],
}


class SetViewportBackgroundTool(ToolBase):
    """Set a solid, gradient, or skybox viewport background."""

    name = "set_viewport_background"
    description = (
        "Set the viewport background as solid, gradient (top_color + bottom_color), "
        "or skybox. Gradient mode uses top_color and bottom_color."
    )

    def schema(self) -> Dict[str, Any]:
        return _SET_VIEWPORT_BACKGROUND_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        bg_type = str(arguments.get("type", "")).strip().lower()
        valid = {"solid", "gradient", "skybox"}
        if bg_type not in valid:
            return ToolResult(
                success=False,
                message=f"Invalid background type '{bg_type}'. Valid types: {', '.join(sorted(valid))}",
            )

        top_color = str(arguments.get("top_color", "#ffffff")) or "#ffffff"
        bottom_color = str(arguments.get("bottom_color", "#000000")) or "#000000"

        if bg_type == "gradient" and (
            not arguments.get("top_color") or not arguments.get("bottom_color")
        ):
            return ToolResult(
                success=False,
                message="Gradient background requires both top_color and bottom_color",
            )

        background: Dict[str, Any] = {"type": bg_type}
        if bg_type == "gradient":
            background["top_color"] = top_color
            background["bottom_color"] = bottom_color
        elif bg_type == "solid":
            # Solid uses top_color as the fill color when provided.
            background["color"] = top_color

        metadata = _ensure_scene_metadata(scene)
        previous = metadata.get("viewport_background")
        metadata["viewport_background"] = background

        return ToolResult(
            success=True,
            message=f"Viewport background set to '{bg_type}'",
            deltas=[SceneDelta(action="update", payload={"viewport_background": background})],
            data={"viewport_background": background, "previous": previous},
        )
