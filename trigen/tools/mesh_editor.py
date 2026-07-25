"""Geometry editing tools.

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
        "target": {"type": "string", "description": "Target object id or name"},
        "position": {
            "type": "array",
            "items": {"type": "number"},
            "description": "New position [x, y, z]; omit to leave unchanged",
        },
        "rotation": {
            "type": "array",
            "items": {"type": "number"},
            "description": "New rotation (radians) [x, y, z]; omit to leave unchanged",
        },
        "scale": {
            "type": "array",
            "items": {"type": "number"},
            "description": "New scale [x, y, z]; omit to leave unchanged",
        },
        "rotation_degrees": {
            "type": "array",
            "items": {"type": "number"},
            "description": "Rotation angle (degrees) [x, y, z]; internally converted to radians",
        },
        "relative": {
            "type": "boolean",
            "description": "Whether to accumulate relative to current values (default false for absolute)",
        },
    },
    "required": ["target"],
}


_MODIFY_GEOMETRY_PARAMS = {
    "type": "object",
    "properties": {
        "target": {"type": "string", "description": "Target object id or name"},
        "params": {
            "type": "object",
            "description": "Geometry parameter key-value pairs to update (e.g. radius/height/widthSegments)",
            "additionalProperties": True,
        },
        "geometry_type": {
            "type": "string",
            "description": "(Optional) switch geometry type",
            "enum": list(GEOMETRY_DEFAULTS.keys()),
        },
    },
    "required": ["target"],
}


_DUPLICATE_PARAMS = {
    "type": "object",
    "properties": {
        "target": {"type": "string", "description": "Target object id or name"},
        "count": {"type": "integer", "description": "Number of copies (default 1)", "minimum": 1, "maximum": 20},
        "offset": {
            "type": "array",
            "items": {"type": "number"},
            "description": "Position offset per copy [x, y, z] (default [1.2, 0, 0])",
        },
        "name_prefix": {"type": "string", "description": "Naming prefix for copies (default keeps original name)"},
    },
    "required": ["target"],
}


_DELETE_PARAMS = {
    "type": "object",
    "properties": {
        "target": {"type": "string", "description": "Target object id or name"},
    },
    "required": ["target"],
}


_LIST_PARAMS = {
    "type": "object",
    "properties": {},
}


class TransformObjectTool(ToolBase):
    """Transform object tool."""

    name = "transform_object"
    description = "Modify the position, rotation, or scale of an existing object. Locate the target by id or name; supports relative/absolute modes."

    def schema(self) -> Dict[str, Any]:
        return _TRANSFORM_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        target_id = arguments.get("target", "")
        obj = scene.find_object(target_id)
        if not obj:
            return ToolResult(success=False, message=f"Object not found: {target_id}")

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
                changes.append(f"position->{obj.transform.position}")

        if "rotation" in arguments and isinstance(arguments["rotation"], list):
            rot = arguments["rotation"]
            if len(rot) == 3:
                if relative:
                    obj.transform.rotation = [
                        obj.transform.rotation[i] + float(rot[i]) for i in range(3)
                    ]
                else:
                    obj.transform.rotation = [float(r) for r in rot]
                changes.append(f"rotation->{obj.transform.rotation}")

        if "rotation_degrees" in arguments and isinstance(arguments["rotation_degrees"], list):
            deg = arguments["rotation_degrees"]
            if len(deg) == 3:
                if relative:
                    obj.transform.rotation = [
                        obj.transform.rotation[i] + math.radians(float(deg[i])) for i in range(3)
                    ]
                else:
                    obj.transform.rotation = [math.radians(float(d)) for d in deg]
                changes.append(f"rotation->{obj.transform.rotation}(radians)")

        if "scale" in arguments and isinstance(arguments["scale"], list):
            sc = arguments["scale"]
            if len(sc) == 3:
                if relative:
                    obj.transform.scale = [
                        max(0.01, obj.transform.scale[i] * float(sc[i])) for i in range(3)
                    ]
                else:
                    obj.transform.scale = [max(0.01, float(s)) for s in sc]
                changes.append(f"scale->{obj.transform.scale}")

        if not changes:
            return ToolResult(success=False, message="No transform parameters provided")

        return ToolResult(
            success=True,
            message=f"{obj.name} transformed: {', '.join(changes)}",
            deltas=[SceneDelta(action="update", target_id=obj.id, payload=obj.to_dict())],
            data={"object": obj.to_dict()},
        )


class ModifyGeometryTool(ToolBase):
    """Modify geometry parameters tool."""

    name = "modify_geometry"
    description = "Modify parameters of an existing geometry (radius, height, segments, etc.), optionally switching geometry type."

    def schema(self) -> Dict[str, Any]:
        return _MODIFY_GEOMETRY_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        target_id = arguments.get("target", "")
        obj = scene.find_object(target_id)
        if not obj:
            return ToolResult(success=False, message=f"Object not found: {target_id}")

        changes: List[str] = []
        new_type = arguments.get("geometry_type")
        if new_type and new_type != obj.geometry.type:
            if new_type not in GEOMETRY_DEFAULTS:
                return ToolResult(success=False, message=f"Unsupported geometry type: {new_type}")
            obj.geometry.type = new_type
            obj.geometry.params = dict(GEOMETRY_DEFAULTS[new_type])
            changes.append(f"type->{new_type}")

        params = arguments.get("params", {})
        if isinstance(params, dict):
            for k, v in params.items():
                obj.geometry.params[k] = v
            if params:
                changes.append(f"params->{params}")

        if not changes:
            return ToolResult(success=False, message="No geometry modification parameters provided")

        return ToolResult(
            success=True,
            message=f"{obj.name} geometry updated: {', '.join(changes)}",
            deltas=[SceneDelta(action="update", target_id=obj.id, payload=obj.to_dict())],
            data={"object": obj.to_dict()},
        )


class DuplicateObjectTool(ToolBase):
    """Duplicate object tool."""

    name = "duplicate_object"
    description = "Duplicate the specified object, with optional copy count and position offset."

    def schema(self) -> Dict[str, Any]:
        return _DUPLICATE_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        target_id = arguments.get("target", "")
        obj = scene.find_object(target_id)
        if not obj:
            return ToolResult(success=False, message=f"Object not found: {target_id}")

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
            message=f"Duplicated {count} object(s): {names}",
            deltas=deltas,
            data={"objects": [o.to_dict() for o in created]},
        )


class DeleteObjectTool(ToolBase):
    """Delete object tool."""

    name = "delete_object"
    description = "Remove the specified object from the scene."

    def schema(self) -> Dict[str, Any]:
        return _DELETE_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        target_id = arguments.get("target", "")
        obj = scene.find_object(target_id)
        if not obj:
            return ToolResult(success=False, message=f"Object not found: {target_id}")
        name = obj.name
        oid = obj.id
        scene.objects.remove(obj)
        # Detach from any group
        for g in scene.groups:
            if oid in g.child_ids:
                g.child_ids.remove(oid)
        return ToolResult(
            success=True,
            message=f"Deleted {name}",
            deltas=[SceneDelta(action="delete", target_id=oid)],
        )


class ListObjectsTool(ToolBase):
    """List scene objects tool."""

    name = "list_objects"
    description = "List all objects, lights, cameras, and groups in the current scene."

    def schema(self) -> Dict[str, Any]:
        return _LIST_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        if not scene.objects and not scene.lights:
            return ToolResult(
                success=True,
                message="The current scene is empty",
                data={"objects": [], "lights": [], "cameras": [], "groups": []},
            )
        objs = [o.to_dict() for o in scene.objects]
        lights = [l.to_dict() for l in scene.lights]
        cameras = [c.to_dict() for c in scene.cameras]
        groups = [g.to_dict() for g in scene.groups]
        summary = ", ".join(f"{o['name']}({o['geometry']['type']})" for o in objs)
        return ToolResult(
            success=True,
            message=f"Scene contains {len(objs)} object(s), {len(lights)} light(s), "
            f"{len(cameras)} camera(s), {len(groups)} group(s): {summary}",
            data={
                "objects": objs,
                "lights": lights,
                "cameras": cameras,
                "groups": groups,
            },
        )
