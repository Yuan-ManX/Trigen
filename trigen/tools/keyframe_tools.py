"""Per-property keyframing and animation clip tools.

Provides fine-grained keyframe insertion (set_keyframe) and named
animation clip management so the Agent can author complex animation
schedules without hand-assembling multiple animation descriptors.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from trigen.scene import Scene, SceneObject
from trigen.tools.base import SceneDelta, ToolBase, ToolResult


class SetKeyframeTool(ToolBase):
    """Insert a single keyframe for a property on an existing animation track."""

    name = "set_keyframe"
    description = "Insert a single keyframe (position/rotation/scale) at a normalized time on an object's animation track."

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "Target object id or name"},
                "time": {"type": "number", "description": "Normalized time 0..1 for the keyframe"},
                "position": {"type": "array", "items": {"type": "number"}, "description": "[x, y, z] position"},
                "rotation": {"type": "array", "items": {"type": "number"}, "description": "[rx, ry, rz] rotation (radians)"},
                "scale": {"type": "array", "items": {"type": "number"}, "description": "[sx, sy, sz] scale"},
                "duration": {"type": "number", "description": "Total animation duration in seconds (default 4)"},
                "loop": {"type": "boolean", "description": "Loop the animation (default true)"},
                "easing": {
                    "type": "string",
                    "enum": ["linear", "easeIn", "easeOut", "easeInOut"],
                    "description": "Interpolation easing (default linear)",
                },
            },
            "required": ["target", "time"],
        }

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        target_id = arguments.get("target", "")
        obj = scene.find_object(target_id)
        if not obj:
            return ToolResult(success=False, message=f"Object not found: {target_id}")

        t = float(arguments.get("time", 0.0))
        t = max(0.0, min(1.0, t))

        # Find or create a keyframe animation descriptor.
        existing = obj.animation
        if existing and existing.get("type") == "keyframe":
            descriptor = dict(existing)
        else:
            descriptor: Dict[str, Any] = {
                "type": "keyframe",
                "keyframes": [],
                "duration": float(arguments.get("duration", 4.0)),
                "loop": bool(arguments.get("loop", True)),
                "easing": str(arguments.get("easing", "linear")),
            }

        # Build the keyframe entry with provided properties.
        entry: Dict[str, Any] = {"t": t}
        for field in ("position", "rotation", "scale"):
            val = arguments.get(field)
            if isinstance(val, list) and len(val) == 3:
                entry[field] = [float(v) for v in val]

        if len(entry) <= 1:
            return ToolResult(success=False, message="At least one of position/rotation/scale is required")

        keyframes: List[Dict[str, Any]] = descriptor["keyframes"]

        # Replace any existing keyframe at the same time tolerance (±0.001).
        tolerance = 0.001
        replaced = False
        for i, kf in enumerate(keyframes):
            if abs(kf.get("t", -1.0) - t) < tolerance:
                keyframes[i] = entry
                replaced = True
                break
        if not replaced:
            keyframes.append(entry)

        keyframes.sort(key=lambda k: k.get("t", 0.0))

        descriptor["keyframes"] = keyframes
        obj.animation = descriptor

        return ToolResult(
            success=True,
            message=f"Keyframe at t={t:.2f} set on {obj.name} ({len(keyframes)} total keyframes)",
            deltas=[SceneDelta(action="update", target_id=obj.id, payload=obj.to_dict())],
            data={"object": obj.to_dict(), "keyframe": entry, "total_keyframes": len(keyframes)},
        )


class CreateAnimationClipTool(ToolBase):
    """Create a named reusable animation clip from the current animation descriptor."""

    name = "create_animation_clip"
    description = "Save an object's current animation descriptor as a named clip that can be reused."

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "Target object id or name"},
                "clip_name": {"type": "string", "description": "Name for the animation clip"},
                "description": {"type": "string", "description": "Optional clip description"},
            },
            "required": ["target", "clip_name"],
        }

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        target_id = arguments.get("target", "")
        obj = scene.find_object(target_id)
        if not obj:
            return ToolResult(success=False, message=f"Object not found: {target_id}")

        if not obj.animation:
            return ToolResult(success=False, message=f"Object {obj.name} has no animation to clip")

        clip_name = str(arguments.get("clip_name", "Clip"))
        description = str(arguments.get("description", ""))

        # Store the clip on the object's tags as a lightweight persistence
        # mechanism — the frontend can read tags to rebuild a clip library.
        tag = f"clip:{clip_name}"
        if tag not in obj.tags:
            obj.tags.append(tag)

        # Build clip metadata stored as an annotation-like dict.
        clip_data: Dict[str, Any] = {
            "clip_name": clip_name,
            "description": description,
            "target": obj.id,
            "animation": obj.animation,
            "tags": list(obj.tags),
        }

        return ToolResult(
            success=True,
            message=f"Animation clip '{clip_name}' created from {obj.name}",
            deltas=[SceneDelta(action="update", target_id=obj.id, payload=obj.to_dict())],
            data={"clip": clip_data},
        )


class FitCameraToSelectionTool(ToolBase):
    """Auto-frame the camera to show a target object or selection."""

    name = "fit_camera_to_selection"
    description = "Frame the viewport camera to show a target object or all selected objects with proper padding."

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "Target object id or name (empty for all objects)"},
                "padding": {"type": "number", "description": "Frame padding multiplier (default 1.5)"},
                "camera_distance": {"type": "number", "description": "Camera distance from target (auto if not set)"},
                "view_angle": {
                    "type": "string",
                    "enum": ["perspective", "top", "front", "side", "iso"],
                    "description": "View angle preset (default perspective)",
                },
            },
            "required": [],
        }

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        target_name = str(arguments.get("target", ""))
        padding = float(arguments.get("padding", 1.5))
        view_angle = str(arguments.get("view_angle", "perspective"))

        # Determine the focus bounds.
        if target_name:
            obj = scene.find_object(target_name)
            if not obj:
                return ToolResult(success=False, message=f"Object not found: {target_name}")
            center = [obj.transform.position[0], obj.transform.position[1], obj.transform.position[2]]
            max_dim = max(
                abs(obj.transform.scale[0]),
                abs(obj.transform.scale[1]),
                abs(obj.transform.scale[2]),
                1.0,
            )
            radius = max_dim * padding
        elif scene.objects:
            # Compute aggregate bounds of all objects.
            xs = [o.transform.position[0] for o in scene.objects]
            ys = [o.transform.position[1] for o in scene.objects]
            zs = [o.transform.position[2] for o in scene.objects]
            center = [(min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, (min(zs) + max(zs)) / 2]
            extent_x = (max(xs) - min(xs)) / 2 or 1.0
            extent_y = (max(ys) - min(ys)) / 2 or 1.0
            extent_z = (max(zs) - min(zs)) / 2 or 1.0
            radius = max(extent_x, extent_y, extent_z) * padding
        else:
            return ToolResult(success=False, message="No objects to frame")

        distance = float(arguments.get("camera_distance", 0))
        if distance <= 0:
            distance = radius * 3.0

        # Compute camera position based on view angle.
        if view_angle == "top":
            cam_pos = [center[0], center[1] + distance, center[2]]
        elif view_angle == "front":
            cam_pos = [center[0], center[1], center[2] + distance]
        elif view_angle == "side":
            cam_pos = [center[0] + distance, center[1], center[2]]
        elif view_angle == "iso":
            d = distance * 0.7
            cam_pos = [center[0] + d, center[1] + d, center[2] + d]
        else:
            cam_pos = [center[0] + distance * 0.6, center[1] + distance * 0.5, center[2] + distance * 0.8]

        # Update the active viewport camera if one exists.
        cam_updated = False
        for cam in scene.cameras:
            cam.position = cam_pos
            cam.target = center
            cam_updated = True
            break

        result_data: Dict[str, Any] = {
            "center": center,
            "camera_position": cam_pos,
            "radius": radius,
            "view_angle": view_angle,
            "camera_updated": cam_updated,
        }

        deltas: List[SceneDelta] = []
        if cam_updated:
            deltas.append(
                SceneDelta(
                    action="update",
                    target_id=scene.cameras[0].id,
                    payload={"position": cam_pos, "target": center, "view_angle": view_angle},
                )
            )

        target_desc = target_name or "all objects"
        return ToolResult(
            success=True,
            message=f"Camera framed to {target_desc} ({view_angle} view, distance {distance:.1f})",
            deltas=deltas,
            data=result_data,
        )
