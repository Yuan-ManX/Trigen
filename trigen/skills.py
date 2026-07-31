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
    return reg
