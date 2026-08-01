"""Procedural generation tools.

Adds higher-order procedural geometry: noise-based terrain heightmaps,
parameterized L-system plant/tree generation, a spiral staircase direct
tool (mirroring the creative skill), and Voronoi-style object shattering.
Each tool emits standard scene deltas for incremental frontend updates.
"""

from __future__ import annotations

import math
import random
import uuid
from typing import Any, Dict, List, Optional

from trigen.scene import Scene, SceneObject
from trigen.tools.base import SceneDelta, ToolBase, ToolResult


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

_TERRAIN_PARAMS = {
    "type": "object",
    "properties": {
        "size": {"type": "number", "description": "Terrain side length (default 20)"},
        "resolution": {"type": "integer", "description": "Grid cells per side (default 24, max 60)", "minimum": 4, "maximum": 60},
        "height_scale": {"type": "number", "description": "Max height variation (default 2.0)"},
        "octaves": {"type": "integer", "description": "Noise octaves (default 4)", "minimum": 1, "maximum": 8},
        "seed": {"type": "integer", "description": "Random seed (default 1)"},
        "name": {"type": "string", "description": "Optional terrain object name"},
        "color": {"type": "string", "description": "Terrain base color (default #4a6a3a)"},
    },
    "required": [],
}

_LSYSTEM_PARAMS = {
    "type": "object",
    "properties": {
        "position": {
            "type": "array",
            "items": {"type": "number"},
            "description": "Base position [x, y, z] (default [0, 0, 0])",
        },
        "iterations": {"type": "integer", "description": "L-system iterations (default 3, max 5)", "minimum": 1, "maximum": 5},
        "branch_length": {"type": "number", "description": "Branch segment length (default 0.6)"},
        "branch_radius": {"type": "number", "description": "Trunk base radius (default 0.12)"},
        "angle": {"type": "number", "description": "Branch fork angle in radians (default 0.5)"},
        "season": {
            "type": "string",
            "enum": ["spring", "summer", "autumn", "winter"],
            "description": "Foliage color season (default summer)",
        },
        "seed": {"type": "integer", "description": "Random seed (default 11)"},
        "name": {"type": "string", "description": "Optional plant name prefix"},
    },
    "required": [],
}

_SPIRAL_STAIRCASE_PARAMS = {
    "type": "object",
    "properties": {
        "steps": {"type": "integer", "description": "Number of steps (default 16, max 60)", "minimum": 3, "maximum": 60},
        "radius": {"type": "number", "description": "Step radius from center (default 1.5)"},
        "height": {"type": "number", "description": "Total rise height (default 5)"},
        "step_depth": {"type": "number", "description": "Step depth (default 0.6)"},
        "material_preset": {
            "type": "string",
            "description": "Material preset for steps (default stone)",
        },
        "center": {
            "type": "array",
            "items": {"type": "number"},
            "description": "Center position [x, y, z] (default [0, 0, 0])",
        },
    },
    "required": [],
}

_SHATTER_PARAMS = {
    "type": "object",
    "properties": {
        "target": {"type": "string", "description": "Object id or name to shatter"},
        "fragments": {"type": "integer", "description": "Number of fragments (default 8, max 30)", "minimum": 2, "maximum": 30},
        "spread": {"type": "number", "description": "Outward spread distance (default 1.0)"},
        "delete_source": {"type": "boolean", "description": "Remove the source object after shattering (default true)"},
        "seed": {"type": "integer", "description": "Random seed (default 5)"},
    },
    "required": ["target"],
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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
    # Smoothstep interpolation
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


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

class TerrainGeneratorTool(ToolBase):
    """Generate a noise-based terrain heightmap as a grid of box cells."""

    name = "terrain_generator"
    description = "Generate a noise-based terrain heightmap as a grid of vertical box cells with smooth FBM noise."

    def schema(self) -> Dict[str, Any]:
        return _TERRAIN_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        size = max(2.0, min(80.0, float(arguments.get("size", 20.0))))
        resolution = max(4, min(60, int(arguments.get("resolution", 24))))
        height_scale = max(0.1, float(arguments.get("height_scale", 2.0)))
        octaves = max(1, min(8, int(arguments.get("octaves", 4))))
        seed = int(arguments.get("seed", 1))
        base_name = arguments.get("name") or "Terrain"
        color = str(arguments.get("color", "#4a6a3a"))

        cell = size / resolution
        half = size / 2.0
        deltas: List[SceneDelta] = []
        created: List[SceneObject] = []
        base_id = uuid.uuid4().hex[:6]

        for j in range(resolution):
            for i in range(resolution):
                # Sample noise in normalized [0, 4] range for varied features
                nx = (i / resolution) * 4.0
                ny = (j / resolution) * 4.0
                n = _fbm_noise(nx, ny, octaves, seed)
                h = max(0.05, n * height_scale)
                px = -half + (i + 0.5) * cell
                pz = -half + (j + 0.5) * cell
                obj = SceneObject(
                    name=f"{base_name}_{i}_{j}",
                    type="mesh",
                    geometry={"type": "box", "params": {"width": cell, "height": h, "depth": cell}},
                    material={"color": color},
                    transform={"position": [px, h / 2.0, pz], "rotation": [0, 0, 0], "scale": [1, 1, 1]},
                    tags=[f"terrain:{base_id}", f"row:{j}", f"col:{i}"],
                )
                scene.objects.append(obj)
                created.append(obj)
                deltas.append(SceneDelta(action="create", target_id=obj.id, payload=obj.to_dict()))

        return ToolResult(
            success=True,
            message=f"Generated terrain {size}x{size} with {len(created)} cells (height scale {height_scale})",
            deltas=deltas,
            data={"count": len(created), "size": size, "resolution": resolution, "height_scale": height_scale},
        )


class LSystemTool(ToolBase):
    """Generate a parameterized plant or tree via a branching L-system."""

    name = "l_system"
    description = "Generate a parameterized plant or tree by expanding a branching L-system into trunk and foliage segments."

    def schema(self) -> Dict[str, Any]:
        return _LSYSTEM_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        position = arguments.get("position", [0, 0, 0])
        if not isinstance(position, list) or len(position) != 3:
            position = [0.0, 0.0, 0.0]
        position = [float(position[0]), float(position[1]), float(position[2])]

        iterations = max(1, min(5, int(arguments.get("iterations", 3))))
        branch_length = max(0.1, float(arguments.get("branch_length", 0.6)))
        base_radius = max(0.02, float(arguments.get("branch_radius", 0.12)))
        fork_angle = float(arguments.get("angle", 0.5))
        season = str(arguments.get("season", "summer"))
        seed = int(arguments.get("seed", 11))
        name_prefix = arguments.get("name") or "Plant"
        rng = random.Random(seed)

        season_colors = {
            "spring": "#7acc5a",
            "summer": "#2d8a3e",
            "autumn": "#d97520",
            "winter": "#c8d8e0",
        }
        foliage_color = season_colors.get(season, "#2d8a3e")

        # L-system rules: F = forward branch, [ ] = push/pop state, + - = rotate
        axiom = "F"
        rules = {"F": "FF+[+F-F-F]-[-F+F+F]"}
        sentence = axiom
        for _ in range(iterations):
            new_sentence = []
            for ch in sentence:
                new_sentence.append(rules.get(ch, ch))
            sentence = "".join(new_sentence)
            if len(sentence) > 8000:
                break  # Safety cap

        # Walk the L-system string to build branches
        deltas: List[SceneDelta] = []
        created: List[SceneObject] = []
        # State: position, heading (yaw), pitch, current radius, depth
        state_stack: List[List[Any]] = []
        x, y, z = position
        yaw = 0.0
        pitch = 0.0
        radius = base_radius
        depth = 0
        seg_idx = 0

        for ch in sentence:
            if ch == "F":
                # Compute segment end position
                cy = math.cos(pitch)
                dx = math.sin(yaw) * cy
                dy = math.sin(pitch)
                dz = math.cos(yaw) * cy
                ex = x + dx * branch_length
                ey = y + dy * branch_length
                ez = z + dz * branch_length
                mid = [(x + ex) / 2.0, (y + ey) / 2.0, (z + ez) / 2.0]
                # Branch as a thin cylinder oriented along its direction
                seg = SceneObject(
                    name=f"{name_prefix}_Branch_{seg_idx}",
                    type="mesh",
                    geometry={"type": "cylinder", "params": {"radiusTop": max(0.01, radius * 0.7), "radiusBottom": max(0.01, radius), "height": branch_length, "radialSegments": 6}},
                    material={"color": "#5a3a1a"},
                    transform={"position": mid, "rotation": [pitch, yaw, 0], "scale": [1, 1, 1]},
                    tags=[f"plant:{name_prefix}", "branch"],
                )
                scene.objects.append(seg)
                created.append(seg)
                deltas.append(SceneDelta(action="create", target_id=seg.id, payload=seg.to_dict()))
                # Foliage sphere at the tip for thinner branches
                if radius < base_radius * 0.5 and rng.random() < 0.4:
                    foliage = SceneObject(
                        name=f"{name_prefix}_Leaf_{seg_idx}",
                        type="mesh",
                        geometry={"type": "sphere", "params": {"radius": max(0.08, branch_length * 0.6), "widthSegments": 8, "heightSegments": 6}},
                        material={"color": foliage_color},
                        transform={"position": [ex, ey, ez], "rotation": [0, 0, 0], "scale": [1, 1, 1]},
                        tags=[f"plant:{name_prefix}", "foliage"],
                    )
                    scene.objects.append(foliage)
                    created.append(foliage)
                    deltas.append(SceneDelta(action="create", target_id=foliage.id, payload=foliage.to_dict()))
                x, y, z = ex, ey, ez
                radius *= 0.85
                seg_idx += 1
            elif ch == "+":
                yaw += fork_angle + rng.uniform(-0.1, 0.1)
            elif ch == "-":
                yaw -= fork_angle + rng.uniform(-0.1, 0.1)
            elif ch == "[":
                state_stack.append([x, y, z, yaw, pitch, radius, depth])
                depth += 1
            elif ch == "]":
                if state_stack:
                    x, y, z, yaw, pitch, radius, depth = state_stack.pop()

        return ToolResult(
            success=True,
            message=f"Generated L-system plant with {len(created)} segments (iterations={iterations})",
            deltas=deltas,
            data={"count": len(created), "iterations": iterations, "season": season},
        )


class SpiralStaircaseTool(ToolBase):
    """Build a spiral staircase as a single direct tool call.

    Mirrors the SpiralStaircaseSkill but is invokable as a regular tool —
    useful when the LLM emits a single create_staircase call rather than
    expanding the skill into a multi-step plan.
    """

    name = "create_spiral_staircase"
    description = "Build a spiral staircase with a central pillar and evenly spaced steps spiraling upward."

    def schema(self) -> Dict[str, Any]:
        return _SPIRAL_STAIRCASE_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        steps_count = max(3, min(60, int(arguments.get("steps", 16))))
        radius = float(arguments.get("radius", 1.5))
        total_height = float(arguments.get("height", 5))
        step_depth = float(arguments.get("step_depth", 0.6))
        center = arguments.get("center", [0, 0, 0])
        if not isinstance(center, list) or len(center) != 3:
            center = [0.0, 0.0, 0.0]
        cx, cy, cz = float(center[0]), float(center[1]), float(center[2])

        rise = total_height / steps_count
        deltas: List[SceneDelta] = []
        created: List[SceneObject] = []
        batch = uuid.uuid4().hex[:6]

        # Central pillar
        pillar = SceneObject(
            name=f"Staircase_Pillar_{batch}",
            type="mesh",
            geometry={"type": "cylinder", "params": {"radiusTop": 0.3, "radiusBottom": 0.3, "height": total_height, "radialSegments": 12}},
            material={"color": "#e8e6e0", "metalness": 0.1, "roughness": 0.2},
            transform={"position": [cx, cy + total_height / 2.0, cz], "rotation": [0, 0, 0], "scale": [1, 1, 1]},
            tags=[f"staircase:{batch}", "pillar"],
        )
        scene.objects.append(pillar)
        created.append(pillar)
        deltas.append(SceneDelta(action="create", target_id=pillar.id, payload=pillar.to_dict()))

        for i in range(steps_count):
            angle = (i / steps_count) * math.pi * 2 * (steps_count / 8.0)
            y = cy + i * rise + rise / 2.0
            x = cx + math.cos(angle) * radius * 0.5
            z = cz + math.sin(angle) * radius * 0.5
            step = SceneObject(
                name=f"Staircase_Step_{batch}_{i + 1}",
                type="mesh",
                geometry={"type": "box", "params": {"width": radius, "height": 0.08, "depth": step_depth}},
                material={"color": "#9aa3ad", "metalness": 0.0, "roughness": 0.6},
                transform={"position": [x, y, z], "rotation": [0, angle, 0], "scale": [1, 1, 1]},
                tags=[f"staircase:{batch}", "step"],
            )
            scene.objects.append(step)
            created.append(step)
            deltas.append(SceneDelta(action="create", target_id=step.id, payload=step.to_dict()))

        return ToolResult(
            success=True,
            message=f"Built spiral staircase with {steps_count} steps (height {total_height})",
            deltas=deltas,
            data={"count": len(created), "steps": steps_count, "height": total_height},
        )


class VoronoiShatterTool(ToolBase):
    """Shatter an object into fragment cells using a Voronoi-like partition."""

    name = "voronoi_shatter"
    description = "Shatter an object into N fragments by generating random Voronoi cell sites and creating smaller box fragments inside the source bounding box."

    def schema(self) -> Dict[str, Any]:
        return _SHATTER_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        target_id = arguments.get("target", "")
        src = scene.find_object(target_id)
        if not src:
            return ToolResult(success=False, message=f"Object not found: {target_id}")

        fragment_count = max(2, min(30, int(arguments.get("fragments", 8))))
        spread = float(arguments.get("spread", 1.0))
        delete_source = bool(arguments.get("delete_source", True))
        seed = int(arguments.get("seed", 5))
        rng = random.Random(seed)

        # Source bbox (reuse the composite_tools helper logic inline)
        g = src.geometry
        p = g.params or {}
        t = g.type
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
        sx, sy, sz = src.transform.scale
        px, py, pz = src.transform.position
        ext = [hx * sx, hy * sy, hz * sz]

        # Generate random Voronoi sites inside the bbox
        sites = []
        for _ in range(fragment_count):
            sxp = px + rng.uniform(-ext[0], ext[0])
            syp = py + rng.uniform(-ext[1], ext[1])
            szp = pz + rng.uniform(-ext[2], ext[2])
            sites.append((sxp, syp, szp))

        # Each fragment occupies a sub-region around its site. For visual
        # effect, we create one small box per site, displaced outward.
        deltas: List[SceneDelta] = []
        created: List[SceneObject] = []
        batch = uuid.uuid4().hex[:6]
        for i, (sxp, syp, szp) in enumerate(sites):
            # Push fragment slightly outward from the source center
            dx = sxp - px
            dy = syp - py
            dz = szp - pz
            length = math.sqrt(dx * dx + dy * dy + dz * dz) or 1.0
            push = spread * 0.3
            fx = sxp + (dx / length) * push + rng.uniform(-spread * 0.1, spread * 0.1)
            fy = syp + (dy / length) * push + rng.uniform(-spread * 0.1, spread * 0.1)
            fz = szp + (dz / length) * push + rng.uniform(-spread * 0.1, spread * 0.1)
            frag_size = [
                max(0.05, (ext[0] * 2) / math.sqrt(fragment_count) * rng.uniform(0.6, 1.0)),
                max(0.05, (ext[1] * 2) / math.sqrt(fragment_count) * rng.uniform(0.6, 1.0)),
                max(0.05, (ext[2] * 2) / math.sqrt(fragment_count) * rng.uniform(0.6, 1.0)),
            ]
            frag = SceneObject(
                name=f"{src.name}_Frag_{i + 1}",
                type="mesh",
                geometry={"type": "box", "params": {"width": frag_size[0], "height": frag_size[1], "depth": frag_size[2]}},
                material=src.material.to_dict(),
                transform={"position": [fx, fy, fz], "rotation": [rng.uniform(-0.4, 0.4), rng.uniform(-0.4, 0.4), rng.uniform(-0.4, 0.4)], "scale": [1, 1, 1]},
                tags=[f"shatter:{batch}", f"src:{src.id}", f"frag:{i + 1}"],
            )
            scene.objects.append(frag)
            created.append(frag)
            deltas.append(SceneDelta(action="create", target_id=frag.id, payload=frag.to_dict()))

        if delete_source:
            if src in scene.objects:
                scene.objects.remove(src)
                deltas.append(SceneDelta(action="delete", target_id=src.id))

        return ToolResult(
            success=True,
            message=f"Shattered {src.name} into {len(created)} fragments",
            deltas=deltas,
            data={"count": len(created), "source": src.name, "source_deleted": delete_source},
        )
