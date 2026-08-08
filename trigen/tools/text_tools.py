"""Text and sprite authoring tools.

These tools create text geometry objects and sprite-style markers so a
user can label, caption, and annotate a scene conversationally — "add a
label that reads 'Hero' above the platform". Text objects use the shared
``text`` geometry type that the scene renderer already understands, so
the resulting object renders as a nameplate in the viewport and remains a
fully editable scene object (transform / material / layer / animation).
"""

from __future__ import annotations

from typing import Any, Dict

from trigen.scene import Geometry, Material, Scene, SceneObject, Transform
from trigen.tools.base import SceneDelta, ToolBase, ToolResult

# ---------------------------------------------------------------------------
# create_text
# ---------------------------------------------------------------------------
_CREATE_TEXT_PARAMS = {
    "type": "object",
    "properties": {
        "text": {
            "type": "string",
            "description": "The string to render as 3D text.",
        },
        "size": {
            "type": "number",
            "description": "Glyph size (default 0.6).",
        },
        "height": {
            "type": "number",
            "description": "Extrusion depth (default 0.12).",
        },
        "name": {
            "type": "string",
            "description": "Object name, for later reference.",
        },
        "position": {
            "type": "array",
            "items": {"type": "number"},
            "description": "Position [x, y, z] (default [0, 0, 0]).",
        },
        "color": {
            "type": "string",
            "description": "Material color (hex such as #00F0FF).",
        },
        "emissive": {
            "type": "string",
            "description": "Emissive color.",
        },
        "emissive_intensity": {
            "type": "number",
            "description": "Emissive intensity 0-5.",
        },
        "metalness": {
            "type": "number",
            "description": "Metalness 0-1.",
        },
        "roughness": {
            "type": "number",
            "description": "Roughness 0-1.",
        },
    },
    "required": ["text"],
}


class CreateTextTool(ToolBase):
    """Create a 3D text object in the scene.

    Renders as a text geometry (a nameplate in the viewport, with the glyph
    string stored for SDF generation). The object is a normal scene object,
    so it can be moved, scaled, recolored, animated, and exported just like
    any other mesh. Read/write — adds a new object.
    """

    name = "create_text"
    description = (
        "Create a 3D text label in the scene. Use it to caption objects, add "
        "signage, or annotate a composition. Pass the text string plus optional "
        "size, color, and position."
    )

    def schema(self) -> Dict[str, Any]:
        return _CREATE_TEXT_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        text = str(arguments.get("text", "")).strip()
        if not text:
            return ToolResult(
                success=False,
                message="Text cannot be empty",
                deltas=[],
                data={},
            )

        size = float(arguments.get("size", 0.6))
        height = float(arguments.get("height", 0.12))
        params: Dict[str, Any] = {
            "text": text,
            "size": size,
            "height": height,
            "curveSegments": 8,
            "bevelEnabled": bool(arguments.get("bevelEnabled", False)),
        }

        pos = arguments.get("position", [0.0, 0.0, 0.0])
        if isinstance(pos, (list, tuple)) and len(pos) >= 3:
            position = [float(pos[0]), float(pos[1]), float(pos[2])]
        else:
            position = [0.0, 0.0, 0.0]

        name = str(arguments.get("name", "")).strip() or text
        name = scene.next_auto_name(name)

        mat = Material(
            color=str(arguments.get("color", "#00F0FF")),
            metalness=float(arguments.get("metalness", 0.0)),
            roughness=float(arguments.get("roughness", 0.4)),
            emissive=str(arguments.get("emissive", "#000000")),
            emissive_intensity=float(arguments.get("emissive_intensity", 0.0)),
        )

        obj = SceneObject(
            name=name,
            geometry=Geometry(type="text", params=params),
            material=mat,
            transform=Transform(position=position),
            tags=["text", "label"],
        )
        scene.objects.append(obj)

        return ToolResult(
            success=True,
            message=f"Created text '{name}' reading '{text}'",
            deltas=[
                SceneDelta(
                    action="add_object",
                    target_id=obj.id,
                    payload=obj.to_dict(),
                )
            ],
            data={"id": obj.id, "name": name, "text": text},
        )


__all__ = [
    "CreateTextTool",
]
