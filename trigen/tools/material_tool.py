"""Material orchestration tools / 材质编排工具.

Applies PBR material properties and presets to scene objects, controlling
color, metalness, roughness, opacity, wireframe, emissive, flat shading,
and double-sided rendering.
"""

from __future__ import annotations

from typing import Any, Dict, List

from trigen.scene import MATERIAL_PRESETS, Material, Scene
from trigen.tools.base import SceneDelta, ToolBase, ToolResult


_MATERIAL_PARAMS = {
    "type": "object",
    "properties": {
        "target": {"type": "string", "description": "目标对象的 id 或 name"},
        "color": {"type": "string", "description": "材质颜色（十六进制如 #00F0FF）"},
        "metalness": {"type": "number", "description": "金属度 0-1"},
        "roughness": {"type": "number", "description": "粗糙度 0-1"},
        "opacity": {"type": "number", "description": "不透明度 0-1"},
        "wireframe": {"type": "boolean", "description": "是否线框模式"},
        "emissive": {"type": "string", "description": "自发光颜色"},
        "emissive_intensity": {"type": "number", "description": "自发光强度"},
        "flat_shading": {"type": "boolean", "description": "是否平面着色"},
        "side": {
            "type": "string",
            "enum": ["front", "back", "double"],
            "description": "渲染面（front/back/double）",
        },
    },
    "required": ["target"],
}


_PRESET_PARAMS = {
    "type": "object",
    "properties": {
        "target": {"type": "string", "description": "目标对象的 id 或 name"},
        "preset": {
            "type": "string",
            "enum": list(MATERIAL_PRESETS.keys()),
            "description": "预设材质名（metal/gold/copper/glass/plastic/wood/rubber/ceramic/marble/emissive/neon/wireframe）",
        },
        "color_override": {
            "type": "string",
            "description": "（可选）覆盖预设的颜色",
        },
    },
    "required": ["target", "preset"],
}


class ApplyMaterialTool(ToolBase):
    """Apply material tool / 应用材质工具."""

    name = "apply_material"
    description = "为对象应用材质属性（颜色、金属度、粗糙度、透明度、线框、自发光、平面着色、双面）。"

    def schema(self) -> Dict[str, Any]:
        return _MATERIAL_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        target_id = arguments.get("target", "")
        obj = scene.find_object(target_id)
        if not obj:
            return ToolResult(success=False, message=f"未找到对象: {target_id}")

        changes: List[str] = []
        mat = obj.material
        if "color" in arguments:
            mat.color = str(arguments["color"])
            changes.append(f"颜色→{mat.color}")
        if "metalness" in arguments:
            mat.metalness = max(0.0, min(1.0, float(arguments["metalness"])))
            changes.append(f"金属度→{mat.metalness}")
        if "roughness" in arguments:
            mat.roughness = max(0.0, min(1.0, float(arguments["roughness"])))
            changes.append(f"粗糙度→{mat.roughness}")
        if "opacity" in arguments:
            mat.opacity = max(0.0, min(1.0, float(arguments["opacity"])))
            changes.append(f"不透明度→{mat.opacity}")
        if "wireframe" in arguments:
            mat.wireframe = bool(arguments["wireframe"])
            changes.append(f"线框→{mat.wireframe}")
        if "emissive" in arguments:
            mat.emissive = str(arguments["emissive"])
            changes.append(f"自发光→{mat.emissive}")
        if "emissive_intensity" in arguments:
            mat.emissive_intensity = float(arguments["emissive_intensity"])
            changes.append(f"发光强度→{mat.emissive_intensity}")
        if "flat_shading" in arguments:
            mat.flat_shading = bool(arguments["flat_shading"])
            changes.append(f"平面着色→{mat.flat_shading}")
        if "side" in arguments:
            side = str(arguments["side"])
            if side in ("front", "back", "double"):
                mat.side = side
                changes.append(f"渲染面→{mat.side}")

        if not changes:
            return ToolResult(success=False, message="未提供任何材质参数")

        return ToolResult(
            success=True,
            message=f"{obj.name} 材质已更新：{'，'.join(changes)}",
            deltas=[SceneDelta(action="update", target_id=obj.id, payload=obj.to_dict())],
            data={"object": obj.to_dict()},
        )


class ApplyMaterialPresetTool(ToolBase):
    """Apply material preset tool / 应用预设材质工具."""

    name = "apply_material_preset"
    description = "一键应用预设材质（metal/gold/copper/glass/plastic/wood/rubber/ceramic/marble/emissive/neon/wireframe）。"

    def schema(self) -> Dict[str, Any]:
        return _PRESET_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        target_id = arguments.get("target", "")
        obj = scene.find_object(target_id)
        if not obj:
            return ToolResult(success=False, message=f"未找到对象: {target_id}")

        preset_name = arguments.get("preset", "")
        preset = MATERIAL_PRESETS.get(preset_name)
        if not preset:
            return ToolResult(
                success=False,
                message=f"未知预设: {preset_name}，可用: {', '.join(MATERIAL_PRESETS.keys())}",
            )

        # Apply preset values / 应用预设值
        for k, v in preset.items():
            if k == "color" and arguments.get("color_override"):
                # Allow color override / 允许颜色覆盖
                setattr(obj.material, k, str(arguments["color_override"]))
            elif hasattr(obj.material, k):
                setattr(obj.material, k, v)

        return ToolResult(
            success=True,
            message=f"{obj.name} 已应用 {preset_name} 预设材质",
            deltas=[SceneDelta(action="update", target_id=obj.id, payload=obj.to_dict())],
            data={"object": obj.to_dict(), "preset": preset_name},
        )
