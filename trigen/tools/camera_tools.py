"""Camera orchestration tools.

Adds, modifies, and switches viewport cameras, controlling type,
position, target, fov, near, far, and preset view angles.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from trigen.scene import CameraObject, Scene
from trigen.tools.base import SceneDelta, ToolBase, ToolResult


_ADD_CAMERA_PARAMS = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "description": "Camera name"},
        "camera_type": {
            "type": "string",
            "enum": ["perspective", "orthographic"],
            "description": "Camera type (default perspective)",
        },
        "position": {
            "type": "array",
            "items": {"type": "number"},
            "description": "Camera position [x, y, z] (default [5, 4, 7])",
        },
        "target": {
            "type": "array",
            "items": {"type": "number"},
            "description": "Camera target [x, y, z] (default [0, 0.5, 0])",
        },
        "fov": {"type": "number", "description": "Field of view (degrees, default 45)"},
        "near": {"type": "number", "description": "Near clipping plane (default 0.1)"},
        "far": {"type": "number", "description": "Far clipping plane (default 1000)"},
    },
    "required": [],
}


_MODIFY_CAMERA_PARAMS = {
    "type": "object",
    "properties": {
        "target": {"type": "string", "description": "Target camera id or name"},
        "name": {"type": "string", "description": "Rename the camera"},
        "camera_type": {
            "type": "string",
            "enum": ["perspective", "orthographic"],
            "description": "Switch camera type",
        },
        "position": {
            "type": "array",
            "items": {"type": "number"},
            "description": "New position [x, y, z]",
        },
        "target_pos": {
            "type": "array",
            "items": {"type": "number"},
            "description": "New target [x, y, z]",
        },
        "fov": {"type": "number", "description": "Field of view (degrees)"},
        "near": {"type": "number", "description": "Near clipping plane"},
        "far": {"type": "number", "description": "Far clipping plane"},
    },
    "required": ["target"],
}


_SET_VIEW_PARAMS = {
    "type": "object",
    "properties": {
        "view": {
            "type": "string",
            "enum": ["front", "back", "top", "bottom", "left", "right", "perspective"],
            "description": "Preset view",
        },
        "distance": {"type": "number", "description": "Camera distance from origin (default 10)"},
    },
    "required": ["view"],
}


# Preset view positions/targets
_VIEW_PRESETS: Dict[str, Any] = {
    "front":       ([0.0, 5.0, 10.0],    [0.0, 0.0, 0.0]),
    "back":        ([0.0, 5.0, -10.0],   [0.0, 0.0, 0.0]),
    "top":         ([0.0, 10.0, 0.001],  [0.0, 0.0, 0.0]),
    "bottom":      ([0.0, -10.0, 0.001], [0.0, 0.0, 0.0]),
    "left":        ([-10.0, 5.0, 0.0],   [0.0, 0.0, 0.0]),
    "right":       ([10.0, 5.0, 0.0],    [0.0, 0.0, 0.0]),
    "perspective": ([7.0, 5.0, 9.0],     [0.0, 0.0, 0.0]),
}


def _find_camera(scene: Scene, identifier: str) -> Optional[CameraObject]:
    """Find a camera by id or name."""
    for cam in scene.cameras:
        if cam.id == identifier or cam.name.lower() == identifier.lower():
            return cam
    return None


class AddCameraTool(ToolBase):
    """Add camera tool."""

    name = "add_camera"
    description = "Add a camera to the scene (perspective/orthographic), with optional position, target, field of view, etc."

    def schema(self) -> Dict[str, Any]:
        return _ADD_CAMERA_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        camera_type = arguments.get("camera_type", "perspective")
        if camera_type not in ("perspective", "orthographic"):
            camera_type = "perspective"
        name = arguments.get("name") or "Camera"

        # Auto-append index for duplicate names
        existing = {c.name for c in scene.cameras}
        if name in existing:
            idx = 2
            while f"{name}_{idx}" in existing:
                idx += 1
            name = f"{name}_{idx}"

        position = arguments.get("position", [5.0, 4.0, 7.0])
        if not isinstance(position, list) or len(position) != 3:
            position = [5.0, 4.0, 7.0]

        target = arguments.get("target", [0.0, 0.5, 0.0])
        if not isinstance(target, list) or len(target) != 3:
            target = [0.0, 0.5, 0.0]

        camera = CameraObject(
            name=name,
            type=camera_type,
            position=[float(p) for p in position],
            target=[float(t) for t in target],
            fov=float(arguments.get("fov", 45.0)),
            near=float(arguments.get("near", 0.1)),
            far=float(arguments.get("far", 1000.0)),
        )
        scene.cameras.append(camera)

        return ToolResult(
            success=True,
            message=f"Added {name} ({camera_type}), fov {camera.fov}°, position {camera.position}",
            deltas=[SceneDelta(action="create_camera", target_id=camera.id, payload=camera.to_dict())],
            data={"camera": camera.to_dict()},
        )


class ModifyCameraTool(ToolBase):
    """Modify camera tool."""

    name = "modify_camera"
    description = "Modify properties of an existing camera (position, target, field of view, near/far clipping planes, type)."

    def schema(self) -> Dict[str, Any]:
        return _MODIFY_CAMERA_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        target_id = arguments.get("target", "")
        camera = _find_camera(scene, target_id)
        if not camera:
            return ToolResult(success=False, message=f"Camera not found: {target_id}")

        changes: List[str] = []
        if "name" in arguments and arguments["name"]:
            camera.name = str(arguments["name"])
            changes.append(f"name->{camera.name}")
        if "camera_type" in arguments:
            ct = str(arguments["camera_type"])
            if ct in ("perspective", "orthographic"):
                camera.type = ct
                changes.append(f"type->{ct}")
        if "position" in arguments and isinstance(arguments["position"], list):
            pos = arguments["position"]
            if len(pos) == 3:
                camera.position = [float(p) for p in pos]
                changes.append(f"position->{camera.position}")
        if "target_pos" in arguments and isinstance(arguments["target_pos"], list):
            tgt = arguments["target_pos"]
            if len(tgt) == 3:
                camera.target = [float(t) for t in tgt]
                changes.append(f"target->{camera.target}")
        if "fov" in arguments:
            camera.fov = max(1.0, min(170.0, float(arguments["fov"])))
            changes.append(f"fov->{camera.fov}°")
        if "near" in arguments:
            camera.near = max(0.001, float(arguments["near"]))
            changes.append(f"near->{camera.near}")
        if "far" in arguments:
            camera.far = max(camera.near + 0.1, float(arguments["far"]))
            changes.append(f"far->{camera.far}")

        if not changes:
            return ToolResult(success=False, message="No camera modification parameters provided")

        return ToolResult(
            success=True,
            message=f"{camera.name} camera updated: {', '.join(changes)}",
            deltas=[SceneDelta(action="update_camera", target_id=camera.id, payload=camera.to_dict())],
            data={"camera": camera.to_dict()},
        )


class SetViewTool(ToolBase):
    """Set viewport preset view tool.

    Creates or updates a camera named "ViewportCamera" with appropriate
    position/target for each preset, so the frontend can switch the
    active view angle.
    """

    name = "set_view"
    description = (
        "Switch the viewport camera to a preset view (front/back/top/bottom/left/right/perspective). "
        "Creates or updates a camera named ViewportCamera."
    )

    def schema(self) -> Dict[str, Any]:
        return _SET_VIEW_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        view = arguments.get("view", "perspective")
        if view not in _VIEW_PRESETS:
            return ToolResult(
                success=False,
                message=f"Unknown view: {view}, available: {', '.join(_VIEW_PRESETS.keys())}",
            )

        distance = float(arguments.get("distance", 10.0))
        base_pos, base_target = _VIEW_PRESETS[view]
        # Scale position by distance relative to the default distance of 10
        scale = distance / 10.0 if distance > 0 else 1.0
        position = [base_pos[i] * scale for i in range(3)]
        target = list(base_target)

        # Find or create the ViewportCamera
        camera = _find_camera(scene, "ViewportCamera")
        action = "update_camera"
        if camera is None:
            camera = CameraObject(
                name="ViewportCamera",
                type="perspective",
                position=position,
                target=target,
                fov=45.0,
            )
            scene.cameras.append(camera)
            action = "create_camera"
        else:
            camera.position = position
            camera.target = target

        return ToolResult(
            success=True,
            message=f"Viewport switched to {view} view, camera position {position}, target {target}",
            deltas=[SceneDelta(action=action, target_id=camera.id, payload=camera.to_dict())],
            data={"view": view, "camera": camera.to_dict(), "camera_id": camera.id},
        )
