"""Agent scene intelligence tools.

Gives the Agent the ability to "see" the current scene and reason about it
spatially and aesthetically, plus propose creative next steps. These are
read-only tools that produce natural-language descriptions and structured
metrics — they do not mutate the scene.

1. ``DescribeSceneTool`` — generates a rich semantic description of the
   current scene: spatial layout (clustered / spread / stacked), color
   palette summary, lighting mood (bright / dim / dramatic / flat),
   composition balance (left/right weighting, vertical extent), and
   dominant geometry types. Returns a natural-language paragraph plus
   structured metrics the Agent can quote back to the user.
2. ``SuggestNextActionsTool`` — analyzes the scene state and proposes 3-5
   creative, actionable next steps with rationale. Wraps the central
   ``generate_suggestions`` engine so the tool surface and the post-turn
   proactive-suggestion flow share a single source of truth.

Both tools follow the standard ``ToolBase`` contract.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

from trigen.scene import Scene
from trigen.suggestions import generate_suggestions
from trigen.tools.base import ToolBase, ToolResult
from trigen.tools.scene_workflow_tools import (
    _estimate_polygons,
    _scene_bbox,
)


# ---------------------------------------------------------------------------
# Helpers shared by DescribeSceneTool
# ---------------------------------------------------------------------------


def _hex_to_rgb(hex_str: str) -> List[int]:
    """Parse a #RRGGBB string to [r, g, b] ints in 0-255."""
    s = (hex_str or "").lstrip("#")
    if len(s) != 6:
        return [200, 200, 200]
    try:
        return [int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)]
    except ValueError:
        return [200, 200, 200]


def _rgb_to_hsl(r: int, g: int, b: int) -> List[float]:
    """Convert RGB (0-255) to HSL (h in degrees, s/l in 0-1)."""
    rf, gf, bf = r / 255.0, g / 255.0, b / 255.0
    mx, mn = max(rf, gf, bf), min(rf, gf, bf)
    l = (mx + mn) / 2.0
    if mx == mn:
        return [0.0, 0.0, l]
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
    return [h, s, l]


def _hue_name(h: float) -> str:
    """Map a hue angle (degrees) to a coarse color family name."""
    if h < 15 or h >= 345:
        return "red"
    if h < 45:
        return "orange"
    if h < 70:
        return "yellow"
    if h < 100:
        return "yellow-green"
    if h < 160:
        return "green"
    if h < 200:
        return "cyan"
    if h < 260:
        return "blue"
    if h < 290:
        return "purple"
    return "magenta"


def _classify_lighting_mood(scene: Scene) -> Dict[str, Any]:
    """Classify the scene lighting as a coarse mood label + rationale.

    Considers light count, light types, intensity balance, and the
    background's tonal lightness.
    """
    lights = scene.lights
    n = len(lights)
    total_intensity = sum(float(getattr(l, "intensity", 0.0)) for l in lights)
    has_ambient = any(l.type == "ambient" for l in lights)
    has_directional = any(l.type == "directional" for l in lights)
    has_spot = any(l.type == "spot" for l in lights)
    bg_l = _rgb_to_hsl(*_hex_to_rgb(scene.background))[2]

    if n == 0:
        mood = "unlit"
        rationale = "No lights are present — the scene relies on ambient/material emission only."
    elif n == 1 and has_ambient:
        mood = "flat"
        rationale = "A single ambient light flattens depth — no directional shading."
    elif n >= 4 and total_intensity > 4.0:
        mood = "bright"
        rationale = f"{n} lights totaling ~{total_intensity:.1f} intensity — well-illuminated."
    elif has_spot and total_intensity < 3.0:
        mood = "dramatic"
        rationale = "Spot lighting with restrained intensity creates focused pools of light."
    elif has_directional and has_ambient:
        mood = "balanced"
        rationale = "Directional key + ambient fill yields a balanced key/fill rig."
    elif total_intensity < 1.5:
        mood = "dim"
        rationale = f"Low total intensity ({total_intensity:.1f}) — scene reads as dimly lit."
    elif bg_l < 0.2:
        mood = "moody"
        rationale = "Bright lights against a dark backdrop produce high-contrast mood."
    else:
        mood = "neutral"
        rationale = f"{n} light(s) at ~{total_intensity:.1f} total intensity."

    return {
        "mood": mood,
        "light_count": n,
        "total_intensity": round(total_intensity, 2),
        "has_ambient": has_ambient,
        "has_directional": has_directional,
        "has_spot": has_spot,
        "background_lightness": round(bg_l, 2),
        "rationale": rationale,
    }


def _classify_spatial_layout(scene: Scene) -> Dict[str, Any]:
    """Classify the spatial arrangement: clustered / spread / stacked / linear."""
    objs = scene.objects
    if not objs:
        return {"layout": "empty", "rationale": "Scene is empty."}
    positions = [o.transform.position for o in objs]
    xs = [p[0] for p in positions]
    ys = [p[1] for p in positions]
    zs = [p[2] for p in positions]

    def _span(vals: List[float]) -> float:
        return max(vals) - min(vals) if vals else 0.0

    span_x = _span(xs)
    span_y = _span(ys)
    span_z = _span(zs)
    n = len(objs)

    # Compute average pairwise distance (sampled for performance on large scenes).
    sample = positions if n <= 12 else positions[:12]
    if len(sample) >= 2:
        total = 0.0
        count = 0
        for i in range(len(sample)):
            for j in range(i + 1, len(sample)):
                dx = sample[i][0] - sample[j][0]
                dy = sample[i][1] - sample[j][1]
                dz = sample[i][2] - sample[j][2]
                total += math.sqrt(dx * dx + dy * dy + dz * dz)
                count += 1
        avg_dist = total / count if count else 0.0
    else:
        avg_dist = 0.0

    # Heuristic classification.
    if span_y > max(span_x, span_z) * 1.5:
        layout = "stacked"
        rationale = f"Vertical span ({span_y:.1f}) dominates horizontal extents — a stacked/tower arrangement."
    elif span_x > max(span_y, span_z) * 2.0:
        layout = "linear-horizontal"
        rationale = f"X-axis span ({span_x:.1f}) dominates — a left-to-right linear arrangement."
    elif span_z > max(span_y, span_x) * 2.0:
        layout = "linear-depth"
        rationale = f"Z-axis span ({span_z:.1f}) dominates — a front-to-back linear arrangement."
    elif avg_dist < 2.0 and n >= 3:
        layout = "clustered"
        rationale = f"Objects are tightly grouped (avg distance ~{avg_dist:.1f})."
    elif avg_dist > 6.0:
        layout = "spread"
        rationale = f"Objects are widely scattered (avg distance ~{avg_dist:.1f})."
    else:
        layout = "balanced"
        rationale = f"Objects are reasonably distributed (avg distance ~{avg_dist:.1f})."

    # Centroid + bbox center offset.
    cx = sum(xs) / n
    cy = sum(ys) / n
    cz = sum(zs) / n

    return {
        "layout": layout,
        "rationale": rationale,
        "object_count": n,
        "centroid": [round(cx, 2), round(cy, 2), round(cz, 2)],
        "span": [round(span_x, 2), round(span_y, 2), round(span_z, 2)],
        "avg_pairwise_distance": round(avg_dist, 2),
    }


def _classify_composition_balance(scene: Scene) -> Dict[str, Any]:
    """Estimate left/right and front/back weight balance from object mass proxy.

    Uses uniform mass per object (proxy = 1.0) weighted by average scale to
    approximate visual weight on each side of the scene centroid.
    """
    objs = scene.objects
    if not objs:
        return {"balance": "empty", "rationale": "No objects to balance."}
    n = len(objs)
    cx = sum(o.transform.position[0] for o in objs) / n
    cz = sum(o.transform.position[2] for o in objs) / n

    left_mass = 0.0  # x < cx
    right_mass = 0.0  # x > cx
    front_mass = 0.0  # z > cz (closer to camera looking down -z)
    back_mass = 0.0  # z < cz
    for o in objs:
        # Mass proxy = average scale.
        s = o.transform.scale
        mass = (abs(s[0]) + abs(s[1]) + abs(s[2])) / 3.0
        if o.transform.position[0] < cx:
            left_mass += mass
        else:
            right_mass += mass
        if o.transform.position[2] > cz:
            front_mass += mass
        else:
            back_mass += mass

    total_lr = left_mass + right_mass
    total_fb = front_mass + back_mass
    lr_ratio = (left_mass / total_lr) if total_lr > 0 else 0.5
    fb_ratio = (front_mass / total_fb) if total_fb > 0 else 0.5

    def _bucket(ratio: float, low_label: str, high_label: str) -> str:
        if ratio < 0.35:
            return high_label
        if ratio > 0.65:
            return low_label
        return "even"

    lr_balance = _bucket(lr_ratio, "left-heavy", "right-heavy")
    fb_balance = _bucket(fb_ratio, "back-heavy", "front-heavy")

    if lr_balance == "even" and fb_balance == "even":
        balance = "centered"
        rationale = "Visual mass is distributed evenly across left/right and front/back."
    elif lr_balance == "even":
        balance = fb_balance
        rationale = f"Left/right mass is even, but the composition is {fb_balance}."
    elif fb_balance == "even":
        balance = lr_balance
        rationale = f"Front/back mass is even, but the composition is {lr_balance}."
    else:
        balance = f"{lr_balance} + {fb_balance}"
        rationale = f"Composition is {lr_balance} and {fb_balance}."

    return {
        "balance": balance,
        "rationale": rationale,
        "left_mass": round(left_mass, 2),
        "right_mass": round(right_mass, 2),
        "front_mass": round(front_mass, 2),
        "back_mass": round(back_mass, 2),
        "left_right_ratio": round(lr_ratio, 2),
        "front_back_ratio": round(fb_ratio, 2),
    }


def _summarize_palette(scene: Scene) -> Dict[str, Any]:
    """Summarize the scene's dominant material colors as a hue family."""
    colors = [o.material.color for o in scene.objects]
    if not colors:
        return {"count": 0, "dominant_hue": None, "palette_summary": "no objects"}
    hsls = [_rgb_to_hsl(*_hex_to_rgb(c)) for c in colors]
    avg_l = sum(h[2] for h in hsls) / len(hsls)
    avg_s = sum(h[1] for h in hsls) / len(hsls)
    # Hue histogram weighted by count.
    hue_buckets: Dict[str, int] = {}
    for h, s, _ in hsls:
        if s < 0.12:
            key = "neutral"
        else:
            key = _hue_name(h)
        hue_buckets[key] = hue_buckets.get(key, 0) + 1
    dominant = max(hue_buckets, key=hue_buckets.get)
    distinct = len({c.lower() for c in colors})

    if avg_l < 0.25:
        tone = "dark"
    elif avg_l > 0.75:
        tone = "light"
    else:
        tone = "mid-tone"
    if avg_s < 0.15:
        saturation = "muted/neutral"
    elif avg_s < 0.5:
        saturation = "moderately saturated"
    else:
        saturation = "highly saturated"

    summary = f"{distinct} distinct color(s), {tone} {saturation}, dominant family: {dominant}"
    return {
        "count": len(colors),
        "distinct_colors": distinct,
        "dominant_hue": dominant,
        "tone": tone,
        "saturation": saturation,
        "avg_lightness": round(avg_l, 2),
        "avg_saturation": round(avg_s, 2),
        "hue_histogram": hue_buckets,
        "palette_summary": summary,
    }


def _dominant_geometry_types(scene: Scene) -> Dict[str, Any]:
    """Return the geometry type distribution sorted by frequency."""
    counts: Dict[str, int] = {}
    for o in scene.objects:
        counts[o.geometry.type] = counts.get(o.geometry.type, 0) + 1
    if not counts:
        return {"dominant": None, "distribution": {}, "summary": "no objects"}
    ranked = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
    dominant = ranked[0][0]
    summary_parts = [f"{t} ({c})" for t, c in ranked[:3]]
    return {
        "dominant": dominant,
        "distribution": counts,
        "summary": ", ".join(summary_parts),
    }


def _build_description_paragraph(
    layout: Dict[str, Any],
    palette: Dict[str, Any],
    lighting: Dict[str, Any],
    balance: Dict[str, Any],
    geometry: Dict[str, Any],
    bbox: Dict[str, Any],
) -> str:
    """Compose a natural-language paragraph summarizing the scene."""
    parts: List[str] = []
    n = layout.get("object_count", 0)
    if n == 0:
        return "The scene is currently empty — no objects, lights, or composition to describe yet."

    parts.append(
        f"The scene contains {n} object(s) arranged in a {layout['layout']} layout "
        f"({layout['rationale']})"
    )
    if not bbox.get("empty", True):
        size = bbox.get("size", [0, 0, 0])
        center = bbox.get("center", [0, 0, 0])
        parts.append(
            f"spanning ~{size[0]:.1f} x {size[1]:.1f} x {size[2]:.1f} units "
            f"centered near ({center[0]:.1f}, {center[1]:.1f}, {center[2]:.1f})"
        )
    parts.append(f". Dominant geometry: {geometry['summary']}.")
    parts.append(f" Palette: {palette['palette_summary']}.")
    parts.append(f" Lighting reads as {lighting['mood']} — {lighting['rationale']}")
    parts.append(f" Composition is {balance['balance']} ({balance['rationale']}).")
    return " ".join(parts)


# ---------------------------------------------------------------------------
# 1. DescribeSceneTool — semantic scene description
# ---------------------------------------------------------------------------


_DESCRIBE_SCENE_PARAMS = {
    "type": "object",
    "properties": {
        "include_metrics": {
            "type": "boolean",
            "description": "If true (default), include the structured metrics block alongside the natural-language description.",
        },
        "focus": {
            "type": "string",
            "enum": ["all", "layout", "palette", "lighting", "balance", "geometry"],
            "description": "(Optional) limit the description to a single aspect. Default 'all'.",
        },
    },
}


class DescribeSceneTool(ToolBase):
    """Generate a rich semantic description of the current scene.

    Reads the scene and produces a natural-language paragraph covering
    spatial layout, color palette, lighting mood, composition balance, and
    dominant geometry types — plus a structured metrics block. Lets the
    Agent reason about the scene spatially and quote the description back
    to the user. Read-only.
    """

    name = "describe_scene"
    description = (
        "Generate a rich semantic description of the current scene: spatial "
        "layout (clustered / spread / stacked / linear), color palette "
        "summary, lighting mood (bright / dim / dramatic / flat / moody), "
        "composition balance (left/right and front/back weighting), and "
        "dominant geometry types. Returns a natural-language paragraph "
        "plus structured metrics. Read-only — does not mutate the scene. "
        "Use this to 'see' the scene before reasoning about next steps."
    )

    def schema(self) -> Dict[str, Any]:
        return _DESCRIBE_SCENE_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        include_metrics = bool(arguments.get("include_metrics", True))
        focus = str(arguments.get("focus", "all")).lower()
        if focus not in ("all", "layout", "palette", "lighting", "balance", "geometry"):
            focus = "all"

        layout = _classify_spatial_layout(scene)
        palette = _summarize_palette(scene)
        lighting = _classify_lighting_mood(scene)
        balance = _classify_composition_balance(scene)
        geometry = _dominant_geometry_types(scene)
        bbox = _scene_bbox(scene)

        if focus != "all":
            focused = {
                "layout": (layout, layout.get("rationale", "")),
                "palette": (palette, palette.get("palette_summary", "")),
                "lighting": (lighting, lighting.get("rationale", "")),
                "balance": (balance, balance.get("rationale", "")),
                "geometry": (geometry, geometry.get("summary", "")),
            }[focus]
            paragraph = f"[{focus}] " + focused[1]
            metrics: Dict[str, Any] = {focus: focused[0]}
        else:
            paragraph = _build_description_paragraph(
                layout, palette, lighting, balance, geometry, bbox
            )
            metrics = {
                "layout": layout,
                "palette": palette,
                "lighting": lighting,
                "composition_balance": balance,
                "geometry": geometry,
                "bounding_box": bbox,
                "polygon_estimate_total": sum(_estimate_polygons(o) for o in scene.objects),
            }

        data: Dict[str, Any] = {"description": paragraph, "focus": focus}
        if include_metrics:
            data["metrics"] = metrics

        return ToolResult(
            success=True,
            message=paragraph,
            deltas=[],
            data=data,
        )


# ---------------------------------------------------------------------------
# 2. SuggestNextActionsTool — actionable creative next-step proposals
# ---------------------------------------------------------------------------


_SUGGEST_NEXT_ACTIONS_PARAMS = {
    "type": "object",
    "properties": {
        "count": {
            "type": "integer",
            "description": "(Optional) maximum number of suggestions to return (default 3, capped at 5).",
        },
        "direction": {
            "type": "string",
            "enum": ["any", "lighting", "motion", "material", "composition", "population"],
            "description": (
                "(Optional) bias suggestions toward a creative direction. "
                "'lighting' emphasizes light rig changes, 'motion' adds animation, "
                "'material' recolors/restyles, 'composition' rebalances positions, "
                "'population' adds new content. Default 'any'."
            ),
        },
    },
}


def _matches_direction(suggestion: Dict[str, Any], direction: str) -> bool:
    """Heuristic: does a suggestion roughly align with the requested direction?"""
    if direction == "any":
        return True
    skill_or_tool = str(suggestion.get("skill_or_tool", "")).lower()
    args = suggestion.get("arguments", {}) or {}
    name = str(suggestion.get("name", "")).lower()
    desc = str(suggestion.get("description", "")).lower()
    if direction == "lighting":
        return any(k in (skill_or_tool + name + desc) for k in ("light", "studio", "rim", "fill"))
    if direction == "motion":
        return skill_or_tool.endswith("_animation") or "orbit" in skill_or_tool or "motion" in (name + desc)
    if direction == "material":
        return skill_or_tool in ("randomize_palette", "apply_material", "apply_material_preset", "style_scene") or "palette" in (name + desc)
    if direction == "composition":
        return skill_or_tool in ("arrange_layout", "align_objects", "distribute_objects", "group_objects") or "arrange" in (name + desc)
    if direction == "population":
        return skill_or_tool == "invoke_skill" or "add" in name or "build" in name or "plant" in name or "grow" in name
    return True


class SuggestNextActionsTool(ToolBase):
    """Analyze the scene and propose actionable creative next steps.

    Wraps the central ``generate_suggestions`` engine so the tool surface
    and the post-turn proactive-suggestion flow share a single source of
    truth. Returns 3-5 actionable suggestions with rationale, optionally
    biased toward a creative direction (lighting / motion / material /
    composition / population). Read-only.
    """

    name = "suggest_next_actions"
    description = (
        "Analyze the current scene state and propose 3-5 actionable creative "
        "next steps (e.g. 'add a key light from the upper right to balance "
        "shadows', 'group the furniture objects for easier manipulation', "
        "'try a cyberpunk material style'). Each suggestion includes a name, "
        "description, target skill_or_tool, suggested arguments, and rationale. "
        "Optionally bias the direction toward lighting / motion / material / "
        "composition / population. Read-only — does not mutate the scene."
    )

    def schema(self) -> Dict[str, Any]:
        return _SUGGEST_NEXT_ACTIONS_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        try:
            count = int(arguments.get("count", 3))
        except (TypeError, ValueError):
            count = 3
        count = max(1, min(5, count))
        direction = str(arguments.get("direction", "any")).lower()
        if direction not in ("any", "lighting", "motion", "material", "composition", "population"):
            direction = "any"

        # Generate the base suggestion set from the central engine.
        base = generate_suggestions(scene.to_dict())

        # Direction filtering: keep direction-matching suggestions first,
        # then fall back to the rest to fill out the requested count.
        if direction != "any":
            matched = [s for s in base if _matches_direction(s, direction)]
            others = [s for s in base if s not in matched]
            ordered = matched + others
        else:
            ordered = base

        suggestions = ordered[:count]

        return ToolResult(
            success=True,
            message=f"Proposed {len(suggestions)} next action(s)"
            + (f" biased toward {direction}" if direction != "any" else "")
            + ".",
            deltas=[],
            data={
                "suggestions": suggestions,
                "count": len(suggestions),
                "direction": direction,
            },
        )


__all__ = [
    "DescribeSceneTool",
    "SuggestNextActionsTool",
]
