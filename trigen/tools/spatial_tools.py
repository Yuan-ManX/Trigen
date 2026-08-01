"""Spatial manipulation and measurement tools.

Adds alignment, distribution, camera animation, HDRI environment,
viewpoint snapshot, and distance measurement capabilities on top of
the base scene model.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

from trigen.scene import CameraObject, Scene, SceneObject
from trigen.tools.base import SceneDelta, ToolBase, ToolResult


_AXIS_INDEX = {"x": 0, "y": 1, "z": 2}

# Preset HDRI library (publicly hosted) keyed by friendly name. The frontend
# Environment component can resolve these to a Three.js loader.
_HDRI_PRESETS: Dict[str, Dict[str, Any]] = {
    "studio": {"url": "studio.hdr", "intensity": 1.0, "label": "Studio"},
    "sunset": {"url": "sunset.hdr", "intensity": 1.0, "label": "Sunset"},
    "city": {"url": "city.hdr", "intensity": 0.9, "label": "City"},
    "forest": {"url": "forest.hdr", "intensity": 0.85, "label": "Forest"},
    "night": {"url": "night.hdr", "intensity": 0.6, "label": "Night"},
    "neutral": {"url": "neutral.hdr", "intensity": 1.0, "label": "Neutral"},
}


_ALIGN_PARAMS = {
    "type": "object",
    "properties": {
        "targets": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Object ids or names to align (at least 2 recommended)",
        },
        "axis": {"type": "string", "enum": ["x", "y", "z"], "description": "Axis to align along"},
        "align_to": {
            "type": "string",
            "enum": ["min", "center", "max"],
            "description": "Reference point on each object's bounding box (default center)",
        },
        "value": {
            "type": "number",
            "description": "Explicit target coordinate; if omitted, align to the first object",
        },
    },
    "required": ["targets", "axis"],
}


_DISTRIBUTE_PARAMS = {
    "type": "object",
    "properties": {
        "targets": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Object ids or names to distribute (at least 2)",
        },
        "axis": {"type": "string", "enum": ["x", "y", "z"], "description": "Distribution axis"},
        "spacing": {
            "type": "number",
            "description": "Fixed spacing between consecutive objects; if omitted, distribute evenly between endpoints",
        },
        "preserve_order": {
            "type": "boolean",
            "description": "Keep the input order instead of sorting by current position (default false)",
        },
    },
    "required": ["targets", "axis"],
}


_ANIMATE_CAMERA_PARAMS = {
    "type": "object",
    "properties": {
        "camera": {
            "type": "string",
            "description": "Camera id or name; if omitted, uses the first camera in the scene",
        },
        "animation_type": {
            "type": "string",
            "enum": ["orbit", "flythrough"],
            "description": "Animation type: orbit (rotate around a point) or flythrough (visit waypoints)",
        },
        "duration": {"type": "number", "description": "Animation duration in seconds (default 6)"},
        "loop": {"type": "boolean", "description": "Whether the animation loops (default true for orbit)"},
        "target": {
            "type": "array",
            "items": {"type": "number"},
            "description": "Orbit center [x, y, z] (default [0, 0, 0])",
        },
        "radius": {"type": "number", "description": "Orbit radius (default current distance to target)"},
        "height": {"type": "number", "description": "Orbit camera height (default current y)"},
        "points": {
            "type": "array",
            "items": {"type": "array", "items": {"type": "number"}},
            "description": "Flythrough waypoints as [[x,y,z], ...]",
        },
    },
    "required": ["animation_type"],
}


_SET_ENVIRONMENT_PARAMS = {
    "type": "object",
    "properties": {
        "hdri": {
            "type": "string",
            "description": "HDRI preset name (studio/sunset/city/forest/night/neutral) or a URL/path",
        },
        "intensity": {"type": "number", "description": "Environment lighting intensity (default 1.0)"},
        "enabled": {"type": "boolean", "description": "Disable the environment (default true)"},
    },
    "required": ["hdri"],
}


_SNAPSHOT_VIEW_PARAMS = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "description": "Snapshot name (default Snapshot_N)"},
        "camera": {
            "type": "string",
            "description": "Camera id or name to snapshot; if omitted, uses the first camera",
        },
        "position": {
            "type": "array",
            "items": {"type": "number"},
            "description": "Explicit camera position [x,y,z]; if omitted, uses the camera's current position",
        },
        "target": {
            "type": "array",
            "items": {"type": "number"},
            "description": "Explicit look-at target [x,y,z]; if omitted, uses the camera's current target",
        },
    },
    "required": [],
}


_MEASURE_DISTANCE_PARAMS = {
    "type": "object",
    "properties": {
        "target_a": {"type": "string", "description": "First object id or name"},
        "target_b": {"type": "string", "description": "Second object id or name"},
    },
    "required": ["target_a", "target_b"],
}


def _bbox_extent(obj: SceneObject) -> List[float]:
    """Estimate bounding-box half-extent per axis from geometry params.

    Used to compute min/center/max alignment references. Falls back to
    a unit half-extent when geometry params are unavailable.
    """
    g = obj.geometry
    p = g.params or {}
    t = g.type
    # Default half extent
    hx = hy = hz = 0.5
    if t == "box":
        hx = float(p.get("width", 1.0)) / 2
        hy = float(p.get("height", 1.0)) / 2
        hz = float(p.get("depth", 1.0)) / 2
    elif t in ("sphere", "icosahedron", "dodecahedron", "octahedron", "tetrahedron"):
        r = float(p.get("radius", 0.6))
        hx = hy = hz = r
    elif t == "cylinder":
        r = float(p.get("radiusTop", p.get("radiusBottom", 0.5)))
        hy = float(p.get("height", 1.2)) / 2
        hx = hz = r
    elif t == "cone":
        r = float(p.get("radius", 0.6))
        hy = float(p.get("height", 1.2)) / 2
        hx = hz = r
    elif t == "torus":
        r = float(p.get("radius", 0.6)) + float(p.get("tube", 0.2))
        hy = float(p.get("tube", 0.2))
        hx = hz = r
    elif t == "plane":
        hx = float(p.get("width", 2.0)) / 2
        hz = float(p.get("height", 2.0)) / 2
        hy = 0.0
    # Apply object scale
    sx, sy, sz = obj.transform.scale
    return [hx * sx, hy * sy, hz * sz]


def _axis_value(point: List[float], axis: str, extent: float, align_to: str) -> float:
    """Return the alignment reference coordinate for one axis."""
    idx = _AXIS_INDEX[axis]
    base = float(point[idx])
    if align_to == "min":
        return base - extent
    if align_to == "max":
        return base + extent
    return base  # center


class AlignObjectsTool(ToolBase):
    """Align multiple objects along an axis by min/center/max reference."""

    name = "align_objects"
    description = "Align multiple objects along X/Y/Z by min/center/max reference point."

    def schema(self) -> Dict[str, Any]:
        return _ALIGN_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        targets = arguments.get("targets", [])
        if not isinstance(targets, list) or len(targets) < 2:
            return ToolResult(success=False, message="align_objects requires at least 2 targets")
        axis = str(arguments.get("axis", "y")).lower()
        if axis not in _AXIS_INDEX:
            return ToolResult(success=False, message=f"Invalid axis: {axis}")
        align_to = str(arguments.get("align_to", "center")).lower()
        if align_to not in ("min", "center", "max"):
            return ToolResult(success=False, message=f"Invalid align_to: {align_to}")

        objs = scene.find_objects([str(t) for t in targets])
        if len(objs) < 2:
            return ToolResult(success=False, message="Fewer than 2 objects resolved")

        idx = _AXIS_INDEX[axis]
        extents = [_bbox_extent(o)[idx] for o in objs]
        refs = [_axis_value(o.transform.position, axis, ext, align_to) for o, ext in zip(objs, extents)]

        if "value" in arguments and arguments["value"] is not None:
            target_val = float(arguments["value"])
        else:
            # Align to the first object's reference
            target_val = refs[0]

        deltas: List[SceneDelta] = []
        moved = 0
        for obj, ref, ext in zip(objs, refs, extents):
            delta = target_val - ref
            if abs(delta) < 1e-9:
                continue
            obj.transform.position[idx] = float(obj.transform.position[idx]) + delta
            moved += 1
            deltas.append(SceneDelta(action="update", target_id=obj.id, payload=obj.to_dict()))

        return ToolResult(
            success=True,
            message=f"Aligned {moved} object(s) on {axis} ({align_to}) to {target_val:.3f}",
            deltas=deltas,
            data={"axis": axis, "align_to": align_to, "value": target_val, "moved": moved},
        )


class DistributeObjectsTool(ToolBase):
    """Distribute objects evenly along an axis."""

    name = "distribute_objects"
    description = "Distribute multiple objects evenly along X/Y/Z between their endpoints."

    def schema(self) -> Dict[str, Any]:
        return _DISTRIBUTE_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        targets = arguments.get("targets", [])
        if not isinstance(targets, list) or len(targets) < 2:
            return ToolResult(success=False, message="distribute_objects requires at least 2 targets")
        axis = str(arguments.get("axis", "x")).lower()
        if axis not in _AXIS_INDEX:
            return ToolResult(success=False, message=f"Invalid axis: {axis}")

        objs = scene.find_objects([str(t) for t in targets])
        if len(objs) < 2:
            return ToolResult(success=False, message="Fewer than 2 objects resolved")

        preserve_order = bool(arguments.get("preserve_order", False))
        if not preserve_order:
            idx = _AXIS_INDEX[axis]
            objs.sort(key=lambda o: float(o.transform.position[idx]))

        idx = _AXIS_INDEX[axis]
        positions = [float(o.transform.position[idx]) for o in objs]
        first, last = positions[0], positions[-1]
        n = len(objs)
        spacing = arguments.get("spacing")
        deltas: List[SceneDelta] = []

        if spacing is not None:
            step = float(spacing)
            # Anchor at the first object; subsequent objects spaced by `step`
            for i, obj in enumerate(objs):
                new_pos = first + i * step
                obj.transform.position[idx] = new_pos
                deltas.append(SceneDelta(action="update", target_id=obj.id, payload=obj.to_dict()))
            mode = f"fixed spacing {step:.3f}"
        else:
            # Even distribution between endpoints
            if n > 2 and last > first:
                step = (last - first) / (n - 1)
            else:
                step = 0.0
            for i, obj in enumerate(objs):
                obj.transform.position[idx] = first + i * step
                deltas.append(SceneDelta(action="update", target_id=obj.id, payload=obj.to_dict()))
            mode = f"even distribution step {step:.3f}"

        return ToolResult(
            success=True,
            message=f"Distributed {n} object(s) along {axis} ({mode})",
            deltas=deltas,
            data={"axis": axis, "count": n, "mode": mode},
        )


class AnimateCameraTool(ToolBase):
    """Attach an orbit or flythrough animation to a camera."""

    name = "animate_camera"
    description = "Attach an orbit or flythrough animation descriptor to a camera in the scene."

    def schema(self) -> Dict[str, Any]:
        return _ANIMATE_CAMERA_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        cam_id = arguments.get("camera")
        camera: Optional[CameraObject] = None
        if cam_id:
            for c in scene.cameras:
                if c.id == cam_id or c.name.lower() == str(cam_id).lower():
                    camera = c
                    break
        if camera is None and scene.cameras:
            camera = scene.cameras[0]
        if camera is None:
            return ToolResult(success=False, message="No camera available in the scene")

        animation_type = str(arguments.get("animation_type", "orbit")).lower()
        duration = float(arguments.get("duration", 6.0))
        loop = bool(arguments.get("loop", animation_type == "orbit"))

        target = arguments.get("target", list(camera.target))
        if not isinstance(target, list) or len(target) != 3:
            target = list(camera.target)
        target = [float(target[0]), float(target[1]), float(target[2])]

        descriptor: Dict[str, Any] = {
            "type": animation_type,
            "duration": duration,
            "loop": loop,
            "target": target,
        }

        if animation_type == "orbit":
            # Compute current radius and height from camera position
            cx, cy, cz = (float(v) for v in camera.position)
            radius = arguments.get("radius")
            if radius is None:
                radius = math.sqrt((cx - target[0]) ** 2 + (cz - target[2]) ** 2)
            else:
                radius = float(radius)
            height = arguments.get("height")
            if height is None:
                height = cy
            else:
                height = float(height)
            descriptor.update({"radius": radius, "height": height})
        elif animation_type == "flythrough":
            points = arguments.get("points")
            if not isinstance(points, list) or len(points) < 2:
                return ToolResult(
                    success=False,
                    message="flythrough animation requires at least 2 waypoints",
                )
            cleaned = []
            for p in points:
                if not isinstance(p, list) or len(p) != 3:
                    return ToolResult(success=False, message="Each waypoint must be [x, y, z]")
                cleaned.append([float(p[0]), float(p[1]), float(p[2])])
            descriptor["points"] = cleaned
        else:
            return ToolResult(success=False, message=f"Unknown animation type: {animation_type}")

        camera.animation = descriptor
        return ToolResult(
            success=True,
            message=f"Attached {animation_type} animation to camera {camera.name}",
            deltas=[SceneDelta(action="update_camera", target_id=camera.id, payload=camera.to_dict())],
            data={"camera": camera.to_dict()},
        )


class SetEnvironmentTool(ToolBase):
    """Set or clear the HDRI environment map."""

    name = "set_environment"
    description = "Set the HDRI environment map (preset name or URL) and lighting intensity."

    def schema(self) -> Dict[str, Any]:
        return _SET_ENVIRONMENT_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        enabled = arguments.get("enabled", True)
        if not enabled:
            old = scene.environment
            scene.environment = None
            return ToolResult(
                success=True,
                message="Environment cleared",
                deltas=[SceneDelta(action="set_environment", payload={"environment": None})],
                data={"environment": None, "previous": old},
            )

        hdri = str(arguments.get("hdri", "")).strip()
        if not hdri:
            return ToolResult(success=False, message="No hdri preset or URL provided")

        preset = _HDRI_PRESETS.get(hdri.lower())
        if preset:
            url = preset["url"]
            intensity = float(arguments.get("intensity", preset["intensity"]))
            label = preset["label"]
        else:
            url = hdri
            intensity = float(arguments.get("intensity", 1.0))
            label = hdri

        old = scene.environment
        # Encode the environment as "url|intensity" so the field stays a string
        # while still carrying the intensity. The frontend parses this.
        scene.environment = f"{url}|{intensity}"
        return ToolResult(
            success=True,
            message=f"Environment set to {label} (intensity {intensity})",
            deltas=[SceneDelta(action="set_environment", payload={"environment": scene.environment, "url": url, "intensity": intensity, "label": label})],
            data={"environment": scene.environment, "url": url, "intensity": intensity, "label": label, "previous": old},
        )


class SnapshotViewTool(ToolBase):
    """Capture the current camera state as a named snapshot view."""

    name = "snapshot_view"
    description = "Capture the current camera position/target as a named snapshot view saved to the scene."

    def schema(self) -> Dict[str, Any]:
        return _SNAPSHOT_VIEW_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        cam_id = arguments.get("camera")
        source: Optional[CameraObject] = None
        if cam_id:
            for c in scene.cameras:
                if c.id == cam_id or c.name.lower() == str(cam_id).lower():
                    source = c
                    break
        if source is None and scene.cameras:
            source = scene.cameras[0]
        if source is None:
            return ToolResult(success=False, message="No camera available to snapshot")

        position = arguments.get("position")
        if not isinstance(position, list) or len(position) != 3:
            position = list(source.position)
        position = [float(position[0]), float(position[1]), float(position[2])]

        target = arguments.get("target")
        if not isinstance(target, list) or len(target) != 3:
            target = list(source.target)
        target = [float(target[0]), float(target[1]), float(target[2])]

        name = arguments.get("name") or f"Snapshot_{len(scene.cameras) + 1}"
        existing = {c.name for c in scene.cameras}
        if name in existing:
            idx = 2
            while f"{name}_{idx}" in existing:
                idx += 1
            name = f"{name}_{idx}"

        snapshot = CameraObject(
            name=name,
            type=source.type,
            position=position,
            target=target,
            fov=source.fov,
            near=source.near,
            far=source.far,
        )
        scene.cameras.append(snapshot)
        return ToolResult(
            success=True,
            message=f"Snapshot view '{name}' saved at {position} -> {target}",
            deltas=[SceneDelta(action="create_camera", target_id=snapshot.id, payload=snapshot.to_dict())],
            data={"camera": snapshot.to_dict()},
        )


class MeasureDistanceTool(ToolBase):
    """Measure the Euclidean distance between two objects."""

    name = "measure_distance"
    description = "Measure Euclidean and per-axis distance between two objects in the scene."

    def schema(self) -> Dict[str, Any]:
        return _MEASURE_DISTANCE_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        a_id = str(arguments.get("target_a", ""))
        b_id = str(arguments.get("target_b", ""))
        if not a_id or not b_id:
            return ToolResult(success=False, message="Both target_a and target_b are required")

        a = scene.find_object(a_id)
        b = scene.find_object(b_id)
        if a is None:
            return ToolResult(success=False, message=f"Object not found: {a_id}")
        if b is None:
            return ToolResult(success=False, message=f"Object not found: {b_id}")

        pa = [float(v) for v in a.transform.position]
        pb = [float(v) for v in b.transform.position]
        dx, dy, dz = pb[0] - pa[0], pb[1] - pa[1], pb[2] - pa[2]
        dist = math.sqrt(dx * dx + dy * dy + dz * dz)
        # Emit an editor_measure delta so the frontend can render a viewport
        # overlay (line + distance label) between the two measured objects.
        # This delta is editor-only: it does not mutate the backend Scene.
        return ToolResult(
            success=True,
            message=f"Distance between '{a.name}' and '{b.name}' is {dist:.4f} (dx={dx:.3f}, dy={dy:.3f}, dz={dz:.3f})",
            data={
                "target_a": a.name,
                "target_b": b.name,
                "distance": dist,
                "delta": {"x": dx, "y": dy, "z": dz},
            },
            deltas=[
                SceneDelta(
                    action="editor_measure",
                    payload={
                        "a_id": a.id,
                        "b_id": b.id,
                        "a_name": a.name,
                        "b_name": b.name,
                        "a_position": pa,
                        "b_position": pb,
                        "distance": dist,
                        "delta": {"x": dx, "y": dy, "z": dz},
                    },
                )
            ],
        )
