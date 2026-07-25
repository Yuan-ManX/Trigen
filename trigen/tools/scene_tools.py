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
