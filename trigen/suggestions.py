"""Proactive creative suggestion engine.

Analyzes the current scene state (object count, geometry distribution,
material palette, lighting, color usage) and proposes 2-3 next-step
creative directions. Suggestions are intentionally non-prescriptive —
they surface creative affordances (skills, tools, palette tweaks) the
user might not have considered, rather than restating obvious actions.

The output is a list of suggestion dictionaries with the shape:
    {
        "name": str,              # short label
        "description": str,       # 1-2 sentence explanation
        "skill_or_tool": str,     # skill name or tool name to invoke
        "arguments": dict,        # suggested arguments
        "rationale": str,         # why this is suggested now
    }

Used by the frontend to render a "Suggestions" strip and by the Agent
to seed proactive continuation offers in offline mode.
"""

from __future__ import annotations

import math
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple


# Harmonious palette families keyed by a dominant hue name. Each family
# lists 3-5 hex colors that work well together so RandomizePaletteTool
# and the suggestion engine can propose coherent looks.
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

# Skills that make sense to suggest proactively, keyed by the trigger
# condition under which they are recommended.
SKILL_SUGGESTIONS: List[Dict[str, Any]] = [
    {
        "skill": "spiral_staircase",
        "name": "Add a spiral staircase",
        "description": "Generate a spiral staircase with a central pillar and spiraling steps.",
        "trigger": "empty_or_flat",
        "rationale": "Adds vertical architectural interest to the scene.",
    },
    {
        "skill": "colonnade",
        "name": "Build a colonnade",
        "description": "Row of marble columns topped by an entablature beam.",
        "trigger": "few_objects",
        "rationale": "Classical architectural element complements current geometry.",
    },
    {
        "skill": "forest",
        "name": "Plant a forest",
        "description": "Scatter trees across a ground plane with seasonal foliage colors.",
        "trigger": "outdoor",
        "rationale": "Fills the scene with organic content and ground cover.",
    },
    {
        "skill": "crystal_garden",
        "name": "Grow a crystal garden",
        "description": "Cluster of glowing crystals in a dark, foggy atmosphere.",
        "trigger": "dark_scene",
        "rationale": "Dark backdrop pairs naturally with emissive crystals.",
    },
    {
        "skill": "dna_helix",
        "name": "Construct a DNA helix",
        "description": "Double-helix of spheres with connecting rungs.",
        "trigger": "abstract",
        "rationale": "Abstract scientific structure adds visual intrigue.",
    },
    {
        "skill": "spiral_galaxy",
        "name": "Form a spiral galaxy",
        "description": "Spiral arms of emissive stars around a bright core.",
        "trigger": "dark_scene",
        "rationale": "Empty dark space is ideal for a galactic composition.",
    },
    {
        "skill": "studio_lighting",
        "name": "Set up studio lighting",
        "description": "Three-point key/fill/rim lighting rig with HDRI environment.",
        "trigger": "unlit_or_product",
        "rationale": "Balanced lighting brings out form and material depth.",
    },
]


def _hex_to_rgb(hex_str: str) -> Tuple[int, int, int]:
    """Parse a #RRGGBB string to (r, g, b) ints in 0-255."""
    s = hex_str.lstrip("#")
    if len(s) != 6:
        return (200, 200, 200)
    try:
        return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))
    except ValueError:
        return (200, 200, 200)


def _rgb_to_hsl(r: int, g: int, b: int) -> Tuple[float, float, float]:
    """Convert RGB (0-255) to HSL (h in degrees, s/l in 0-1)."""
    rf, gf, bf = r / 255.0, g / 255.0, b / 255.0
    mx, mn = max(rf, gf, bf), min(rf, gf, bf)
    l = (mx + mn) / 2.0
    if mx == mn:
        return (0.0, 0.0, l)
    d = mx - mn
    s = d / (2.0 - mx - mn) if l > 0.5 else d / (mx + mn)
    if mx == rf:
        h = ((gf - bf) / d) % 6
    elif mx == gf:
        h = (bf - rf) / d + 2.0
    else:
        h = (rf - gf) / d + 4.0
    h *= 60.0
    if h < 0:
        h += 360.0
    return (h, s, l)


def _color_distance(c1: str, c2: str) -> float:
    """Euclidean distance between two hex colors in RGB space."""
    r1, g1, b1 = _hex_to_rgb(c1)
    r2, g2, b2 = _hex_to_rgb(c2)
    return math.sqrt((r1 - r2) ** 2 + (g1 - g2) ** 2 + (b1 - b2) ** 2)


def _analyze_palette(colors: List[str]) -> Dict[str, Any]:
    """Summarize the dominant hues and tonal range of a color list."""
    if not colors:
        return {"count": 0, "dominant_hue": None, "is_dark": False, "is_monochrome": True}
    hsls = [_rgb_to_hsl(*_hex_to_rgb(c)) for c in colors]
    avg_l = sum(h[2] for h in hsls) / len(hsls)
    hues = [h[0] for h in hsls if h[1] > 0.1]
    if not hues:
        dominant_hue = None
        is_monochrome = True
    else:
        # Bin hues into 8 sectors to find the dominant sector
        buckets: Dict[int, int] = {}
        for hh in hues:
            key = int(hh / 45.0) % 8
            buckets[key] = buckets.get(key, 0) + 1
        dominant_bucket = max(buckets, key=buckets.get)
        dominant_hue = dominant_bucket * 45.0
        is_monochrome = len(buckets) <= 1
    return {
        "count": len(colors),
        "dominant_hue": dominant_hue,
        "is_dark": avg_l < 0.25,
        "is_monochrome": is_monochrome,
        "avg_lightness": avg_l,
    }


def _scene_is_dark(scene: Dict[str, Any]) -> bool:
    """Heuristic: dark background or dark dominant material colors."""
    bg = scene.get("background", "#0a0a0f")
    bg_l = _rgb_to_hsl(*_hex_to_rgb(bg))[2]
    if bg_l < 0.2:
        return True
    colors = [o.get("material", {}).get("color", "#cccccc") for o in scene.get("objects", [])]
    if colors:
        avg_l = sum(_rgb_to_hsl(*_hex_to_rgb(c))[2] for c in colors) / len(colors)
        return avg_l < 0.3
    return False


def _has_outdoor_ground(scene: Dict[str, Any]) -> bool:
    """Detect a plane/large ground object indicating an outdoor scene."""
    for o in scene.get("objects", []):
        if o.get("geometry", {}).get("type") == "plane":
            return True
    return False


def _has_only_primitives(scene: Dict[str, Any]) -> bool:
    """True when every object is a basic primitive (no assembly)."""
    primitives = {"box", "sphere", "cylinder", "cone", "torus", "plane"}
    objs = scene.get("objects", [])
    if not objs:
        return False
    return all(o.get("geometry", {}).get("type") in primitives for o in objs)


def _light_count(scene: Dict[str, Any]) -> int:
    return len(scene.get("lights", []))


def _pick_palette_for(scene: Dict[str, Any]) -> Tuple[str, List[str]]:
    """Choose the most fitting palette family based on scene mood."""
    if _scene_is_dark(scene):
        return ("gem", PALETTE_FAMILIES["gem"])
    if _has_outdoor_ground(scene):
        return ("forest", PALETTE_FAMILIES["forest"])
    return ("sunset", PALETTE_FAMILIES["sunset"])


def generate_suggestions(scene_dict: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Generate 2-3 proactive creative suggestions for the current scene.

    The selection strategy combines scene-size awareness, lighting state,
    color palette, and presence of architectural / natural elements.
    Suggestions are ordered by relevance and capped at 3 entries.
    """
    objs: List[Dict[str, Any]] = scene_dict.get("objects", [])
    obj_count = len(objs)
    is_dark = _scene_is_dark(scene_dict)
    has_ground = _has_outdoor_ground(scene_dict)
    only_primitives = _has_only_primitives(scene_dict)
    light_n = _light_count(scene_dict)

    palette_name, palette_colors = _pick_palette_for(scene_dict)
    material_colors = [o.get("material", {}).get("color", "#cccccc") for o in objs]
    palette_info = _analyze_palette(material_colors)

    suggestions: List[Dict[str, Any]] = []

    # 1. Empty / sparse scene — suggest a flagship skill
    if obj_count == 0:
        suggestions.append({
            "name": "Start with a crystal garden",
            "description": "Generate a cluster of glowing crystals in a dark atmosphere.",
            "skill_or_tool": "invoke_skill",
            "arguments": {"skill": "crystal_garden"},
            "rationale": "Empty scene — a single skill call creates a complete composition.",
        })
        suggestions.append({
            "name": "Build a spiral galaxy",
            "description": "Spiral arms of emissive stars around a bright core.",
            "skill_or_tool": "invoke_skill",
            "arguments": {"skill": "spiral_galaxy"},
            "rationale": "Empty scene — galactic composition fills the volume dramatically.",
        })
        return suggestions[:3]

    # 2. Dark scene with few objects — propose a glow/abstract skill
    if is_dark and obj_count < 8:
        suggestions.append({
            "name": "Add a spiral galaxy",
            "description": "Bright galactic core with spiral arms of emissive stars.",
            "skill_or_tool": "invoke_skill",
            "arguments": {"skill": "spiral_galaxy"},
            "rationale": "Dark scene + few objects — galactic structure is visually dominant.",
        })

    # 3. Outdoor / ground plane — suggest populating with a forest
    if has_ground and obj_count < 20:
        suggestions.append({
            "name": "Plant a forest",
            "description": "Scatter trees across the existing ground plane.",
            "skill_or_tool": "invoke_skill",
            "arguments": {"skill": "forest", "tree_count": 10},
            "rationale": "Ground plane present — trees anchor the landscape.",
        })

    # 4. Few primitives only — suggest an architectural element
    if only_primitives and obj_count <= 4:
        suggestions.append({
            "name": "Add a spiral staircase",
            "description": "Spiral staircase with central pillar and rising steps.",
            "skill_or_tool": "invoke_skill",
            "arguments": {"skill": "spiral_staircase", "steps": 14, "height": 5},
            "rationale": "Basic primitives benefit from an architectural focal point.",
        })

    # 5. Under-lit scene — propose studio lighting
    if light_n < 2 and obj_count >= 3:
        suggestions.append({
            "name": "Set up studio lighting",
            "description": "Three-point key/fill/rim rig with HDRI environment.",
            "skill_or_tool": "invoke_skill",
            "arguments": {"skill": "studio_lighting"},
            "rationale": "Scene has content but limited lighting — balanced rig brings depth.",
        })

    # 6. Monochrome palette — suggest a harmonious palette assignment
    if palette_info["count"] >= 3 and palette_info["is_monochrome"]:
        suggestions.append({
            "name": f"Apply a {palette_name} palette",
            "description": f"Recolor all objects with a harmonious {palette_name} palette.",
            "skill_or_tool": "randomize_palette",
            "arguments": {"palette": palette_name, "target": "all"},
            "rationale": "Materials are tonally uniform — a curated palette adds contrast.",
        })

    # 7. Many objects, no animation — suggest adding motion
    animated = sum(1 for o in objs if o.get("animation"))
    if obj_count >= 5 and animated == 0:
        # Pick the most central object as the orbit anchor target
        center_obj = min(objs, key=lambda o: sum(abs(v) for v in o.get("transform", {}).get("position", [0, 0, 0])))
        suggestions.append({
            "name": "Animate an object with an orbit",
            "description": f"Have '{center_obj.get('name', 'an object')}' orbit around the scene center.",
            "skill_or_tool": "orbit_animation",
            "arguments": {"target": center_obj.get("id", ""), "radius": 3.0, "duration": 6.0, "loop": True},
            "rationale": "Static scene — adding orbit motion creates instant visual energy.",
        })

    # 8. Fallback when nothing matched — propose a colonnade
    if not suggestions:
        suggestions.append({
            "name": "Build a colonnade",
            "description": "Row of marble columns topped by a horizontal beam.",
            "skill_or_tool": "invoke_skill",
            "arguments": {"skill": "colonnade", "count": 6},
            "rationale": "Adds structured architectural rhythm to the scene.",
        })

    return suggestions[:3]


def format_suggestions_brief(suggestions: List[Dict[str, Any]]) -> str:
    """Render suggestions as a short bullet list for chat display."""
    if not suggestions:
        return ""
    lines = ["Here are a few next-step ideas:"]
    for i, s in enumerate(suggestions, 1):
        lines.append(f"{i}. {s['name']} — {s['description']}")
    return "\n".join(lines)
