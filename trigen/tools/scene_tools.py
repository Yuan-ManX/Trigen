"""Scene organization tools.

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
            "description": "List of object ids or names to group",
        },
        "name": {"type": "string", "description": "Group name"},
    },
    "required": ["targets"],
}


_UNGROUP_PARAMS = {
    "type": "object",
    "properties": {
        "target": {"type": "string", "description": "Group id or name to dissolve"},
    },
    "required": ["target"],
}


_BACKGROUND_PARAMS = {
    "type": "object",
    "properties": {
        "color": {"type": "string", "description": "Background color (hex)"},
    },
    "required": ["color"],
}


_FOG_PARAMS = {
    "type": "object",
    "properties": {
        "color": {"type": "string", "description": "Fog color (hex, defaults to background)"},
        "near": {"type": "number", "description": "Fog near distance (default 10)"},
        "far": {"type": "number", "description": "Fog far distance (default 50)"},
        "enabled": {"type": "boolean", "description": "Whether to enable fog (default true)"},
    },
    "required": [],
}


_ARRANGE_PARAMS = {
    "type": "object",
    "properties": {
        "layout_type": {
            "type": "string",
            "enum": ["circle", "grid", "linear"],
            "description": "Layout type",
        },
        "targets": {
            "type": "array",
            "items": {"type": "string"},
            "description": "(Optional) list of object ids/names to arrange; if omitted, all objects are arranged",
        },
        "radius": {"type": "number", "description": "Circle layout radius (default 3)"},
        "spacing": {"type": "number", "description": "Grid/linear layout spacing (default 2)"},
        "center": {
            "type": "array",
            "items": {"type": "number"},
            "description": "Layout center [x, y, z] (default [0, 0, 0])",
        },
    },
    "required": ["layout_type"],
}


class GroupObjectsTool(ToolBase):
    """Group objects tool."""

    name = "group_objects"
    description = "Combine multiple objects into a group for unified management."

    def schema(self) -> Dict[str, Any]:
        return _GROUP_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        targets = arguments.get("targets", [])
        if not targets or not isinstance(targets, list):
            return ToolResult(success=False, message="No group target list provided")

        objs = scene.find_objects([str(t) for t in targets])
        if not objs:
            return ToolResult(success=False, message="No groupable objects found")

        name = arguments.get("name") or f"Group_{len(scene.groups) + 1}"
        existing = {g.name for g in scene.groups}
        if name in existing:
            idx = 2
            while f"{name}_{idx}" in existing:
                idx += 1
            name = f"{name}_{idx}"

        group = GroupObject(name=name, child_ids=[o.id for o in objs])
        scene.groups.append(group)
        # Mark group_id on children
        for o in objs:
            o.group_id = group.id

        return ToolResult(
            success=True,
            message=f"Created group {name} containing {len(objs)} object(s)",
            deltas=[SceneDelta(action="create_group", target_id=group.id, payload=group.to_dict())]
            + [SceneDelta(action="update", target_id=o.id, payload=o.to_dict()) for o in objs],
            data={"group": group.to_dict()},
        )


class UngroupObjectsTool(ToolBase):
    """Ungroup objects tool."""

    name = "ungroup_objects"
    description = "Dissolve the specified group, releasing its objects."

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
            return ToolResult(success=False, message=f"Group not found: {target_id}")

        # Clear group_id on children
        for oid in group.child_ids:
            obj = scene.find_object(oid)
            if obj:
                obj.group_id = None

        scene.groups.remove(group)
        return ToolResult(
            success=True,
            message=f"Dissolved group {group.name}",
            deltas=[SceneDelta(action="delete_group", target_id=group.id)],
        )


class SetBackgroundTool(ToolBase):
    """Set background color tool."""

    name = "set_background"
    description = "Set the scene background color."

    def schema(self) -> Dict[str, Any]:
        return _BACKGROUND_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        color = arguments.get("color", "")
        if not color:
            return ToolResult(success=False, message="No background color provided")
        old = scene.background
        scene.background = str(color)
        return ToolResult(
            success=True,
            message=f"Background color changed from {old} to {scene.background}",
            deltas=[SceneDelta(action="set_background", payload={"color": scene.background})],
            data={"background": scene.background},
        )


class SetFogTool(ToolBase):
    """Set fog tool."""

    name = "set_fog"
    description = "Configure scene fog effects (color, near, far)."

    def schema(self) -> Dict[str, Any]:
        return _FOG_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        enabled = arguments.get("enabled", True)
        if not enabled:
            scene.fog = None
            return ToolResult(
                success=True,
                message="Fog disabled",
                deltas=[SceneDelta(action="set_fog", payload={"fog": None})],
                data={"fog": None},
            )

        color = arguments.get("color", scene.background)
        near = float(arguments.get("near", 10))
        far = float(arguments.get("far", 50))
        scene.fog = {"color": str(color), "near": near, "far": far}
        return ToolResult(
            success=True,
            message=f"Fog set: color {color}, near {near}, far {far}",
            deltas=[SceneDelta(action="set_fog", payload={"fog": scene.fog})],
            data={"fog": scene.fog},
        )


_ENVIRONMENT_PRESETS: Dict[str, Dict[str, Any]] = {
    "sunset": {
        "background": "#ff8a5c",
        "fog": {"color": "#ffb08a", "near": 15, "far": 55},
        "ambient": {"intensity": 0.5, "color": "#ffd0a0"},
    },
    "night": {
        "background": "#0a0e2a",
        "fog": {"color": "#1a2040", "near": 20, "far": 60},
        "ambient": {"intensity": 0.15, "color": "#6080c0"},
    },
    "winter": {
        "background": "#e0ecf5",
        "fog": {"color": "#d0dce5", "near": 15, "far": 50},
        "ambient": {"intensity": 0.5, "color": "#c0d8f0"},
    },
    "ocean": {
        "background": "#1a4a7a",
        "fog": {"color": "#3a6a9a", "near": 10, "far": 55, "density": 0.01},
        "ambient": {"intensity": 0.4, "color": "#4a7aaa"},
    },
    "forest": {
        "background": "#1a3a1a",
        "fog": {"color": "#3a5a3a", "near": 10, "far": 45},
        "ambient": {"intensity": 0.35, "color": "#70a070"},
    },
    "rainy": {
        "background": "#3a4a5a",
        "fog": {"color": "#5a6a7a", "near": 8, "far": 40},
        "ambient": {"intensity": 0.3, "color": "#8a9aaa"},
    },
    "dawn": {
        "background": "#f0a080",
        "fog": {"color": "#f5c0a0", "near": 12, "far": 50},
        "ambient": {"intensity": 0.45, "color": "#ffd0b0"},
    },
    "cave": {
        "background": "#0a0a0a",
        "fog": {"color": "#1a1a1a", "near": 5, "far": 25},
        "ambient": {"intensity": 0.1, "color": "#4a3a2a"},
    },
    "underwater": {
        "background": "#0a3a5a",
        "fog": {"color": "#2a5a7a", "near": 5, "far": 35},
        "ambient": {"intensity": 0.25, "color": "#4a8aaa"},
    },
    "beach": {
        "background": "#ffd88c",
        "fog": {"color": "#ffe0a0", "near": 15, "far": 55},
        "ambient": {"intensity": 0.75, "color": "#fff0c0"},
    },
    "default": {
        "background": "#1a1a2a",
        "fog": None,
        "ambient": {"intensity": 0.3, "color": "#ffffff"},
    },
}

_SET_ENVIRONMENT_PARAMS = {
    "type": "object",
    "properties": {
        "preset": {
            "type": "string",
            "enum": list(_ENVIRONMENT_PRESETS.keys()),
            "description": "Named atmosphere preset to apply to the scene.",
        },
    },
    "required": ["preset"],
}


class SetSceneEnvironmentTool(ToolBase):
    """Apply a named atmosphere preset to the scene.

    Bundles background color, fog, and ambient level into a single call so
    the Agent can quickly shift the mood of the viewport in one tool call.
    """

    name = "set_scene_environment"
    description = (
        "Apply a named atmosphere preset (sunset, night, winter, ocean, forest, "
        "rainy, dawn, cave, underwater, beach, default) to set background color, "
        "fog, and ambient lighting in one step."
    )

    def schema(self) -> Dict[str, Any]:
        return _SET_ENVIRONMENT_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        preset_name = str(arguments.get("preset", "")).strip()
        preset = _ENVIRONMENT_PRESETS.get(preset_name)
        if preset is None:
            keys = ", ".join(_ENVIRONMENT_PRESETS.keys())
            return ToolResult(
                success=False,
                message=f"Unknown environment preset '{preset_name}'. Known presets: {keys}",
                deltas=[],
                data={},
            )

        deltas: List[SceneDelta] = []

        scene.background = str(preset["background"])
        deltas.append(SceneDelta(action="set_background", payload={"color": scene.background}))

        if preset["fog"] is not None:
            scene.fog = {
                "color": str(preset["fog"]["color"]),
                "near": float(preset["fog"].get("near", 10)),
                "far": float(preset["fog"].get("far", 50)),
            }
            deltas.append(SceneDelta(action="set_fog", payload={"fog": scene.fog}))
        else:
            scene.fog = None
            deltas.append(SceneDelta(action="set_fog", payload={"fog": None}))

        ambient = preset["ambient"]
        intensity = float(ambient.get("intensity", 0.3))
        color = str(ambient.get("color", "#ffffff"))
        scene.ambient_intensity = intensity
        scene.ambient_color = color
        deltas.append(SceneDelta(
            action="set_ambient_level",
            payload={"intensity": intensity, "color": color},
        ))

        return ToolResult(
            success=True,
            message=f"Environment set to '{preset_name}'",
            deltas=deltas,
            data={"preset": preset_name, "fog": scene.fog, "background": scene.background},
        )


_SET_GLOBAL_GRAVITY_PARAMS = {
    "type": "object",
    "properties": {
        "gravity": {
            "type": "number",
            "description": "Global gravity magnitude applied to all physics-enabled objects (0-60, default 9.8).",
        },
    },
    "required": ["gravity"],
}


class SetGlobalGravityTool(ToolBase):
    """Set the gravity value used by every physics-enabled object.

    The per-object physics descriptor typically falls back to a global
    default; this tool rewrites the stored gravity on every currently
    physics-enabled object so they all accelerate at the same rate.
    """

    name = "set_global_gravity"
    description = (
        "Set the global gravity magnitude (0-60) for all currently physics-enabled "
        "objects. Use 9.8 for earth-like, 1.6 for moon-like, 0 to float."
    )

    def schema(self) -> Dict[str, Any]:
        return _SET_GLOBAL_GRAVITY_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        try:
            gravity = max(0.0, min(60.0, float(arguments["gravity"])))
        except (TypeError, ValueError):
            return ToolResult(
                success=False,
                message="Invalid gravity value",
                deltas=[],
                data={},
            )

        changed = 0
        deltas: List[SceneDelta] = []
        for obj in scene.objects:
            if obj.physics and obj.physics.get("enabled"):
                merged = dict(obj.physics)
                merged["gravity"] = gravity
                obj.physics = merged
                deltas.append(SceneDelta(
                    action="update_object",
                    target_id=obj.id,
                    payload=obj.to_dict(),
                ))
                changed += 1

        # Also store as a scene-level default for newly-applied physics.
        scene.global_gravity = gravity

        return ToolResult(
            success=True,
            message=f"Global gravity set to {gravity}; updated {changed} active physics objects.",
            deltas=deltas,
            data={"gravity": gravity, "updated_count": changed},
        )


class ArrangeLayoutTool(ToolBase):
    """Arrange layout tool."""

    name = "arrange_layout"
    description = "Automatically arrange scene objects in a layout (circle/grid/linear)."

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
            return ToolResult(success=False, message="No arrangeable objects in the scene")

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
            return ToolResult(success=False, message=f"Unknown layout type: {layout_type}")

        return ToolResult(
            success=True,
            message=f"Arranged {n} object(s) in {layout_type} layout",
            deltas=deltas,
            data={"layout": layout_type, "count": n},
        )
