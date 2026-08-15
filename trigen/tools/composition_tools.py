"""Scene composition and editing tools.

Higher-level construction tools that compose multiple primitives into
recognizable structures: random object scattering, staircases, bridges,
noise-based terrain meshes, and chained clones along a path. Each tool
emits its output as a grouped collection of primitives so downstream
tools can target the group as a unit, and returns SceneDelta entries
for incremental frontend updates.
"""

from __future__ import annotations

import copy
import math
import random
from typing import Any, Dict, List, Tuple

from trigen.scene import (
    MATERIAL_PRESETS,
    Geometry,
    GroupObject,
    Material,
    Scene,
    SceneObject,
    Transform,
)
from trigen.tools.base import SceneDelta, ToolBase, ToolResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _add_object(
    scene: Scene,
    name: str,
    geometry_type: str,
    geo_params: Dict[str, Any],
    position: List[float],
    color: str = "#cccccc",
    rotation: List[float] | None = None,
    scale: List[float] | None = None,
    group_id: str | None = None,
    metalness: float = 0.0,
    roughness: float = 0.5,
    emissive: str = "#000000",
    emissive_intensity: float = 0.0,
) -> Tuple[SceneObject, SceneDelta]:
    """Create a scene object, register it, and return (obj, delta)."""
    obj = SceneObject(
        name=scene.next_auto_name(name),
        type="mesh",
        geometry=Geometry(type=geometry_type, params=dict(geo_params)),
        material=Material(
            color=color,
            metalness=metalness,
            roughness=roughness,
            emissive=emissive,
            emissive_intensity=emissive_intensity,
        ),
        transform=Transform(
            position=position,
            rotation=rotation if rotation else [0.0, 0.0, 0.0],
            scale=scale if scale else [1.0, 1.0, 1.0],
        ),
        group_id=group_id,
    )
    scene.objects.append(obj)
    delta = SceneDelta(action="create", target_id=obj.id, payload=obj.to_dict())
    return obj, delta


def _resolve_material(preset: str) -> Tuple[str, float, float]:
    """Resolve a material preset name to (color, metalness, roughness)."""
    spec = MATERIAL_PRESETS.get(preset) or MATERIAL_PRESETS["wood"]
    return (
        str(spec.get("color", "#cccccc")),
        float(spec.get("metalness", 0.0)),
        float(spec.get("roughness", 0.5)),
    )


def _make_group(scene: Scene, base_name: str, key: str) -> Tuple[GroupObject, str, List[SceneDelta]]:
    """Create and register a GroupObject, returning (group, group_id, deltas)."""
    gid = f"grp_{key}_{abs(hash(base_name)) & 0xFFFFF:05x}"
    group_obj = GroupObject(id=gid, name=scene.next_auto_name(base_name), child_ids=[])
    scene.groups.append(group_obj)
    deltas: List[SceneDelta] = [
        SceneDelta(action="create", target_id=gid, payload=group_obj.to_dict())
    ]
    return group_obj, gid, deltas


def _value_noise_2d(x: float, y: float, seed: int) -> float:
    """Smooth value noise in [0, 1] from integer lattice hashing."""

    def _hash(ix: int, iy: int) -> float:
        h = (ix * 374761393 + iy * 668265263 + seed * 1442695040) & 0xFFFFFFFF
        h = (h ^ (h >> 13)) * 1274126177 & 0xFFFFFFFF
        return ((h ^ (h >> 16)) & 0xFFFFFFFF) / 0xFFFFFFFF

    x0, y0 = math.floor(x), math.floor(y)
    x1, y1 = x0 + 1, y0 + 1
    sx = x - x0
    sy = y - y0
    fx = sx * sx * (3 - 2 * sx)
    fy = sy * sy * (3 - 2 * sy)
    n00 = _hash(x0, y0)
    n10 = _hash(x1, y0)
    n01 = _hash(x0, y1)
    n11 = _hash(x1, y1)
    nx0 = n00 * (1 - fx) + n10 * fx
    nx1 = n01 * (1 - fx) + n11 * fx
    return nx0 * (1 - fy) + nx1 * fy


def _fbm_noise(x: float, y: float, octaves: int, seed: int) -> float:
    """Fractal Brownian motion noise summing multiple octaves."""
    total = 0.0
    amplitude = 1.0
    frequency = 1.0
    max_value = 0.0
    for _ in range(octaves):
        total += _value_noise_2d(x * frequency, y * frequency, seed) * amplitude
        max_value += amplitude
        amplitude *= 0.5
        frequency *= 2.0
    return total / max_value if max_value > 0 else 0.0


def _sample_noise(noise_type: str, x: float, y: float, seed: int) -> float:
    """Sample normalized noise in [0, 1] for the requested noise type."""
    base = _fbm_noise(x, y, 4, seed)
    if noise_type == "perlin":
        return max(0.0, min(1.0, base))
    if noise_type == "ridge":
        # Ridge noise: sharp crests from 1 - |2n - 1|, squared for contrast.
        r = 1.0 - abs(2.0 * base - 1.0)
        return max(0.0, min(1.0, r * r))
    if noise_type == "valley":
        # Valley noise: emphasize low areas via abs(noise) shaping.
        v = abs(2.0 * base - 1.0)
        return max(0.0, min(1.0, v))
    return max(0.0, min(1.0, base))


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

class ScatterObjectsTool(ToolBase):
    """Scatter N copies of a source object randomly within a region."""

    name = "scatter_objects"
    description = (
        "Create N copies of a source object scattered randomly within a "
        "box, sphere, or plane region. Each copy can receive random "
        "rotation and scale jitter. Useful for populating forests, "
        "crowds, debris fields, or scattered props."
    )
    category = "creation"
    requires_approval = False

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "source": {"type": "string", "description": "Name or id of the object to copy"},
                "count": {"type": "integer", "default": 10, "description": "Number of copies to create"},
                "region_type": {
                    "type": "string",
                    "enum": ["box", "sphere", "plane"],
                    "default": "box",
                    "description": "Shape of the scatter region",
                },
                "center": {
                    "type": "array",
                    "items": {"type": "number"},
                    "default": [0.0, 0.0, 0.0],
                    "description": "Center of the scatter region",
                },
                "size": {"type": "number", "default": 5.0, "description": "Size of the region (edge length / radius)"},
                "random_rotation": {"type": "boolean", "default": True, "description": "Apply random Y-axis rotation"},
                "random_scale_min": {"type": "number", "default": 0.8, "description": "Minimum random scale factor"},
                "random_scale_max": {"type": "number", "default": 1.2, "description": "Maximum random scale factor"},
                "seed": {"type": "integer", "default": 0, "description": "Random seed (0 = non-deterministic)"},
            },
            "required": ["source"],
        }

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        source_id = str(arguments.get("source", "")).strip()
        source = scene.find_object(source_id)
        if not source:
            return ToolResult(success=False, message=f"Source object not found: {source_id}")

        count = max(1, min(200, int(arguments.get("count", 10))))
        region_type = str(arguments.get("region_type", "box"))
        center = [float(v) for v in arguments.get("center", [0.0, 0.0, 0.0])]
        size = max(0.01, float(arguments.get("size", 5.0)))
        random_rotation = bool(arguments.get("random_rotation", True))
        s_min = float(arguments.get("random_scale_min", 0.8))
        s_max = float(arguments.get("random_scale_max", 1.2))
        if s_min > s_max:
            s_min, s_max = s_max, s_min
        seed = int(arguments.get("seed", 0))
        rng = random.Random(seed if seed != 0 else None)

        group_obj, gid, deltas = _make_group(scene, f"{source.name}_Scatter", "scatter")

        half = size * 0.5
        created = 0
        for i in range(count):
            # Sample a position within the chosen region.
            if region_type == "sphere":
                # Uniform point inside a sphere of radius `half`.
                u = rng.random()
                r = half * (u ** (1.0 / 3.0))
                theta = rng.uniform(0.0, 2.0 * math.pi)
                phi = math.acos(2.0 * rng.random() - 1.0)
                px = center[0] + r * math.sin(phi) * math.cos(theta)
                py = center[1] + r * math.sin(phi) * math.sin(theta)
                pz = center[2] + r * math.cos(phi)
            elif region_type == "plane":
                px = center[0] + rng.uniform(-half, half)
                py = center[1]
                pz = center[2] + rng.uniform(-half, half)
            else:  # box
                px = center[0] + rng.uniform(-half, half)
                py = center[1] + rng.uniform(-half, half)
                pz = center[2] + rng.uniform(-half, half)

            # Deep-copy the source so geometry / material are independent.
            new_obj = SceneObject.from_dict(copy.deepcopy(source.to_dict()))
            new_obj.id = f"obj_{__import__('uuid').uuid4().hex[:8]}"
            new_obj.name = scene.next_auto_name(source.name)
            new_obj.group_id = gid
            new_obj.transform.position = [px, py, pz]
            if random_rotation:
                new_obj.transform.rotation = [
                    source.transform.rotation[0],
                    rng.uniform(0.0, 2.0 * math.pi),
                    source.transform.rotation[2],
                ]
            s = rng.uniform(s_min, s_max)
            base = source.transform.scale
            new_obj.transform.scale = [base[0] * s, base[1] * s, base[2] * s]
            scene.objects.append(new_obj)
            group_obj.child_ids.append(new_obj.id)
            deltas.append(SceneDelta(action="create", target_id=new_obj.id, payload=new_obj.to_dict()))
            created += 1

        return ToolResult(
            success=True,
            message=f"Scattered {created} copies of '{source.name}' in a {region_type} region within group '{group_obj.name}'.",
            deltas=deltas,
            data={"group_id": gid, "count": created, "group_name": group_obj.name, "region_type": region_type},
        )


class CreateStaircaseTool(ToolBase):
    """Create a staircase with N steps in straight, spiral, or L-shaped style."""

    name = "create_staircase"
    description = (
        "Build a staircase with a configurable number of steps. Supports "
        "straight runs, spiraling towers, and L-shaped landings. Each "
        "step is a box primitive grouped so the whole staircase can be "
        "transformed as one unit."
    )
    category = "creation"
    requires_approval = False

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "steps": {"type": "integer", "default": 10, "description": "Number of steps"},
                "width": {"type": "number", "default": 1.5, "description": "Step width"},
                "height": {"type": "number", "default": 0.2, "description": "Riser height per step"},
                "depth": {"type": "number", "default": 0.3, "description": "Tread depth per step"},
                "style": {
                    "type": "string",
                    "enum": ["straight", "spiral", "L-shaped"],
                    "default": "straight",
                    "description": "Staircase layout style",
                },
                "material_preset": {"type": "string", "default": "marble", "description": "Material preset name"},
                "center": {
                    "type": "array",
                    "items": {"type": "number"},
                    "default": [0.0, 0.0, 0.0],
                    "description": "Base center of the staircase",
                },
            },
        }

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        steps = max(1, min(80, int(arguments.get("steps", 10))))
        width = max(0.1, float(arguments.get("width", 1.5)))
        height = max(0.02, float(arguments.get("height", 0.2)))
        depth = max(0.05, float(arguments.get("depth", 0.3)))
        style = str(arguments.get("style", "straight"))
        material_preset = str(arguments.get("material_preset", "marble"))
        center = [float(v) for v in arguments.get("center", [0.0, 0.0, 0.0])]
        color, metalness, roughness = _resolve_material(material_preset)

        group_obj, gid, deltas = _make_group(scene, f"Staircase_{style}", "stair")

        step_height = height
        step_depth = depth
        geo_params = {"width": width, "height": step_height, "depth": step_depth}

        if style == "spiral":
            # Spiral staircase: steps rotate around the center axis while rising.
            radius = max(width * 0.6, step_depth * 1.5)
            angle_step = (2.0 * math.pi) / max(8, steps) * 1.2
            for i in range(steps):
                angle = i * angle_step
                y = center[1] + (i + 0.5) * step_height
                px = center[0] + math.cos(angle) * radius
                pz = center[2] + math.sin(angle) * radius
                obj, d = _add_object(
                    scene,
                    f"Step_{i:02d}",
                    "box",
                    geo_params,
                    position=[px, y, pz],
                    rotation=[0.0, -angle, 0.0],
                    color=color,
                    group_id=gid,
                    metalness=metalness,
                    roughness=roughness,
                )
                group_obj.child_ids.append(obj.id)
                deltas.append(d)
        elif style == "L-shaped":
            # L-shaped: first half runs along +X, second half runs along +Z
            # after a landing turn, forming an L footprint.
            half_steps = steps // 2
            for i in range(steps):
                if i < half_steps:
                    # Run along +X
                    run_idx = i
                    px = center[0] + run_idx * step_depth
                    pz = center[2]
                    rot_y = 0.0
                else:
                    # Run along +Z, offset by the first run length
                    run_idx = i - half_steps
                    px = center[0] + (half_steps - 1) * step_depth
                    pz = center[2] + (run_idx + 1) * step_depth
                    rot_y = math.pi / 2.0
                y = center[1] + (i + 0.5) * step_height
                obj, d = _add_object(
                    scene,
                    f"Step_{i:02d}",
                    "box",
                    geo_params,
                    position=[px, y, pz],
                    rotation=[0.0, rot_y, 0.0],
                    color=color,
                    group_id=gid,
                    metalness=metalness,
                    roughness=roughness,
                )
                group_obj.child_ids.append(obj.id)
                deltas.append(d)
        else:
            # Straight run: steps advance along +X while rising along +Y.
            total_depth = (steps - 1) * step_depth
            for i in range(steps):
                px = center[0] + i * step_depth - total_depth * 0.5
                y = center[1] + (i + 0.5) * step_height
                obj, d = _add_object(
                    scene,
                    f"Step_{i:02d}",
                    "box",
                    geo_params,
                    position=[px, y, center[2]],
                    color=color,
                    group_id=gid,
                    metalness=metalness,
                    roughness=roughness,
                )
                group_obj.child_ids.append(obj.id)
                deltas.append(d)

        return ToolResult(
            success=True,
            message=f"Created {style} staircase with {steps} steps in group '{group_obj.name}'.",
            deltas=deltas,
            data={"group_id": gid, "group_name": group_obj.name, "steps": steps, "style": style},
        )


class CreateBridgeTool(ToolBase):
    """Create a bridge structure with deck, railings, and supports."""

    name = "create_bridge"
    description = (
        "Build a bridge spanning a gap. The structure includes a flat "
        "deck, two side railings, and evenly spaced support pillars. "
        "An optional arch curves beneath the deck for an arched bridge "
        "silhouette. Output is grouped for unified transformation."
    )
    category = "creation"
    requires_approval = False

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "length": {"type": "number", "default": 10.0, "description": "Span length along X"},
                "width": {"type": "number", "default": 2.0, "description": "Deck width along Z"},
                "arch": {"type": "boolean", "default": False, "description": "Add an arch beneath the deck"},
                "num_supports": {"type": "integer", "default": 3, "description": "Number of support pillars"},
                "material_preset": {"type": "string", "default": "wood", "description": "Material preset name"},
                "position": {
                    "type": "array",
                    "items": {"type": "number"},
                    "default": [0.0, 0.0, 0.0],
                    "description": "Center position of the bridge",
                },
            },
        }

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        length = max(1.0, float(arguments.get("length", 10.0)))
        width = max(0.5, float(arguments.get("width", 2.0)))
        arch = bool(arguments.get("arch", False))
        num_supports = max(0, min(12, int(arguments.get("num_supports", 3))))
        material_preset = str(arguments.get("material_preset", "wood"))
        position = [float(v) for v in arguments.get("position", [0.0, 0.0, 0.0])]
        color, metalness, roughness = _resolve_material(material_preset)

        group_obj, gid, deltas = _make_group(scene, "Bridge", "bridge")

        deck_thickness = max(0.1, width * 0.08)
        deck_y = position[1]
        half_len = length * 0.5
        half_w = width * 0.5

        # Deck
        deck, d = _add_object(
            scene,
            "Bridge_Deck",
            "box",
            {"width": length, "height": deck_thickness, "depth": width},
            position=[position[0], deck_y, position[2]],
            color=color,
            group_id=gid,
            metalness=metalness,
            roughness=roughness,
        )
        group_obj.child_ids.append(deck.id)
        deltas.append(d)

        # Railings — two thin boxes along the deck edges
        rail_height = max(0.2, width * 0.25)
        rail_thickness = max(0.05, width * 0.05)
        rail_y = deck_y + deck_thickness * 0.5 + rail_height * 0.5
        for side, z_off in (("N", half_w - rail_thickness * 0.5), ("S", -half_w + rail_thickness * 0.5)):
            rail, rd = _add_object(
                scene,
                f"Bridge_Rail_{side}",
                "box",
                {"width": length, "height": rail_height, "depth": rail_thickness},
                position=[position[0], rail_y, position[2] + z_off],
                color=color,
                group_id=gid,
                metalness=metalness,
                roughness=roughness,
            )
            group_obj.child_ids.append(rail.id)
            deltas.append(rd)

        # Support pillars — vertical boxes evenly spaced along the span
        support_h = max(0.5, length * 0.25)
        support_w = max(0.1, width * 0.1)
        support_y = deck_y - deck_thickness * 0.5 - support_h * 0.5
        if num_supports > 0:
            if num_supports == 1:
                xs = [position[0]]
            else:
                spacing = length / (num_supports - 1)
                xs = [position[0] - half_len + i * spacing for i in range(num_supports)]
            for i, sx in enumerate(xs):
                sup, sd = _add_object(
                    scene,
                    f"Bridge_Support_{i:02d}",
                    "box",
                    {"width": support_w, "height": support_h, "depth": width * 0.6},
                    position=[sx, support_y, position[2]],
                    color=color,
                    group_id=gid,
                    metalness=metalness,
                    roughness=roughness,
                )
                group_obj.child_ids.append(sup.id)
                deltas.append(sd)

        # Optional arch — a torus segment curving beneath the deck
        if arch:
            arch_radius = half_len
            arch_tube = max(0.05, width * 0.06)
            arch_y = deck_y - deck_thickness * 0.5 - arch_tube
            arch_obj, ad = _add_object(
                scene,
                "Bridge_Arch",
                "torus",
                {
                    "radius": arch_radius,
                    "tube": arch_tube,
                    "radialSegments": 10,
                    "tubularSegments": 64,
                    "arc": math.pi,
                },
                position=[position[0], arch_y, position[2]],
                rotation=[0.0, 0.0, 0.0],
                color=color,
                group_id=gid,
                metalness=metalness,
                roughness=roughness,
            )
            group_obj.child_ids.append(arch_obj.id)
            deltas.append(ad)

        part_count = 1 + 2 + num_supports + (1 if arch else 0)
        return ToolResult(
            success=True,
            message=f"Created bridge (length {length}, width {width}) with {part_count} parts in group '{group_obj.name}'.",
            deltas=deltas,
            data={
                "group_id": gid,
                "group_name": group_obj.name,
                "length": length,
                "width": width,
                "arch": arch,
                "supports": num_supports,
            },
        )


class CreateTerrainTool(ToolBase):
    """Create a terrain mesh from procedural noise as a grouped height grid."""

    name = "create_terrain_mesh"
    description = (
        "Generate a terrain height mesh from procedural noise. The "
        "surface is built as a resolution-by-resolution grid of columns "
        "whose heights follow the selected noise type (perlin, ridge, or "
        "valley). Useful for landscapes, hills, and ground planes."
    )
    category = "creation"
    requires_approval = False

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "width": {"type": "number", "default": 20.0, "description": "Terrain width along X"},
                "depth": {"type": "number", "default": 20.0, "description": "Terrain depth along Z"},
                "resolution": {"type": "integer", "default": 24, "description": "Grid cells per side"},
                "height_scale": {"type": "number", "default": 2.0, "description": "Maximum height of the terrain"},
                "noise_type": {
                    "type": "string",
                    "enum": ["perlin", "ridge", "valley"],
                    "default": "perlin",
                    "description": "Noise shaping function",
                },
                "seed": {"type": "integer", "default": 1, "description": "Noise random seed"},
                "color": {"type": "string", "default": "#4a6a3a", "description": "Terrain color"},
            },
        }

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        width = max(2.0, min(120.0, float(arguments.get("width", 20.0))))
        depth = max(2.0, min(120.0, float(arguments.get("depth", 20.0))))
        resolution = max(4, min(80, int(arguments.get("resolution", 24))))
        height_scale = max(0.1, float(arguments.get("height_scale", 2.0)))
        noise_type = str(arguments.get("noise_type", "perlin"))
        seed = int(arguments.get("seed", 1))
        color = str(arguments.get("color", "#4a6a3a"))

        group_obj, gid, deltas = _make_group(scene, "Terrain", "terrain")

        cell_w = width / resolution
        cell_d = depth / resolution
        half_w = width * 0.5
        half_d = depth * 0.5

        for j in range(resolution):
            for i in range(resolution):
                # Sample noise in a normalized range for varied features.
                nx = (i / resolution) * 4.0
                ny = (j / resolution) * 4.0
                n = _sample_noise(noise_type, nx, ny, seed)
                h = max(0.05, n * height_scale)
                px = -half_w + (i + 0.5) * cell_w
                pz = -half_d + (j + 0.5) * cell_d
                obj, d = _add_object(
                    scene,
                    f"Terrain_{i}_{j}",
                    "box",
                    {"width": cell_w * 1.001, "height": h, "depth": cell_d * 1.001},
                    position=[px, h * 0.5, pz],
                    color=color,
                    group_id=gid,
                    roughness=0.85,
                    metalness=0.0,
                )
                group_obj.child_ids.append(obj.id)
                deltas.append(d)

        count = resolution * resolution
        return ToolResult(
            success=True,
            message=f"Created {noise_type} terrain mesh {width}x{depth} with {count} cells in group '{group_obj.name}'.",
            deltas=deltas,
            data={
                "group_id": gid,
                "group_name": group_obj.name,
                "count": count,
                "width": width,
                "depth": depth,
                "resolution": resolution,
                "noise_type": noise_type,
            },
        )


class CloneChainTool(ToolBase):
    """Create a chain of cloned objects distributed along a path."""

    name = "clone_chain"
    description = (
        "Clone a source object along a parametric path. Supports linear "
        "chains (straight line between two points), arcs (circular sweep "
        "around a center), and spirals (rising helix around a center). "
        "Output is grouped so the chain can be transformed as one unit."
    )
    category = "creation"
    requires_approval = False

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "source": {"type": "string", "description": "Name or id of the object to clone"},
                "path_type": {
                    "type": "string",
                    "enum": ["line", "arc", "spiral"],
                    "default": "line",
                    "description": "Path shape along which clones are placed",
                },
                "count": {"type": "integer", "default": 8, "description": "Number of clones in the chain"},
                "start_point": {
                    "type": "array",
                    "items": {"type": "number"},
                    "default": [-3.0, 0.0, 0.0],
                    "description": "Start point (used for line path)",
                },
                "end_point": {
                    "type": "array",
                    "items": {"type": "number"},
                    "default": [3.0, 0.0, 0.0],
                    "description": "End point (used for line path)",
                },
                "center": {
                    "type": "array",
                    "items": {"type": "number"},
                    "default": [0.0, 0.0, 0.0],
                    "description": "Center of the arc / spiral path",
                },
                "radius": {"type": "number", "default": 3.0, "description": "Radius of the arc / spiral path"},
                "height": {"type": "number", "default": 4.0, "description": "Total vertical rise of a spiral path"},
                "arc_angle": {"type": "number", "default": 6.2832, "description": "Sweep angle of the arc / spiral (radians)"},
            },
            "required": ["source"],
        }

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        source_id = str(arguments.get("source", "")).strip()
        source = scene.find_object(source_id)
        if not source:
            return ToolResult(success=False, message=f"Source object not found: {source_id}")

        path_type = str(arguments.get("path_type", "line"))
        count = max(1, min(200, int(arguments.get("count", 8))))
        start_point = [float(v) for v in arguments.get("start_point", [-3.0, 0.0, 0.0])]
        end_point = [float(v) for v in arguments.get("end_point", [3.0, 0.0, 0.0])]
        center = [float(v) for v in arguments.get("center", [0.0, 0.0, 0.0])]
        radius = max(0.01, float(arguments.get("radius", 3.0)))
        height = float(arguments.get("height", 4.0))
        arc_angle = float(arguments.get("arc_angle", 2.0 * math.pi))

        group_obj, gid, deltas = _make_group(scene, f"{source.name}_Chain", "chain")

        created = 0
        # For count==1 place at the path start; otherwise distribute evenly.
        segments = max(1, count - 1) if count > 1 else 1
        for i in range(count):
            t = i / segments if count > 1 else 0.0
            if path_type == "line":
                px = start_point[0] + (end_point[0] - start_point[0]) * t
                py = start_point[1] + (end_point[1] - start_point[1]) * t
                pz = start_point[2] + (end_point[2] - start_point[2]) * t
                rot_y = 0.0
            elif path_type == "arc":
                angle = -math.pi / 2.0 + arc_angle * t
                px = center[0] + math.cos(angle) * radius
                py = center[1]
                pz = center[2] + math.sin(angle) * radius
                # Orient clones tangentially along the arc.
                rot_y = angle + math.pi / 2.0
            else:  # spiral
                angle = arc_angle * t
                px = center[0] + math.cos(angle) * radius
                py = center[1] + height * t
                pz = center[2] + math.sin(angle) * radius
                rot_y = angle + math.pi / 2.0

            new_obj = SceneObject.from_dict(copy.deepcopy(source.to_dict()))
            new_obj.id = f"obj_{__import__('uuid').uuid4().hex[:8]}"
            new_obj.name = scene.next_auto_name(source.name)
            new_obj.group_id = gid
            new_obj.transform.position = [px, py, pz]
            new_obj.transform.rotation = [
                source.transform.rotation[0],
                rot_y,
                source.transform.rotation[2],
            ]
            scene.objects.append(new_obj)
            group_obj.child_ids.append(new_obj.id)
            deltas.append(SceneDelta(action="create", target_id=new_obj.id, payload=new_obj.to_dict()))
            created += 1

        return ToolResult(
            success=True,
            message=f"Cloned {created} copies of '{source.name}' along a {path_type} path in group '{group_obj.name}'.",
            deltas=deltas,
            data={
                "group_id": gid,
                "group_name": group_obj.name,
                "count": created,
                "path_type": path_type,
            },
        )
