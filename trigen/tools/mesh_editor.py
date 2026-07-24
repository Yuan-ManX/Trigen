"""Geometry editing tools / 几何编辑工具.

Provides object transforms (translate/rotate/scale), geometry parameter
modification, duplication, deletion, and list-query capabilities.
"""

from __future__ import annotations

import copy
import math
from typing import Any, Dict, List

from trigen.scene import GEOMETRY_DEFAULTS, Scene, SceneObject
from trigen.tools.base import SceneDelta, ToolBase, ToolResult


_TRANSFORM_PARAMS = {
    "type": "object",
    "properties": {
        "target": {"type": "string", "description": "目标对象的 id 或 name"},
        "position": {
            "type": "array",
            "items": {"type": "number"},
            "description": "新位置 [x, y, z]，不传则不修改",
        },
        "rotation": {
            "type": "array",
            "items": {"type": "number"},
            "description": "新旋转（弧度）[x, y, z]，不传则不修改",
        },
        "scale": {
            "type": "array",
            "items": {"type": "number"},
            "description": "新缩放 [x, y, z]，不传则不修改",
        },
        "rotation_degrees": {
            "type": "array",
            "items": {"type": "number"},
            "description": "旋转角度（度）[x, y, z]，内部自动转弧度",
        },
        "relative": {
            "type": "boolean",
            "description": "是否相对当前值累加（默认 false 为绝对设置）",
        },
    },
    "required": ["target"],
}


_MODIFY_GEOMETRY_PARAMS = {
    "type": "object",
    "properties": {
        "target": {"type": "string", "description": "目标对象的 id 或 name"},
        "params": {
            "type": "object",
            "description": "要更新的几何参数键值对（如 radius/height/widthSegments 等）",
            "additionalProperties": True,
        },
        "geometry_type": {
            "type": "string",
            "description": "（可选）切换几何体类型",
            "enum": list(GEOMETRY_DEFAULTS.keys()),
        },
    },
    "required": ["target"],
}


_DUPLICATE_PARAMS = {
    "type": "object",
    "properties": {
        "target": {"type": "string", "description": "目标对象的 id 或 name"},
        "count": {"type": "integer", "description": "副本数量（默认 1）", "minimum": 1, "maximum": 20},
        "offset": {
            "type": "array",
            "items": {"type": "number"},
            "description": "每个副本的位置偏移 [x, y, z]（默认 [1.2, 0, 0]）",
        },
        "name_prefix": {"type": "string", "description": "副本命名前缀（默认沿用原名）"},
    },
    "required": ["target"],
}


_DELETE_PARAMS = {
    "type": "object",
    "properties": {
        "target": {"type": "string", "description": "目标对象的 id 或 name"},
    },
    "required": ["target"],
}


_LIST_PARAMS = {
    "type": "object",
    "properties": {},
}


class TransformObjectTool(ToolBase):
    """Transform object tool / 变换对象工具."""

    name = "transform_object"
    description = "修改已有对象的位置、旋转或缩放。通过 id 或 name 定位目标，支持相对/绝对模式。"

    def schema(self) -> Dict[str, Any]:
        return _TRANSFORM_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        target_id = arguments.get("target", "")
        obj = scene.find_object(target_id)
        if not obj:
            return ToolResult(success=False, message=f"未找到对象: {target_id}")

        relative = bool(arguments.get("relative", False))
        changes: List[str] = []

        if "position" in arguments and isinstance(arguments["position"], list):
            pos = arguments["position"]
            if len(pos) == 3:
                if relative:
                    obj.transform.position = [
                        obj.transform.position[i] + float(pos[i]) for i in range(3)
                    ]
                else:
                    obj.transform.position = [float(p) for p in pos]
                changes.append(f"位置→{obj.transform.position}")

        if "rotation" in arguments and isinstance(arguments["rotation"], list):
            rot = arguments["rotation"]
            if len(rot) == 3:
                if relative:
                    obj.transform.rotation = [
                        obj.transform.rotation[i] + float(rot[i]) for i in range(3)
                    ]
                else:
                    obj.transform.rotation = [float(r) for r in rot]
                changes.append(f"旋转→{obj.transform.rotation}")

        if "rotation_degrees" in arguments and isinstance(arguments["rotation_degrees"], list):
            deg = arguments["rotation_degrees"]
            if len(deg) == 3:
                if relative:
                    obj.transform.rotation = [
                        obj.transform.rotation[i] + math.radians(float(deg[i])) for i in range(3)
                    ]
                else:
                    obj.transform.rotation = [math.radians(float(d)) for d in deg]
                changes.append(f"旋转→{obj.transform.rotation}(弧度)")

        if "scale" in arguments and isinstance(arguments["scale"], list):
            sc = arguments["scale"]
            if len(sc) == 3:
                if relative:
                    obj.transform.scale = [
                        max(0.01, obj.transform.scale[i] * float(sc[i])) for i in range(3)
                    ]
                else:
                    obj.transform.scale = [max(0.01, float(s)) for s in sc]
                changes.append(f"缩放→{obj.transform.scale}")

        if not changes:
            return ToolResult(success=False, message="未提供任何变换参数")

        return ToolResult(
            success=True,
            message=f"{obj.name} 已变换：{'，'.join(changes)}",
            deltas=[SceneDelta(action="update", target_id=obj.id, payload=obj.to_dict())],
            data={"object": obj.to_dict()},
        )


class ModifyGeometryTool(ToolBase):
    """Modify geometry parameters tool / 修改几何参数工具."""

    name = "modify_geometry"
    description = "修改已有几何体的参数（半径、高度、分段等），可选切换几何体类型。"

    def schema(self) -> Dict[str, Any]:
        return _MODIFY_GEOMETRY_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        target_id = arguments.get("target", "")
        obj = scene.find_object(target_id)
        if not obj:
            return ToolResult(success=False, message=f"未找到对象: {target_id}")

        changes: List[str] = []
        new_type = arguments.get("geometry_type")
        if new_type and new_type != obj.geometry.type:
            if new_type not in GEOMETRY_DEFAULTS:
                return ToolResult(success=False, message=f"不支持的几何类型: {new_type}")
            obj.geometry.type = new_type
            obj.geometry.params = dict(GEOMETRY_DEFAULTS[new_type])
            changes.append(f"类型→{new_type}")

        params = arguments.get("params", {})
        if isinstance(params, dict):
            for k, v in params.items():
                obj.geometry.params[k] = v
            if params:
                changes.append(f"参数→{params}")

        if not changes:
            return ToolResult(success=False, message="未提供任何几何修改参数")

        return ToolResult(
            success=True,
            message=f"{obj.name} 几何已更新：{'，'.join(changes)}",
            deltas=[SceneDelta(action="update", target_id=obj.id, payload=obj.to_dict())],
            data={"object": obj.to_dict()},
        )


class DuplicateObjectTool(ToolBase):
    """Duplicate object tool / 复制对象工具."""

    name = "duplicate_object"
    description = "复制指定对象，可指定副本数量与位置偏移。"

    def schema(self) -> Dict[str, Any]:
        return _DUPLICATE_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        target_id = arguments.get("target", "")
        obj = scene.find_object(target_id)
        if not obj:
            return ToolResult(success=False, message=f"未找到对象: {target_id}")

        count = max(1, min(20, int(arguments.get("count", 1))))
        offset = arguments.get("offset", [1.2, 0.0, 0.0])
        if not isinstance(offset, list) or len(offset) != 3:
            offset = [1.2, 0.0, 0.0]
        name_prefix = arguments.get("name_prefix") or obj.name

        created: List[SceneObject] = []
        deltas: List[SceneDelta] = []
        for i in range(count):
            import json

            new_obj = SceneObject.from_dict(json.loads(json.dumps(obj.to_dict())))
            new_obj.id = f"obj_{__import__('uuid').uuid4().hex[:8]}"
            new_obj.name = scene.next_auto_name(name_prefix)
            new_obj.transform.position = [
                obj.transform.position[j] + float(offset[j]) * (i + 1) for j in range(3)
            ]
            scene.objects.append(new_obj)
            created.append(new_obj)
            deltas.append(SceneDelta(action="create", target_id=new_obj.id, payload=new_obj.to_dict()))

        names = ", ".join(o.name for o in created)
        return ToolResult(
            success=True,
            message=f"已复制 {count} 个对象：{names}",
            deltas=deltas,
            data={"objects": [o.to_dict() for o in created]},
        )


class DeleteObjectTool(ToolBase):
    """Delete object tool / 删除对象工具."""

    name = "delete_object"
    description = "从场景中移除指定对象。"

    def schema(self) -> Dict[str, Any]:
        return _DELETE_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        target_id = arguments.get("target", "")
        obj = scene.find_object(target_id)
        if not obj:
            return ToolResult(success=False, message=f"未找到对象: {target_id}")
        name = obj.name
        oid = obj.id
        scene.objects.remove(obj)
        # Detach from any group / 从所在分组移除
        for g in scene.groups:
            if oid in g.child_ids:
                g.child_ids.remove(oid)
        return ToolResult(
            success=True,
            message=f"已删除 {name}",
            deltas=[SceneDelta(action="delete", target_id=oid)],
        )


class ListObjectsTool(ToolBase):
    """List scene objects tool / 列出场景对象工具."""

    name = "list_objects"
    description = "列出当前场景中所有对象、光源、相机与分组。"

    def schema(self) -> Dict[str, Any]:
        return _LIST_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        if not scene.objects and not scene.lights:
            return ToolResult(
                success=True,
                message="当前场景为空",
                data={"objects": [], "lights": [], "cameras": [], "groups": []},
            )
        objs = [o.to_dict() for o in scene.objects]
        lights = [l.to_dict() for l in scene.lights]
        cameras = [c.to_dict() for c in scene.cameras]
        groups = [g.to_dict() for g in scene.groups]
        summary = ", ".join(f"{o['name']}({o['geometry']['type']})" for o in objs)
        return ToolResult(
            success=True,
            message=f"场景含 {len(objs)} 个对象，{len(lights)} 盏灯光，"
            f"{len(cameras)} 个相机，{len(groups)} 个分组：{summary}",
            data={
                "objects": objs,
                "lights": lights,
                "cameras": cameras,
                "groups": groups,
            },
        )
