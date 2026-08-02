"""Lighting orchestration tools.

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
            "description": "Light type",
        },
        "name": {"type": "string", "description": "Light name"},
        "color": {"type": "string", "description": "Light color (hex)"},
        "intensity": {"type": "number", "description": "Light intensity 0-20"},
        "position": {
            "type": "array",
            "items": {"type": "number"},
            "description": "Light position [x, y, z] (effective for directional/point/spot)",
        },
        "target": {
            "type": "array",
            "items": {"type": "number"},
            "description": "Light target [x, y, z] (effective for directional/spot)",
        },
        "cast_shadow": {"type": "boolean", "description": "Whether to cast shadows"},
        "angle": {"type": "number", "description": "Spot cone angle (radians, effective for spot)"},
        "penumbra": {"type": "number", "description": "Spot penumbra 0-1 (effective for spot)"},
        "distance": {"type": "number", "description": "Light distance, 0 means infinite"},
        "decay": {"type": "number", "description": "Decay factor (default 2)"},
    },
    "required": ["light_type"],
}


_MODIFY_LIGHT_PARAMS = {
    "type": "object",
    "properties": {
        "target": {"type": "string", "description": "Target light id or name"},
        "color": {"type": "string", "description": "Light color (hex)"},
        "intensity": {"type": "number", "description": "Light intensity 0-20"},
        "position": {
            "type": "array",
            "items": {"type": "number"},
            "description": "Light position [x, y, z]",
        },
        "target_pos": {
            "type": "array",
            "items": {"type": "number"},
            "description": "Light target [x, y, z]",
        },
        "cast_shadow": {"type": "boolean", "description": "Whether to cast shadows"},
        "angle": {"type": "number", "description": "Spot cone angle (radians)"},
        "penumbra": {"type": "number", "description": "Spot penumbra 0-1"},
        "distance": {"type": "number", "description": "Light distance"},
        "decay": {"type": "number", "description": "Decay factor"},
    },
    "required": ["target"],
}


_DELETE_LIGHT_PARAMS = {
    "type": "object",
    "properties": {
        "target": {"type": "string", "description": "Target light id or name"},
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
    """Add light tool."""

    name = "add_light"
    description = "Add a light source to the scene (ambient/directional/point/spot/hemisphere), controlling color, intensity, position, angle, etc."

    def schema(self) -> Dict[str, Any]:
        return _LIGHT_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        light_type = arguments.get("light_type", "directional")
        name = arguments.get("name") or _LIGHT_NAME_MAP.get(light_type, "Light")

        # Auto-append index for duplicate names
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
            message=f"Added {name} ({light_type}), intensity {light.intensity}, color {light.color}",
            deltas=[SceneDelta(action="create_light", target_id=light.id, payload=light.to_dict())],
            data={"light": light.to_dict()},
        )


class ModifyLightTool(ToolBase):
    """Modify light tool."""

    name = "modify_light"
    description = "Modify properties of an existing light source (color, intensity, position, angle, etc.)."

    def schema(self) -> Dict[str, Any]:
        return _MODIFY_LIGHT_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        target_id = arguments.get("target", "")
        light = scene.find_light(target_id)
        if not light:
            return ToolResult(success=False, message=f"Light not found: {target_id}")

        changes: List[str] = []
        if "color" in arguments:
            light.color = str(arguments["color"])
            changes.append(f"color->{light.color}")
        if "intensity" in arguments:
            light.intensity = max(0.0, float(arguments["intensity"]))
            changes.append(f"intensity->{light.intensity}")
        if "position" in arguments and isinstance(arguments["position"], list):
            pos = arguments["position"]
            if len(pos) == 3:
                light.position = [float(p) for p in pos]
                changes.append(f"position->{light.position}")
        if "target_pos" in arguments and isinstance(arguments["target_pos"], list):
            tgt = arguments["target_pos"]
            if len(tgt) == 3:
                light.target = [float(t) for t in tgt]
                changes.append(f"target->{light.target}")
        if "cast_shadow" in arguments:
            light.cast_shadow = bool(arguments["cast_shadow"])
            changes.append(f"cast_shadow->{light.cast_shadow}")
        if "angle" in arguments:
            light.angle = float(arguments["angle"])
            changes.append(f"angle->{light.angle}")
        if "penumbra" in arguments:
            light.penumbra = max(0.0, min(1.0, float(arguments["penumbra"])))
            changes.append(f"penumbra->{light.penumbra}")
        if "distance" in arguments:
            light.distance = max(0.0, float(arguments["distance"]))
            changes.append(f"distance->{light.distance}")
        if "decay" in arguments:
            light.decay = float(arguments["decay"])
            changes.append(f"decay->{light.decay}")

        if not changes:
            return ToolResult(success=False, message="No light modification parameters provided")

        return ToolResult(
            success=True,
            message=f"{light.name} light updated: {', '.join(changes)}",
            deltas=[SceneDelta(action="update_light", target_id=light.id, payload=light.to_dict())],
            data={"light": light.to_dict()},
        )


class DeleteLightTool(ToolBase):
    """Delete light tool."""

    name = "delete_light"
    description = "Delete the specified light source."
    requires_approval = True  # Destructive: removes a light source

    def schema(self) -> Dict[str, Any]:
        return _DELETE_LIGHT_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        target_id = arguments.get("target", "")
        light = scene.find_light(target_id)
        if not light:
            return ToolResult(success=False, message=f"Light not found: {target_id}")
        name = light.name
        lid = light.id
        scene.lights.remove(light)
        return ToolResult(
            success=True,
            message=f"Deleted light {name}",
            deltas=[SceneDelta(action="delete_light", target_id=lid)],
        )
