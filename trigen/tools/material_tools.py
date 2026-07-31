"""Advanced material tools.

Provides multi-color gradient assignment (via per-object tags the frontend
renderer interpolates), material blending between two source objects, and
harmonious palette assignment across the whole scene. Each tool emits
standard scene deltas for incremental frontend updates.
"""

from __future__ import annotations

import colorsys
import random
from typing import Any, Dict, List, Optional

from trigen.scene import Scene, SceneObject
from trigen.tools.base import SceneDelta, ToolBase, ToolResult


# Curated harmonious palettes. Each entry is a list of hex colors that work
# well together; the randomize palette tool cycles through these.
PALETTE_FAMILIES: Dict[str, List[str]] = {
    "sunset": ["#FFB800", "#FF6B35", "#C73E1D", "#3E1F1F"],
    "ocean": ["#00F0FF", "#0077BE", "#003D5B", "#7DD3C0"],
    "forest": ["#2D8A3E", "#7ACC5A", "#3A5A2A", "#8A5A2B"],
    "neon": ["#FF00FF", "#00F0FF", "#FFB800", "#050510"],
    "pastel": ["#FFB3BA", "#BAFFC9", "#BAE1FF", "#FFFFBA", "#E6B3FF"],
    "monochrome": ["#0A0A0F", "#3A3A4A", "#888899", "#E8E8F0"],
    "earth": ["#8A5A2B", "#C87533", "#5A3A1A", "#9AA3AD", "#F5F1EA"],
    "gem": ["#00F0FF", "#9A3AFF", "#FFB800", "#ffffff", "#050510"],
}


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

_GRADIENT_PARAMS = {
    "type": "object",
    "properties": {
        "target": {"type": "string", "description": "Target object id or name"},
        "colors": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Ordered list of 2+ hex colors forming the gradient",
        },
        "axis": {
            "type": "string",
            "enum": ["x", "y", "z"],
            "description": "Gradient application axis (default y, top-to-bottom)",
        },
        "mode": {
            "type": "string",
            "enum": ["linear", "radial"],
            "description": "Gradient interpolation mode (default linear)",
        },
    },
    "required": ["target", "colors"],
}

_BLEND_PARAMS = {
    "type": "object",
    "properties": {
        "target_a": {"type": "string", "description": "First source object id or name"},
        "target_b": {"type": "string", "description": "Second source object id or name"},
        "factor": {"type": "number", "description": "Blend factor 0..1 where 0 = A and 1 = B (default 0.5)"},
        "apply_to": {
            "type": "string",
            "description": "Optional target object id or name to receive the blended result; if omitted, target_a is updated",
        },
    },
    "required": ["target_a", "target_b"],
}

_RANDOMIZE_PALETTE_PARAMS = {
    "type": "object",
    "properties": {
        "palette": {
            "type": "string",
            "description": "Palette family name (sunset/ocean/forest/neon/pastel/monochrome/earth/gem). If omitted, a palette is auto-selected.",
        },
        "target": {
            "type": "string",
            "description": "Optional object id or name to recolor; if omitted, all objects are recolored.",
        },
        "seed": {"type": "integer", "description": "Random seed for deterministic assignment (default 1)"},
        "preserve_metalness": {"type": "boolean", "description": "Keep each object's existing metalness/roughness (default true)"},
    },
    "required": [],
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _hex_to_rgb(hex_str: str) -> tuple:
    s = hex_str.lstrip("#")
    if len(s) != 6:
        return (200, 200, 200)
    try:
        return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))
    except ValueError:
        return (200, 200, 200)


def _rgb_to_hex(r: int, g: int, b: int) -> str:
    r = max(0, min(255, int(round(r))))
    g = max(0, min(255, int(round(g))))
    b = max(0, min(255, int(round(b))))
    return f"#{r:02x}{g:02x}{b:02x}"


def _lerp_color(c1: str, c2: str, t: float) -> str:
    """Linear interpolation between two hex colors in RGB space."""
    t = max(0.0, min(1.0, t))
    r1, g1, b1 = _hex_to_rgb(c1)
    r2, g2, b2 = _hex_to_rgb(c2)
    return _rgb_to_hex(r1 + (r2 - r1) * t, g1 + (g2 - g1) * t, b1 + (b2 - b1) * t)


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

class GradientMaterialTool(ToolBase):
    """Assign a multi-color gradient to an object via material tags.

    The frontend renderer reads the ``gradient`` tag on the object and
    interpolates vertex colors along the chosen axis. The base material
    color is set to the first color so non-gradient renderers still show
    a sensible result.
    """

    name = "gradient_material"
    description = "Apply a multi-color gradient material to an object by storing the color stops and axis in the object's material tags."

    def schema(self) -> Dict[str, Any]:
        return _GRADIENT_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        target_id = arguments.get("target", "")
        obj = scene.find_object(target_id)
        if not obj:
            return ToolResult(success=False, message=f"Object not found: {target_id}")

        colors = arguments.get("colors")
        if not isinstance(colors, list) or len(colors) < 2:
            return ToolResult(success=False, message="At least 2 colors are required")

        cleaned_colors: List[str] = []
        for c in colors:
            if isinstance(c, str):
                cleaned_colors.append(c if c.startswith("#") else f"#{c}")

        axis = str(arguments.get("axis", "y")).lower()
        if axis not in ("x", "y", "z"):
            axis = "y"
        mode = str(arguments.get("mode", "linear")).lower()
        if mode not in ("linear", "radial"):
            mode = "linear"

        # Set base color to the middle of the gradient as a sensible fallback
        mid_color = cleaned_colors[len(cleaned_colors) // 2]
        obj.material.color = mid_color

        # Remove any existing gradient tag entries
        obj.tags = [t for t in obj.tags if not t.startswith("gradient:")]
        # Encode the gradient as a single tag the frontend can parse:
        #   gradient:<axis>:<mode>:color1,color2,color3,...
        obj.tags.append(f"gradient:{axis}:{mode}:{','.join(cleaned_colors)}")

        return ToolResult(
            success=True,
            message=f"Applied {len(cleaned_colors)}-color {mode} gradient on {axis} axis to {obj.name}",
            deltas=[SceneDelta(action="update", target_id=obj.id, payload=obj.to_dict())],
            data={"object": obj.to_dict(), "gradient": {"axis": axis, "mode": mode, "colors": cleaned_colors}},
        )


class MaterialBlendTool(ToolBase):
    """Blend the materials of two source objects by a factor."""

    name = "material_blend"
    description = "Blend the materials of two source objects by a factor (0..1) and optionally apply the result to a third object."

    def schema(self) -> Dict[str, Any]:
        return _BLEND_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        a_id = str(arguments.get("target_a", ""))
        b_id = str(arguments.get("target_b", ""))
        a = scene.find_object(a_id)
        b = scene.find_object(b_id)
        if a is None:
            return ToolResult(success=False, message=f"Object not found: {a_id}")
        if b is None:
            return ToolResult(success=False, message=f"Object not found: {b_id}")

        factor = max(0.0, min(1.0, float(arguments.get("factor", 0.5))))
        apply_to = arguments.get("apply_to")
        target_obj = scene.find_object(str(apply_to)) if apply_to else a
        if target_obj is None:
            return ToolResult(success=False, message=f"apply_to target not found: {apply_to}")

        # Blend color
        blended_color = _lerp_color(a.material.color, b.material.color, factor)
        target_obj.material.color = blended_color
        # Blend emissive
        blended_emissive = _lerp_color(a.material.emissive, b.material.emissive, factor)
        target_obj.material.emissive = blended_emissive
        target_obj.material.emissive_intensity = (
            a.material.emissive_intensity * (1 - factor) + b.material.emissive_intensity * factor
        )
        # Blend numeric PBR params
        for field in ("metalness", "roughness", "opacity"):
            va = float(getattr(a.material, field))
            vb = float(getattr(b.material, field))
            setattr(target_obj.material, field, va * (1 - factor) + vb * factor)

        return ToolResult(
            success=True,
            message=f"Blended materials of {a.name} and {b.name} (factor {factor:.2f}) -> {target_obj.name}",
            deltas=[SceneDelta(action="update", target_id=target_obj.id, payload=target_obj.to_dict())],
            data={
                "object": target_obj.to_dict(),
                "blended_color": blended_color,
                "factor": factor,
                "source_a": a.name,
                "source_b": b.name,
            },
        )


class RandomizePaletteTool(ToolBase):
    """Assign a harmonious palette across one or all objects in the scene."""

    name = "randomize_palette"
    description = "Assign a harmonious color palette from a named family to one object or all objects, preserving optional material properties."

    def schema(self) -> Dict[str, Any]:
        return _RANDOMIZE_PALETTE_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        palette_name = arguments.get("palette")
        if not palette_name or palette_name not in PALETTE_FAMILIES:
            # Auto-select based on background darkness
            bg = scene.background.lower()
            bg_l = sum(_hex_to_rgb(bg)) / (3 * 255.0)
            palette_name = "gem" if bg_l < 0.2 else "sunset"
        colors = PALETTE_FAMILIES[palette_name]

        seed = int(arguments.get("seed", 1))
        rng = random.Random(seed)
        preserve = bool(arguments.get("preserve_metalness", True))

        target_id = arguments.get("target")
        if target_id and target_id != "all":
            targets: List[SceneObject] = []
            obj = scene.find_object(str(target_id))
            if obj is None:
                return ToolResult(success=False, message=f"Object not found: {target_id}")
            targets.append(obj)
        else:
            targets = list(scene.objects)

        if not targets:
            return ToolResult(success=False, message="No objects to recolor")

        deltas: List[SceneDelta] = []
        for i, obj in enumerate(targets):
            # Cycle through palette colors with a small random jitter for variety
            base_color = colors[i % len(colors)]
            # 30% chance to use a neighboring color for variety
            if rng.random() < 0.3 and len(colors) > 1:
                base_color = colors[(i + 1) % len(colors)]
            obj.material.color = base_color
            if not preserve:
                obj.material.metalness = rng.uniform(0.0, 0.4)
                obj.material.roughness = rng.uniform(0.2, 0.7)
            deltas.append(SceneDelta(action="update", target_id=obj.id, payload=obj.to_dict()))

        return ToolResult(
            success=True,
            message=f"Applied '{palette_name}' palette to {len(targets)} object(s)",
            deltas=deltas,
            data={"palette": palette_name, "colors": colors, "count": len(targets)},
        )
