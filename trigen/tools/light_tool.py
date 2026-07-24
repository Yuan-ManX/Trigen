"""Lighting orchestration tools / 灯光编排工具.

Adds, modifies, and removes lights from the scene, controlling color,
intensity, position, angle, penumbra, distance, and decay.
"""

from __future__ import annotations

from typing import Any, Dict, List

from trigen.scene import LightObject, Scene
from trigen.tools.base import SceneDelta, ToolBase, ToolResult


_LIGHT_PARAMS = {
    "type": "object",
    "properties": {
        "light_type": {
            "type": "string",
            "enum": ["ambient", "directional", "point", "spot", "hemisphere"],
            "description": "光源类型",
        },
        "name": {"type": "string", "description": "光源名称"},
        "color": {"type": "string", "description": "光色（十六进制）"},
        "intensity": {"type": "number", "description": "光强 0-20"},
        "position": {
            "type": "array",
            "items": {"type": "number"},
            "description": "光源位置 [x, y, z]（directional/point/spot 有效）",
        },
        "target": {
            "type": "array",
            "items": {"type": "number"},
            "description": "光源目标 [x, y, z]（directional/spot 有效）",
        },
        "cast_shadow": {"type": "boolean", "description": "是否投射阴影"},
        "angle": {"type": "number", "description": "聚光锥角度（弧度，spot 有效）"},
        "penumbra": {"type": "number", "description": "聚光半影 0-1（spot 有效）"},
        "distance": {"type": "number", "description": "光照距离，0 表示无限"},
        "decay": {"type": "number", "description": "衰减系数（默认 2）"},
    },
    "required": ["light_type"],
}


_MODIFY_LIGHT_PARAMS = {
    "type": "object",
    "properties": {
        "target": {"type": "string", "description": "目标光源的 id 或 name"},
        "color": {"type": "string", "description": "光色（十六进制）"},
        "intensity": {"type": "number", "description": "光强 0-20"},
        "position": {
            "type": "array",
            "items": {"type": "number"},
            "description": "光源位置 [x, y, z]",
        },
        "target_pos": {
            "type": "array",
            "items": {"type": "number"},
            "description": "光源目标 [x, y, z]",
        },
        "cast_shadow": {"type": "boolean", "description": "是否投射阴影"},
        "angle": {"type": "number", "description": "聚光锥角度（弧度）"},
        "penumbra": {"type": "number", "description": "聚光半影 0-1"},
        "distance": {"type": "number", "description": "光照距离"},
        "decay": {"type": "number", "description": "衰减系数"},
    },
    "required": ["target"],
}


_DELETE_LIGHT_PARAMS = {
    "type": "object",
    "properties": {
        "target": {"type": "string", "description": "目标光源的 id 或 name"},
    },
    "required": ["target"],
}


_LIGHT_NAME_MAP = {
    "ambient": "AmbientLight",
    "directional": "DirectionalLight",
    "point": "PointLight",
    "spot": "SpotLight",
    "hemisphere": "HemisphereLight",
}


class AddLightTool(ToolBase):
    """Add light tool / 添加光源工具."""

    name = "add_light"
    description = "向场景添加光源（ambient/directional/point/spot/hemisphere），可控制颜色、强度、位置、角度等。"

    def schema(self) -> Dict[str, Any]:
        return _LIGHT_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        light_type = arguments.get("light_type", "directional")
        name = arguments.get("name") or _LIGHT_NAME_MAP.get(light_type, "Light")

        # Auto-append index for duplicate names / 同名追加序号
        existing = {l.name for l in scene.lights}
        if name in existing:
            idx = 2
            while f"{name}_{idx}" in existing:
                idx += 1
            name = f"{name}_{idx}"

        position = arguments.get("position", [5.0, 5.0, 5.0])
        if not isinstance(position, list) or len(position) != 3:
            position = [5.0, 5.0, 5.0]

        light = LightObject(
            name=name,
            type=light_type,
            color=arguments.get("color", "#ffffff"),
            intensity=float(arguments.get("intensity", 1.0)),
            position=[float(p) for p in position],
            target=arguments.get("target"),
            cast_shadow=bool(arguments.get("cast_shadow", True)),
            angle=float(arguments.get("angle", 0.785398)),
            penumbra=float(arguments.get("penumbra", 0.2)),
            distance=float(arguments.get("distance", 0.0)),
            decay=float(arguments.get("decay", 2.0)),
        )
        scene.lights.append(light)

        return ToolResult(
            success=True,
            message=f"已添加 {name}（{light_type}），强度 {light.intensity}，颜色 {light.color}",
            deltas=[SceneDelta(action="create_light", target_id=light.id, payload=light.to_dict())],
            data={"light": light.to_dict()},
        )


class ModifyLightTool(ToolBase):
    """Modify light tool / 修改光源工具."""

    name = "modify_light"
    description = "修改已有光源的属性（颜色、强度、位置、角度等）。"

    def schema(self) -> Dict[str, Any]:
        return _MODIFY_LIGHT_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        target_id = arguments.get("target", "")
        light = scene.find_light(target_id)
        if not light:
            return ToolResult(success=False, message=f"未找到光源: {target_id}")

        changes: List[str] = []
        if "color" in arguments:
            light.color = str(arguments["color"])
            changes.append(f"颜色→{light.color}")
        if "intensity" in arguments:
            light.intensity = max(0.0, float(arguments["intensity"]))
            changes.append(f"强度→{light.intensity}")
        if "position" in arguments and isinstance(arguments["position"], list):
            pos = arguments["position"]
            if len(pos) == 3:
                light.position = [float(p) for p in pos]
                changes.append(f"位置→{light.position}")
        if "target_pos" in arguments and isinstance(arguments["target_pos"], list):
            tgt = arguments["target_pos"]
            if len(tgt) == 3:
                light.target = [float(t) for t in tgt]
                changes.append(f"目标→{light.target}")
        if "cast_shadow" in arguments:
            light.cast_shadow = bool(arguments["cast_shadow"])
            changes.append(f"阴影→{light.cast_shadow}")
        if "angle" in arguments:
            light.angle = float(arguments["angle"])
            changes.append(f"角度→{light.angle}")
        if "penumbra" in arguments:
            light.penumbra = max(0.0, min(1.0, float(arguments["penumbra"])))
            changes.append(f"半影→{light.penumbra}")
        if "distance" in arguments:
            light.distance = max(0.0, float(arguments["distance"]))
            changes.append(f"距离→{light.distance}")
        if "decay" in arguments:
            light.decay = float(arguments["decay"])
            changes.append(f"衰减→{light.decay}")

        if not changes:
            return ToolResult(success=False, message="未提供任何光源修改参数")

        return ToolResult(
            success=True,
            message=f"{light.name} 光源已更新：{'，'.join(changes)}",
            deltas=[SceneDelta(action="update_light", target_id=light.id, payload=light.to_dict())],
            data={"light": light.to_dict()},
        )


class DeleteLightTool(ToolBase):
    """Delete light tool / 删除光源工具."""

    name = "delete_light"
    description = "删除指定光源。"

    def schema(self) -> Dict[str, Any]:
        return _DELETE_LIGHT_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        target_id = arguments.get("target", "")
        light = scene.find_light(target_id)
        if not light:
            return ToolResult(success=False, message=f"未找到光源: {target_id}")
        name = light.name
        lid = light.id
        scene.lights.remove(light)
        return ToolResult(
            success=True,
            message=f"已删除光源 {name}",
            deltas=[SceneDelta(action="delete_light", target_id=lid)],
        )
