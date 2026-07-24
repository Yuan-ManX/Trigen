"""Geometry generation tool / 几何生成工具.

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
            "description": "几何体类型",
        },
        "name": {"type": "string", "description": "对象名称，便于后续引用"},
        "params": {
            "type": "object",
            "description": "几何参数（如 width/height/radius/segments 等），未提供则用默认值",
            "additionalProperties": True,
        },
        "position": {
            "type": "array",
            "items": {"type": "number"},
            "description": "初始位置 [x, y, z]",
        },
        "rotation": {
            "type": "array",
            "items": {"type": "number"},
            "description": "初始旋转（弧度）[x, y, z]",
        },
        "scale": {
            "type": "array",
            "items": {"type": "number"},
            "description": "初始缩放 [x, y, z]",
        },
        "color": {"type": "string", "description": "材质颜色（十六进制如 #00F0FF）"},
        "metalness": {"type": "number", "description": "金属度 0-1"},
        "roughness": {"type": "number", "description": "粗糙度 0-1"},
        "opacity": {"type": "number", "description": "不透明度 0-1"},
        "emissive": {"type": "string", "description": "自发光颜色"},
        "emissive_intensity": {"type": "number", "description": "自发光强度"},
        "wireframe": {"type": "boolean", "description": "是否线框模式"},
    },
    "required": ["geometry_type"],
}


class CreateObjectTool(ToolBase):
    """Create 3D object tool / 创建 3D 对象工具."""

    name = "create_object"
    description = (
        "创建一个 3D 对象并加入场景。支持 box/sphere/cylinder/cone/torus/plane/"
        "torusKnot/多面体/capsule/ring 等几何类型，可一并指定材质属性。"
    )

    def schema(self) -> Dict[str, Any]:
        return _CREATE_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        geo_type = arguments.get("geometry_type", "box")
        if geo_type not in GEOMETRY_DEFAULTS:
            return ToolResult(
                success=False,
                message=f"不支持的几何类型: {geo_type}。可用: {', '.join(GEOMETRY_DEFAULTS.keys())}",
            )

        # Merge default params with user params / 合并默认参数与用户参数
        params = dict(GEOMETRY_DEFAULTS[geo_type])
        user_params = arguments.get("params", {})
        if isinstance(user_params, dict):
            params.update(user_params)

        # Position / 位置
        position = arguments.get("position", [0.0, 0.0, 0.0])
        if not isinstance(position, list) or len(position) != 3:
            position = [0.0, 0.0, 0.0]

        # Rotation / 旋转
        rotation = arguments.get("rotation", [0.0, 0.0, 0.0])
        if not isinstance(rotation, list) or len(rotation) != 3:
            rotation = [0.0, 0.0, 0.0]

        # Scale / 缩放
        scale = arguments.get("scale", [1.0, 1.0, 1.0])
        if not isinstance(scale, list) or len(scale) != 3:
            scale = [1.0, 1.0, 1.0]

        # Material / 材质
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
        # Auto-append index for duplicate names / 同名对象自动追加序号
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
            message=f"已创建 {name}（{geo_type}），位置 {position}，颜色 {material.color}",
            deltas=[SceneDelta(action="create", target_id=obj.id, payload=obj.to_dict())],
            data={"object": obj.to_dict()},
        )
