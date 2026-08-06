"""Scene critique tool.

Gives the Agent a prescriptive "fresh eyes" review of the current scene.
Unlike ``analyze_scene`` (descriptive inventory) and ``describe_scene``
(semantic mood), this tool is *prescriptive*: it inspects the scene for
concrete, common design problems and proposes specific corrective tool
calls for each one. This lets the Agent act as its own editorial reviewer —
it can find a dim-scene problem and immediately fix it with a proposed
``add_light`` call, or a floating object and propose a ``transform_object``.

The engine is fully deterministic and offline: it runs on scene geometry
alone, so it works without an LLM API key and is easy to test.

Checks performed (each produces zero or more findings):
  1. Empty scene.
  2. Missing or sparse lighting (no lights / weak total intensity / glare).
  3. Floating objects (an object hovering well above the ground plane when
     a ground/plane object is present).
  4. Overlapping objects (approximate axis-aligned bounding-box overlap).
  5. Composition drift (objects clustered at the origin or scattered far
     apart into empty margins).
  6. Palette monotony (all objects share one material color).
  7. Background/object contrast (materials too close to the backdrop).

Findings are ranked by severity and capped so the output stays legible.
Each finding carries a ``proposed_fix`` recommending a concrete tool call.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

from trigen.scene import Scene
from trigen.tools.base import ToolBase, ToolResult


# ---------------------------------------------------------------------------
# Geometry extent estimation
# ---------------------------------------------------------------------------

# Maps a geometry type to its primary linear dimensions (half-extents).
# The dict values are callables that derive [half_x, half_y, half_z] from
# the geometry params. Falls back to a default box when the type is unknown
# or the params are missing.
def _sphere_r(params: Dict[str, Any]) -> float:
    return float(params.get("radius", 0.5))


def _box_extent(params: Dict[str, Any]) -> List[float]:
    return [
        float(params.get("width", 1.0)) / 2.0,
        float(params.get("height", 1.0)) / 2.0,
        float(params.get("depth", 1.0)) / 2.0,
    ]


def _cylinder_extent(params: Dict[str, Any]) -> List[float]:
    r = max(float(params.get("radiusTop", 0.5)), float(params.get("radiusBottom", 0.5)))
    return [r, float(params.get("height", 1.0)) / 2.0, r]


def _cone_extent(params: Dict[str, Any]) -> List[float]:
    r = float(params.get("radius", 0.5))
    return [r, float(params.get("height", 1.0)) / 2.0, r]


def _torus_extent(params: Dict[str, Any]) -> List[float]:
    r = float(params.get("radius", 0.5))
    tube = float(params.get("tube", 0.2))
    return [r + tube, tube, r + tube]


def _plane_extent(params: Dict[str, Any]) -> List[float]:
    return [
        float(params.get("width", 1.0)) / 2.0,
        0.0,
        float(params.get("height", 1.0)) / 2.0,
    ]


def _poly_extent(params: Dict[str, Any]) -> List[float]:
    r = _sphere_r(params)
    return [r, r, r]


def _ring_extent(params: Dict[str, Any]) -> List[float]:
    outer = float(params.get("outerRadius", 0.5))
    return [outer, 0.0, outer]


def _capsule_extent(params: Dict[str, Any]) -> List[float]:
    r = float(params.get("radius", 0.25))
    length = float(params.get("length", 1.0))
    return [r, length / 2.0 + r, r]


def _tube_extent(params: Dict[str, Any]) -> List[float]:
    r = float(params.get("radius", 0.25))
    return [r, r, r]


_EXTENT_FN = {
    "box": _box_extent,
    "sphere": lambda p: [_sphere_r(p)] * 3,
    "cylinder": _cylinder_extent,
    "cone": _cone_extent,
    "torus": _torus_extent,
    "torusKnot": _torus_extent,
    "plane": _plane_extent,
    "dodecahedron": _poly_extent,
    "icosahedron": _poly_extent,
    "octahedron": _poly_extent,
    "tetrahedron": _poly_extent,
    "ring": _ring_extent,
    "capsule": _capsule_extent,
    "tube": _tube_extent,
    "lathe": _poly_extent,
    "extrude": _poly_extent,
    "text": lambda p: [1.0, 0.5, 0.1],
    "spline": _tube_extent,
    "group": lambda p: [0.5, 0.5, 0.5],
}

_DEFAULT_EXTENT = [0.5, 0.5, 0.5]


def _estimate_extent(geo_type: str, params: Dict[str, Any]) -> List[float]:
    """Return approximate half-extents [x, y, z] for a geometry type."""
    fn = _EXTENT_FN.get(geo_type)
    if fn is None:
        return list(_DEFAULT_EXTENT)
    try:
        return [abs(float(v)) for v in fn(params or {})]
    except (TypeError, ValueError):
        return list(_DEFAULT_EXTENT)


def _aabb(obj: Any) -> Dict[str, List[float]]:
    """Compute the world-space axis-aligned bounding box of an object as a
    dict of {min, max} 3-vectors. Uses the geometry half-extents scaled by
    the object transform, centered on its position."""
    half = _estimate_extent(obj.geometry.type, obj.geometry.params or {})
    scale = list(obj.transform.scale or [1.0, 1.0, 1.0])
    pos = list(obj.transform.position or [0.0, 0.0, 0.0])
    hx = half[0] * abs(scale[0])
    hy = half[1] * abs(scale[1])
    hz = half[2] * abs(scale[2])
    return {
        "min": [pos[0] - hx, pos[1] - hy, pos[2] - hz],
        "max": [pos[0] + hx, pos[1] + hy, pos[2] + hz],
    }


def _overlap_ratio(a: Dict[str, List[float]], b: Dict[str, List[float]]) -> float:
    """Return a 0..1 overlap ratio between two AABBs (0 = disjoint)."""
    dx = min(a["max"][0], b["max"][0]) - max(a["min"][0], b["min"][0])
    dy = min(a["max"][1], b["max"][1]) - max(a["min"][1], b["min"][1])
    dz = min(a["max"][2], b["max"][2]) - max(a["min"][2], b["min"][2])
    if dx <= 0 or dy <= 0 or dz <= 0:
        return 0.0
    overlap = dx * dy * dz
    va = (a["max"][0] - a["min"][0]) * (a["max"][1] - a["min"][1]) * (a["max"][2] - a["min"][2])
    vb = (b["max"][0] - b["min"][0]) * (b["max"][1] - b["min"][1]) * (b["max"][2] - b["min"][2])
    if va <= 0 or vb <= 0:
        return 0.0
    return overlap / min(va, vb)


def _hex_lightness(hex_str: str) -> float:
    """Approximate perceptual lightness of a #RRGGBB color (0..1)."""
    s = (hex_str or "").lstrip("#")
    if len(s) != 6:
        return 0.5
    try:
        r = int(s[0:2], 16) / 255.0
        g = int(s[2:4], 16) / 255.0
        b = int(s[4:6], 16) / 255.0
    except ValueError:
        return 0.5
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


# ---------------------------------------------------------------------------
# Critique engine
# ---------------------------------------------------------------------------

_SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


class SceneCritiqueTool(ToolBase):
    """Review the scene for design problems and propose concrete fixes."""

    name = "critique_scene"
    description = (
        "Review the current 3D scene for common design problems and propose "
        "concrete corrective tool calls for each. Returns a ranked list of "
        "findings — empty scene, missing/dim/harsh lighting, floating objects, "
        "overlapping objects, composition drift, palette monotony, poor "
        "background contrast — each with a severity and a proposed fix "
        "(a specific tool name + arguments you could call to resolve it). "
        "Use this to self-review before presenting a finished scene, or when "
        "the user asks 'how does this look?' or 'what's wrong with my scene?'. "
        "Read-only; it never mutates the scene."
    )
    category = "intelligence"

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "max_findings": {
                    "type": "integer",
                    "description": "Maximum number of findings to return (default 12, capped at 30).",
                },
                "focus": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Optional list of check names to limit the review to, e.g. "
                        "['lighting', 'overlap', 'floating']. When omitted, all checks run."
                    ),
                },
            },
            "required": [],
        }

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        try:
            max_findings = int(arguments.get("max_findings", 12))
        except (TypeError, ValueError):
            max_findings = 12
        max_findings = max(1, min(max_findings, 30))

        focus = arguments.get("focus")
        focused: Optional[set] = None
        if isinstance(focus, list):
            focused = {str(f).strip().lower() for f in focus if isinstance(f, str)}

        findings: List[Dict[str, Any]] = []
        self._check_emptiness(scene, findings)
        if focused is None or "lighting" in focused:
            self._check_lighting(scene, findings)
        if focused is None or "floating" in focused:
            self._check_floating(scene, findings)
        if focused is None or "overlap" in focused:
            self._check_overlap(scene, findings)
        if focused is None or "composition" in focused:
            self._check_composition(scene, findings)
        if focused is None or "palette" in focused:
            self._check_palette(scene, findings)
        if focused is None or "contrast" in focused:
            self._check_contrast(scene, findings)

        findings.sort(key=lambda f: _SEVERITY_ORDER.get(f["severity"], 3))
        findings = findings[:max_findings]

        if not findings:
            count = len(scene.objects)
            return ToolResult(
                success=True,
                message=(
                    f"The scene looks well-formed: {count} object(s), "
                    f"{len(scene.lights)} light(s), no obvious design problems found."
                ),
                data={
                    "object_count": count,
                    "light_count": len(scene.lights),
                    "findings": [],
                    "verdict": "clean",
                },
            )

        order = {"high": 0, "medium": 1, "low": 2}
        lines = [
            f"Found {len(findings)} design problem(s), ranked by severity:"
        ]
        for i, f in enumerate(findings, start=1):
            fix = f.get("proposed_fix") or {}
            fix_txt = f" -> call {fix.get('tool')}({fix.get('arguments', {})})" if fix else ""
            lines.append(
                f"{i}. [{f['severity'].upper()}] {f['title']}: {f['detail']}{fix_txt}"
            )

        return ToolResult(
            success=True,
            message="\n".join(lines),
            data={
                "object_count": len(scene.objects),
                "light_count": len(scene.lights),
                "verdict": "needs_attention",
                "findings": findings,
            },
        )

    # ------------------------------------------------------------------
    # Individual checks
    # ------------------------------------------------------------------

    def _check_emptiness(self, scene: Scene, findings: List[Dict[str, Any]]) -> None:
        if len(scene.objects) == 0:
            findings.append({
                "id": "empty_scene",
                "severity": "high",
                "title": "Scene is empty",
                "detail": (
                    "There are no objects in the scene. Nothing is visible to the "
                    "viewer yet."
                ),
                "proposed_fix": {
                    "tool": "create_object",
                    "arguments": {
                        "geometry_type": "box",
                        "position": [0, 0, 0],
                        "color": "#00F0FF",
                    },
                },
            })

    def _check_lighting(self, scene: Scene, findings: List[Dict[str, Any]]) -> None:
        lights = scene.lights
        if not lights:
            findings.append({
                "id": "no_lights",
                "severity": "high",
                "title": "Scene has no lights",
                "detail": (
                    "Without any light sources the scene will render very dark or "
                    "flat. Add a key light plus a fill or ambient."
                ),
                "proposed_fix": {
                    "tool": "add_light",
                    "arguments": {
                        "light_type": "directional",
                        "name": "Key Light",
                        "intensity": 2.0,
                        "position": [5, 8, 5],
                    },
                },
            })
            return
        total = sum(float(getattr(l, "intensity", 0.0)) for l in lights)
        if total < 0.8:
            findings.append({
                "id": "dim_lighting",
                "severity": "medium",
                "title": "Lighting is dim",
                "detail": (
                    f"Total light intensity is only {total:.2f}, which will render "
                    "the scene too dark. Raise intensities or add a light."
                ),
                "proposed_fix": {
                    "tool": "modify_light",
                    "arguments": {
                        "target": lights[0].name,
                        "intensity": max(2.0, float(getattr(lights[0], "intensity", 1.0))),
                    },
                },
            })
        elif total > 12.0:
            findings.append({
                "id": "harsh_lighting",
                "severity": "low",
                "title": "Lighting is harsh",
                "detail": (
                    f"Total light intensity {total:.2f} is very high and may blow "
                    "out highlights. Diffuse the rig or reduce intensities."
                ),
                "proposed_fix": {
                    "tool": "modify_light",
                    "arguments": {
                        "target": lights[0].name,
                        "intensity": max(1.0, float(getattr(lights[0], "intensity", 1.0)) / 2.0),
                    },
                },
            })

    def _check_floating(self, scene: Scene, findings: List[Dict[str, Any]]) -> None:
        # Only meaningful when a ground/plane object is present.
        has_ground = any(
            o.geometry.type in ("plane", "box") and
            abs((o.transform.position or [0, 0, 0])[1]) < 0.5
            for o in scene.objects
        )
        if not has_ground:
            return
        for o in scene.objects:
            if o.type != "mesh":
                continue
            pos = list(o.transform.position or [0, 0, 0])
            half = _estimate_extent(o.geometry.type, o.geometry.params or {})
            scale = list(o.transform.scale or [1.0, 1.0, 1.0])
            min_y = pos[1] - half[1] * abs(scale[1])
            # A sizeable object hovering well above the ground is likely a
            # placement mistake. Small or very distant floats (e.g. a sun in
            # the sky) are tolerated via the 8.0 upper bound.
            if 0.5 < min_y < 8.0:
                findings.append({
                    "id": "floating_object",
                    "severity": "medium",
                    "title": f"'{o.name}' appears to float",
                    "detail": (
                        f"'{o.name}' sits at y={pos[1]:.2f} with its base around "
                        f"y={min_y:.2f}, hovering above the ground plane. It may "
                        "have been placed off the surface by mistake."
                    ),
                    "proposed_fix": {
                        "tool": "transform_object",
                        "arguments": {
                            "target": o.name,
                            "position": [pos[0], half[1] * abs(scale[1]), pos[2]],
                        },
                    },
                })

    def _check_overlap(self, scene: Scene, findings: List[Dict[str, Any]]) -> None:
        meshes = [o for o in scene.objects if o.type == "mesh"]
        if len(meshes) < 2:
            return
        checked: set = set()
        for i in range(len(meshes)):
            for j in range(i + 1, len(meshes)):
                a, b = meshes[i], meshes[j]
                # Skip intentional nesting? No — flag any significant overlap.
                ratio = _overlap_ratio(_aabb(a), _aabb(b))
                if ratio >= 0.5:
                    key = f"{a.id}|{b.id}"
                    if key in checked:
                        continue
                    checked.add(key)
                    findings.append({
                        "id": "object_overlap",
                        "severity": "medium",
                        "title": f"'{a.name}' overlaps '{b.name}'",
                        "detail": (
                            f"'{a.name}' and '{b.name}' intersect with an overlap "
                            f"ratio of {ratio:.0%}. They may be fighting for the "
                            "same space."
                        ),
                        "proposed_fix": {
                            "tool": "transform_object",
                            "arguments": {
                                "target": b.name,
                                "position": [
                                    (b.transform.position or [0, 0, 0])[0] + 1.5,
                                    (b.transform.position or [0, 0, 0])[1],
                                    (b.transform.position or [0, 0, 0])[2] + 1.5,
                                ],
                            },
                        },
                    })
                    break  # one finding per object pair cluster, keep it bounded

    def _check_composition(self, scene: Scene, findings: List[Dict[str, Any]]) -> None:
        meshes = [o for o in scene.objects if o.type == "mesh"]
        if len(meshes) < 2:
            return
        positions = [list(o.transform.position or [0, 0, 0]) for o in meshes]
        xs = [p[0] for p in positions]
        zs = [p[2] for p in positions]
        spread_x = max(xs) - min(xs)
        spread_z = max(zs) - min(zs)
        # Cluster at origin: everything within a tight box near (0,·,0).
        if spread_x < 1.2 and spread_z < 1.2:
            findings.append({
                "id": "clustered_composition",
                "severity": "low",
                "title": "Objects are clustered at the origin",
                "detail": (
                    f"All {len(meshes)} objects sit within a {spread_x:.1f} x "
                    f"{spread_z:.1f} region at the origin. The composition reads "
                    "as a single dense pile."
                ),
                "proposed_fix": {
                    "tool": "arrange_layout",
                    "arguments": {"layout_type": "grid"},
                },
            })
        elif spread_x > 20 or spread_z > 20:
            findings.append({
                "id": "scattered_composition",
                "severity": "low",
                "title": "Objects are scattered too far apart",
                "detail": (
                    f"Objects span {spread_x:.1f} x {spread_z:.1f} units, leaving "
                    "large empty margins. Consider tightening the layout."
                ),
                "proposed_fix": {
                    "tool": "arrange_layout",
                    "arguments": {"layout": "circle"},
                },
            })

    def _check_palette(self, scene: Scene, findings: List[Dict[str, Any]]) -> None:
        meshes = [o for o in scene.objects if o.type == "mesh"]
        if len(meshes) < 3:
            return
        colors = {o.material.color for o in meshes}
        if len(colors) == 1:
            c = next(iter(colors))
            findings.append({
                "id": "monotone_palette",
                "severity": "low",
                "title": "All objects share one color",
                "detail": (
                    f"Every object uses the same material color {c}, so the scene "
                    "reads as a single flat silhouette."
                ),
                "proposed_fix": {
                    "tool": "randomize_palette",
                    "arguments": {"palette": "ocean"},
                },
            })

    def _check_contrast(self, scene: Scene, findings: List[Dict[str, Any]]) -> None:
        meshes = [o for o in scene.objects if o.type == "mesh"]
        if not meshes:
            return
        bg_light = _hex_lightness(scene.background or "#0a0a0f")
        dim = [o.name for o in meshes if abs(_hex_lightness(o.material.color) - bg_light) < 0.12]
        if len(dim) > 0 and len(dim) <= len(meshes):
            findings.append({
                "id": "low_contrast",
                "severity": "low",
                "title": "Some objects blend into the background",
                "detail": (
                    f"{len(dim)} object(s) — {', '.join(dim[:5])} — have a color "
                    "very close in lightness to the scene background, so they may "
                    "be hard to make out."
                ),
                "proposed_fix": {
                    "tool": "apply_material",
                    "arguments": {"target": dim[0], "color": "#00F0FF"},
                },
            })