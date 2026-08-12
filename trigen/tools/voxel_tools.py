"""Voxel sculpting and particle system tools.

Provides direct voxel-based 3D sculpting — builds structures by placing
or removing cubes on a regular grid, enabling blocky/architectural forms
that complement the smooth primitive geometry. Also provides a particle
system creator that emits particle-effect objects (fire, smoke, sparks,
fountain) as animated point-cloud descriptors the frontend can render.
"""

from __future__ import annotations

import math
import random
from typing import Any, Dict, List, Optional, Tuple

from trigen.scene import Geometry, Material, Scene, SceneObject, Transform
from trigen.tools.base import SceneDelta, ToolBase, ToolResult


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

_VOXEL_SCULPT_PARAMS = {
    "type": "object",
    "properties": {
        "operation": {
            "type": "string",
            "enum": ["add", "remove", "paint", "sphere", "box", "pyramid"],
            "description": "Sculpt operation: add/remove single voxel, paint color, or generate a shape.",
        },
        "position": {
            "type": "array",
            "items": {"type": "number"},
            "description": "Voxel grid position [x, y, z] (default [0, 0, 0]).",
        },
        "size": {
            "type": "integer",
            "description": "Voxel grid cell size (default 1).",
            "minimum": 1,
            "maximum": 10,
        },
        "color": {
            "type": "string",
            "description": "Voxel color (default #ff6600).",
        },
        "radius": {
            "type": "number",
            "description": "Radius for sphere operation (default 3).",
        },
        "dimensions": {
            "type": "array",
            "items": {"type": "integer"},
            "description": "Dimensions [w, h, d] for box/pyramid operations (default [3, 3, 3]).",
        },
        "target": {
            "type": "string",
            "description": "Target voxel group name for remove/paint operations.",
        },
        "seed": {
            "type": "integer",
            "description": "Random seed for noise variation (default 42).",
        },
    },
    "required": ["operation"],
}

_PARTICLE_SYSTEM_PARAMS = {
    "type": "object",
    "properties": {
        "effect_type": {
            "type": "string",
            "enum": ["fire", "smoke", "sparks", "fountain", "explosion", "dust", "magic"],
            "description": "Particle effect type.",
        },
        "position": {
            "type": "array",
            "items": {"type": "number"},
            "description": "Emitter position [x, y, z] (default [0, 0, 0]).",
        },
        "intensity": {
            "type": "number",
            "description": "Particle density 0.1-2.0 (default 1.0).",
            "minimum": 0.1,
            "maximum": 2.0,
        },
        "scale": {
            "type": "number",
            "description": "Overall effect scale (default 1.0).",
        },
        "color": {
            "type": "string",
            "description": "Override particle color (uses effect default if omitted).",
        },
        "name": {
            "type": "string",
            "description": "Optional particle system name.",
        },
    },
    "required": ["effect_type"],
}


# ---------------------------------------------------------------------------
# Voxel sculpting tool
# ---------------------------------------------------------------------------

class VoxelSculptTool(ToolBase):
    """Sculpt voxel-based structures on a regular 3D grid.

    Supports add/remove/paint operations on individual voxels and bulk
    shape generation (sphere, box, pyramid). Each voxel is a unit cube
    placed at integer grid coordinates, enabling blocky architectural
    forms, pixel-art style 3D, and rapid prototyping layouts.
    """

    name = "voxel_sculpt"
    description = (
        "Sculpt voxel-based 3D structures by placing, removing, or painting "
        "cubes on a regular grid. Supports bulk shape generation (sphere, "
        "box, pyramid) for rapid architectural prototyping."
    )
    category = "procedural"

    def schema(self) -> Dict[str, Any]:
        return _VOXEL_SCULPT_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        operation = str(arguments.get("operation", "add"))
        pos = arguments.get("position", [0, 0, 0])
        cell_size = int(arguments.get("size", 1))
        color = str(arguments.get("color", "#ff6600"))
        radius = float(arguments.get("radius", 3))
        dimensions = arguments.get("dimensions", [3, 3, 3])
        seed = int(arguments.get("seed", 42))
        target_name = arguments.get("target", "")

        deltas: List[SceneDelta] = []
        created_objects: List[Dict[str, Any]] = []
        rng = random.Random(seed)

        if operation == "add":
            voxels = [self._make_voxel(pos, cell_size, color, "Voxel")]
            self._apply_voxels(scene, voxels, deltas, created_objects)

        elif operation == "remove":
            removed = 0
            for obj in scene.objects[:]:
                if target_name and target_name in obj.name or "Voxel" in obj.name:
                    if self._voxel_matches(obj, pos, cell_size):
                        scene.objects.remove(obj)
                        removed += 1
                        deltas.append(SceneDelta(
                            action="delete",
                            target_id=obj.id,
                            payload={"name": obj.name},
                        ))
            return ToolResult(
                success=True,
                message=f"Removed {removed} voxel(s).",
                deltas=deltas,
                data={"removed": removed},
            )

        elif operation == "paint":
            painted = 0
            for obj in scene.objects:
                if "Voxel" in obj.name and self._voxel_matches(obj, pos, cell_size):
                    obj.material.color = color
                    painted += 1
                    deltas.append(SceneDelta(
                        action="update",
                        target_id=obj.id,
                        payload={"material": obj.material.to_dict()},
                    ))
            return ToolResult(
                success=True,
                message=f"Painted {painted} voxel(s) with {color}.",
                deltas=deltas,
                data={"painted": painted, "color": color},
            )

        elif operation == "sphere":
            voxels = self._generate_voxel_sphere(pos, radius, cell_size, color, rng)
            self._apply_voxels(scene, voxels, deltas, created_objects)

        elif operation == "box":
            w, h, d = int(dimensions[0]), int(dimensions[1]), int(dimensions[2])
            voxels = self._generate_voxel_box(pos, w, h, d, cell_size, color)
            self._apply_voxels(scene, voxels, deltas, created_objects)

        elif operation == "pyramid":
            base = int(dimensions[0])
            voxels = self._generate_voxel_pyramid(pos, base, cell_size, color)
            self._apply_voxels(scene, voxels, deltas, created_objects)

        else:
            return ToolResult(success=False, message=f"Unknown operation: {operation}")

        return ToolResult(
            success=True,
            message=f"Voxel sculpt '{operation}': created {len(created_objects)} voxel(s).",
            deltas=deltas,
            data={
                "operation": operation,
                "created": len(created_objects),
                "voxels": created_objects[:20],
            },
        )

    @staticmethod
    def _make_voxel(
        grid_pos: List[float], cell_size: int, color: str, prefix: str
    ) -> SceneObject:
        gx, gy, gz = grid_pos
        obj = SceneObject(
            name=f"{prefix}_{int(gx)}_{int(gy)}_{int(gz)}",
            geometry=Geometry(type="box", params={"width": cell_size, "height": cell_size, "depth": cell_size}),
            material=Material(color=color, roughness=0.6, metalness=0.1),
            transform=Transform(
                position=[gx * cell_size, gy * cell_size, gz * cell_size],
                scale=[1.0, 1.0, 1.0],
            ),
            tags=["voxel"],
        )
        return obj

    @staticmethod
    def _voxel_matches(obj: SceneObject, pos: List[float], cell_size: int) -> bool:
        try:
            ox, oy, oz = obj.transform.position
            return (
                abs(ox - pos[0] * cell_size) < 0.01
                and abs(oy - pos[1] * cell_size) < 0.01
                and abs(oz - pos[2] * cell_size) < 0.01
            )
        except (IndexError, TypeError):
            return False

    @staticmethod
    def _generate_voxel_sphere(
        center: List[float], radius: float, cell_size: int, color: str, rng: random.Random
    ) -> List[SceneObject]:
        voxels: List[SceneObject] = []
        r_int = max(1, int(radius))
        cx, cy, cz = center
        for x in range(-r_int, r_int + 1):
            for y in range(-r_int, r_int + 1):
                for z in range(-r_int, r_int + 1):
                    dist = math.sqrt(x * x + y * y + z * z)
                    if dist <= radius:
                        # Color variation for visual interest
                        shade = 1.0 - (dist / radius) * 0.3
                        c = _shade_color(color, shade)
                        voxels.append(VoxelSculptTool._make_voxel(
                            [cx + x, cy + y, cz + z], cell_size, c, "VSphere"
                        ))
        return voxels

    @staticmethod
    def _generate_voxel_box(
        origin: List[float], w: int, h: int, d: int, cell_size: int, color: str
    ) -> List[SceneObject]:
        voxels: List[SceneObject] = []
        ox, oy, oz = origin
        for x in range(w):
            for y in range(h):
                for z in range(d):
                    # Hollow interior for large boxes (shell only)
                    if w > 3 and h > 3 and d > 3:
                        if 0 < x < w - 1 and 0 < y < h - 1 and 0 < z < d - 1:
                            continue
                    voxels.append(VoxelSculptTool._make_voxel(
                        [ox + x, oy + y, oz + z], cell_size, color, "VBox"
                    ))
        return voxels

    @staticmethod
    def _generate_voxel_pyramid(
        origin: List[float], base: int, cell_size: int, color: str
    ) -> List[SceneObject]:
        voxels: List[SceneObject] = []
        ox, oy, oz = origin
        level = 0
        size = base
        while size > 0:
            for x in range(size):
                for z in range(size):
                    voxels.append(VoxelSculptTool._make_voxel(
                        [ox + x, oy + level, oz + z], cell_size, color, "VPyr"
                    ))
            level += 1
            size -= 1
        return voxels

    @staticmethod
    def _apply_voxels(
        scene: Scene,
        voxels: List[SceneObject],
        deltas: List[SceneDelta],
        created: List[Dict[str, Any]],
    ) -> None:
        for voxel in voxels:
            scene.objects.append(voxel)
            deltas.append(SceneDelta(
                action="create",
                target_id=voxel.id,
                payload=voxel.to_dict(),
            ))
            created.append({"id": voxel.id, "name": voxel.name})


def _shade_color(hex_color: str, factor: float) -> str:
    """Multiply a hex color's RGB channels by factor (0.0-1.0)."""
    try:
        r = int(hex_color[1:3], 16)
        g = int(hex_color[3:5], 16)
        b = int(hex_color[5:7], 16)
        r = max(0, min(255, int(r * factor)))
        g = max(0, min(255, int(g * factor)))
        b = max(0, min(255, int(b * factor)))
        return f"#{r:02x}{g:02x}{b:02x}"
    except (ValueError, IndexError):
        return hex_color


# ---------------------------------------------------------------------------
# Particle system tool
# ---------------------------------------------------------------------------

# Default particle configurations per effect type
_PARTICLE_PRESETS: Dict[str, Dict[str, Any]] = {
    "fire": {
        "color": "#ff4400",
        "emissive": "#ff6600",
        "emissive_intensity": 2.0,
        "particle_count": 50,
        "spread": 0.5,
        "upward_speed": 2.0,
        "lifetime": 1.5,
        "size_start": 0.3,
        "size_end": 0.05,
        "geometry": "sphere",
    },
    "smoke": {
        "color": "#666666",
        "emissive": "#333333",
        "emissive_intensity": 0.3,
        "particle_count": 40,
        "spread": 1.0,
        "upward_speed": 0.8,
        "lifetime": 3.0,
        "size_start": 0.2,
        "size_end": 0.8,
        "geometry": "sphere",
    },
    "sparks": {
        "color": "#ffdd00",
        "emissive": "#ffaa00",
        "emissive_intensity": 3.0,
        "particle_count": 30,
        "spread": 2.0,
        "upward_speed": 3.0,
        "lifetime": 0.8,
        "size_start": 0.08,
        "size_end": 0.01,
        "geometry": "sphere",
    },
    "fountain": {
        "color": "#00aaff",
        "emissive": "#0088ff",
        "emissive_intensity": 1.5,
        "particle_count": 60,
        "spread": 0.3,
        "upward_speed": 4.0,
        "lifetime": 2.0,
        "size_start": 0.15,
        "size_end": 0.05,
        "geometry": "sphere",
    },
    "explosion": {
        "color": "#ff2200",
        "emissive": "#ff4400",
        "emissive_intensity": 4.0,
        "particle_count": 80,
        "spread": 3.0,
        "upward_speed": 0.0,
        "lifetime": 1.0,
        "size_start": 0.4,
        "size_end": 0.02,
        "geometry": "sphere",
    },
    "dust": {
        "color": "#ccccaa",
        "emissive": "#888866",
        "emissive_intensity": 0.2,
        "particle_count": 25,
        "spread": 1.5,
        "upward_speed": 0.2,
        "lifetime": 4.0,
        "size_start": 0.1,
        "size_end": 0.15,
        "geometry": "sphere",
    },
    "magic": {
        "color": "#aa00ff",
        "emissive": "#cc44ff",
        "emissive_intensity": 2.5,
        "particle_count": 45,
        "spread": 1.2,
        "upward_speed": 1.0,
        "lifetime": 2.5,
        "size_start": 0.12,
        "size_end": 0.03,
        "geometry": "sphere",
    },
}


class ParticleSystemTool(ToolBase):
    """Create animated particle effect objects in the scene.

    Generates a cluster of small emissive spheres with per-particle
    animation descriptors that simulate fire, smoke, sparks, fountains,
    explosions, dust, or magic effects. Each particle has individual
    trajectory, lifetime, and size interpolation parameters stored
    in the object's animation field.
    """

    name = "create_particle_system"
    description = (
        "Generate animated particle effects (fire, smoke, sparks, fountain, "
        "explosion, dust, magic) as clusters of emissive animated spheres "
        "with per-particle trajectory and lifetime parameters."
    )
    category = "creation"

    def schema(self) -> Dict[str, Any]:
        return _PARTICLE_SYSTEM_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        effect_type = str(arguments.get("effect_type", "fire"))
        pos = arguments.get("position", [0, 0, 0])
        intensity = float(arguments.get("intensity", 1.0))
        scale = float(arguments.get("scale", 1.0))
        override_color = arguments.get("color")
        name = arguments.get("name", f"Particles_{effect_type}")

        preset = _PARTICLE_PRESETS.get(effect_type, _PARTICLE_PRESETS["fire"])
        if override_color:
            preset = {**preset, "color": override_color}

        particle_count = max(5, int(preset["particle_count"] * intensity))
        ex, ey, ez = pos[0], pos[1], pos[2]
        rng = random.Random(hash(effect_type) & 0xFFFFFFFF)

        deltas: List[SceneDelta] = []
        created: List[Dict[str, Any]] = []

        for i in range(particle_count):
            # Random spread within the effect's cone
            spread = preset["spread"] * scale
            px = ex + rng.uniform(-spread, spread)
            py = ey + rng.uniform(-spread * 0.3, spread * 0.3)
            pz = ez + rng.uniform(-spread, spread)

            # Per-particle trajectory
            angle = rng.uniform(0, 2 * math.pi)
            radial = rng.uniform(0.3, 1.0) * spread
            vx = math.cos(angle) * radial * 0.5
            vy = preset["upward_speed"] * rng.uniform(0.7, 1.3) * scale
            vz = math.sin(angle) * radial * 0.5

            lifetime = preset["lifetime"] * rng.uniform(0.7, 1.3)
            size_start = preset["size_start"] * scale * rng.uniform(0.8, 1.2)
            size_end = preset["size_end"] * scale

            # Per-particle color variation
            shade = rng.uniform(0.7, 1.0)
            pcolor = _shade_color(preset["color"], shade)

            particle = SceneObject(
                name=f"{name}_{i:03d}",
                geometry=Geometry(
                    type=preset["geometry"],
                    params={"radius": size_start},
                ),
                material=Material(
                    color=pcolor,
                    emissive=preset["emissive"],
                    emissive_intensity=preset["emissive_intensity"] * shade,
                    roughness=0.3,
                    metalness=0.0,
                    opacity=0.85,
                ),
                transform=Transform(position=[px, py, pz]),
                tags=["particle", effect_type],
                animation={
                    "type": "particle",
                    "effect": effect_type,
                    "velocity": [vx, vy, vz],
                    "lifetime": lifetime,
                    "size_start": size_start,
                    "size_end": size_end,
                    "gravity": 0.5 if effect_type in ("sparks", "fountain", "explosion") else -0.1,
                    "loop": True,
                },
            )
            scene.objects.append(particle)
            deltas.append(SceneDelta(
                action="create",
                target_id=particle.id,
                payload=particle.to_dict(),
            ))
            created.append({"id": particle.id, "name": particle.name})

        return ToolResult(
            success=True,
            message=f"Created {effect_type} particle system with {particle_count} particles.",
            deltas=deltas,
            data={
                "effect_type": effect_type,
                "particle_count": particle_count,
                "position": pos,
                "scale": scale,
                "intensity": intensity,
                "particles": created[:20],
            },
        )
