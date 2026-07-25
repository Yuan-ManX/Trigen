"""Geometry generation tool.

Creates base geometry via parametric means, supporting cubes, spheres,
cylinders, cones, tori, planes, polyhedra, capsules, rings, and tubes.
All parameters can be dynamically specified by LLM tool calls.
"""

from __future__ import annotations

import math
from typing import Any, Dict

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


_CREATE_PARAMS = {
    "type": "object",
    "properties": {
        "geometry_type": {
            "type": "string",
            "enum": list(GEOMETRY_DEFAULTS.keys()),
            "description": "Geometry type",
        },
        "name": {"type": "string", "description": "Object name, for later reference"},
        "params": {
            "type": "object",
            "description": "Geometry parameters (e.g. width/height/radius/segments). Defaults are used if not provided.",
            "additionalProperties": True,
        },
        "position": {
            "type": "array",
            "items": {"type": "number"},
            "description": "Initial position [x, y, z]",
        },
        "rotation": {
            "type": "array",
            "items": {"type": "number"},
            "description": "Initial rotation (radians) [x, y, z]",
        },
        "scale": {
            "type": "array",
            "items": {"type": "number"},
            "description": "Initial scale [x, y, z]",
        },
        "color": {"type": "string", "description": "Material color (hex such as #00F0FF)"},
        "metalness": {"type": "number", "description": "Metalness 0-1"},
        "roughness": {"type": "number", "description": "Roughness 0-1"},
        "opacity": {"type": "number", "description": "Opacity 0-1"},
        "emissive": {"type": "string", "description": "Emissive color"},
        "emissive_intensity": {"type": "number", "description": "Emissive intensity"},
        "wireframe": {"type": "boolean", "description": "Whether to use wireframe mode"},
    },
    "required": ["geometry_type"],
}


class CreateObjectTool(ToolBase):
    """Create 3D object tool."""

    name = "create_object"
    description = (
        "Create a 3D object and add it to the scene. Supports box/sphere/cylinder/cone/torus/plane/"
        "torusKnot/polyhedra/capsule/ring geometry types; material properties may be specified as well."
    )

    def schema(self) -> Dict[str, Any]:
        return _CREATE_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        geo_type = arguments.get("geometry_type", "box")
        if geo_type not in GEOMETRY_DEFAULTS:
            return ToolResult(
                success=False,
                message=f"Unsupported geometry type: {geo_type}. Available: {', '.join(GEOMETRY_DEFAULTS.keys())}",
            )

        # Merge default params with user params
        params = dict(GEOMETRY_DEFAULTS[geo_type])
        user_params = arguments.get("params", {})
        if isinstance(user_params, dict):
            params.update(user_params)

        # Position
        position = arguments.get("position", [0.0, 0.0, 0.0])
        if not isinstance(position, list) or len(position) != 3:
            position = [0.0, 0.0, 0.0]

        # Rotation
        rotation = arguments.get("rotation", [0.0, 0.0, 0.0])
        if not isinstance(rotation, list) or len(rotation) != 3:
            rotation = [0.0, 0.0, 0.0]

        # Scale
        scale = arguments.get("scale", [1.0, 1.0, 1.0])
        if not isinstance(scale, list) or len(scale) != 3:
            scale = [1.0, 1.0, 1.0]

        # Material
        material = Material(
            color=arguments.get("color", "#cccccc"),
            metalness=float(arguments.get("metalness", 0.0)),
            roughness=float(arguments.get("roughness", 0.5)),
            opacity=float(arguments.get("opacity", 1.0)),
            emissive=arguments.get("emissive", "#000000"),
            emissive_intensity=float(arguments.get("emissive_intensity", 0.0)),
            wireframe=bool(arguments.get("wireframe", False)),
        )

        name = arguments.get("name") or GEOMETRY_DISPLAY_NAMES.get(geo_type, "Object")
        # Auto-append index for duplicate names
        name = scene.next_auto_name(name)

        obj = SceneObject(
            name=name,
            type="mesh",
            geometry=Geometry(type=geo_type, params=params),
            material=material,
            transform=Transform(
                position=[float(p) for p in position],
                rotation=[float(r) for r in rotation],
                scale=[float(s) for s in scale],
            ),
        )
        scene.objects.append(obj)

        return ToolResult(
            success=True,
            message=f"Created {name} ({geo_type}), position {position}, color {material.color}",
            deltas=[SceneDelta(action="create", target_id=obj.id, payload=obj.to_dict())],
            data={"object": obj.to_dict()},
        )
