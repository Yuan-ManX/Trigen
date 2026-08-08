"""Lighting rig, scene preset, and exposure tools.

Provides one-call studio rigs, environment presets, and per-view
exposure control so the Agent can set up a complete lighting +
environment pass without hand-assembling many individual light calls.
"""

from __future__ import annotations

from typing import Any, Dict, List

from trigen.scene import LightObject, Scene
from trigen.tools.base import SceneDelta, ToolBase, ToolResult


# ---------------------------------------------------------------------------
# Preset rigs — each entry is a list of LightObject-ready dicts.
# ---------------------------------------------------------------------------

_RIG_PRESETS: Dict[str, List[Dict[str, Any]]] = {
    "three_point": [
        {
            "name": "KeyLight",
            "type": "directional",
            "color": "#fff5e6",
            "intensity": 1.4,
            "position": [4.0, 6.0, 3.0],
            "target": [0.0, 0.5, 0.0],
            "cast_shadow": True,
            "decay": 0.0,
        },
        {
            "name": "FillLight",
            "type": "directional",
            "color": "#e6f0ff",
            "intensity": 0.7,
            "position": [-3.0, 4.0, 2.0],
            "target": [0.0, 0.5, 0.0],
            "cast_shadow": False,
            "decay": 0.0,
        },
        {
            "name": "RimLight",
            "type": "directional",
            "color": "#ffffff",
            "intensity": 1.0,
            "position": [0.0, 3.0, -4.0],
            "target": [0.0, 0.5, 0.0],
            "cast_shadow": True,
            "decay": 0.0,
        },
    ],
    "studio": [
        {
            "name": "StudioKey",
            "type": "spot",
            "color": "#fff8f0",
            "intensity": 1.6,
            "position": [3.0, 5.0, 4.0],
            "target": [0.0, 0.8, 0.0],
            "angle": 0.5,
            "penumbra": 0.6,
            "cast_shadow": True,
            "distance": 0.0,
            "decay": 1.5,
        },
        {
            "name": "StudioSoft",
            "type": "area",  # Treated as a wide point for runtime compatibility
            "color": "#f0f4ff",
            "intensity": 0.8,
            "position": [-2.0, 4.0, 3.0],
            "target": [0.0, 0.8, 0.0],
            "cast_shadow": False,
            "distance": 8.0,
            "decay": 2.0,
        },
        {
            "name": "StudioBack",
            "type": "point",
            "color": "#ffffff",
            "intensity": 0.6,
            "position": [0.0, 3.0, -3.0],
            "cast_shadow": False,
            "distance": 0.0,
            "decay": 2.0,
        },
        {
            "name": "StudioAmbient",
            "type": "ambient",
            "color": "#2a2a3a",
            "intensity": 0.3,
        },
    ],
    "product": [
        {
            "name": "ProductKey",
            "type": "spot",
            "color": "#ffffff",
            "intensity": 2.0,
            "position": [2.5, 4.0, 3.5],
            "target": [0.0, 0.4, 0.0],
            "angle": 0.35,
            "penumbra": 0.8,
            "cast_shadow": True,
            "distance": 0.0,
            "decay": 1.0,
        },
        {
            "name": "ProductFill",
            "type": "point",
            "color": "#fff0e0",
            "intensity": 1.2,
            "position": [-2.5, 2.5, 2.0],
            "cast_shadow": False,
            "distance": 0.0,
            "decay": 2.0,
        },
        {
            "name": "ProductRim",
            "type": "spot",
            "color": "#ffffff",
            "intensity": 1.5,
            "position": [0.0, 2.0, -3.0],
            "target": [0.0, 0.4, 0.0],
            "angle": 0.6,
            "penumbra": 0.3,
            "cast_shadow": True,
            "distance": 0.0,
            "decay": 1.5,
        },
    ],
    "outdoor": [
        {
            "name": "Sun",
            "type": "directional",
            "color": "#fffbe6",
            "intensity": 1.3,
            "position": [5.0, 8.0, 3.0],
            "target": [0.0, 0.0, 0.0],
            "cast_shadow": True,
            "decay": 0.0,
        },
        {
            "name": "SkyFill",
            "type": "hemisphere",
            "color": "#b0d4ff",
            "intensity": 0.6,
            "position": [0.0, 10.0, 0.0],
        },
        {
            "name": "GroundBounce",
            "type": "directional",
            "color": "#6b5b3e",
            "intensity": 0.25,
            "position": [0.0, -5.0, 0.0],
            "target": [0.0, 0.0, 0.0],
            "cast_shadow": False,
            "decay": 0.0,
        },
    ],
    "portrait": [
        {
            "name": "BeautyDish",
            "type": "spot",
            "color": "#fff8f5",
            "intensity": 1.8,
            "position": [0.0, 2.5, 3.0],
            "target": [0.0, 1.5, 0.0],
            "angle": 0.4,
            "penumbra": 0.7,
            "cast_shadow": True,
            "distance": 0.0,
            "decay": 1.2,
        },
        {
            "name": "SideFill",
            "type": "point",
            "color": "#ffeedd",
            "intensity": 1.0,
            "position": [-2.0, 1.5, 1.5],
            "cast_shadow": False,
            "distance": 0.0,
            "decay": 2.0,
        },
        {
            "name": "HairLight",
            "type": "spot",
            "color": "#fff0e0",
            "intensity": 1.4,
            "position": [0.0, 3.0, -2.5],
            "target": [0.0, 1.5, 0.0],
            "angle": 0.5,
            "penumbra": 0.4,
            "cast_shadow": True,
            "distance": 0.0,
            "decay": 1.0,
        },
        {
            "name": "PortraitAmbient",
            "type": "ambient",
            "color": "#1a1a2a",
            "intensity": 0.25,
        },
    ],
}


_SCENE_PRESETS: Dict[str, Dict[str, Any]] = {
    "studio_white": {
        "background": "#f5f5f0",
        "environment": "studio",
        "fog": None,
        "grid_visible": False,
        "rig": "studio",
    },
    "studio_dark": {
        "background": "#0f1020",
        "environment": "night",
        "fog": {"color": "#0f1020", "near": 12, "far": 40},
        "grid_visible": False,
        "rig": "studio",
    },
    "outdoor_day": {
        "background": "#87ceeb",
        "environment": "outdoor_day",
        "fog": {"color": "#c8dcf0", "near": 30, "far": 80},
        "grid_visible": True,
        "rig": "outdoor",
    },
    "outdoor_sunset": {
        "background": "#ff7043",
        "environment": "sunset",
        "fog": {"color": "#ff8a65", "near": 20, "far": 60},
        "grid_visible": False,
        "rig": "outdoor",
    },
    "product_white": {
        "background": "#ffffff",
        "environment": "studio",
        "fog": None,
        "grid_visible": False,
        "rig": "product",
    },
    "gallery": {
        "background": "#202028",
        "environment": "gallery",
        "fog": {"color": "#202028", "near": 8, "far": 30},
        "grid_visible": False,
        "rig": "three_point",
    },
    "night": {
        "background": "#050510",
        "environment": "night",
        "fog": {"color": "#050510", "near": 5, "far": 25},
        "grid_visible": False,
        "rig": "portrait",
    },
}


class CreateLightingRigTool(ToolBase):
    """One-call lighting rig setup — 3-point / studio / product / outdoor / portrait."""

    name = "create_lighting_rig"
    description = "Set up a complete multi-light rig in one call. Presets: three_point, studio, product, outdoor, portrait."

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "preset": {
                    "type": "string",
                    "enum": list(_RIG_PRESETS.keys()),
                    "description": "Lighting rig preset name",
                },
                "target_position": {
                    "type": "array",
                    "items": {"type": "number"},
                    "description": "World-space center the rig targets [x, y, z] (default origin)",
                },
                "scale": {
                    "type": "number",
                    "description": "Uniform rig scale (default 1.0)",
                },
                "replace_existing": {
                    "type": "boolean",
                    "description": "Remove existing lights before adding rig (default true)",
                },
            },
            "required": ["preset"],
        }

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        preset_name = str(arguments.get("preset", "three_point"))
        preset = _RIG_PRESETS.get(preset_name)
        if not preset:
            return ToolResult(
                success=False,
                message=f"Unknown rig preset '{preset_name}'. Available: {', '.join(_RIG_PRESETS.keys())}",
            )

        target_pos = arguments.get("target_position", [0.0, 0.5, 0.0])
        if not isinstance(target_pos, list) or len(target_pos) != 3:
            target_pos = [0.0, 0.5, 0.0]
        target_pos = [float(target_pos[0]), float(target_pos[1]), float(target_pos[2])]

        scale = float(arguments.get("scale", 1.0))
        replace = bool(arguments.get("replace_existing", True))

        deltas: List[SceneDelta] = []
        rig_count = 0

        if replace and scene.lights:
            # Remove existing lights, recording delete deltas.
            for l in scene.lights:
                deltas.append(SceneDelta(action="delete_light", target_id=l.id))
            scene.lights.clear()

        for entry in preset:
            position = entry.get("position", [0.0, 0.0, 0.0])
            if isinstance(position, list) and len(position) == 3:
                position = [
                    float(position[0]) * scale + target_pos[0],
                    float(position[1]) * scale + target_pos[1],
                    float(position[2]) * scale + target_pos[2],
                ]
            light = LightObject(
                name=entry["name"],
                type=entry.get("type", "directional"),
                color=entry.get("color", "#ffffff"),
                intensity=float(entry.get("intensity", 1.0)),
                position=position,
                target=[float(t) for t in entry["target"]] if "target" in entry else None,
                cast_shadow=bool(entry.get("cast_shadow", True)),
                angle=float(entry.get("angle", 0.785398)),
                penumbra=float(entry.get("penumbra", 0.2)),
                distance=float(entry.get("distance", 0.0)),
                decay=float(entry.get("decay", 2.0)),
            )
            scene.lights.append(light)
            deltas.append(SceneDelta(action="create_light", target_id=light.id, payload=light.to_dict()))
            rig_count += 1

        return ToolResult(
            success=True,
            message=f"Created {preset_name} rig with {rig_count} lights (scale {scale})",
            deltas=deltas,
            data={"preset": preset_name, "light_count": rig_count, "lights": [l.to_dict() for l in scene.lights]},
        )


class SetAmbientLevelTool(ToolBase):
    """Control scene ambient light level and color."""

    name = "set_ambient_level"
    description = "Set the scene ambient light intensity and color. Creates an ambient light if none exists."

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "intensity": {"type": "number", "description": "Ambient intensity 0-5 (default 0.4)"},
                "color": {"type": "string", "description": "Ambient color hex (default #202030)"},
            },
            "required": ["intensity"],
        }

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        intensity = max(0.0, float(arguments.get("intensity", 0.4)))
        color = str(arguments.get("color", "#202030"))

        ambient = None
        for light in scene.lights:
            if light.type == "ambient":
                ambient = light
                break

        if ambient:
            ambient.intensity = intensity
            ambient.color = color
            return ToolResult(
                success=True,
                message=f"Ambient set: intensity {intensity}, color {color}",
                deltas=[SceneDelta(action="update_light", target_id=ambient.id, payload=ambient.to_dict())],
                data={"light": ambient.to_dict()},
            )

        ambient = LightObject(
            name="Ambient",
            type="ambient",
            color=color,
            intensity=intensity,
        )
        scene.lights.append(ambient)
        return ToolResult(
            success=True,
            message=f"Created ambient light: intensity {intensity}, color {color}",
            deltas=[SceneDelta(action="create_light", target_id=ambient.id, payload=ambient.to_dict())],
            data={"light": ambient.to_dict()},
        )


class SetExposureTool(ToolBase):
    """Adjust viewport exposure (implemented as ambient + directional intensity scaling)."""

    name = "set_exposure"
    description = "Adjust scene exposure level by scaling all light intensities. Range -2..+2 stops."

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "exposure": {
                    "type": "number",
                    "description": "Exposure adjustment in stops (-2 to +2, default 0)",
                },
            },
            "required": ["exposure"],
        }

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        exposure = max(-2.0, min(2.0, float(arguments.get("exposure", 0.0))))
        factor = 2.0 ** exposure

        # Persist base intensities on the Scene so they survive round-trips.
        base_intensities: Dict[str, float] = getattr(scene, "_exposure_bases", None) or {}

        deltas: List[SceneDelta] = []
        adjusted = 0
        for light in scene.lights:
            original = base_intensities.get(light.id)
            if original is None:
                original = light.intensity
                base_intensities[light.id] = original
            light.intensity = round(original * factor, 4)
            adjusted += 1
            deltas.append(SceneDelta(action="update_light", target_id=light.id, payload=light.to_dict()))

        scene._exposure_bases = base_intensities  # type: ignore[attr-defined]

        return ToolResult(
            success=True,
            message=f"Exposure set to {exposure:+.1f} stops ({factor:.2f}× intensity on {adjusted} lights)",
            deltas=deltas,
            data={"exposure": exposure, "factor": factor, "lights_adjusted": adjusted},
        )


class ApplyScenePresetTool(ToolBase):
    """Apply a named scene preset (background + environment + fog + rig)."""

    name = "apply_scene_preset"
    description = "Apply a complete scene preset: background, environment, fog, grid, and lighting rig in one call."

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "preset": {
                    "type": "string",
                    "enum": list(_SCENE_PRESETS.keys()),
                    "description": "Scene preset name",
                },
                "position": {
                    "type": "array",
                    "items": {"type": "number"},
                    "description": "Rig target position [x, y, z] (default origin)",
                },
            },
            "required": ["preset"],
        }

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        preset_name = str(arguments.get("preset", "studio_white"))
        preset = _SCENE_PRESETS.get(preset_name)
        if not preset:
            return ToolResult(
                success=False,
                message=f"Unknown scene preset '{preset_name}'. Available: {', '.join(_SCENE_PRESETS.keys())}",
            )

        # Apply scene-level settings.
        scene.background = preset.get("background", scene.background)
        scene.environment = preset.get("environment", scene.environment)
        scene.fog = preset.get("fog", scene.fog)
        scene.grid_visible = preset.get("grid_visible", scene.grid_visible)

        # Apply lighting rig if specified.
        rig_name = preset.get("rig")
        rig_result = None
        if rig_name and rig_name in _RIG_PRESETS:
            rig_tool = CreateLightingRigTool()
            rig_args: Dict[str, Any] = {"preset": rig_name, "replace_existing": True}
            if "position" in arguments:
                rig_args["target_position"] = arguments["position"]
            rig_result = await rig_tool.execute(scene, rig_args)

        message = f"Applied '{preset_name}' preset (background={scene.background}, env={scene.environment})"
        if rig_result:
            message += f" + {rig_name} rig ({len(scene.lights)} lights)"

        deltas = [
            SceneDelta(
                action="update",
                target_id=None,
                payload={
                    "background": scene.background,
                    "environment": scene.environment,
                    "fog": scene.fog,
                    "grid_visible": scene.grid_visible,
                },
            )
        ]
        if rig_result:
            deltas.extend(rig_result.deltas)

        return ToolResult(
            success=True,
            message=message,
            deltas=deltas,
            data={
                "preset": preset_name,
                "rig_applied": rig_name,
                "lights_count": len(scene.lights),
            },
        )
