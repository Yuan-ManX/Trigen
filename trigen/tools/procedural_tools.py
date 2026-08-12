"""Procedural generation tools.

Adds higher-order procedural geometry: noise-based terrain heightmaps,
parameterized L-system plant/tree generation, a spiral staircase direct
tool (mirroring the creative skill), and Voronoi object shattering.
Each tool emits standard scene deltas for incremental frontend updates.
"""

from __future__ import annotations

import math
import random
import uuid
from typing import Any, Dict, List, Optional

from trigen.scene import Geometry, Material, Scene, SceneObject, Transform
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
                    geometry=Geometry(type="box", params={"width": cell, "height": h, "depth": cell}),
                    material=Material(color=color),
                    transform=Transform(
                        position=[px, h / 2.0, pz],
                        rotation=[0.0, 0.0, 0.0],
                        scale=[1.0, 1.0, 1.0],
                    ),
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
                    geometry=Geometry(
                        type="cylinder",
                        params={"radiusTop": max(0.01, radius * 0.7), "radiusBottom": max(0.01, radius), "height": branch_length, "radialSegments": 6},
                    ),
                    material=Material(color="#5a3a1a"),
                    transform=Transform(
                        position=mid,
                        rotation=[pitch, yaw, 0.0],
                        scale=[1.0, 1.0, 1.0],
                    ),
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
                        geometry=Geometry(
                            type="sphere",
                            params={"radius": max(0.08, branch_length * 0.6), "widthSegments": 8, "heightSegments": 6},
                        ),
                        material=Material(color=foliage_color),
                        transform=Transform(
                            position=[ex, ey, ez],
                            rotation=[0.0, 0.0, 0.0],
                            scale=[1.0, 1.0, 1.0],
                        ),
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
            geometry=Geometry(
                type="cylinder",
                params={"radiusTop": 0.3, "radiusBottom": 0.3, "height": total_height, "radialSegments": 12},
            ),
            material=Material(color="#e8e6e0", metalness=0.1, roughness=0.2),
            transform=Transform(
                position=[cx, cy + total_height / 2.0, cz],
                rotation=[0.0, 0.0, 0.0],
                scale=[1.0, 1.0, 1.0],
            ),
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
                geometry=Geometry(type="box", params={"width": radius, "height": 0.08, "depth": step_depth}),
                material=Material(color="#9aa3ad", metalness=0.0, roughness=0.6),
                transform=Transform(
                    position=[x, y, z],
                    rotation=[0.0, angle, 0.0],
                    scale=[1.0, 1.0, 1.0],
                ),
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
    requires_approval = True  # Destructive: replaces one object with many fragments

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
            # Reuse the source material so fragments inherit its look.
            _m = src.material.to_dict()
            frag = SceneObject(
                name=f"{src.name}_Frag_{i + 1}",
                type="mesh",
                geometry=Geometry(type="box", params={"width": frag_size[0], "height": frag_size[1], "depth": frag_size[2]}),
                material=Material(**_m),
                transform=Transform(
                    position=[fx, fy, fz],
                    rotation=[rng.uniform(-0.4, 0.4), rng.uniform(-0.4, 0.4), rng.uniform(-0.4, 0.4)],
                    scale=[1.0, 1.0, 1.0],
                ),
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


# ---------------------------------------------------------------------------
# Geodesic dome — icosahedron subdivision projected to a spherical lattice.
# ---------------------------------------------------------------------------

_DOME_PARAMS = {
    "type": "object",
    "properties": {
        "radius": {"type": "number", "description": "Dome radius in world units (default 3.0)"},
        "detail": {
            "type": "integer",
            "description": "Subdivision depth 0-2 (default 1). Higher depth produces a denser, smoother lattice.",
            "minimum": 0,
            "maximum": 2,
        },
        "joint_radius": {"type": "number", "description": "Radius of the joint spheres (default 0.09)"},
        "strut_radius": {"type": "number", "description": "Radius of the connecting struts (default 0.03)"},
        "dome": {
            "type": "boolean",
            "description": "Keep only the upper half-sphere as an open bowl (default false -> full sphere)",
        },
        "color": {"type": "string", "description": "Strut and joint color (default #dfe6ff)"},
        "position": {
            "type": "array",
            "items": {"type": "number"},
            "description": "Base position [x, y, z] (default [0, 0, 0])",
        },
        "name": {"type": "string", "description": "Optional name prefix"},
    },
    "required": [],
}


# Unit icosahedron: 12 vertices + 20 triangular faces. Vertices are projected
# to the unit sphere before any subdivision, giving a convex hull of roughly
# equal spherical triangles from which the dome lattice is derived.
_ICOSA_PHI = (1.0 + math.sqrt(5.0)) / 2.0
_ICOSA_VERTICES = [
    (-1.0, _ICOSA_PHI, 0.0),
    (1.0, _ICOSA_PHI, 0.0),
    (-1.0, -_ICOSA_PHI, 0.0),
    (1.0, -_ICOSA_PHI, 0.0),
    (0.0, -1.0, _ICOSA_PHI),
    (0.0, 1.0, _ICOSA_PHI),
    (0.0, -1.0, -_ICOSA_PHI),
    (0.0, 1.0, -_ICOSA_PHI),
    (_ICOSA_PHI, 0.0, -1.0),
    (_ICOSA_PHI, 0.0, 1.0),
    (-_ICOSA_PHI, 0.0, -1.0),
    (-_ICOSA_PHI, 0.0, 1.0),
]
_ICOSA_FACES = [
    (0, 11, 5),
    (0, 5, 1),
    (0, 1, 7),
    (0, 7, 10),
    (0, 10, 11),
    (1, 5, 9),
    (5, 11, 4),
    (11, 10, 2),
    (10, 7, 6),
    (7, 1, 8),
    (3, 9, 4),
    (3, 4, 2),
    (3, 2, 6),
    (3, 6, 8),
    (3, 8, 9),
    (4, 9, 5),
    (2, 4, 11),
    (6, 2, 10),
    (8, 6, 7),
    (9, 8, 1),
]


def _normalize3(v: List[float]) -> List[float]:
    """Return ``v`` scaled to unit length (identity when already near-zero)."""
    length = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])
    if length < 1e-9:
        return [0.0, 0.0, 0.0]
    return [v[0] / length, v[1] / length, v[2] / length]


def _icosphere(detail: int) -> tuple:
    """Return ``(verts, faces)`` of an icosphere at the given subdivision depth.

    Edge-midpoint subdivision turns each face into four, sharing a cached
    midpoint per edge so the mesh stays connected (watertight). Every vertex is
    renormalized to the unit sphere after each level.
    """
    verts: List[List[float]] = [list(v) for v in _ICOSA_VERTICES]
    faces: List[List[int]] = [list(f) for f in _ICOSA_FACES]
    for _ in range(detail):
        midpoint_cache: Dict[Any, int] = {}
        new_faces: List[List[int]] = []
        for (a, b, c) in faces:
            ab = _subdiv_midpoint(a, b, verts, midpoint_cache)
            bc = _subdiv_midpoint(b, c, verts, midpoint_cache)
            ca = _subdiv_midpoint(c, a, verts, midpoint_cache)
            new_faces.append([a, ab, ca])
            new_faces.append([b, bc, ab])
            new_faces.append([c, ca, bc])
            new_faces.append([ab, bc, ca])
        faces = new_faces
    return verts, faces


def _subdiv_midpoint(a: int, b: int, verts: List[List[float]], cache: Dict[Any, int]) -> int:
    """Return the index of the (renormalized) midpoint of vertices ``a`` and ``b``.

    A stable unordered key reuses the same vertex for every face sharing the
    edge, keeping the subdivided mesh watertight.
    """
    key = (a, b) if a < b else (b, a)
    if key in cache:
        return cache[key]
    va, vb = verts[a], verts[b]
    mid = _normalize3([(va[0] + vb[0]) * 0.5, (va[1] + vb[1]) * 0.5, (va[2] + vb[2]) * 0.5])
    idx = len(verts)
    verts.append(mid)
    cache[key] = idx
    return idx


def _euler_align_y(dx: float, dy: float, dz: float) -> List[float]:
    """Return XYZ Euler angles (radians) rotating +Y onto the unit direction ``d``.

    Derived for the renderer's default Euler order (XYZ). With ``ry = 0`` the
    rotation column for +Y becomes ``(dx, dy, dz)`` exactly:
      rz = asin(-dx), rx = atan2(dz, dy), guarded for axis-aligned directions.
    """
    if abs(dx) < 1e-9 and abs(dz) < 1e-9:
        # Pure vertical direction: rx 0 or pi flips the strut in place.
        return [0.0 if dy > 0 else math.pi, 0.0, 0.0]
    rz = math.asin(max(-1.0, min(1.0, -dx)))
    c3 = math.cos(rz)
    if abs(c3) < 1e-9:
        rx = 0.0
    else:
        rx = math.atan2(dz, dy)
    return [rx, 0.0, rz]


class GeodesicDomeTool(ToolBase):
    """Generate a geodesic dome: a spherical lattice of joint spheres and struts.

    Builds the structure from an icosahedron subdivided to the requested depth,
    projects every vertex onto a sphere of the given radius, then places a
    joint sphere at each vertex and an oriented strut cylinder along every edge.
    All members share a generation tag so they can be selected, animated, and
    exported as a unit.
    """

    name = "create_geodesic_dome"
    description = (
        "Create a geodesic dome: a spherical lattice of joint spheres connected "
        "by strut cylinders, built from an icosahedron subdivided to the chosen "
        "depth. Great for architectural frames, planetarium shells, and sci-fi "
        "structure studies."
    )

    def schema(self) -> Dict[str, Any]:
        return _DOME_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        radius = max(0.5, float(arguments.get("radius", 3.0)))
        detail = max(0, min(2, int(arguments.get("detail", 1))))
        joint_radius = max(0.01, float(arguments.get("joint_radius", 0.09)))
        strut_radius = max(0.005, float(arguments.get("strut_radius", 0.03)))
        dome_only = bool(arguments.get("dome", False))
        color = str(arguments.get("color", "#dfe6ff"))
        position = arguments.get("position", [0, 0, 0])
        if not isinstance(position, list) or len(position) != 3:
            position = [0.0, 0.0, 0.0]
        px, py, pz = float(position[0]), float(position[1]), float(position[2])
        prefix = str(arguments.get("name", "")).strip() or "GeodesicDome"

        local_verts, faces = _icosphere(detail)

        edge_set: Dict[Any, List[int]] = {}
        for (a, b, c) in faces:
            for (u, v) in ((a, b), (b, c), (c, a)):
                key = (u, v) if u < v else (v, u)
                if key not in edge_set:
                    edge_set[key] = [key[0], key[1]]

        # Scale unit-sphere vertices to the requested radius and apply the
        # optional upper-hemisphere filter for an open dome bowl.
        scaled: List[List[float]] = []
        kept: List[bool] = []
        for v in local_verts:
            s = [v[0] * radius, v[1] * radius, v[2] * radius]
            if dome_only and s[1] < 0.0:
                kept.append(False)
            else:
                kept.append(True)
            scaled.append(s)

        batch = uuid.uuid4().hex[:6]
        deltas: List[SceneDelta] = []
        created = 0

        def _place(pos_world: List[float], geometry: Dict[str, Any], tag: str, extra: str, rotation: Optional[List[float]] = None) -> None:
            nonlocal created
            obj = SceneObject(
                name=f"{prefix}_{tag}_{batch}_{extra}",
                type="mesh",
                geometry=Geometry(**geometry),
                material=Material(color=color, metalness=0.2, roughness=0.4),
                transform=Transform(
                    position=[pos_world[0] + px, pos_world[1] + py, pos_world[2] + pz],
                    rotation=rotation if rotation is not None else [0.0, 0.0, 0.0],
                    scale=[1.0, 1.0, 1.0],
                ),
                tags=[f"geodesic:{batch}"],
            )
            scene.objects.append(obj)
            created += 1
            deltas.append(SceneDelta(action="create", target_id=obj.id, payload=obj.to_dict()))

        # Joint spheres at every kept vertex.
        for idx, pos in enumerate(scaled):
            if not kept[idx]:
                continue
            _place(
                pos,
                {"type": "sphere", "params": {"radius": joint_radius}},
                "Joint",
                str(idx),
            )

        # Oriented strut cylinders along every kept edge.
        for i, (a, b) in enumerate(edge_set.values()):
            if not kept[a] or not kept[b]:
                continue
            va, vb = scaled[a], scaled[b]
            dx = vb[0] - va[0]
            dy = vb[1] - va[1]
            dz = vb[2] - va[2]
            length = math.sqrt(dx * dx + dy * dy + dz * dz)
            if length < 1e-9:
                continue
            ux, uy, uz = dx / length, dy / length, dz / length
            rot = _euler_align_y(ux, uy, uz)
            _place(
                [(va[0] + vb[0]) * 0.5, (va[1] + vb[1]) * 0.5, (va[2] + vb[2]) * 0.5],
                {
                    "type": "cylinder",
                    "params": {"radiusTop": strut_radius, "radiusBottom": strut_radius, "height": length},
                },
                "Strut",
                str(i),
                rotation=rot,
            )

        return ToolResult(
            success=True,
            message=f"Generated geodesic dome with {created} members (detail={detail}, radius={radius:.2f})",
            deltas=deltas,
            data={"count": created, "detail": detail, "radius": radius, "tag": f"geodesic:{batch}"},
        )


# ---------------------------------------------------------------------------
# Fractal recursion — self-similar procedural generation of a Sierpinski
# tetrahedron gasket lattice or a recursively branching fractal tree, both
# assembled purely from sphere/cylinder primitives so the renderer can draw
# them without any bespoke mesh loading.
# ---------------------------------------------------------------------------

_FRACTAL_PARAMS = {
    "type": "object",
    "properties": {
        "fractal_type": {
            "type": "string",
            "enum": ["sierpinski", "tree"],
            "description": "Recursion recipe: 'sierpinski' tetrahedron gasket lattice or 'tree' branching fractal (default sierpinski)",
        },
        "depth": {
            "type": "integer",
            "description": "Recursion depth (default 1; sierpinski 0-3, tree 0-4). Each level multiplies the member count.",
            "minimum": 0,
            "maximum": 4,
        },
        "size": {"type": "number", "description": "Overall scale of the root shape (default 3.0)"},
        "joint_radius": {"type": "number", "description": "Sphere radius at joints (sierpinski, default 0.07)"},
        "strut_radius": {"type": "number", "description": "Cylinder radius for edges/branches (default 0.025)"},
        "branching": {
            "type": "integer",
            "description": "Child branches per node (tree, default 3, range 2-5)",
            "minimum": 2,
            "maximum": 5,
        },
        "branch_angle": {"type": "number", "description": "Branch spread angle in degrees (tree, default 28)"},
        "length_ratio": {"type": "number", "description": "Child branch length as a fraction of the parent (tree, default 0.7)"},
        "color": {"type": "string", "description": "Primary lattice/branch color (default #9adcff)"},
        "leaf_color": {"type": "string", "description": "Leaf color (tree tips, default #7ee8a2)"},
        "position": {
            "type": "array",
            "items": {"type": "number"},
            "description": "Base position [x, y, z] (default [0, 0, 0])",
        },
        "seed": {"type": "integer", "description": "Random seed for tree azimuth spread (default 1)"},
        "name": {"type": "string", "description": "Optional name prefix"},
    },
    "required": [],
}


# Unit-circumradius tetrahedron corners — the self-similar vertex set used to
# build each gasket frame. Scaling by 1/2 around any corner yields the four
# congruent sub-tetrahedra of the next level, giving exact self-similarity.
_TETRA_UNIT = [
    (1.0 / math.sqrt(3.0), 1.0 / math.sqrt(3.0), 1.0 / math.sqrt(3.0)),
    (1.0 / math.sqrt(3.0), -1.0 / math.sqrt(3.0), -1.0 / math.sqrt(3.0)),
    (-1.0 / math.sqrt(3.0), 1.0 / math.sqrt(3.0), -1.0 / math.sqrt(3.0)),
    (-1.0 / math.sqrt(3.0), -1.0 / math.sqrt(3.0), 1.0 / math.sqrt(3.0)),
]
_TETRA_EDGES = [(0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3)]


def _orthonormal_frame(direction: List[float]) -> tuple:
    """Return ``(u, v)`` unit vectors spanning the plane perpendicular to ``direction``.

    Used to spread child branches azimuthally around a parent branch so the
    fractal tree fans out uniformly in 3D rather than flattening to a plane.
    """
    d = _normalize3(list(direction))
    helper = [0.0, 1.0, 0.0] if abs(d[1]) < 0.9 else [1.0, 0.0, 0.0]
    u = _normalize3([
        d[1] * helper[2] - d[2] * helper[1],
        d[2] * helper[0] - d[0] * helper[2],
        d[0] * helper[1] - d[1] * helper[0],
    ])
    v = _normalize3([
        d[1] * u[2] - d[2] * u[1],
        d[2] * u[0] - d[0] * u[2],
        d[0] * u[1] - d[1] * u[0],
    ])
    return u, v


class FractalRecursionTool(ToolBase):
    """Generate a self-similar fractal lattice or branching tree from primitives.

    Two recipes are available:
      - ``sierpinski``: a Sierpinski tetrahedron gasket. Each frame places four
        joint spheres at the tetrahedron corners and six oriented struts along
        its edges; every level adds four congruent sub-frames scaled by 1/2 at
        the corners, so the whole structure is exactly self-similar.
      - ``tree``: a recursively branching fractal tree. Each node grows a
        cylinder trunk and spawns ``branching`` child branches tilted away from
        the parent by ``branch_angle`` and fanned around it, with length and
        radius decaying by ``length_ratio`` per level; tips carry leaf spheres.
    All members share a generation tag so they can be selected, animated, and
    exported as a single unit.
    """

    name = "create_fractal"
    description = (
        "Create a self-similar fractal structure from primitives: a Sierpinski "
        "tetrahedron gasket lattice or a recursively branching fractal tree. "
        "Ideal for generative architecture studies, crystalline growth forms, "
        "and stylized vegetation."
    )

    def schema(self) -> Dict[str, Any]:
        return _FRACTAL_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        fractal_type = str(arguments.get("fractal_type", "sierpinski")).lower()
        depth = max(0, min(4, int(arguments.get("depth", 1))))
        size = max(0.5, float(arguments.get("size", 3.0)))
        joint_radius = max(0.01, float(arguments.get("joint_radius", 0.07)))
        strut_radius = max(0.005, float(arguments.get("strut_radius", 0.025)))
        branching = max(2, min(5, int(arguments.get("branching", 3))))
        branch_angle = math.radians(float(arguments.get("branch_angle", 28.0)))
        length_ratio = max(0.3, min(0.95, float(arguments.get("length_ratio", 0.7))))
        color = str(arguments.get("color", "#9adcff"))
        leaf_color = str(arguments.get("leaf_color", "#7ee8a2"))
        position = arguments.get("position", [0, 0, 0])
        if not isinstance(position, list) or len(position) != 3:
            position = [0.0, 0.0, 0.0]
        px, py, pz = float(position[0]), float(position[1]), float(position[2])
        seed = int(arguments.get("seed", 1))
        prefix = str(arguments.get("name", "")).strip() or "Fractal"

        batch = uuid.uuid4().hex[:6]
        deltas: List[SceneDelta] = []
        created = 0

        def _place(
            pos_world: List[float],
            geometry: Dict[str, Any],
            tag: str,
            extra: str,
            mat_color: str,
            rotation: Optional[List[float]] = None,
        ) -> None:
            nonlocal created
            obj = SceneObject(
                name=f"{prefix}_{tag}_{batch}_{extra}",
                type="mesh",
                geometry=Geometry(**geometry),
                material=Material(color=mat_color, metalness=0.25, roughness=0.4),
                transform=Transform(
                    position=[pos_world[0] + px, pos_world[1] + py, pos_world[2] + pz],
                    rotation=rotation if rotation is not None else [0.0, 0.0, 0.0],
                    scale=[1.0, 1.0, 1.0],
                ),
                tags=[f"fractal:{batch}"],
            )
            scene.objects.append(obj)
            created += 1
            deltas.append(SceneDelta(action="create", target_id=obj.id, payload=obj.to_dict()))

        def _build_sierpinski(center: List[float], radius: float, level: int) -> None:
            # Joint spheres at the four corners of the current frame.
            corners = [
                [center[0] + c[0] * radius, center[1] + c[1] * radius, center[2] + c[2] * radius]
                for c in _TETRA_UNIT
            ]
            for idx, corner in enumerate(corners):
                _place(
                    corner,
                    {"type": "sphere", "params": {"radius": joint_radius}},
                    "Node",
                    str(level) + "_" + str(idx),
                    color,
                )
            # Oriented struts along the six edges of the current frame.
            for ei, (a, b) in enumerate(_TETRA_EDGES):
                va, vb = corners[a], corners[b]
                dx, dy, dz = vb[0] - va[0], vb[1] - va[1], vb[2] - va[2]
                length = math.sqrt(dx * dx + dy * dy + dz * dz)
                if length < 1e-9:
                    continue
                ux, uy, uz = dx / length, dy / length, dz / length
                _place(
                    [(va[0] + vb[0]) * 0.5, (va[1] + vb[1]) * 0.5, (va[2] + vb[2]) * 0.5],
                    {
                        "type": "cylinder",
                        "params": {"radiusTop": strut_radius, "radiusBottom": strut_radius, "height": length},
                    },
                    "Strut",
                    str(level) + "_" + str(ei),
                    color,
                    rotation=_euler_align_y(ux, uy, uz),
                )
            # Recurse into the four congruent sub-tetrahedra at the corners.
            if level < depth:
                for corner in corners:
                    _build_sierpinski(corner, radius * 0.5, level + 1)

        def _build_tree(
            start: List[float],
            direction: List[float],
            length: float,
            radius: float,
            level: int,
            rng: random.Random,
        ) -> None:
            end = [start[0] + direction[0] * length, start[1] + direction[1] * length, start[2] + direction[2] * length]
            dx, dy, dz = end[0] - start[0], end[1] - start[1], end[2] - start[2]
            _place(
                [(start[0] + end[0]) * 0.5, (start[1] + end[1]) * 0.5, (start[2] + end[2]) * 0.5],
                {"type": "cylinder", "params": {"radiusTop": radius, "radiusBottom": radius, "height": length}},
                "Branch",
                str(level) + "_" + f"{start[0]:.2f}",
                color,
                rotation=_euler_align_y(dx / length, dy / length, dz / length),
            )
            if level >= depth:
                # Leaf sphere terminates the branch.
                _place(
                    end,
                    {"type": "sphere", "params": {"radius": max(joint_radius, radius * 2.2)}},
                    "Leaf",
                    str(level) + "_" + f"{end[2]:.2f}",
                    leaf_color,
                )
                return
            u, v = _orthonormal_frame(direction)
            base_azimuth = rng.uniform(0.0, 2.0 * math.pi)
            child_len = length * length_ratio
            child_radius = radius * length_ratio
            for k in range(branching):
                azimuth = base_azimuth + k * (2.0 * math.pi / branching)
                tilt = branch_angle * (0.7 + 0.6 * rng.random())
                ca, sa = math.cos(tilt), math.sin(tilt)
                spread = ca * direction[0] + sa * (math.cos(azimuth) * u[0] + math.sin(azimuth) * v[0])
                spread_y = ca * direction[1] + sa * (math.cos(azimuth) * u[1] + math.sin(azimuth) * v[1])
                spread_z = ca * direction[2] + sa * (math.cos(azimuth) * u[2] + math.sin(azimuth) * v[2])
                child_dir = _normalize3([spread, spread_y, spread_z])
                _build_tree(end, child_dir, child_len, child_radius, level + 1, rng)

        if fractal_type == "tree":
            # Seed a deterministic RNG so the same arguments reproduce the
            # exact same tree across runs.
            rng = random.Random(seed)
            _build_tree([0.0, 0.0, 0.0], [0.0, 1.0, 0.0], size, strut_radius, 0, rng)
            label = "fractal tree"
        else:
            _build_sierpinski([0.0, 0.0, 0.0], size, 0)
            label = "Sierpinski gasket"

        return ToolResult(
            success=True,
            message=f"Generated {label} with {created} members (depth={depth}, size={size:.2f})",
            deltas=deltas,
            data={"count": created, "fractal_type": fractal_type, "depth": depth, "tag": f"fractal:{batch}"},
        )


# ---------------------------------------------------------------------------
# Gyroid lattice — a triply-periodic minimal-surface lattice. The gyroid scalar
# field is sampled on a voxel grid and the edges whose endpoints straddle the
# zero isosurface are kept as strut cylinders, with joint spheres at every
# incident vertex. This yields the interconnected "minimal surface" wireframe
# widely used in architectural metamaterials and biomimetic scaffolds.
# ---------------------------------------------------------------------------

_GYROID_PARAMS = {
    "type": "object",
    "properties": {
        "size": {"type": "number", "description": "Bounding-box side length (default 6.0)"},
        "resolution": {"type": "integer", "description": "Grid cells per axis (default 8, max 14)", "minimum": 3, "maximum": 14},
        "period": {"type": "number", "description": "Gyroid field period — smaller gives tighter folds (default 2.4)"},
        "cell_offset": {"type": "number", "description": "Phase offset applied to all three axes (default 0.0)"},
        "joint_radius": {"type": "number", "description": "Sphere radius at lattice vertices (default 0.08)"},
        "strut_radius": {"type": "number", "description": "Cylinder radius for lattice edges (default 0.025)"},
        "color": {"type": "string", "description": "Lattice color (default #cfd8ff)"},
        "position": {
            "type": "array",
            "items": {"type": "number"},
            "description": "Lattice origin [x, y, z] (default [0, 0, 0])",
        },
        "name": {"type": "string", "description": "Optional lattice name prefix"},
    },
    "required": [],
}


class GyroidLatticeTool(ToolBase):
    """Generate a triply-periodic minimal-surface lattice from the gyroid field.

    The gyroid is an isosurface embedded in all three directions at once:
      F(x,y,z) = sin(x)cos(y) + sin(y)cos(z) + sin(z)cos(x)
    Sampling F on a voxel grid and keeping the edges across which F changes
    sign recovers the classic interconnected minimal-surface wireframe. A joint
    sphere is placed at every vertex incident to at least one crossing edge and
    an oriented strut cylinder connects the endpoints of each crossing edge.
    All members share a generation tag so they can be selected, animated, and
    exported as a single unit.
    """

    name = "create_gyroid"
    description = (
        "Create a gyroid lattice: a triply-periodic minimal-surface wireframe "
        "built from joint spheres and strut cylinders by sampling the gyroid "
        "field on a voxel grid. Ideal for architectural metamaterials, "
        "biomimetic scaffolds, and generative structure studies."
    )

    def schema(self) -> Dict[str, Any]:
        return _GYROID_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        size = max(1.0, float(arguments.get("size", 6.0)))
        resolution = max(3, min(14, int(arguments.get("resolution", 8))))
        period = max(0.5, float(arguments.get("period", 2.4)))
        offset = float(arguments.get("cell_offset", 0.0))
        joint_radius = max(0.01, float(arguments.get("joint_radius", 0.08)))
        strut_radius = max(0.005, float(arguments.get("strut_radius", 0.025)))
        color = str(arguments.get("color", "#cfd8ff"))
        position = arguments.get("position", [0, 0, 0])
        if not isinstance(position, list) or len(position) != 3:
            position = [0.0, 0.0, 0.0]
        px, py, pz = float(position[0]), float(position[1]), float(position[2])
        prefix = str(arguments.get("name", "")).strip() or "Gyroid"

        def _field(x: float, y: float, z: float) -> float:
            k = 2.0 * math.pi / period
            fx, fy, fz = x * k, y * k, z * k
            return (
                math.sin(fx) * math.cos(fy)
                + math.sin(fy) * math.cos(fz)
                + math.sin(fz) * math.cos(fx)
            )

        n = resolution
        step = size / n

        # Sample the gyroid field at every grid vertex.
        values: List[List[List[float]]] = []
        for i in range(n + 1):
            row: List[List[float]] = []
            for j in range(n + 1):
                col: List[float] = []
                for k in range(n + 1):
                    x = -size / 2.0 + i * step
                    y = -size / 2.0 + j * step
                    z = -size / 2.0 + k * step
                    col.append(_field(x + offset, y + offset, z + offset))
                row.append(col)
            values.append(row)

        def _index(i: int, j: int, k: int) -> int:
            return i * (n + 1) * (n + 1) + j * (n + 1) + k

        def _pos(i: int, j: int, k: int) -> List[float]:
            return [-size / 2.0 + i * step, -size / 2.0 + j * step, -size / 2.0 + k * step]

        # Collect edges whose endpoints straddle the zero isosurface.
        edge_keys = set()

        def _add_edge(a: int, b: int) -> None:
            edge_keys.add((a, b) if a < b else (b, a))

        for i in range(n + 1):
            for j in range(n + 1):
                for k in range(n + 1):
                    v = values[i][j][k]
                    if i < n and (v < 0) != (values[i + 1][j][k] < 0):
                        _add_edge(_index(i, j, k), _index(i + 1, j, k))
                    if j < n and (v < 0) != (values[i][j + 1][k] < 0):
                        _add_edge(_index(i, j, k), _index(i, j + 1, k))
                    if k < n and (v < 0) != (values[i][j][k + 1] < 0):
                        _add_edge(_index(i, j, k), _index(i, j, k + 1))

        # Vertices incident to at least one crossing edge get a joint sphere.
        incident = set()
        for a, b in edge_keys:
            incident.add(a)
            incident.add(b)

        batch = uuid.uuid4().hex[:6]
        deltas: List[SceneDelta] = []
        created = 0

        def _place(
            pos_world: List[float],
            geometry: Dict[str, Any],
            tag: str,
            extra: str,
            rotation: Optional[List[float]] = None,
        ) -> None:
            nonlocal created
            obj = SceneObject(
                name=f"{prefix}_{tag}_{batch}_{extra}",
                type="mesh",
                geometry=Geometry(**geometry),
                material=Material(color=color, metalness=0.2, roughness=0.4),
                transform=Transform(
                    position=[pos_world[0] + px, pos_world[1] + py, pos_world[2] + pz],
                    rotation=rotation if rotation is not None else [0.0, 0.0, 0.0],
                    scale=[1.0, 1.0, 1.0],
                ),
                tags=[f"gyroid:{batch}"],
            )
            scene.objects.append(obj)
            created += 1
            deltas.append(SceneDelta(action="create", target_id=obj.id, payload=obj.to_dict()))

        stride = (n + 1) * (n + 1)
        for idx in incident:
            i = idx // stride
            rem = idx % stride
            j = rem // (n + 1)
            k = rem % (n + 1)
            _place(_pos(i, j, k), {"type": "sphere", "params": {"radius": joint_radius}}, "Joint", str(idx))

        for ei, (a, b) in enumerate(sorted(edge_keys)):
            ia, ra = a // stride, a % stride
            ja, ka = ra // (n + 1), ra % (n + 1)
            ib, rb = b // stride, b % stride
            jb, kb = rb // (n + 1), rb % (n + 1)
            va, vb = _pos(ia, ja, ka), _pos(ib, jb, kb)
            dx, dy, dz = vb[0] - va[0], vb[1] - va[1], vb[2] - va[2]
            length = math.sqrt(dx * dx + dy * dy + dz * dz)
            if length < 1e-9:
                continue
            ux, uy, uz = dx / length, dy / length, dz / length
            _place(
                [(va[0] + vb[0]) * 0.5, (va[1] + vb[1]) * 0.5, (va[2] + vb[2]) * 0.5],
                {
                    "type": "cylinder",
                    "params": {"radiusTop": strut_radius, "radiusBottom": strut_radius, "height": length},
                },
                "Strut",
                str(ei),
                rotation=_euler_align_y(ux, uy, uz),
            )

        return ToolResult(
            success=True,
            message=f"Generated gyroid lattice with {created} members (resolution={resolution}, period={period:.2f})",
            deltas=deltas,
            data={"count": created, "resolution": resolution, "period": period, "tag": f"gyroid:{batch}"},
        )
