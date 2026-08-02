"""Creative skill library — parameterized multi-tool compositions.

Skills are higher-level creative recipes that expand into ordered tool-call
sequences, letting the Agent express complex constructions (a spiral staircase,
a forest, a crystal garden) as a single invocation. Each skill declares its
parameter schema and a ``build_steps`` generator that yields TaskStep lists
consuming the existing tool registry — so skills compose with the full editor
toolset rather than duplicating logic.

The library is intentionally declarative: adding a new skill is a matter of
defining its schema and step generator, with no changes to the orchestrator.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from trigen.planner import TaskStep


@dataclass
class SkillDescriptor:
    """Metadata for a creative skill."""

    name: str
    description: str
    category: str  # architecture / nature / abstract / lighting / layout
    parameters: Dict[str, Any]
    icon: str = "sparkles"


class SkillBase:
    """Base class for creative skills.

    Subclasses define ``name``, ``description``, ``category``, ``schema``,
    and implement ``build_steps`` to return an ordered list of TaskStep
    objects that the orchestrator executes through the normal tool pipeline.
    """

    name: str = ""
    description: str = ""
    category: str = "abstract"
    icon: str = "sparkles"

    def schema(self) -> Dict[str, Any]:
        """OpenAI-style parameter schema."""
        raise NotImplementedError

    def descriptor(self) -> SkillDescriptor:
        return SkillDescriptor(
            name=self.name,
            description=self.description,
            category=self.category,
            parameters=self.schema(),
            icon=self.icon,
        )

    def build_steps(self, arguments: Dict[str, Any], id_prefix: str = "") -> List[TaskStep]:
        """Expand the skill into ordered tool-call steps."""
        raise NotImplementedError

    @staticmethod
    def _step(tool: str, args: Dict[str, Any], call_id: str, desc: str = "") -> TaskStep:
        return TaskStep(tool_name=tool, arguments=args, tool_call_id=call_id, description=desc)


# ---------------------------------------------------------------------------
# Architecture skills
# ---------------------------------------------------------------------------

class SpiralStaircaseSkill(SkillBase):
    """Build a spiral staircase: central column + radial steps with rise."""

    name = "spiral_staircase"
    description = "Generate a spiral staircase with a central pillar and evenly spaced steps spiraling upward."
    category = "architecture"
    icon = "stairs"

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "steps": {"type": "integer", "description": "Number of steps (default 16)"},
                "radius": {"type": "number", "description": "Step radius from center (default 1.5)"},
                "height": {"type": "number", "description": "Total rise height (default 5)"},
                "step_depth": {"type": "number", "description": "Depth of each step (default 0.6)"},
                "material_preset": {"type": "string", "description": "Material preset for steps (default stone)"},
            },
        }

    def build_steps(self, arguments: Dict[str, Any], id_prefix: str = "") -> List[TaskStep]:
        steps_count = max(3, min(60, int(arguments.get("steps", 16))))
        radius = float(arguments.get("radius", 1.5))
        total_height = float(arguments.get("height", 5))
        step_depth = float(arguments.get("step_depth", 0.6))
        preset = str(arguments.get("material_preset", "stone"))
        rise = total_height / steps_count
        result: List[TaskStep] = []

        # Central pillar
        result.append(self._step(
            "create_object",
            {
                "geometry_type": "cylinder",
                "name": f"{id_prefix}Pillar",
                "position": [0, total_height / 2, 0],
                "scale": [0.3, total_height, 0.3],
            },
            f"{id_prefix}pillar",
            "Central pillar",
        ))

        for i in range(steps_count):
            angle = (i / steps_count) * math.pi * 2 * (steps_count / 8)
            y = i * rise + rise / 2
            x = math.cos(angle) * radius * 0.5
            z = math.sin(angle) * radius * 0.5
            result.append(self._step(
                "create_object",
                {
                    "geometry_type": "box",
                    "name": f"{id_prefix}Step_{i + 1}",
                    "position": [x, y, z],
                    "scale": [radius, 0.08, step_depth],
                },
                f"{id_prefix}step_{i}",
                f"Step {i + 1}",
            ))
            result.append(self._step(
                "transform_object",
                {
                    "target": f"{id_prefix}Step_{i + 1}",
                    "rotation": [0, angle, 0],
                    "relative": False,
                },
                f"{id_prefix}step_rot_{i}",
                f"Rotate step {i + 1}",
            ))

        # Apply material to all steps
        result.append(self._step(
            "apply_material_preset",
            {"target": f"{id_prefix}Pillar", "preset": "marble"},
            f"{id_prefix}pillar_mat",
            "Pillar material",
        ))
        for i in range(steps_count):
            result.append(self._step(
                "apply_material_preset",
                {"target": f"{id_prefix}Step_{i + 1}", "preset": preset},
                f"{id_prefix}step_mat_{i}",
                f"Step {i + 1} material",
            ))
        return result


class ColonnadeSkill(SkillBase):
    """Build a colonnade: row of columns with an entablature on top."""

    name = "colonnade"
    description = "Generate a colonnade: a row of vertical columns topped by a horizontal beam."
    category = "architecture"
    icon = "columns"

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "count": {"type": "integer", "description": "Number of columns (default 6)"},
                "spacing": {"type": "number", "description": "Distance between columns (default 2.5)"},
                "height": {"type": "number", "description": "Column height (default 4)"},
                "radius": {"type": "number", "description": "Column radius (default 0.4)"},
            },
        }

    def build_steps(self, arguments: Dict[str, Any], id_prefix: str = "") -> List[TaskStep]:
        count = max(2, min(20, int(arguments.get("count", 6))))
        spacing = float(arguments.get("spacing", 2.5))
        height = float(arguments.get("height", 4))
        radius = float(arguments.get("radius", 0.4))
        result: List[TaskStep] = []
        total_width = spacing * (count - 1)
        start_x = -total_width / 2

        for i in range(count):
            name = f"{id_prefix}Column_{i + 1}"
            result.append(self._step(
                "create_object",
                {
                    "geometry_type": "cylinder",
                    "name": name,
                    "position": [start_x + i * spacing, height / 2, 0],
                    "scale": [radius, height, radius],
                },
                f"{id_prefix}col_{i}",
                f"Column {i + 1}",
            ))
            result.append(self._step(
                "apply_material_preset",
                {"target": name, "preset": "marble"},
                f"{id_prefix}col_mat_{i}",
                f"Column {i + 1} material",
            ))

        # Entablature beam
        result.append(self._step(
            "create_object",
            {
                "geometry_type": "box",
                "name": f"{id_prefix}Entablature",
                "position": [0, height + 0.15, 0],
                "scale": [total_width + 1, 0.3, 1.2],
            },
            f"{id_prefix}beam",
            "Entablature beam",
        ))
        result.append(self._step(
            "apply_material_preset",
            {"target": f"{id_prefix}Entablature", "preset": "marble"},
            f"{id_prefix}beam_mat",
            "Beam material",
        ))
        return result


# ---------------------------------------------------------------------------
# Nature skills
# ---------------------------------------------------------------------------

class ForestSkill(SkillBase):
    """Scatter trees across an area using L-system-like construction."""

    name = "forest"
    description = "Generate a forest of trees scattered across a ground area with random sizes and positions."
    category = "nature"
    icon = "tree"

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "tree_count": {"type": "integer", "description": "Number of trees (default 12)"},
                "area_size": {"type": "number", "description": "Area side length (default 15)"},
                "season": {"type": "string", "enum": ["spring", "summer", "autumn", "winter"], "description": "Season affecting foliage color"},
            },
        }

    def build_steps(self, arguments: Dict[str, Any], id_prefix: str = "") -> List[TaskStep]:
        import random
        rng = random.Random(arguments.get("seed", 42))
        count = max(1, min(50, int(arguments.get("tree_count", 12))))
        area = float(arguments.get("area_size", 15))
        season = str(arguments.get("season", "summer"))
        half = area / 2

        season_colors = {
            "spring": "#7acc5a",
            "summer": "#2d8a3e",
            "autumn": "#d97520",
            "winter": "#c8d8e0",
        }
        foliage_color = season_colors.get(season, "#2d8a3e")

        result: List[TaskStep] = []
        # Ground plane
        result.append(self._step(
            "create_object",
            {
                "geometry_type": "plane",
                "name": f"{id_prefix}Ground",
                "position": [0, 0, 0],
                "scale": [area, 1, area],
            },
            f"{id_prefix}ground",
            "Forest ground",
        ))
        result.append(self._step(
            "apply_material",
            {"target": f"{id_prefix}Ground", "color": "#3a5a2a"},
            f"{id_prefix}ground_mat",
            "Ground material",
        ))

        for i in range(count):
            x = rng.uniform(-half + 1, half - 1)
            z = rng.uniform(-half + 1, half - 1)
            trunk_h = rng.uniform(1.5, 3.0)
            trunk_r = rng.uniform(0.12, 0.22)
            crown_r = rng.uniform(0.8, 1.6)

            # Trunk
            trunk_name = f"{id_prefix}Tree_{i + 1}_Trunk"
            result.append(self._step(
                "create_object",
                {
                    "geometry_type": "cylinder",
                    "name": trunk_name,
                    "position": [x, trunk_h / 2, z],
                    "scale": [trunk_r, trunk_h, trunk_r],
                },
                f"{id_prefix}trunk_{i}",
                f"Tree {i + 1} trunk",
            ))
            result.append(self._step(
                "apply_material",
                {"target": trunk_name, "color": "#5a3a1a"},
                f"{id_prefix}trunk_mat_{i}",
                f"Tree {i + 1} trunk material",
            ))

            # Crown (cone or sphere)
            crown_name = f"{id_prefix}Tree_{i + 1}_Crown"
            crown_type = "cone" if rng.random() > 0.5 else "sphere"
            result.append(self._step(
                "create_object",
                {
                    "geometry_type": crown_type,
                    "name": crown_name,
                    "position": [x, trunk_h + crown_r * 0.6, z],
                    "scale": [crown_r, crown_r * 1.2, crown_r],
                },
                f"{id_prefix}crown_{i}",
                f"Tree {i + 1} crown",
            ))
            result.append(self._step(
                "apply_material",
                {"target": crown_name, "color": foliage_color},
                f"{id_prefix}crown_mat_{i}",
                f"Tree {i + 1} crown material",
            ))
        return result


class CrystalGardenSkill(SkillBase):
    """Cluster of glowing crystal formations in a dark atmosphere."""

    name = "crystal_garden"
    description = "Generate a cluster of glowing crystal formations with emissive materials and dark ambient lighting."
    category = "nature"
    icon = "gem"

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "crystal_count": {"type": "integer", "description": "Number of crystal formations (default 8)"},
                "spread": {"type": "number", "description": "Area spread radius (default 5)"},
                "glow_color": {"type": "string", "description": "Emissive glow color hex (default #00F0FF)"},
            },
        }

    def build_steps(self, arguments: Dict[str, Any], id_prefix: str = "") -> List[TaskStep]:
        import random
        rng = random.Random(arguments.get("seed", 99))
        count = max(3, min(30, int(arguments.get("crystal_count", 8))))
        spread = float(arguments.get("spread", 5))
        glow = str(arguments.get("glow_color", "#00F0FF"))
        result: List[TaskStep] = []

        # Dark background
        result.append(self._step(
            "set_background",
            {"color": "#050510"},
            f"{id_prefix}bg",
            "Dark atmosphere",
        ))
        result.append(self._step(
            "set_fog",
            {"enabled": True, "color": "#0a0a20", "near": 8, "far": 30},
            f"{id_prefix}fog",
            "Atmospheric fog",
        ))

        for i in range(count):
            angle = (i / count) * math.pi * 2 + rng.uniform(-0.3, 0.3)
            dist = rng.uniform(1, spread)
            x = math.cos(angle) * dist
            z = math.sin(angle) * dist
            h = rng.uniform(1.5, 4.0)
            r = rng.uniform(0.3, 0.7)
            tilt_x = rng.uniform(-0.2, 0.2)
            tilt_z = rng.uniform(-0.2, 0.2)

            name = f"{id_prefix}Crystal_{i + 1}"
            result.append(self._step(
                "create_object",
                {
                    "geometry_type": "octahedron",
                    "name": name,
                    "position": [x, h / 2, z],
                    "scale": [r, h, r],
                },
                f"{id_prefix}crystal_{i}",
                f"Crystal {i + 1}",
            ))
            result.append(self._step(
                "transform_object",
                {"target": name, "rotation": [tilt_x, 0, tilt_z], "relative": False},
                f"{id_prefix}crystal_rot_{i}",
                f"Crystal {i + 1} tilt",
            ))
            result.append(self._step(
                "apply_material",
                {
                    "target": name,
                    "color": glow,
                    "emissive": glow,
                    "emissive_intensity": 1.5,
                    "opacity": 0.75,
                    "metalness": 0.3,
                    "roughness": 0.1,
                },
                f"{id_prefix}crystal_mat_{i}",
                f"Crystal {i + 1} glow material",
            ))

        # Point light at center
        result.append(self._step(
            "add_light",
            {"light_type": "point", "color": glow, "intensity": 2.0, "position": [0, 3, 0]},
            f"{id_prefix}light",
            "Central glow light",
        ))
        return result


# ---------------------------------------------------------------------------
# Abstract / decorative skills
# ---------------------------------------------------------------------------

class DNAHelixSkill(SkillBase):
    """Double-helix structure of spheres connected by rungs."""

    name = "dna_helix"
    description = "Generate a DNA double-helix structure with two spiral strands of spheres and connecting rungs."
    category = "abstract"
    icon = "dna"

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "segments": {"type": "integer", "description": "Number of helix segments (default 20)"},
                "height": {"type": "number", "description": "Total helix height (default 8)"},
                "radius": {"type": "number", "description": "Helix radius (default 1.2)"},
            },
        }

    def build_steps(self, arguments: Dict[str, Any], id_prefix: str = "") -> List[TaskStep]:
        segments = max(4, min(80, int(arguments.get("segments", 20))))
        height = float(arguments.get("height", 8))
        radius = float(arguments.get("radius", 1.2))
        rise = height / segments
        result: List[TaskStep] = []

        for i in range(segments):
            t = i / segments
            angle = t * math.pi * 2 * 3  # 3 full turns
            y = i * rise
            x1 = math.cos(angle) * radius
            z1 = math.sin(angle) * radius
            x2 = math.cos(angle + math.pi) * radius
            z2 = math.sin(angle + math.pi) * radius

            # Strand A sphere
            result.append(self._step(
                "create_object",
                {
                    "geometry_type": "sphere",
                    "name": f"{id_prefix}HelixA_{i + 1}",
                    "position": [x1, y, z1],
                    "scale": [0.25, 0.25, 0.25],
                },
                f"{id_prefix}a_{i}",
                f"Strand A node {i + 1}",
            ))
            result.append(self._step(
                "apply_material",
                {"target": f"{id_prefix}HelixA_{i + 1}", "color": "#00F0FF", "emissive": "#00F0FF", "emissive_intensity": 0.5},
                f"{id_prefix}a_mat_{i}",
                f"Strand A material {i + 1}",
            ))

            # Strand B sphere
            result.append(self._step(
                "create_object",
                {
                    "geometry_type": "sphere",
                    "name": f"{id_prefix}HelixB_{i + 1}",
                    "position": [x2, y, z2],
                    "scale": [0.25, 0.25, 0.25],
                },
                f"{id_prefix}b_{i}",
                f"Strand B node {i + 1}",
            ))
            result.append(self._step(
                "apply_material",
                {"target": f"{id_prefix}HelixB_{i + 1}", "color": "#FFB800", "emissive": "#FFB800", "emissive_intensity": 0.5},
                f"{id_prefix}b_mat_{i}",
                f"Strand B material {i + 1}",
            ))

            # Rung (every 2 segments to avoid clutter)
            if i % 2 == 0:
                mid_x = (x1 + x2) / 2
                mid_z = (z1 + z2) / 2
                rung_len = math.sqrt((x2 - x1) ** 2 + (z2 - z1) ** 2)
                result.append(self._step(
                    "create_object",
                    {
                        "geometry_type": "cylinder",
                        "name": f"{id_prefix}Rung_{i + 1}",
                        "position": [mid_x, y, mid_z],
                        "scale": [0.06, rung_len, 0.06],
                    },
                    f"{id_prefix}rung_{i}",
                    f"Rung {i + 1}",
                ))
                result.append(self._step(
                    "transform_object",
                    {"target": f"{id_prefix}Rung_{i + 1}", "rotation": [0, 0, math.pi / 2], "relative": False},
                    f"{id_prefix}rung_rot_{i}",
                    f"Rung {i + 1} rotation",
                ))
        return result


class SpiralGalaxySkill(SkillBase):
    """Spiral galaxy of emissive spheres with a bright core."""

    name = "spiral_galaxy"
    description = "Generate a spiral galaxy with a bright central core and star particles along spiral arms."
    category = "abstract"
    icon = "galaxy"

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "stars": {"type": "integer", "description": "Number of stars (default 80)"},
                "arms": {"type": "integer", "description": "Number of spiral arms (default 3)"},
                "radius": {"type": "number", "description": "Galaxy radius (default 8)"},
            },
        }

    def build_steps(self, arguments: Dict[str, Any], id_prefix: str = "") -> List[TaskStep]:
        import random
        rng = random.Random(arguments.get("seed", 7))
        star_count = max(10, min(200, int(arguments.get("stars", 80))))
        arms = max(2, min(6, int(arguments.get("arms", 3))))
        galaxy_r = float(arguments.get("radius", 8))
        result: List[TaskStep] = []

        # Core
        result.append(self._step(
            "create_object",
            {
                "geometry_type": "sphere",
                "name": f"{id_prefix}GalaxyCore",
                "position": [0, 0, 0],
                "scale": [1.2, 1.2, 1.2],
            },
            f"{id_prefix}core",
            "Galactic core",
        ))
        result.append(self._step(
            "apply_material",
            {"target": f"{id_prefix}GalaxyCore", "color": "#ffffff", "emissive": "#fff5d0", "emissive_intensity": 3.0},
            f"{id_prefix}core_mat",
            "Core glow",
        ))

        for i in range(star_count):
            arm_idx = i % arms
            t = rng.uniform(0.1, 1.0)
            arm_angle = (arm_idx / arms) * math.pi * 2
            spiral = t * math.pi * 3 + arm_angle
            jitter = rng.uniform(-0.4, 0.4)
            r = t * galaxy_r
            angle = spiral + jitter * 0.3
            x = math.cos(angle) * r
            z = math.sin(angle) * r
            y = rng.uniform(-0.3, 0.3)
            size = rng.uniform(0.05, 0.18)
            hue = rng.choice(["#00F0FF", "#FFB800", "#ffffff", "#aaccff"])

            result.append(self._step(
                "create_object",
                {
                    "geometry_type": "sphere",
                    "name": f"{id_prefix}Star_{i + 1}",
                    "position": [x, y, z],
                    "scale": [size, size, size],
                },
                f"{id_prefix}star_{i}",
                f"Star {i + 1}",
            ))
            result.append(self._step(
                "apply_material",
                {"target": f"{id_prefix}Star_{i + 1}", "color": hue, "emissive": hue, "emissive_intensity": 2.0},
                f"{id_prefix}star_mat_{i}",
                f"Star {i + 1} glow",
            ))

        # Dark background
        result.append(self._step(
            "set_background",
            {"color": "#020208"},
            f"{id_prefix}bg",
            "Deep space",
        ))
        return result


# ---------------------------------------------------------------------------
# Lighting skills
# ---------------------------------------------------------------------------

class StudioLightingSkill(SkillBase):
    """Three-point studio lighting setup."""

    name = "studio_lighting"
    description = "Set up a three-point studio lighting rig: key, fill, and rim lights with balanced intensities."
    category = "lighting"
    icon = "light"

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "key_color": {"type": "string", "description": "Key light color (default #ffffff)"},
                "key_intensity": {"type": "number", "description": "Key light intensity (default 2.0)"},
                "fill_color": {"type": "string", "description": "Fill light color (default #88aaff)"},
                "rim_color": {"type": "string", "description": "Rim light color (default #FFB800)"},
            },
        }

    def build_steps(self, arguments: Dict[str, Any], id_prefix: str = "") -> List[TaskStep]:
        key_color = str(arguments.get("key_color", "#ffffff"))
        key_int = float(arguments.get("key_intensity", 2.0))
        fill_color = str(arguments.get("fill_color", "#88aaff"))
        rim_color = str(arguments.get("rim_color", "#FFB800"))

        return [
            self._step(
                "add_light",
                {"light_type": "directional", "name": f"{id_prefix}Key", "color": key_color, "intensity": key_int, "position": [5, 6, 4]},
                f"{id_prefix}key", "Key light (front-right)",
            ),
            self._step(
                "add_light",
                {"light_type": "directional", "name": f"{id_prefix}Fill", "color": fill_color, "intensity": key_int * 0.4, "position": [-5, 3, 4]},
                f"{id_prefix}fill", "Fill light (front-left, softer)",
            ),
            self._step(
                "add_light",
                {"light_type": "directional", "name": f"{id_prefix}Rim", "color": rim_color, "intensity": key_int * 0.7, "position": [0, 5, -6]},
                f"{id_prefix}rim", "Rim light (back)",
            ),
            self._step(
                "set_environment",
                {"hdri": "studio", "intensity": 0.6},
                f"{id_prefix}env", "Studio HDRI environment",
            ),
        ]


# ---------------------------------------------------------------------------
# Abstract / science skills
# ---------------------------------------------------------------------------

class AtomSkill(SkillBase):
    """Build a Bohr-style atom model: glowing nucleus + electron orbits."""

    name = "atom"
    description = "Generate an atom model with a glowing nucleus and three electron orbits at staggered angles, each carrying an electron."
    category = "abstract"
    icon = "atom"

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "nucleus_radius": {"type": "number", "description": "Nucleus radius (default 0.8)"},
                "orbit_radius": {"type": "number", "description": "Electron orbit radius (default 2.2)"},
                "electrons": {"type": "integer", "description": "Number of orbits/electrons (default 3, max 6)"},
                "nucleus_color": {"type": "string", "description": "Nucleus emissive color (default #FFB800)"},
                "electron_color": {"type": "string", "description": "Electron emissive color (default #00F0FF)"},
            },
        }

    def build_steps(self, arguments: Dict[str, Any], id_prefix: str = "") -> List[TaskStep]:
        n_radius = float(arguments.get("nucleus_radius", 0.8))
        o_radius = float(arguments.get("orbit_radius", 2.2))
        electrons = max(1, min(6, int(arguments.get("electrons", 3))))
        n_color = str(arguments.get("nucleus_color", "#FFB800"))
        e_color = str(arguments.get("electron_color", "#00F0FF"))
        result: List[TaskStep] = []

        # Nucleus
        result.append(self._step(
            "create_object",
            {
                "geometry_type": "sphere",
                "name": f"{id_prefix}Nucleus",
                "position": [0, 0, 0],
                "scale": [n_radius, n_radius, n_radius],
            },
            f"{id_prefix}nucleus",
            "Glowing nucleus",
        ))
        result.append(self._step(
            "apply_material",
            {
                "target": f"{id_prefix}Nucleus",
                "color": n_color,
                "emissive": n_color,
                "emissive_intensity": 1.8,
                "roughness": 0.3,
            },
            f"{id_prefix}nucleus_mat",
            "Nucleus emissive material",
        ))

        # Orbits + electrons. Each orbit is a thin torus rotated to a different
        # plane so the shells read as 3D rather than coplanar rings.
        for i in range(electrons):
            # Stagger orbit plane rotations around Z and X for a shell look.
            rz = (i / max(1, electrons)) * math.pi
            rx = (i / max(1, electrons)) * math.pi * 0.5
            orbit_name = f"{id_prefix}Orbit_{i + 1}"
            result.append(self._step(
                "create_object",
                {
                    "geometry_type": "torus",
                    "name": orbit_name,
                    "position": [0, 0, 0],
                    "scale": [1, 1, 1],
                },
                f"{id_prefix}orbit_{i}",
                f"Orbit {i + 1}",
            ))
            # Torus default radius 0.6 / tube 0.2; scale uniformly to o_radius.
            # We scale X/Y by o_radius / 0.6 and Z (tube) by 0.05 to keep it thin.
            scale_factor = o_radius / 0.6
            result.append(self._step(
                "transform_object",
                {
                    "target": orbit_name,
                    "rotation": [rx, 0, rz],
                    "scale": [scale_factor, scale_factor, 0.08],
                    "relative": False,
                },
                f"{id_prefix}orbit_tf_{i}",
                f"Rotate orbit {i + 1}",
            ))
            result.append(self._step(
                "apply_material",
                {
                    "target": orbit_name,
                    "color": "#3a4250",
                    "metalness": 0.6,
                    "roughness": 0.4,
                    "opacity": 0.5,
                },
                f"{id_prefix}orbit_mat_{i}",
                f"Orbit {i + 1} ring material",
            ))

            # Electron placed on the orbit at azimuth 0 in the orbit's local plane.
            # Approximate position: rotate (o_radius, 0, 0) by rz around Z then rx around X.
            ex = o_radius * math.cos(rz)
            ey = o_radius * math.sin(rz) * math.cos(rx)
            ez = o_radius * math.sin(rz) * math.sin(rx)
            electron_name = f"{id_prefix}Electron_{i + 1}"
            result.append(self._step(
                "create_object",
                {
                    "geometry_type": "sphere",
                    "name": electron_name,
                    "position": [ex, ey, ez],
                    "scale": [0.18, 0.18, 0.18],
                },
                f"{id_prefix}electron_{i}",
                f"Electron {i + 1}",
            ))
            result.append(self._step(
                "apply_material",
                {
                    "target": electron_name,
                    "color": e_color,
                    "emissive": e_color,
                    "emissive_intensity": 2.2,
                    "roughness": 0.2,
                },
                f"{id_prefix}electron_mat_{i}",
                f"Electron {i + 1} emissive material",
            ))

        # Dark backdrop so the emissive shells pop.
        result.append(self._step(
            "set_background",
            {"color": "#05060a"},
            f"{id_prefix}bg",
            "Dark backdrop",
        ))
        result.append(self._step(
            "add_light",
            {"light_type": "ambient", "name": f"{id_prefix}Ambient", "color": "#556677", "intensity": 0.6, "position": [0, 0, 0]},
            f"{id_prefix}ambient",
            "Soft ambient light",
        ))
        return result


# ---------------------------------------------------------------------------
# Architecture skills (extended)
# ---------------------------------------------------------------------------

class BridgeSkill(SkillBase):
    """Build a suspension bridge: deck + piers + towers + cables + hangers."""

    name = "bridge"
    description = "Generate a suspension bridge with a deck, two piers, two towers, two main cables, and a row of vertical hanger cables."
    category = "architecture"
    icon = "bridge"

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "length": {"type": "number", "description": "Deck length (default 16)"},
                "deck_height": {"type": "number", "description": "Deck height above water (default 1.5)"},
                "tower_height": {"type": "number", "description": "Tower height above deck (default 4)"},
                "hangers": {"type": "integer", "description": "Vertical hanger cables per side (default 7)"},
            },
        }

    def build_steps(self, arguments: Dict[str, Any], id_prefix: str = "") -> List[TaskStep]:
        length = float(arguments.get("length", 16))
        deck_y = float(arguments.get("deck_height", 1.5))
        tower_h = float(arguments.get("tower_height", 4))
        hangers = max(2, min(14, int(arguments.get("hangers", 7))))
        result: List[TaskStep] = []
        half = length / 2
        # Tower positions: 25% in from each end.
        tower_x = half * 0.5

        # Deck
        result.append(self._step(
            "create_object",
            {
                "geometry_type": "box",
                "name": f"{id_prefix}Deck",
                "position": [0, deck_y, 0],
                "scale": [length, 0.2, 1.6],
            },
            f"{id_prefix}deck",
            "Bridge deck",
        ))
        result.append(self._step(
            "apply_material_preset",
            {"target": f"{id_prefix}Deck", "preset": "ceramic"},
            f"{id_prefix}deck_mat",
            "Deck material",
        ))

        # Piers (below deck, at tower positions)
        for i, sx in enumerate([-tower_x, tower_x]):
            name = f"{id_prefix}Pier_{i + 1}"
            result.append(self._step(
                "create_object",
                {
                    "geometry_type": "cylinder",
                    "name": name,
                    "position": [sx, deck_y / 2, 0],
                    "scale": [0.5, deck_y, 0.5],
                },
                f"{id_prefix}pier_{i}",
                f"Pier {i + 1}",
            ))
            result.append(self._step(
                "apply_material_preset",
                {"target": name, "preset": "ceramic"},
                f"{id_prefix}pier_mat_{i}",
                f"Pier {i + 1} material",
            ))

        # Towers (above deck)
        for i, sx in enumerate([-tower_x, tower_x]):
            name = f"{id_prefix}Tower_{i + 1}"
            result.append(self._step(
                "create_object",
                {
                    "geometry_type": "cylinder",
                    "name": name,
                    "position": [sx, deck_y + tower_h / 2, 0],
                    "scale": [0.3, tower_h, 0.3],
                },
                f"{id_prefix}tower_{i}",
                f"Tower {i + 1}",
            ))
            result.append(self._step(
                "apply_material_preset",
                {"target": name, "preset": "metal"},
                f"{id_prefix}tower_mat_{i}",
                f"Tower {i + 1} material",
            ))

        # Main cables: a thin box arched between the two tower tops, dipping
        # toward the deck at midspan. We approximate the catenary with a long,
        # thin, slightly downward-tilted box. One cable per side (front/back).
        cable_y_top = deck_y + tower_h
        for side_z in (-0.6, 0.6):
            name = f"{id_prefix}MainCable_{'front' if side_z < 0 else 'back'}"
            result.append(self._step(
                "create_object",
                {
                    "geometry_type": "box",
                    "name": name,
                    "position": [0, (cable_y_top + deck_y + 0.4) / 2, side_z],
                    "scale": [tower_x * 2, 0.06, 0.06],
                },
                f"{id_prefix}cable_{int(side_z * 10)}",
                f"Main cable (z={side_z})",
            ))
            result.append(self._step(
                "apply_material_preset",
                {"target": name, "preset": "metal"},
                f"{id_prefix}cable_mat_{int(side_z * 10)}",
                "Cable material",
            ))

        # Hangers: thin vertical boxes spaced between the towers.
        span = tower_x * 2
        spacing = span / (hangers + 1)
        for j in range(hangers):
            hx = -tower_x + spacing * (j + 1)
            for side_z in (-0.6, 0.6):
                name = f"{id_prefix}Hanger_{j + 1}_{'front' if side_z < 0 else 'back'}"
                result.append(self._step(
                    "create_object",
                    {
                        "geometry_type": "box",
                        "name": name,
                        "position": [hx, (cable_y_top + deck_y) / 2, side_z],
                        "scale": [0.04, cable_y_top - deck_y, 0.04],
                    },
                    f"{id_prefix}hanger_{j}_{int(side_z * 10)}",
                    f"Hanger {j + 1} (z={side_z})",
                ))
                result.append(self._step(
                    "apply_material_preset",
                    {"target": name, "preset": "metal"},
                    f"{id_prefix}hanger_mat_{j}_{int(side_z * 10)}",
                    f"Hanger {j + 1} material",
                ))

        # Water plane below the bridge for context.
        result.append(self._step(
            "create_object",
            {
                "geometry_type": "plane",
                "name": f"{id_prefix}Water",
                "position": [0, 0, 0],
                "scale": [length * 2, 1, length * 2],
            },
            f"{id_prefix}water",
            "Water plane",
        ))
        result.append(self._step(
            "apply_material",
            {
                "target": f"{id_prefix}Water",
                "color": "#1a3a5a",
                "metalness": 0.4,
                "roughness": 0.15,
                "opacity": 0.85,
            },
            f"{id_prefix}water_mat",
            "Water material",
        ))
        result.append(self._step(
            "transform_object",
            {
                "target": f"{id_prefix}Water",
                "rotation": [math.pi / 2, 0, 0],
                "relative": False,
            },
            f"{id_prefix}water_tf",
            "Lay water plane flat",
        ))

        # Lighting
        result.append(self._step(
            "add_light",
            {"light_type": "directional", "name": f"{id_prefix}Sun", "color": "#fff3d6", "intensity": 1.6, "position": [6, 8, 4]},
            f"{id_prefix}sun",
            "Sun light",
        ))
        result.append(self._step(
            "add_light",
            {"light_type": "ambient", "name": f"{id_prefix}Sky", "color": "#88aacc", "intensity": 0.4, "position": [0, 0, 0]},
            f"{id_prefix}sky",
            "Sky ambient",
        ))
        return result


# ---------------------------------------------------------------------------
# Layout skills (extended)
# ---------------------------------------------------------------------------

class ZenGardenSkill(SkillBase):
    """Build a zen garden: sand plane + rocks + rake lines."""

    name = "zen_garden"
    description = "Generate a zen garden with a raked sand plane, scattered rocks of varying sizes, and a grid of rake lines."
    category = "layout"
    icon = "sparkles"

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "size": {"type": "number", "description": "Garden side length (default 10)"},
                "rock_count": {"type": "integer", "description": "Number of rocks (default 5, max 12)"},
                "rake_lines": {"type": "integer", "description": "Number of rake lines (default 8, max 16)"},
                "sand_color": {"type": "string", "description": "Sand color (default #d9c9a3)"},
            },
        }

    def build_steps(self, arguments: Dict[str, Any], id_prefix: str = "") -> List[TaskStep]:
        import random
        rng = random.Random(arguments.get("seed", 7))
        size = float(arguments.get("size", 10))
        rock_count = max(1, min(12, int(arguments.get("rock_count", 5))))
        rake_lines = max(2, min(16, int(arguments.get("rake_lines", 8))))
        sand_color = str(arguments.get("sand_color", "#d9c9a3"))
        half = size / 2
        result: List[TaskStep] = []

        # Sand plane
        result.append(self._step(
            "create_object",
            {
                "geometry_type": "plane",
                "name": f"{id_prefix}Sand",
                "position": [0, 0, 0],
                "scale": [size, 1, size],
            },
            f"{id_prefix}sand",
            "Sand plane",
        ))
        result.append(self._step(
            "apply_material",
            {
                "target": f"{id_prefix}Sand",
                "color": sand_color,
                "roughness": 0.95,
                "metalness": 0.0,
            },
            f"{id_prefix}sand_mat",
            "Sand material",
        ))
        result.append(self._step(
            "transform_object",
            {
                "target": f"{id_prefix}Sand",
                "rotation": [math.pi / 2, 0, 0],
                "relative": False,
            },
            f"{id_prefix}sand_tf",
            "Lay sand plane flat",
        ))

        # Rocks: icosahedrons of varying sizes, kept inside the sand area.
        for i in range(rock_count):
            rx = rng.uniform(-half * 0.75, half * 0.75)
            rz = rng.uniform(-half * 0.75, half * 0.75)
            rscale = rng.uniform(0.25, 0.6)
            name = f"{id_prefix}Rock_{i + 1}"
            result.append(self._step(
                "create_object",
                {
                    "geometry_type": "icosahedron",
                    "name": name,
                    "position": [rx, rscale * 0.6, rz],
                    "scale": [rscale, rscale * 0.7, rscale],
                },
                f"{id_prefix}rock_{i}",
                f"Rock {i + 1}",
            ))
            result.append(self._step(
                "apply_material_preset",
                {"target": name, "preset": "ceramic", "color_override": "#5b5447"},
                f"{id_prefix}rock_mat_{i}",
                f"Rock {i + 1} material",
            ))
            # Slight random rotation so the icosahedrons don't all look identical.
            result.append(self._step(
                "transform_object",
                {
                    "target": name,
                    "rotation": [rng.uniform(0, 0.4), rng.uniform(0, math.pi * 2), rng.uniform(0, 0.4)],
                    "relative": False,
                },
                f"{id_prefix}rock_tf_{i}",
                f"Rotate rock {i + 1}",
            ))

        # Rake lines: thin parallel boxes sitting just above the sand.
        # They run along X, spaced along Z, evoking the classic karesansui pattern.
        line_spacing = (size * 0.85) / max(1, rake_lines - 1) if rake_lines > 1 else 0
        start_z = -size * 0.425
        for j in range(rake_lines):
            lz = start_z + j * line_spacing
            name = f"{id_prefix}RakeLine_{j + 1}"
            result.append(self._step(
                "create_object",
                {
                    "geometry_type": "box",
                    "name": name,
                    "position": [0, 0.012, lz],
                    "scale": [size * 0.92, 0.012, 0.04],
                },
                f"{id_prefix}rake_{j}",
                f"Rake line {j + 1}",
            ))
            result.append(self._step(
                "apply_material",
                {
                    "target": name,
                    "color": "#b8a880",
                    "roughness": 0.95,
                    "metalness": 0.0,
                },
                f"{id_prefix}rake_mat_{j}",
                f"Rake line {j + 1} material",
            ))

        # Soft daylight
        result.append(self._step(
            "add_light",
            {"light_type": "directional", "name": f"{id_prefix}Sun", "color": "#fff4dc", "intensity": 1.4, "position": [4, 7, 3]},
            f"{id_prefix}sun",
            "Warm sun",
        ))
        result.append(self._step(
            "add_light",
            {"light_type": "ambient", "name": f"{id_prefix}Sky", "color": "#c8d8e8", "intensity": 0.5, "position": [0, 0, 0]},
            f"{id_prefix}sky",
            "Sky ambient",
        ))
        result.append(self._step(
            "set_background",
            {"color": "#1a1c22"},
            f"{id_prefix}bg",
            "Muted backdrop",
        ))
        return result


# ---------------------------------------------------------------------------
# Mechanical & character skills
# ---------------------------------------------------------------------------

class GearAssemblySkill(SkillBase):
    """Build an interlocking gear assembly: flat cylinders with radial teeth."""

    name = "gear_assembly"
    description = "Generate a row of interlocking gears with radial teeth that visually mesh between adjacent gears."
    category = "abstract"
    icon = "cog"

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "gear_count": {"type": "integer", "description": "Number of gears in the row (default 3, max 6)"},
                "teeth": {"type": "integer", "description": "Teeth per gear (default 12, max 24)"},
                "radius": {"type": "number", "description": "Gear radius (default 1.2)"},
                "material_preset": {"type": "string", "description": "Material preset for gears (default metal)"},
            },
        }

    def build_steps(self, arguments: Dict[str, Any], id_prefix: str = "") -> List[TaskStep]:
        gear_count = max(2, min(6, int(arguments.get("gear_count", 3))))
        teeth = max(6, min(24, int(arguments.get("teeth", 12))))
        radius = float(arguments.get("radius", 1.2))
        preset = str(arguments.get("material_preset", "metal"))
        result: List[TaskStep] = []
        tooth_angle = (math.pi * 2) / teeth
        tooth_half = tooth_angle * 0.5
        # Adjacent gears touch at the perimeter so teeth visually mesh.
        spacing = radius * 2

        for g in range(gear_count):
            gx = g * spacing
            gear_name = f"{id_prefix}Gear_{g + 1}"
            # Disk body — flat cylinder with its long axis (Y) rotated to Z so
            # the gear lies in the XY plane (like a wall clock).
            result.append(self._step(
                "create_object",
                {
                    "geometry_type": "cylinder",
                    "name": gear_name,
                    "position": [gx, 0, 0],
                    "scale": [radius, 0.15, radius],
                },
                f"{id_prefix}gear_{g}",
                f"Gear {g + 1} disk",
            ))
            result.append(self._step(
                "transform_object",
                {"target": gear_name, "rotation": [math.pi / 2, 0, 0], "relative": False},
                f"{id_prefix}gear_tf_{g}",
                f"Orient gear {g + 1} in plane",
            ))
            result.append(self._step(
                "apply_material_preset",
                {"target": gear_name, "preset": preset},
                f"{id_prefix}gear_mat_{g}",
                f"Gear {g + 1} material",
            ))

            # Teeth: small radial boxes. Adjacent gears are phase-offset by
            # half a tooth so the teeth interlock visually.
            phase = (g % 2) * tooth_half
            for t in range(teeth):
                ang = t * tooth_angle + phase
                tx = gx + math.cos(ang) * radius
                ty = math.sin(ang) * radius
                tooth_name = f"{id_prefix}Gear_{g + 1}_Tooth_{t + 1}"
                result.append(self._step(
                    "create_object",
                    {
                        "geometry_type": "box",
                        "name": tooth_name,
                        "position": [tx, ty, 0],
                        "scale": [0.12, 0.25, 0.18],
                    },
                    f"{id_prefix}tooth_{g}_{t}",
                    f"Gear {g + 1} tooth {t + 1}",
                ))
                # Rotate so the tooth's long axis (Y) points radially outward.
                result.append(self._step(
                    "transform_object",
                    {"target": tooth_name, "rotation": [0, 0, ang - math.pi / 2], "relative": False},
                    f"{id_prefix}tooth_tf_{g}_{t}",
                    f"Tooth {t + 1} rotation",
                ))
                result.append(self._step(
                    "apply_material_preset",
                    {"target": tooth_name, "preset": preset},
                    f"{id_prefix}tooth_mat_{g}_{t}",
                    f"Tooth {t + 1} material",
                ))

            # Axle through the gear center for visual clarity.
            axle_name = f"{id_prefix}Axle_{g + 1}"
            result.append(self._step(
                "create_object",
                {
                    "geometry_type": "cylinder",
                    "name": axle_name,
                    "position": [gx, 0, 0],
                    "scale": [0.08, 0.4, 0.08],
                },
                f"{id_prefix}axle_{g}",
                f"Axle {g + 1}",
            ))
            result.append(self._step(
                "transform_object",
                {"target": axle_name, "rotation": [math.pi / 2, 0, 0], "relative": False},
                f"{id_prefix}axle_tf_{g}",
                f"Orient axle {g + 1}",
            ))
            result.append(self._step(
                "apply_material_preset",
                {"target": axle_name, "preset": "metal"},
                f"{id_prefix}axle_mat_{g}",
                f"Axle {g + 1} material",
            ))

        # Workshop backdrop + key light to read the metal surfaces.
        result.append(self._step(
            "set_background",
            {"color": "#0d1117"},
            f"{id_prefix}bg",
            "Workshop backdrop",
        ))
        result.append(self._step(
            "add_light",
            {"light_type": "directional", "name": f"{id_prefix}Key", "color": "#fff3d6", "intensity": 1.4, "position": [4, 6, 5]},
            f"{id_prefix}key",
            "Key light",
        ))
        result.append(self._step(
            "add_light",
            {"light_type": "ambient", "name": f"{id_prefix}Ambient", "color": "#445566", "intensity": 0.5, "position": [0, 0, 0]},
            f"{id_prefix}ambient",
            "Ambient fill",
        ))
        return result


class MoleculeSkill(SkillBase):
    """Build a ball-and-stick molecule: central atom with satellite atoms and bonds."""

    name = "molecule"
    description = "Generate a ball-and-stick molecule with a central sphere, satellite atoms arranged evenly around it, and bond cylinders connecting each satellite to the center."
    category = "abstract"
    icon = "atom"

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "satellites": {"type": "integer", "description": "Number of satellite atoms (default 4, max 8)"},
                "bond_length": {"type": "number", "description": "Distance from center to each satellite (default 2.0)"},
                "center_color": {"type": "string", "description": "Central atom color (default #FF5555)"},
                "satellite_color": {"type": "string", "description": "Satellite atom color (default #5588FF)"},
                "bond_color": {"type": "string", "description": "Bond cylinder color (default #AAAAAA)"},
            },
        }

    def build_steps(self, arguments: Dict[str, Any], id_prefix: str = "") -> List[TaskStep]:
        satellites = max(2, min(8, int(arguments.get("satellites", 4))))
        bond_length = float(arguments.get("bond_length", 2.0))
        c_color = str(arguments.get("center_color", "#FF5555"))
        s_color = str(arguments.get("satellite_color", "#5588FF"))
        b_color = str(arguments.get("bond_color", "#AAAAAA"))
        result: List[TaskStep] = []

        # Central atom
        result.append(self._step(
            "create_object",
            {
                "geometry_type": "sphere",
                "name": f"{id_prefix}Center",
                "position": [0, 0, 0],
                "scale": [0.6, 0.6, 0.6],
            },
            f"{id_prefix}center",
            "Central atom",
        ))
        result.append(self._step(
            "apply_material",
            {"target": f"{id_prefix}Center", "color": c_color, "roughness": 0.4, "metalness": 0.1},
            f"{id_prefix}center_mat",
            "Central atom material",
        ))

        # Satellites distributed evenly in the XZ plane and bonds linking
        # each one to the origin.
        for i in range(satellites):
            theta = (math.tau / satellites) * i
            sx = math.cos(theta) * bond_length
            sz = math.sin(theta) * bond_length

            sat_name = f"{id_prefix}Satellite_{i + 1}"
            result.append(self._step(
                "create_object",
                {
                    "geometry_type": "sphere",
                    "name": sat_name,
                    "position": [sx, 0, sz],
                    "scale": [0.4, 0.4, 0.4],
                },
                f"{id_prefix}sat_{i}",
                f"Satellite atom {i + 1}",
            ))
            result.append(self._step(
                "apply_material",
                {"target": sat_name, "color": s_color, "roughness": 0.4, "metalness": 0.1},
                f"{id_prefix}sat_mat_{i}",
                f"Satellite {i + 1} material",
            ))

            # Bond cylinder from origin to satellite. Default cylinder axis
            # is Y; rotate so the axis points along (cos theta, 0, sin theta).
            bond_name = f"{id_prefix}Bond_{i + 1}"
            result.append(self._step(
                "create_object",
                {
                    "geometry_type": "cylinder",
                    "name": bond_name,
                    "position": [sx / 2, 0, sz / 2],
                    "scale": [0.08, bond_length, 0.08],
                },
                f"{id_prefix}bond_{i}",
                f"Bond {i + 1}",
            ))
            result.append(self._step(
                "transform_object",
                {"target": bond_name, "rotation": [0, -theta, -math.pi / 2], "relative": False},
                f"{id_prefix}bond_tf_{i}",
                f"Bond {i + 1} rotation",
            ))
            result.append(self._step(
                "apply_material",
                {"target": bond_name, "color": b_color, "roughness": 0.6, "metalness": 0.3},
                f"{id_prefix}bond_mat_{i}",
                f"Bond {i + 1} material",
            ))

        # Soft studio lighting and a dark backdrop so the colors read.
        result.append(self._step(
            "set_background",
            {"color": "#0a0c12"},
            f"{id_prefix}bg",
            "Dark backdrop",
        ))
        result.append(self._step(
            "add_light",
            {"light_type": "directional", "name": f"{id_prefix}Key", "color": "#ffffff", "intensity": 1.2, "position": [5, 6, 4]},
            f"{id_prefix}key",
            "Key light",
        ))
        result.append(self._step(
            "add_light",
            {"light_type": "ambient", "name": f"{id_prefix}Ambient", "color": "#556677", "intensity": 0.5, "position": [0, 0, 0]},
            f"{id_prefix}ambient",
            "Ambient fill",
        ))
        return result


class SnowmanSkill(SkillBase):
    """Build a classic snowman: stacked spheres with a carrot nose, eyes, arms, and a top hat."""

    name = "snowman"
    description = "Generate a snowman from three stacked white spheres with a carrot nose, black coal eyes, stick arms, and a top hat."
    category = "nature"
    icon = "snowflake"

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "height": {"type": "number", "description": "Total snowman height (default 3.0)"},
                "nose_color": {"type": "string", "description": "Carrot nose color (default #FF6A00)"},
                "hat_color": {"type": "string", "description": "Top hat color (default #1a1a1a)"},
            },
        }

    def build_steps(self, arguments: Dict[str, Any], id_prefix: str = "") -> List[TaskStep]:
        h = float(arguments.get("height", 3.0))
        nose_color = str(arguments.get("nose_color", "#FF6A00"))
        hat_color = str(arguments.get("hat_color", "#1a1a1a"))
        result: List[TaskStep] = []

        # Three stacked spheres (bottom > middle > top) with slight overlap.
        # Radii are tuned so total height from ground to hat top is roughly h.
        r1 = h * 0.225  # bottom sphere radius
        r2 = h * 0.175  # middle sphere radius
        r3 = h * 0.125  # top sphere radius
        y1 = r1
        y2 = h * 0.60
        y3 = h * 0.875

        # Body spheres
        for label, ry, rr in (("Bottom", y1, r1), ("Middle", y2, r2), ("Top", y3, r3)):
            name = f"{id_prefix}{label}"
            result.append(self._step(
                "create_object",
                {
                    "geometry_type": "sphere",
                    "name": name,
                    "position": [0, ry, 0],
                    "scale": [rr, rr, rr],
                },
                f"{id_prefix}body_{label.lower()}",
                f"{label} body sphere",
            ))
            result.append(self._step(
                "apply_material",
                {"target": name, "color": "#f5f7fa", "roughness": 0.85, "metalness": 0.0},
                f"{id_prefix}body_mat_{label.lower()}",
                f"{label} snow material",
            ))

        # Carrot nose — cone attached to the middle sphere, pointing forward (+Z).
        # Default cone has its tip at +Y; rotate around X by -pi/2 to point along +Z.
        nose_name = f"{id_prefix}Nose"
        result.append(self._step(
            "create_object",
            {
                "geometry_type": "cone",
                "name": nose_name,
                "position": [0, y2 + h * 0.05, r2 + h * 0.10],
                "scale": [h * 0.05, h * 0.20, h * 0.05],
            },
            f"{id_prefix}nose",
            "Carrot nose",
        ))
        result.append(self._step(
            "transform_object",
            {"target": nose_name, "rotation": [-math.pi / 2, 0, 0], "relative": False},
            f"{id_prefix}nose_tf",
            "Orient nose forward",
        ))
        result.append(self._step(
            "apply_material",
            {"target": nose_name, "color": nose_color, "roughness": 0.6, "metalness": 0.0},
            f"{id_prefix}nose_mat",
            "Carrot material",
        ))

        # Coal eyes — two small black spheres on the front of the top sphere.
        for side, ex in (("L", -h * 0.05), ("R", h * 0.05)):
            eye_name = f"{id_prefix}Eye_{side}"
            result.append(self._step(
                "create_object",
                {
                    "geometry_type": "sphere",
                    "name": eye_name,
                    "position": [ex, y3 + h * 0.07, r3 * 0.85],
                    "scale": [h * 0.025, h * 0.025, h * 0.025],
                },
                f"{id_prefix}eye_{side}",
                f"Eye {side}",
            ))
            result.append(self._step(
                "apply_material",
                {"target": eye_name, "color": "#0a0a0a", "roughness": 0.5, "metalness": 0.2},
                f"{id_prefix}eye_mat_{side}",
                f"Eye {side} material",
            ))

        # Stick arms — thin horizontal cylinders protruding from the middle sphere.
        for side, ax in (("L", -h * 0.30), ("R", h * 0.30)):
            arm_name = f"{id_prefix}Arm_{side}"
            result.append(self._step(
                "create_object",
                {
                    "geometry_type": "cylinder",
                    "name": arm_name,
                    "position": [ax, y2 + h * 0.05, 0],
                    "scale": [h * 0.04, h * 0.40, h * 0.04],
                },
                f"{id_prefix}arm_{side}",
                f"Arm {side}",
            ))
            result.append(self._step(
                "transform_object",
                {"target": arm_name, "rotation": [0, 0, math.pi / 2], "relative": False},
                f"{id_prefix}arm_tf_{side}",
                f"Orient arm {side} horizontally",
            ))
            result.append(self._step(
                "apply_material",
                {"target": arm_name, "color": "#5a3a1a", "roughness": 0.9, "metalness": 0.0},
                f"{id_prefix}arm_mat_{side}",
                f"Arm {side} material",
            ))

        # Top hat — brim (flat cylinder) + top (tall box) sitting on the top sphere.
        brim_name = f"{id_prefix}HatBrim"
        result.append(self._step(
            "create_object",
            {
                "geometry_type": "cylinder",
                "name": brim_name,
                "position": [0, y3 + r3 + h * 0.02, 0],
                "scale": [h * 0.22, h * 0.04, h * 0.22],
            },
            f"{id_prefix}hat_brim",
            "Hat brim",
        ))
        result.append(self._step(
            "apply_material",
            {"target": brim_name, "color": hat_color, "roughness": 0.6, "metalness": 0.1},
            f"{id_prefix}hat_brim_mat",
            "Hat brim material",
        ))
        top_name = f"{id_prefix}HatTop"
        result.append(self._step(
            "create_object",
            {
                "geometry_type": "box",
                "name": top_name,
                "position": [0, y3 + r3 + h * 0.13, 0],
                "scale": [h * 0.15, h * 0.18, h * 0.15],
            },
            f"{id_prefix}hat_top",
            "Hat top",
        ))
        result.append(self._step(
            "apply_material",
            {"target": top_name, "color": hat_color, "roughness": 0.6, "metalness": 0.1},
            f"{id_prefix}hat_top_mat",
            "Hat top material",
        ))

        # Soft daylight so the snow reads as snow.
        result.append(self._step(
            "set_background",
            {"color": "#cfe0f0"},
            f"{id_prefix}bg",
            "Snowy sky backdrop",
        ))
        result.append(self._step(
            "add_light",
            {"light_type": "directional", "name": f"{id_prefix}Sun", "color": "#fff6e0", "intensity": 1.5, "position": [4, 7, 3]},
            f"{id_prefix}sun",
            "Sun light",
        ))
        result.append(self._step(
            "add_light",
            {"light_type": "ambient", "name": f"{id_prefix}Sky", "color": "#a8c4e0", "intensity": 0.7, "position": [0, 0, 0]},
            f"{id_prefix}sky",
            "Sky ambient",
        ))
        return result


# ---------------------------------------------------------------------------
# Skill registry
# ---------------------------------------------------------------------------

class SkillRegistry:
    """Manages skill registration and lookup."""

    def __init__(self):
        self._skills: Dict[str, SkillBase] = {}

    def register(self, skill: SkillBase) -> None:
        if not skill.name:
            raise ValueError(f"Skill {skill.__class__.__name__} is missing name")
        self._skills[skill.name] = skill

    def get(self, name: str) -> Optional[SkillBase]:
        return self._skills.get(name)

    def all(self) -> List[SkillBase]:
        return list(self._skills.values())

    def descriptors(self) -> List[SkillDescriptor]:
        return [s.descriptor() for s in self._skills.values()]

    def schemas(self) -> List[Dict[str, Any]]:
        return [
            {"name": s.name, "description": s.description, "category": s.category, "parameters": s.schema()}
            for s in self._skills.values()
        ]


def build_default_registry() -> SkillRegistry:
    """Build the default skill registry with all built-in skills."""
    reg = SkillRegistry()
    reg.register(SpiralStaircaseSkill())
    reg.register(ColonnadeSkill())
    reg.register(ForestSkill())
    reg.register(CrystalGardenSkill())
    reg.register(DNAHelixSkill())
    reg.register(SpiralGalaxySkill())
    reg.register(StudioLightingSkill())
    reg.register(AtomSkill())
    reg.register(BridgeSkill())
    reg.register(ZenGardenSkill())
    reg.register(GearAssemblySkill())
    reg.register(MoleculeSkill())
    reg.register(SnowmanSkill())
    return reg
