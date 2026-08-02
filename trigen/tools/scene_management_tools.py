"""Scene organization management tools.

Closes the editor-function coverage so every Outliner / scene-structure
action the frontend exposes is also drivable by the Agent through natural
language: moving an object between groups, renaming a group, deleting a
scene camera, reordering the layer stack, and selecting the whole scene.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from trigen.scene import CameraObject, GroupObject, Scene
from trigen.tools.base import SceneDelta, ToolBase, ToolResult


_ASSIGN_GROUP_PARAMS = {
    "type": "object",
    "properties": {
        "target": {
            "type": "string",
            "description": "Object id or name to move",
        },
        "group": {
            "type": "string",
            "description": "Destination group id or name. Pass empty string or omit to detach from any group.",
        },
        "detach": {
            "type": "boolean",
            "description": "When true, remove the object from its current group without reassigning (default false)",
        },
    },
    "required": ["target"],
}


_RENAME_GROUP_PARAMS = {
    "type": "object",
    "properties": {
        "target": {"type": "string", "description": "Group id or name to rename"},
        "name": {"type": "string", "description": "New group name"},
    },
    "required": ["target", "name"],
}


_DELETE_CAMERA_PARAMS = {
    "type": "object",
    "properties": {
        "target": {"type": "string", "description": "Camera id or name to delete"},
    },
    "required": ["target"],
}


_REORDER_LAYER_PARAMS = {
    "type": "object",
    "properties": {
        "target": {
            "type": "string",
            "description": "Object id or name to reposition (used with to_index)",
        },
        "to_index": {
            "type": "integer",
            "description": "Target index in the layer stack (0 = top). Used with target.",
            "minimum": 0,
        },
        "ordered_ids": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Full ordered list of object ids/names defining the new layer order. Overrides target/to_index when provided.",
        },
    },
    "required": [],
}


_SELECT_ALL_PARAMS = {
    "type": "object",
    "properties": {
        "include_lights": {
            "type": "boolean",
            "description": "Also include light ids in the selection (default false)",
        },
    },
    "required": [],
}


class AssignToGroupTool(ToolBase):
    """Move an object into a group, or detach it from its current group."""

    name = "assign_to_group"
    description = (
        "Move an object into a named group, or detach it from its current group. "
        "Keeps group membership and the object's group_id in sync."
    )

    def schema(self) -> Dict[str, Any]:
        return _ASSIGN_GROUP_PARAMS

    def _find_group(self, scene: Scene, identifier: str) -> Optional[GroupObject]:
        for g in scene.groups:
            if g.id == identifier or g.name.lower() == identifier.lower():
                return g
        return None

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        target_id = str(arguments.get("target", "")).strip()
        obj = scene.find_object(target_id)
        if not obj:
            return ToolResult(success=False, message=f"Object not found: {target_id}")

        detach = bool(arguments.get("detach", False))
        group_arg = str(arguments.get("group", "")).strip()

        # Detach path: remove from current group only
        if detach or not group_arg:
            removed_from: List[str] = []
            for g in scene.groups:
                if obj.id in g.child_ids:
                    g.child_ids = [c for c in g.child_ids if c != obj.id]
                    removed_from.append(g.name)
            obj.group_id = None
            if removed_from:
                return ToolResult(
                    success=True,
                    message=f"{obj.name} detached from group(s): {', '.join(removed_from)}",
                    deltas=[SceneDelta(action="update", target_id=obj.id, payload=obj.to_dict())]
                    + [SceneDelta(action="update_group", target_id=g.id, payload=g.to_dict())
                       for g in scene.groups],
                    data={"object": obj.to_dict(), "group_id": None},
                )
            return ToolResult(
                success=True,
                message=f"{obj.name} is not part of any group",
                deltas=[SceneDelta(action="update", target_id=obj.id, payload=obj.to_dict())],
                data={"object": obj.to_dict(), "group_id": None},
            )

        group = self._find_group(scene, group_arg)
        if not group:
            return ToolResult(success=False, message=f"Group not found: {group_arg}")

        # Remove from any previous group, then add to the destination
        for g in scene.groups:
            if g is not group and obj.id in g.child_ids:
                g.child_ids = [c for c in g.child_ids if c != obj.id]
        if obj.id not in group.child_ids:
            group.child_ids.append(obj.id)
        obj.group_id = group.id

        return ToolResult(
            success=True,
            message=f"{obj.name} moved into group {group.name}",
            deltas=[SceneDelta(action="update", target_id=obj.id, payload=obj.to_dict()),
                    SceneDelta(action="update_group", target_id=group.id, payload=group.to_dict())],
            data={"object": obj.to_dict(), "group": group.to_dict()},
        )


class RenameGroupTool(ToolBase):
    """Rename an existing group."""

    name = "rename_group"
    description = "Rename an existing group. Subsequent tool calls can reference the new name."

    def schema(self) -> Dict[str, Any]:
        return _RENAME_GROUP_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        target_id = str(arguments.get("target", "")).strip()
        group = None
        for g in scene.groups:
            if g.id == target_id or g.name.lower() == target_id.lower():
                group = g
                break
        if not group:
            return ToolResult(success=False, message=f"Group not found: {target_id}")

        new_name = str(arguments.get("name", "")).strip()
        if not new_name:
            return ToolResult(success=False, message="New name must be a non-empty string")

        # Avoid name collisions with other groups
        for other in scene.groups:
            if other is not group and other.name.lower() == new_name.lower():
                return ToolResult(success=False, message=f"Group name '{new_name}' is already in use")

        old_name = group.name
        group.name = new_name
        return ToolResult(
            success=True,
            message=f"Renamed group {old_name} -> {new_name}",
            deltas=[SceneDelta(action="update_group", target_id=group.id, payload=group.to_dict())],
            data={"group": group.to_dict(), "old_name": old_name, "new_name": new_name},
        )


class DeleteCameraTool(ToolBase):
    """Remove a scene camera from the camera list."""

    name = "delete_camera"
    description = "Delete a scene camera. The interactive viewport camera cannot be removed."

    def schema(self) -> Dict[str, Any]:
        return _DELETE_CAMERA_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        target_id = str(arguments.get("target", "")).strip()
        camera: Optional[CameraObject] = None
        for c in scene.cameras:
            if c.id == target_id or c.name.lower() == target_id.lower():
                camera = c
                break
        if not camera:
            return ToolResult(success=False, message=f"Camera not found: {target_id}")
        # Guard the internal viewport camera so the editor never loses its default view
        if camera.name == "ViewportCamera":
            return ToolResult(success=False, message="The ViewportCamera cannot be deleted")

        scene.cameras.remove(camera)
        return ToolResult(
            success=True,
            message=f"Deleted camera {camera.name}",
            deltas=[SceneDelta(action="delete_camera", target_id=camera.id)],
            data={"deleted_id": camera.id, "deleted_name": camera.name},
        )


class ReorderLayerTool(ToolBase):
    """Reorder an object within the layer stack, or apply a full layer order."""

    name = "reorder_layer"
    description = (
        "Reorder an object within the Outliner layer stack, or apply a full ordered "
        "id list to redefine the layer order from top to bottom."
    )

    def schema(self) -> Dict[str, Any]:
        return _REORDER_LAYER_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        ordered_ids = arguments.get("ordered_ids")
        if isinstance(ordered_ids, list) and ordered_ids:
            # Resolve names to ids and preserve only known objects, then append
            # any objects not mentioned so nothing is silently dropped.
            resolved: List[str] = []
            for entry in ordered_ids:
                obj = scene.find_object(str(entry))
                if obj and obj.id not in resolved:
                    resolved.append(obj.id)
            seen = set(resolved)
            for obj in scene.objects:
                if obj.id not in seen:
                    resolved.append(obj.id)
            if len(resolved) != len(scene.objects):
                return ToolResult(success=False, message="Layer reorder could not resolve every object")
            # Apply the new order in place
            by_id = {o.id: o for o in scene.objects}
            scene.objects = [by_id[i] for i in resolved]
            return ToolResult(
                success=True,
                message=f"Layer order applied to {len(resolved)} object(s)",
                deltas=[SceneDelta(action="editor_reorder_layer", payload={"ordered_ids": resolved})],
                data={"ordered_ids": resolved},
            )

        target_id = str(arguments.get("target", "")).strip()
        obj = scene.find_object(target_id)
        if not obj:
            return ToolResult(success=False, message=f"Object not found: {target_id}")
        try:
            to_index = int(arguments.get("to_index", -1))
        except (TypeError, ValueError):
            return ToolResult(success=False, message="to_index must be an integer")
        if to_index < 0 or to_index >= len(scene.objects):
            return ToolResult(
                success=False,
                message=f"to_index {to_index} out of range (0..{len(scene.objects) - 1})",
            )

        from_idx = scene.objects.index(obj)
        if from_idx == to_index:
            return ToolResult(success=True, message=f"{obj.name} already at index {to_index}")
        scene.objects.pop(from_idx)
        scene.objects.insert(to_index, obj)
        ordered_ids = [o.id for o in scene.objects]
        return ToolResult(
            success=True,
            message=f"Moved {obj.name} to layer index {to_index}",
            deltas=[SceneDelta(action="editor_reorder_layer", payload={"ordered_ids": ordered_ids})],
            data={"ordered_ids": ordered_ids, "moved_id": obj.id, "to_index": to_index},
        )


class SelectAllTool(ToolBase):
    """Select every object (and optionally every light) in the scene."""

    name = "select_all"
    description = "Select all objects in the scene at once. Optionally include lights."

    def schema(self) -> Dict[str, Any]:
        return _SELECT_ALL_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        ids = [o.id for o in scene.objects]
        if bool(arguments.get("include_lights", False)):
            ids = ids + [l.id for l in scene.lights]
        if not ids:
            return ToolResult(success=False, message="Scene is empty; nothing to select")
        names = ", ".join(o.name for o in scene.objects[:5])
        if len(scene.objects) > 5:
            names += f", ... ({len(scene.objects)} total)"
        return ToolResult(
            success=True,
            message=f"Selected {len(ids)} item(s): {names}",
            deltas=[SceneDelta(action="editor_set_selection", payload={"ids": ids, "clear": True})],
            data={"ids": ids},
        )
