"""Layer management and vertex painting tools.

Provides Agent-callable layer management (create/delete/color) and
per-vertex color painting so the left-panel Agent can drive every
layer and vertex-colour operation the RightPanel exposes.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from trigen.scene import Scene, SceneObject
from trigen.tools.base import SceneDelta, ToolBase, ToolResult


# ---------------------------------------------------------------------------
# Layer storage — layers are stored on the Scene as a dict keyed by name.
# The frontend reads scene.layers to render the layer panel.
# ---------------------------------------------------------------------------


class CreateLayerTool(ToolBase):
    """Create a named layer on the scene."""

    name = "create_layer"
    description = "Create a new named layer for organizing scene objects."

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Layer name"},
                "color": {"type": "string", "description": "Layer display color (hex, default #3b82f6)"},
                "parent": {"type": "string", "description": "Parent layer name (empty for root)"},
                "locked": {"type": "boolean", "description": "Whether the layer is locked (default false)"},
            },
            "required": ["name"],
        }

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        name = str(arguments.get("name", "Layer"))
        color = str(arguments.get("color", "#3b82f6"))
        parent = str(arguments.get("parent", ""))
        locked = bool(arguments.get("locked", False))

        # Ensure the scene has a layers dict.
        layers: Dict[str, Any] = getattr(scene, "layers", None) or {}
        if not isinstance(layers, dict):
            layers = {}

        if name in layers:
            return ToolResult(success=False, message=f"Layer '{name}' already exists")

        layers[name] = {
            "name": name,
            "color": color,
            "parent": parent or None,
            "locked": locked,
            "visible": True,
            "object_count": 0,
        }
        scene.layers = layers  # type: ignore[attr-defined]

        return ToolResult(
            success=True,
            message=f"Created layer '{name}' (color={color})",
            deltas=[SceneDelta(action="update", target_id=None, payload={"layers": layers})],
            data={"layer": layers[name]},
        )


class DeleteLayerTool(ToolBase):
    """Delete a named layer and optionally reassign its objects."""

    name = "delete_layer"
    description = "Delete a named layer. Objects on that layer can be reassigned to another layer."

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Layer name to delete"},
                "reassign_to": {"type": "string", "description": "Layer to reassign objects to (default: root)"},
            },
            "required": ["name"],
        }

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        name = str(arguments.get("name", ""))
        reassign = str(arguments.get("reassign_to", ""))

        layers: Dict[str, Any] = getattr(scene, "layers", None) or {}
        if name not in layers:
            return ToolResult(success=False, message=f"Layer '{name}' not found")

        # Reassign objects tagged with this layer.
        reassigned = 0
        for obj in scene.objects:
            layer_tag = None
            for tag in obj.tags:
                if tag.startswith("layer:"):
                    layer_tag = tag[len("layer:"):]
                    break
            if layer_tag == name:
                if layer_tag in obj.tags:
                    obj.tags.remove(f"layer:{layer_tag}")
                if reassign:
                    obj.tags.append(f"layer:{reassign}")
                reassigned += 1

        del layers[name]
        scene.layers = layers  # type: ignore[attr-defined]

        return ToolResult(
            success=True,
            message=f"Deleted layer '{name}' ({reassigned} objects reassigned to '{reassign or 'root'}')",
            deltas=[SceneDelta(action="update", target_id=None, payload={"layers": layers})],
            data={"deleted_layer": name, "reassigned": reassigned},
        )


class SetLayerColorTool(ToolBase):
    """Set a layer's display color."""

    name = "set_layer_color"
    description = "Update the display color of an existing layer."

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Layer name"},
                "color": {"type": "string", "description": "New layer color (hex)"},
            },
            "required": ["name", "color"],
        }

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        name = str(arguments.get("name", ""))
        color = str(arguments.get("color", "#3b82f6"))

        layers: Dict[str, Any] = getattr(scene, "layers", None) or {}
        if name not in layers:
            return ToolResult(success=False, message=f"Layer '{name}' not found")

        layers[name]["color"] = color
        scene.layers = layers  # type: ignore[attr-defined]

        return ToolResult(
            success=True,
            message=f"Layer '{name}' color set to {color}",
            deltas=[SceneDelta(action="update", target_id=None, payload={"layers": layers})],
            data={"layer": layers[name]},
        )


class PaintVertexColorsTool(ToolBase):
    """Apply a vertex-color palette to an object's geometry."""

    name = "paint_vertex_colors"
    description = "Paint vertex colors on an object's geometry using a color or palette. Useful for hand-painted looks and color variation."

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "Target object id or name"},
                "color": {"type": "string", "description": "Base color hex (default #ff8844)"},
                "palette": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional array of hex colors for multi-color painting",
                },
                "blend_mode": {
                    "type": "string",
                    "enum": ["replace", "multiply", "overlay", "soft_light"],
                    "description": "Color blend mode (default replace)",
                },
                "intensity": {
                    "type": "number",
                    "description": "Color intensity 0-1 (default 0.8)",
                },
                "noise": {
                    "type": "number",
                    "description": "Color noise variation 0-1 (default 0.15)",
                },
            },
            "required": ["target"],
        }

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        target_id = arguments.get("target", "")
        obj = scene.find_object(target_id)
        if not obj:
            return ToolResult(success=False, message=f"Object not found: {target_id}")

        base_color = str(arguments.get("color", "#ff8844"))
        palette = arguments.get("palette")
        blend_mode = str(arguments.get("blend_mode", "replace"))
        intensity = max(0.0, min(1.0, float(arguments.get("intensity", 0.8))))
        noise = max(0.0, min(1.0, float(arguments.get("noise", 0.15))))

        # Build vertex color metadata on the object's material.
        vertex_meta: Dict[str, Any] = {
            "enabled": True,
            "base_color": base_color,
            "blend_mode": blend_mode,
            "intensity": intensity,
            "noise": noise,
        }
        if palette and isinstance(palette, list):
            vertex_meta["palette"] = [str(c) for c in palette]

        # Store vertex paint metadata in the material's extended props field.
        mat_dict = obj.material.to_dict()
        mat_dict["vertex_colors"] = vertex_meta
        obj.material.vertex_colors = vertex_meta  # type: ignore[attr-defined]

        palette_info = f", palette of {len(palette)} colors" if palette else ""
        return ToolResult(
            success=True,
            message=f"Vertex colors painted on {obj.name} (color={base_color}, blend={blend_mode}, intensity={intensity:.0%}{palette_info})",
            deltas=[SceneDelta(action="update", target_id=obj.id, payload=obj.to_dict())],
            data={"object": obj.to_dict(), "vertex_colors": vertex_meta},
        )


class RenameLayerTool(ToolBase):
    """Rename an existing layer and reassign its objects to the new name."""

    name = "rename_layer"
    description = "Rename a layer and re-tag all objects that belonged to it."

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Current layer name"},
                "new_name": {"type": "string", "description": "New layer name"},
            },
            "required": ["name", "new_name"],
        }

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        old_name = str(arguments.get("name", ""))
        new_name = str(arguments.get("new_name", ""))

        layers: Dict[str, Any] = getattr(scene, "layers", None) or {}
        if old_name not in layers:
            return ToolResult(success=False, message=f"Layer '{old_name}' not found")
        if not new_name:
            return ToolResult(success=False, message="New layer name cannot be empty")
        if new_name in layers:
            return ToolResult(success=False, message=f"Layer '{new_name}' already exists")

        # Copy the layer entry under the new name.
        layers[new_name] = dict(layers[old_name])
        layers[new_name]["name"] = new_name
        del layers[old_name]

        # Re-tag objects from old layer to new layer.
        retagged = 0
        for obj in scene.objects:
            layer_tag = None
            for tag in obj.tags:
                if tag.startswith("layer:"):
                    layer_tag = tag[len("layer:"):]
                    break
            if layer_tag == old_name:
                if "layer:" + old_name in obj.tags:
                    obj.tags.remove("layer:" + old_name)
                obj.tags.append("layer:" + new_name)
                retagged += 1

        scene.layers = layers  # type: ignore[attr-defined]

        return ToolResult(
            success=True,
            message=f"Layer '{old_name}' renamed to '{new_name}' ({retagged} objects retagged)",
            deltas=[SceneDelta(action="update", target_id=None, payload={"layers": layers})],
            data={"old_name": old_name, "new_name": new_name, "retagged": retagged},
        )


class SetLayerVisibleTool(ToolBase):
    """Show or hide all objects in a layer."""

    name = "set_layer_visible"
    description = "Toggle visibility of all objects belonging to a layer."

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Layer name"},
                "visible": {"type": "boolean", "description": "Set visible (true) or hidden (false)"},
            },
            "required": ["name", "visible"],
        }

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        name = str(arguments.get("name", ""))
        visible = bool(arguments.get("visible", True))

        layers: Dict[str, Any] = getattr(scene, "layers", None) or {}
        if name not in layers:
            return ToolResult(success=False, message=f"Layer '{name}' not found")

        layers[name]["visible"] = visible
        scene.layers = layers  # type: ignore[attr-defined]

        # Apply visibility to all objects in this layer.
        affected = 0
        for obj in scene.objects:
            layer_tag = None
            for tag in obj.tags:
                if tag.startswith("layer:"):
                    layer_tag = tag[len("layer:"):]
                    break
            if layer_tag == name:
                obj.visible = visible
                affected += 1

        return ToolResult(
            success=True,
            message=f"Layer '{name}' set to {'visible' if visible else 'hidden'} ({affected} objects)",
            deltas=[SceneDelta(action="update", target_id=None, payload={"layers": layers})],
            data={"layer": name, "visible": visible, "affected": affected},
        )


class SetLayerLockedTool(ToolBase):
    """Lock or unlock all objects in a layer."""

    name = "set_layer_locked"
    description = "Toggle lock state of all objects belonging to a layer."

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Layer name"},
                "locked": {"type": "boolean", "description": "Set locked (true) or unlocked (false)"},
            },
            "required": ["name", "locked"],
        }

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        name = str(arguments.get("name", ""))
        locked = bool(arguments.get("locked", False))

        layers: Dict[str, Any] = getattr(scene, "layers", None) or {}
        if name not in layers:
            return ToolResult(success=False, message=f"Layer '{name}' not found")

        layers[name]["locked"] = locked
        scene.layers = layers  # type: ignore[attr-defined]

        # Apply lock state to all objects in this layer.
        affected = 0
        for obj in scene.objects:
            layer_tag = None
            for tag in obj.tags:
                if tag.startswith("layer:"):
                    layer_tag = tag[len("layer:"):]
                    break
            if layer_tag == name:
                obj.locked = locked
                affected += 1

        return ToolResult(
            success=True,
            message=f"Layer '{name}' set to {'locked' if locked else 'unlocked'} ({affected} objects)",
            deltas=[SceneDelta(action="update", target_id=None, payload={"layers": layers})],
            data={"layer": name, "locked": locked, "affected": affected},
        )
