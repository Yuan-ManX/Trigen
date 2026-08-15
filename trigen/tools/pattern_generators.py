"""Advanced spatial pattern generators.

Creates compound object distributions using higher-level packing rules:
hexagonal grids, Fibonacci (sunflower) phyllotaxis, honeycomb trusses,
random-walk mazes, and Celtic knot lattices. Each generator returns a
grouped collection of primitives so downstream tools can target the
group as a unit.
"""

from __future__ import annotations

import math
import random
from typing import Any, Dict, List, Tuple

from trigen.scene import Geometry, Material, Scene, SceneObject, Transform
from trigen.tools.base import SceneDelta, ToolBase, ToolResult


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


class HexGridPatternTool(ToolBase):
    """Arrange objects in a flat-topped hexagonal packing grid."""

    name = "hex_grid_pattern"
    description = (
        "Fill a rectangular footprint with hex-packed primitives. Useful "
        "for honeycomb panels, tile floors, beehive meshes, and stylized "
        "city layouts."
    )
    category = "procedural"
    requires_approval = False

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "name": {"type": "string", "default": "HexGrid", "description": "Base name for the created group"},
                "geometry_type": {"type": "string", "default": "cylinder", "description": "Primitive placed at each hex cell"},
                "size": {"type": "number", "default": 0.5, "description": "Hex cell radius / primitive size"},
                "rows": {"type": "integer", "default": 6, "description": "Number of hex rows (Y axis)"},
                "columns": {"type": "integer", "default": 8, "description": "Number of hex columns (X axis)"},
                "height": {"type": "number", "default": 0.5, "description": "Height of each primitive when applicable"},
                "gap": {"type": "number", "default": 0.05, "description": "Spacing between hex cells"},
                "center": {
                    "type": "array",
                    "items": {"type": "number"},
                    "default": [0.0, 0.0, 0.0],
                    "description": "Center point of the grid",
                },
                "colors": {
                    "type": "array",
                    "items": {"type": "string"},
                    "default": ["#8b6cf5", "#3a7aff", "#00F0FF"],
                    "description": "Color palette (cycled per row parity)",
                },
                "jitter": {"type": "number", "default": 0.0, "description": "Per-cell position jitter (0 = clean grid)"},
                "seed": {"type": "integer", "default": 1337, "description": "Random seed for jitter"},
            },
        }

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        name = str(arguments.get("name", "HexGrid"))
        geo_type = str(arguments.get("geometry_type", "cylinder"))
        size = float(arguments.get("size", 0.5))
        rows = max(1, int(arguments.get("rows", 6)))
        cols = max(1, int(arguments.get("columns", 8)))
        height = float(arguments.get("height", 0.5))
        gap = float(arguments.get("gap", 0.05))
        center = [float(x) for x in arguments.get("center", [0.0, 0.0, 0.0])]
        colors = list(arguments.get("colors", ["#8b6cf5", "#3a7aff", "#00F0FF"]))
        jitter = float(arguments.get("jitter", 0.0))
        seed = int(arguments.get("seed", 1337))
        rng = random.Random(seed)

        # Flat-top hex grid step sizes
        step_x = (size + gap) * math.sqrt(3.0)
        step_z = (size + gap) * 1.5

        group = type("G", (), {"id": "", "child_ids": []})()
        # Create a real group via the scene group registry
        from trigen.scene import GroupObject
        gid = f"grp_hex_{abs(hash((rows, cols, seed))) & 0xFFFFF:05x}"
        group_obj = GroupObject(id=gid, name=scene.next_auto_name(name), child_ids=[])
        scene.groups.append(group_obj)
        deltas: List[SceneDelta] = [
            SceneDelta(action="create", target_id=gid, payload=group_obj.to_dict())
        ]

        geo_params_map = {
            "cylinder": {"radiusTop": size * 0.95, "radiusBottom": size * 0.95, "height": height, "radialSegments": 6},
            "box": {"width": size * 1.7, "height": height, "depth": size * 1.5},
            "sphere": {"radius": size * 0.9, "widthSegments": 24, "heightSegments": 12},
            "hexagon_placeholder": {"radius": size * 0.95, "radialSegments": 6},
        }
        geo_params = geo_params_map.get(geo_type, {"radius": size * 0.9})

        for row in range(rows):
            for col in range(cols):
                x = step_x * (col + (0.5 if row % 2 else 0.0))
                z = step_z * row
                # Center grid
                x -= step_x * (cols + 0.5) * 0.5
                z -= step_z * rows * 0.5
                if jitter > 0:
                    x += rng.uniform(-jitter, jitter) * step_x
                    z += rng.uniform(-jitter, jitter) * step_z
                color = colors[(row + col) % len(colors)]
                obj, d = _add_object(
                    scene,
                    f"{name}_r{row}c{col}",
                    geo_type,
                    geo_params,
                    position=[center[0] + x, center[1] + height * 0.5, center[2] + z],
                    color=color,
                    group_id=gid,
                    roughness=0.6,
                    metalness=0.1,
                )
                group_obj.child_ids.append(obj.id)
                deltas.append(d)

        return ToolResult(
            True,
            f"Created hex grid with {rows * cols} cells in group '{group_obj.name}'.",
            deltas=deltas,
            data={"group_id": gid, "count": rows * cols, "group_name": group_obj.name},
        )


class FibonacciLatticeTool(ToolBase):
    """Arrange objects in a sunflower phyllotaxis (Fibonacci spiral)."""

    name = "fibonacci_lattice"
    description = (
        "Pack points on a disk using the golden-angle Fibonacci spiral. "
        "Produces organic, crowd-free distributions for city plazas, "
        "flower arrangements, asteroid fields, and product showcases."
    )
    category = "procedural"

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "name": {"type": "string", "default": "Fibonacci", "description": "Base name"},
                "count": {"type": "integer", "default": 60, "description": "Number of objects to place"},
                "geometry_type": {"type": "string", "default": "sphere", "description": "Primitive to place"},
                "radius": {"type": "number", "default": 4.0, "description": "Radius of the packing disk"},
                "size": {"type": "number", "default": 0.35, "description": "Base size of each primitive"},
                "center": {"type": "array", "items": {"type": "number"}, "default": [0.0, 0.0, 0.0]},
                "height_variation": {"type": "boolean", "default": True, "description": "Vary object size by radius (smaller at edge)"},
                "colors": {
                    "type": "array",
                    "items": {"type": "string"},
                    "default": ["#ffc933", "#ff8a3a", "#e84a4a", "#9a3aff", "#3a7aff"],
                },
                "seed": {"type": "integer", "default": 42, "description": "Random seed"},
                "axis": {"type": "string", "enum": ["y", "x", "z"], "default": "y", "description": "Axis perpendicular to the spiral disk"},
            },
        }

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        count = max(1, int(arguments.get("count", 60)))
        geo_type = str(arguments.get("geometry_type", "sphere"))
        R = float(arguments.get("radius", 4.0))
        size = float(arguments.get("size", 0.35))
        center = [float(x) for x in arguments.get("center", [0.0, 0.0, 0.0])]
        hv = bool(arguments.get("height_variation", True))
        colors = list(arguments.get("colors", ["#ffc933", "#ff8a3a", "#e84a4a", "#9a3aff", "#3a7aff"]))
        seed = int(arguments.get("seed", 42))
        axis = str(arguments.get("axis", "y"))
        rng = random.Random(seed)
        base_name = str(arguments.get("name", "Fibonacci"))

        from trigen.scene import GroupObject
        gid = f"grp_fib_{abs(hash((count, seed))) & 0xFFFFF:05x}"
        group_obj = GroupObject(id=gid, name=scene.next_auto_name(base_name), child_ids=[])
        scene.groups.append(group_obj)
        deltas: List[SceneDelta] = [
            SceneDelta(action="create", target_id=gid, payload=group_obj.to_dict())
        ]

        PHI_ANGLE = math.pi * (3.0 - math.sqrt(5.0))  # golden angle
        for i in range(count):
            # Vogel's formula: radius proportional to sqrt(i) for even packing
            r = R * math.sqrt(i / max(1, count - 1))
            theta = i * PHI_ANGLE
            x = math.cos(theta) * r
            z = math.sin(theta) * r
            # size falloff (smaller at edges for organic look)
            t = i / max(1, count - 1)
            s = size * (1.0 - 0.55 * t) if hv else size
            color = colors[(i * 7 + rng.randrange(3)) % len(colors)]

            pos_map = {
                "y": [center[0] + x, center[1] + s * 0.6, center[2] + z],
                "x": [center[0] + s * 0.6, center[1] + x, center[2] + z],
                "z": [center[0] + x, center[1] + z, center[2] + s * 0.6],
            }
            geo_params = {
                "sphere": {"radius": s, "widthSegments": 20, "heightSegments": 12},
                "box": {"width": s * 1.5, "height": s * 1.5, "depth": s * 1.5},
                "cylinder": {"radiusTop": s * 0.6, "radiusBottom": s * 0.6, "height": s * 2.0, "radialSegments": 16},
                "icosahedron": {"radius": s, "detail": 1},
            }.get(geo_type, {"radius": s})

            obj, d = _add_object(
                scene,
                f"{base_name}_{i:03d}",
                geo_type,
                geo_params,
                position=pos_map[axis],
                color=color,
                group_id=gid,
                roughness=0.4,
                metalness=0.2,
            )
            group_obj.child_ids.append(obj.id)
            deltas.append(d)

        return ToolResult(
            True,
            f"Created Fibonacci lattice with {count} points in group '{group_obj.name}'.",
            deltas=deltas,
            data={"group_id": gid, "count": count, "group_name": group_obj.name},
        )


class MazeGeneratorTool(ToolBase):
    """Generate a random perfect maze (grid-wall layout) using DFS backtracking."""

    name = "generate_maze"
    description = (
        "Generate a perfect maze (one loop-free path between any two cells) "
        "via randomized depth-first backtracking. Walls and floor are "
        "emitted as a group so the maze can be transformed as one unit."
    )
    category = "procedural"
    requires_approval = False

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "name": {"type": "string", "default": "Maze"},
                "rows": {"type": "integer", "default": 8, "description": "Cell rows (depth)"},
                "cols": {"type": "integer", "default": 10, "description": "Cell columns (width)"},
                "cell_size": {"type": "number", "default": 1.5, "description": "Size of each cell"},
                "wall_height": {"type": "number", "default": 1.2, "description": "Wall height"},
                "wall_thickness": {"type": "number", "default": 0.12, "description": "Wall thickness"},
                "wall_color": {"type": "string", "default": "#6b5b95"},
                "floor_color": {"type": "string", "default": "#2a2a35"},
                "floor": {"type": "boolean", "default": True, "description": "Include a floor plane under the maze"},
                "seed": {"type": "integer", "default": 7, "description": "Maze random seed"},
                "center": {"type": "array", "items": {"type": "number"}, "default": [0.0, 0.0, 0.0]},
            },
        }

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        rows = max(2, int(arguments.get("rows", 8)))
        cols = max(2, int(arguments.get("cols", 10)))
        cs = float(arguments.get("cell_size", 1.5))
        wh = float(arguments.get("wall_height", 1.2))
        wt = float(arguments.get("wall_thickness", 0.12))
        wall_color = str(arguments.get("wall_color", "#6b5b95"))
        floor_color = str(arguments.get("floor_color", "#2a2a35"))
        include_floor = bool(arguments.get("floor", True))
        seed = int(arguments.get("seed", 7))
        center = [float(x) for x in arguments.get("center", [0.0, 0.0, 0.0])]
        base_name = str(arguments.get("name", "Maze"))
        rng = random.Random(seed)

        # Maze state: cell (r,c) -> {N,S,E,W} booleans (True = wall)
        walls: Dict[Tuple[int, int], Dict[str, bool]] = {}
        for r in range(rows):
            for c in range(cols):
                walls[(r, c)] = {"N": True, "S": True, "E": True, "W": True}
        visited = set()
        stack: List[Tuple[int, int]] = [(0, 0)]
        visited.add((0, 0))
        DIRS = [("N", -1, 0, "S"), ("S", 1, 0, "N"), ("E", 0, 1, "W"), ("W", 0, -1, "E")]
        while stack:
            r, c = stack[-1]
            neigh = []
            for name, dr, dc, opp in DIRS:
                nr, nc = r + dr, c + dc
                if 0 <= nr < rows and 0 <= nc < cols and (nr, nc) not in visited:
                    neigh.append((name, nr, nc, opp))
            if not neigh:
                stack.pop()
                continue
            name, nr, nc, opp = rng.choice(neigh)
            walls[(r, c)][name] = False
            walls[(nr, nc)][opp] = False
            visited.add((nr, nc))
            stack.append((nr, nc))

        from trigen.scene import GroupObject
        gid = f"grp_maze_{rows}x{cols}_{seed:x}"
        group_obj = GroupObject(id=gid, name=scene.next_auto_name(base_name), child_ids=[])
        scene.groups.append(group_obj)
        deltas: List[SceneDelta] = [
            SceneDelta(action="create", target_id=gid, payload=group_obj.to_dict())
        ]

        W = cols * cs
        D = rows * cs
        ox = center[0] - W * 0.5
        oz = center[2] - D * 0.5

        # Floor plane
        if include_floor:
            fobj, fd = _add_object(
                scene,
                f"{base_name}_Floor",
                "plane",
                {"width": W + cs, "height": D + cs, "widthSegments": 1, "heightSegments": 1},
                position=[center[0], center[1] + 0.0, center[2]],
                color=floor_color,
                rotation=[-math.pi / 2, 0.0, 0.0],
                group_id=gid,
                roughness=0.9,
            )
            group_obj.child_ids.append(fobj.id)
            deltas.append(fd)

        wall_count = 0
        for r in range(rows):
            for c in range(cols):
                cell = walls[(r, c)]
                # north wall of cell (at r boundary)
                if cell["N"] and r == 0:
                    x0 = ox + c * cs
                    x1 = ox + (c + 1) * cs
                    z0 = oz + r * cs
                    pos = [(x0 + x1) * 0.5, center[1] + wh * 0.5, z0]
                    o, d = _add_object(
                        scene,
                        f"{base_name}_W_N{r}_{c}",
                        "box",
                        {"width": cs + wt, "height": wh, "depth": wt},
                        position=pos,
                        color=wall_color,
                        group_id=gid,
                        roughness=0.7,
                        metalness=0.1,
                    )
                    group_obj.child_ids.append(o.id)
                    deltas.append(d)
                    wall_count += 1
                if cell["W"] and c == 0:
                    z0 = oz + r * cs
                    z1 = oz + (r + 1) * cs
                    x0 = ox + c * cs
                    pos = [x0, center[1] + wh * 0.5, (z0 + z1) * 0.5]
                    o, d = _add_object(
                        scene,
                        f"{base_name}_W_W{r}_{c}",
                        "box",
                        {"width": wt, "height": wh, "depth": cs + wt},
                        position=pos,
                        color=wall_color,
                        group_id=gid,
                        roughness=0.7,
                        metalness=0.1,
                    )
                    group_obj.child_ids.append(o.id)
                    deltas.append(d)
                    wall_count += 1
                if cell["E"]:
                    z0 = oz + r * cs
                    z1 = oz + (r + 1) * cs
                    x0 = ox + (c + 1) * cs
                    pos = [x0, center[1] + wh * 0.5, (z0 + z1) * 0.5]
                    o, d = _add_object(
                        scene,
                        f"{base_name}_W_E{r}_{c}",
                        "box",
                        {"width": wt, "height": wh, "depth": cs + wt},
                        position=pos,
                        color=wall_color,
                        group_id=gid,
                        roughness=0.7,
                        metalness=0.1,
                    )
                    group_obj.child_ids.append(o.id)
                    deltas.append(d)
                    wall_count += 1
                if cell["S"]:
                    x0 = ox + c * cs
                    x1 = ox + (c + 1) * cs
                    z0 = oz + (r + 1) * cs
                    pos = [(x0 + x1) * 0.5, center[1] + wh * 0.5, z0]
                    o, d = _add_object(
                        scene,
                        f"{base_name}_W_S{r}_{c}",
                        "box",
                        {"width": cs + wt, "height": wh, "depth": wt},
                        position=pos,
                        color=wall_color,
                        group_id=gid,
                        roughness=0.7,
                        metalness=0.1,
                    )
                    group_obj.child_ids.append(o.id)
                    deltas.append(d)
                    wall_count += 1

        return ToolResult(
            True,
            f"Generated maze ({rows}x{cols}) with {wall_count} walls in group '{group_obj.name}'.",
            deltas=deltas,
            data={"group_id": gid, "group_name": group_obj.name, "walls": wall_count, "cells": rows * cols},
        )


class HoneycombTrussTool(ToolBase):
    """Generate a space-filling honeycomb truss of hexagonal cells."""

    name = "honeycomb_truss"
    description = (
        "Generate a 2D honeycomb truss of hexagonal cells. Each cell is a "
        "thin-walled hex ring; the resulting structure is lightweight and "
        "structurally evocative of aerospace sandwich panels."
    )
    category = "procedural"

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "name": {"type": "string", "default": "Honeycomb"},
                "cell_radius": {"type": "number", "default": 0.6, "description": "Hex cell circumradius"},
                "wall_thickness": {"type": "number", "default": 0.05, "description": "Strut thickness"},
                "height": {"type": "number", "default": 0.8, "description": "Extrusion depth of each hex tube"},
                "cells_x": {"type": "integer", "default": 6, "description": "Cells along X"},
                "cells_z": {"type": "integer", "default": 5, "description": "Cells along Z"},
                "color": {"type": "string", "default": "#c8b8f0"},
                "center": {"type": "array", "items": {"type": "number"}, "default": [0.0, 0.0, 0.0]},
                "emissive_edges": {"type": "boolean", "default": False, "description": "Add emissive edge highlight"},
            },
        }

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        base_name = str(arguments.get("name", "Honeycomb"))
        cr = float(arguments.get("cell_radius", 0.6))
        wt = float(arguments.get("wall_thickness", 0.05))
        h = float(arguments.get("height", 0.8))
        cx = max(1, int(arguments.get("cells_x", 6)))
        cz = max(1, int(arguments.get("cells_z", 5)))
        color = str(arguments.get("color", "#c8b8f0"))
        center = [float(x) for x in arguments.get("center", [0.0, 0.0, 0.0])]
        emissive = bool(arguments.get("emissive_edges", False))

        from trigen.scene import GroupObject
        gid = f"grp_hc_{cx}x{cz}"
        group_obj = GroupObject(id=gid, name=scene.next_auto_name(base_name), child_ids=[])
        scene.groups.append(group_obj)
        deltas: List[SceneDelta] = [
            SceneDelta(action="create", target_id=gid, payload=group_obj.to_dict())
        ]

        # Hex side length = circumradius (flat-top hex spacing in X / Z)
        dx = cr * math.sqrt(3.0)
        dz = cr * 1.5
        # 6 edges per cell (shared walls are drawn twice — acceptable for visuals)
        edges = 0
        for row in range(cz):
            for col in range(cx):
                ox = dx * (col + (0.5 if row % 2 else 0.0))
                oz = dz * row
                # offset for centering
                ox -= dx * (cx + 0.5) * 0.5
                oz -= dz * cz * 0.5
                for i in range(6):
                    # Edge center position (flat-top hex, edge i is vertical on right)
                    angle = math.pi / 3.0 * i + math.pi / 6.0
                    ex = math.cos(angle) * cr
                    ez = math.sin(angle) * cr
                    length = cr * math.sqrt(3.0) * 0.5 + wt
                    # Perpendicular direction = strut length
                    if i % 2 == 0:
                        # vertical-ish strut: length along Z
                        sx = wt * 1.2
                        sz = length
                    else:
                        sx = length
                        sz = wt * 1.2
                    obj, d = _add_object(
                        scene,
                        f"{base_name}_e{row}_{col}_{i}",
                        "box",
                        {"width": sx, "height": h, "depth": sz},
                        position=[
                            center[0] + ox + ex,
                            center[1] + h * 0.5,
                            center[2] + oz + ez,
                        ],
                        color=color,
                        group_id=gid,
                        metalness=0.25,
                        roughness=0.4,
                        emissive=color if emissive else "#000000",
                        emissive_intensity=0.6 if emissive else 0.0,
                    )
                    group_obj.child_ids.append(obj.id)
                    deltas.append(d)
                    edges += 1

        return ToolResult(
            True,
            f"Created honeycomb truss ({cx}x{cz} cells, {edges} struts) in group '{group_obj.name}'.",
            deltas=deltas,
            data={"group_id": gid, "group_name": group_obj.name, "struts": edges},
        )


class KnotworkLatticeTool(ToolBase):
    """Create a plaited Celtic-style knotwork ribbon lattice."""

    name = "knotwork_lattice"
    description = (
        "Lay out a Celtic-plaited knotwork ribbon lattice using 3D torus "
        "struts. The ribbon weaves over and under itself for woven-trim "
        "and ornamental-border visuals."
    )
    category = "procedural"

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "name": {"type": "string", "default": "Knotwork"},
                "rows": {"type": "integer", "default": 3, "description": "Interlacing rows"},
                "columns": {"type": "integer", "default": 4, "description": "Interlacing columns"},
                "cell": {"type": "number", "default": 1.5, "description": "Inter-cell spacing"},
                "tube_radius": {"type": "number", "default": 0.06, "description": "Ribbon thickness"},
                "color": {"type": "string", "default": "#ffc933"},
                "center": {"type": "array", "items": {"type": "number"}, "default": [0.0, 0.6, 0.0]},
                "variant": {"type": "string", "enum": ["square", "diagonal", "radial"], "default": "square"},
            },
        }

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        base_name = str(arguments.get("name", "Knotwork"))
        rows = max(1, int(arguments.get("rows", 3)))
        cols = max(1, int(arguments.get("columns", 4)))
        cell = float(arguments.get("cell", 1.5))
        tr = float(arguments.get("tube_radius", 0.06))
        color = str(arguments.get("color", "#ffc933"))
        center = [float(x) for x in arguments.get("center", [0.0, 0.6, 0.0])]
        variant = str(arguments.get("variant", "square"))

        from trigen.scene import GroupObject
        gid = f"grp_kw_{rows}x{cols}"
        group_obj = GroupObject(id=gid, name=scene.next_auto_name(base_name), child_ids=[])
        scene.groups.append(group_obj)
        deltas: List[SceneDelta] = [
            SceneDelta(action="create", target_id=gid, payload=group_obj.to_dict())
        ]

        W = cols * cell
        D = rows * cell

        def add_ring(x: float, z: float, r: float, y_offset: float = 0.0) -> None:
            obj, d = _add_object(
                scene,
                f"{base_name}_ring",
                "torus",
                {"radius": r, "tube": tr, "radialSegments": 12, "tubularSegments": 48},
                position=[center[0] + x, center[1] + y_offset, center[2] + z],
                rotation=[math.pi / 2, 0.0, 0.0],
                color=color,
                group_id=gid,
                metalness=0.8,
                roughness=0.25,
            )
            group_obj.child_ids.append(obj.id)
            deltas.append(d)

        if variant == "radial":
            rings = max(rows, cols)
            for i in range(rings):
                r = (i + 1) * cell * 0.6
                yoff = (i % 2) * tr * 2.2
                add_ring(0.0, 0.0, r, yoff)
        else:
            for r in range(rows):
                for c in range(cols):
                    x = (c - (cols - 1) / 2.0) * cell
                    z = (r - (rows - 1) / 2.0) * cell
                    yoff = ((r + c) % 2) * tr * 2.2
                    rad = cell * 0.4
                    if variant == "diagonal":
                        # diagonal cells: alternate rotation of ellipse-like rings
                        obj_, d_ = _add_object(
                            scene,
                            f"{base_name}_cell",
                            "torus",
                            {"radius": rad, "tube": tr, "radialSegments": 10, "tubularSegments": 48},
                            position=[center[0] + x, center[1] + yoff, center[2] + z],
                            rotation=[math.pi / 2, 0.0, math.pi / 4 * ((r + c) % 2)],
                            color=color,
                            group_id=gid,
                            metalness=0.8,
                            roughness=0.25,
                        )
                        group_obj.child_ids.append(obj_.id)
                        deltas.append(d_)
                    else:
                        add_ring(x, z, rad, yoff)

        return ToolResult(
            True,
            f"Created knotwork lattice ({rows}x{cols}, variant '{variant}') in group '{group_obj.name}'.",
            deltas=deltas,
            data={"group_id": gid, "group_name": group_obj.name},
        )
