"""Material orchestration tools.

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
        "target": {"type": "string", "description": "Target object id or name"},
        "color": {"type": "string", "description": "Material color (hex such as #00F0FF)"},
        "metalness": {"type": "number", "description": "Metalness 0-1"},
        "roughness": {"type": "number", "description": "Roughness 0-1"},
        "opacity": {"type": "number", "description": "Opacity 0-1"},
        "wireframe": {"type": "boolean", "description": "Whether to use wireframe mode"},
        "emissive": {"type": "string", "description": "Emissive color"},
        "emissive_intensity": {"type": "number", "description": "Emissive intensity"},
        "flat_shading": {"type": "boolean", "description": "Whether to use flat shading"},
        "side": {
            "type": "string",
            "enum": ["front", "back", "double"],
            "description": "Render side (front/back/double)",
        },
    },
    "required": ["target"],
}


_PRESET_PARAMS = {
    "type": "object",
    "properties": {
        "target": {"type": "string", "description": "Target object id or name"},
        "preset": {
            "type": "string",
            "enum": list(MATERIAL_PRESETS.keys()),
            "description": "Preset material name (metal/gold/copper/glass/plastic/wood/rubber/ceramic/marble/emissive/neon/wireframe)",
        },
        "color_override": {
            "type": "string",
            "description": "(Optional) override the preset color",
        },
    },
    "required": ["target", "preset"],
}


class ApplyMaterialTool(ToolBase):
    """Apply material tool."""

    name = "apply_material"
    description = "Apply material properties to an object (color, metalness, roughness, opacity, wireframe, emissive, flat shading, double-sided)."

    def schema(self) -> Dict[str, Any]:
        return _MATERIAL_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        target_id = arguments.get("target", "")
        obj = scene.find_object(target_id)
        if not obj:
            return ToolResult(success=False, message=f"Object not found: {target_id}")

        changes: List[str] = []
        mat = obj.material
        if "color" in arguments:
            mat.color = str(arguments["color"])
            changes.append(f"color->{mat.color}")
        if "metalness" in arguments:
            mat.metalness = max(0.0, min(1.0, float(arguments["metalness"])))
            changes.append(f"metalness->{mat.metalness}")
        if "roughness" in arguments:
            mat.roughness = max(0.0, min(1.0, float(arguments["roughness"])))
            changes.append(f"roughness->{mat.roughness}")
        if "opacity" in arguments:
            mat.opacity = max(0.0, min(1.0, float(arguments["opacity"])))
            changes.append(f"opacity->{mat.opacity}")
        if "wireframe" in arguments:
            mat.wireframe = bool(arguments["wireframe"])
            changes.append(f"wireframe->{mat.wireframe}")
        if "emissive" in arguments:
            mat.emissive = str(arguments["emissive"])
            changes.append(f"emissive->{mat.emissive}")
        if "emissive_intensity" in arguments:
            mat.emissive_intensity = float(arguments["emissive_intensity"])
            changes.append(f"emissive_intensity->{mat.emissive_intensity}")
        if "flat_shading" in arguments:
            mat.flat_shading = bool(arguments["flat_shading"])
            changes.append(f"flat_shading->{mat.flat_shading}")
        if "side" in arguments:
            side = str(arguments["side"])
            if side in ("front", "back", "double"):
                mat.side = side
                changes.append(f"side->{mat.side}")

        if not changes:
            return ToolResult(success=False, message="No material parameters provided")

        return ToolResult(
            success=True,
            message=f"{obj.name} material updated: {', '.join(changes)}",
            deltas=[SceneDelta(action="update", target_id=obj.id, payload=obj.to_dict())],
            data={"object": obj.to_dict()},
        )


class ApplyMaterialPresetTool(ToolBase):
    """Apply material preset tool."""

    name = "apply_material_preset"
    description = "Apply a preset material in one click (metal/gold/copper/glass/plastic/wood/rubber/ceramic/marble/emissive/neon/wireframe)."

    def schema(self) -> Dict[str, Any]:
        return _PRESET_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        target_id = arguments.get("target", "")
        obj = scene.find_object(target_id)
        if not obj:
            return ToolResult(success=False, message=f"Object not found: {target_id}")

        preset_name = arguments.get("preset", "")
        preset = MATERIAL_PRESETS.get(preset_name)
        if not preset:
            return ToolResult(
                success=False,
                message=f"Unknown preset: {preset_name}, available: {', '.join(MATERIAL_PRESETS.keys())}",
            )

        # Apply preset values
        for k, v in preset.items():
            if k == "color" and arguments.get("color_override"):
                # Allow color override
                setattr(obj.material, k, str(arguments["color_override"]))
            elif hasattr(obj.material, k):
                setattr(obj.material, k, v)

        return ToolResult(
            success=True,
            message=f"{obj.name} applied {preset_name} preset material",
            deltas=[SceneDelta(action="update", target_id=obj.id, payload=obj.to_dict())],
            data={"object": obj.to_dict(), "preset": preset_name},
        )
