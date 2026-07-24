"""Scene organization tools / 场景组织工具.

Provides grouping/ungrouping, background color, fog, and automatic
layout arrangement (circle / grid / linear) for scene objects.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List

from trigen.scene import GroupObject, Scene, SceneObject
from trigen.tools.base import SceneDelta, ToolBase, ToolResult


_GROUP_PARAMS = {
    "type": "object",
    "properties": {
        "targets": {
            "type": "array",
            "items": {"type": "string"},
            "description": "要分组的对象 id 或 name 列表",
        },
        "name": {"type": "string", "description": "分组名称"},
    },
    "required": ["targets"],
}


_UNGROUP_PARAMS = {
    "type": "object",
    "properties": {
        "target": {"type": "string", "description": "要解散的分组 id 或 name"},
    },
    "required": ["target"],
}


_BACKGROUND_PARAMS = {
    "type": "object",
    "properties": {
        "color": {"type": "string", "description": "背景颜色（十六进制）"},
    },
    "required": ["color"],
}


_FOG_PARAMS = {
    "type": "object",
    "properties": {
        "color": {"type": "string", "description": "雾色（十六进制，默认与背景一致）"},
        "near": {"type": "number", "description": "雾近端距离（默认 10）"},
        "far": {"type": "number", "description": "雾远端距离（默认 50）"},
        "enabled": {"type": "boolean", "description": "是否启用雾效（默认 true）"},
    },
    "required": [],
}


_ARRANGE_PARAMS = {
    "type": "object",
    "properties": {
        "layout_type": {
            "type": "string",
            "enum": ["circle", "grid", "linear"],
            "description": "布局类型",
        },
        "targets": {
            "type": "array",
            "items": {"type": "string"},
            "description": "（可选）要排列的对象 id/name 列表，不传则排列全部对象",
        },
        "radius": {"type": "number", "description": "圆形布局半径（默认 3）"},
        "spacing": {"type": "number", "description": "网格/线性布局间距（默认 2）"},
        "center": {
            "type": "array",
            "items": {"type": "number"},
            "description": "布局中心 [x, y, z]（默认 [0, 0, 0]）",
        },
    },
    "required": ["layout_type"],
}


class GroupObjectsTool(ToolBase):
    """Group objects tool / 对象分组工具."""

    name = "group_objects"
    description = "将多个对象组合为分组，便于统一管理。"

    def schema(self) -> Dict[str, Any]:
        return _GROUP_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        targets = arguments.get("targets", [])
        if not targets or not isinstance(targets, list):
            return ToolResult(success=False, message="未提供分组目标列表")

        objs = scene.find_objects([str(t) for t in targets])
        if not objs:
            return ToolResult(success=False, message="未找到任何可分组的对象")

        name = arguments.get("name") or f"Group_{len(scene.groups) + 1}"
        existing = {g.name for g in scene.groups}
        if name in existing:
            idx = 2
            while f"{name}_{idx}" in existing:
                idx += 1
            name = f"{name}_{idx}"

        group = GroupObject(name=name, child_ids=[o.id for o in objs])
        scene.groups.append(group)
        # Mark group_id on children / 标记子对象的 group_id
        for o in objs:
            o.group_id = group.id

        return ToolResult(
            success=True,
            message=f"已创建分组 {name}，包含 {len(objs)} 个对象",
            deltas=[SceneDelta(action="create_group", target_id=group.id, payload=group.to_dict())]
            + [SceneDelta(action="update", target_id=o.id, payload=o.to_dict()) for o in objs],
            data={"group": group.to_dict()},
        )


class UngroupObjectsTool(ToolBase):
    """Ungroup objects tool / 解散分组工具."""

    name = "ungroup_objects"
    description = "解散指定分组，释放其中的对象。"

    def schema(self) -> Dict[str, Any]:
        return _UNGROUP_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        target_id = arguments.get("target", "")
        group = None
        for g in scene.groups:
            if g.id == target_id or g.name.lower() == target_id.lower():
                group = g
                break
        if not group:
            return ToolResult(success=False, message=f"未找到分组: {target_id}")

        # Clear group_id on children / 清除子对象的 group_id
        for oid in group.child_ids:
            obj = scene.find_object(oid)
            if obj:
                obj.group_id = None

        scene.groups.remove(group)
        return ToolResult(
            success=True,
            message=f"已解散分组 {group.name}",
            deltas=[SceneDelta(action="delete_group", target_id=group.id)],
        )


class SetBackgroundTool(ToolBase):
    """Set background color tool / 设置背景色工具."""

    name = "set_background"
    description = "设置场景背景颜色。"

    def schema(self) -> Dict[str, Any]:
        return _BACKGROUND_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        color = arguments.get("color", "")
        if not color:
            return ToolResult(success=False, message="未提供背景颜色")
        old = scene.background
        scene.background = str(color)
        return ToolResult(
            success=True,
            message=f"背景色已从 {old} 改为 {scene.background}",
            deltas=[SceneDelta(action="set_background", payload={"color": scene.background})],
            data={"background": scene.background},
        )


class SetFogTool(ToolBase):
    """Set fog tool / 设置雾效工具."""

    name = "set_fog"
    description = "配置场景雾效（颜色、近端、远端）。"

    def schema(self) -> Dict[str, Any]:
        return _FOG_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        enabled = arguments.get("enabled", True)
        if not enabled:
            scene.fog = None
            return ToolResult(
                success=True,
                message="已关闭雾效",
                deltas=[SceneDelta(action="set_fog", payload={"fog": None})],
                data={"fog": None},
            )

        color = arguments.get("color", scene.background)
        near = float(arguments.get("near", 10))
        far = float(arguments.get("far", 50))
        scene.fog = {"color": str(color), "near": near, "far": far}
        return ToolResult(
            success=True,
            message=f"雾效已设置：颜色 {color}，近端 {near}，远端 {far}",
            deltas=[SceneDelta(action="set_fog", payload={"fog": scene.fog})],
            data={"fog": scene.fog},
        )


class ArrangeLayoutTool(ToolBase):
    """Arrange layout tool / 布局排列工具."""

    name = "arrange_layout"
    description = "自动布局排列场景对象（circle/grid/linear）。"

    def schema(self) -> Dict[str, Any]:
        return _ARRANGE_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        layout_type = arguments.get("layout_type", "grid")
        targets = arguments.get("targets")
        if targets and isinstance(targets, list):
            objs = scene.find_objects([str(t) for t in targets])
        else:
            objs = list(scene.objects)

        if not objs:
            return ToolResult(success=False, message="场景中没有可排列的对象")

        radius = float(arguments.get("radius", 3.0))
        spacing = float(arguments.get("spacing", 2.0))
        center = arguments.get("center", [0.0, 0.0, 0.0])
        if not isinstance(center, list) or len(center) != 3:
            center = [0.0, 0.0, 0.0]
        cx, cy, cz = float(center[0]), float(center[1]), float(center[2])

        n = len(objs)
        deltas: List[SceneDelta] = []

        if layout_type == "circle":
            for i, obj in enumerate(objs):
                angle = (2 * math.pi * i) / max(n, 1)
                obj.transform.position = [
                    cx + radius * math.cos(angle),
                    cy,
                    cz + radius * math.sin(angle),
                ]
                deltas.append(
                    SceneDelta(action="update", target_id=obj.id, payload=obj.to_dict())
                )
        elif layout_type == "grid":
            cols = int(math.ceil(math.sqrt(n)))
            rows = int(math.ceil(n / cols))
            start_x = cx - (cols - 1) * spacing / 2
            start_z = cz - (rows - 1) * spacing / 2
            for i, obj in enumerate(objs):
                r = i // cols
                c = i % cols
                obj.transform.position = [
                    start_x + c * spacing,
                    cy,
                    start_z + r * spacing,
                ]
                deltas.append(
                    SceneDelta(action="update", target_id=obj.id, payload=obj.to_dict())
                )
        elif layout_type == "linear":
            start = cx - (n - 1) * spacing / 2
            for i, obj in enumerate(objs):
                obj.transform.position = [start + i * spacing, cy, cz]
                deltas.append(
                    SceneDelta(action="update", target_id=obj.id, payload=obj.to_dict())
                )
        else:
            return ToolResult(success=False, message=f"未知布局类型: {layout_type}")

        return ToolResult(
            success=True,
            message=f"已按 {layout_type} 布局排列 {n} 个对象",
            deltas=deltas,
            data={"layout": layout_type, "count": n},
        )
