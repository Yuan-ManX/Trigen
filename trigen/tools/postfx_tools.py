"""Post-processing and visual-effects tools.

Configures the viewport's screen-space effect graph: bloom with threshold/
knee/radius, ACES/Reinhard/Filmic tone mapping, color grading (lift/gamma/
gain + temperature/tint), vignette, film grain, depth-of-field, and
chromatic aberration. The payload is written onto the Scene's
``post_processing`` dict so the three.js composer applies it in real time.
"""

from __future__ import annotations

from typing import Any, Dict, List

from trigen.scene import Scene
from trigen.tools.base import SceneDelta, ToolBase, ToolResult


def _write_postfx(scene: Scene, key: str, value: Any) -> SceneDelta:
    """Write a postfx sub-key onto the scene and emit an update delta."""
    if not hasattr(scene, "post_processing") or scene.post_processing is None:
        scene.post_processing = {}
    scene.post_processing[key] = value
    snapshot = {
        "post_processing": dict(scene.post_processing),
        "background": scene.background,
    }
    return SceneDelta(action="update", target_id="scene", payload=snapshot, snapshot=snapshot)


class SetBloomTool(ToolBase):
    """Configure screen-space bloom for emissive and bright regions."""

    name = "set_bloom"
    description = (
        "Configure screen-space bloom. Bloom bleeds bright pixels beyond "
        "their boundaries for neon, lens-flare, and HDR-like effects."
    )
    category = "viewport"

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "enabled": {"type": "boolean", "default": True, "description": "Enable or disable bloom"},
                "strength": {"type": "number", "default": 0.85, "description": "Bloom intensity multiplier"},
                "threshold": {"type": "number", "default": 0.9, "description": "Minimum brightness to trigger bloom (0..1)"},
                "knee": {"type": "number", "default": 0.2, "description": "Softness of the threshold cutoff (0 = hard edge)"},
                "radius": {"type": "number", "default": 0.5, "description": "Bloom blur radius (0..1)"},
                "mipmap_blur": {"type": "boolean", "default": True, "description": "Use multi-pass mipmap blur for smoothness"},
            },
        }

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        cfg = {
            "enabled": bool(arguments.get("enabled", True)),
            "strength": float(arguments.get("strength", 0.85)),
            "threshold": float(arguments.get("threshold", 0.9)),
            "knee": float(arguments.get("knee", 0.2)),
            "radius": float(arguments.get("radius", 0.5)),
            "mipmap_blur": bool(arguments.get("mipmap_blur", True)),
        }
        delta = _write_postfx(scene, "bloom", cfg)
        on_off = "enabled" if cfg["enabled"] else "disabled"
        return ToolResult(True, f"Bloom {on_off} (strength {cfg['strength']:.2f}).", deltas=[delta], data={"bloom": cfg})


class SetToneMappingTool(ToolBase):
    """Select the HDR-to-LDR tone mapping operator."""

    name = "set_tone_mapping"
    description = (
        "Select the tone mapping operator that compresses HDR colours "
        "into the displayable 0..1 range. Each operator gives a different "
        "cinematic look."
    )
    category = "viewport"

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "required": ["mode"],
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": ["none", "linear", "reinhard", "aces", "aces_filmic", "filmic", "agx", "neutral"],
                    "default": "aces_filmic",
                    "description": "Tone mapping operator",
                },
                "exposure": {"type": "number", "default": 1.0, "description": "Global exposure multiplier (applied before tone mapping)"},
            },
        }

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        cfg = {
            "mode": str(arguments.get("mode", "aces_filmic")),
            "exposure": float(arguments.get("exposure", 1.0)),
        }
        delta = _write_postfx(scene, "tone_mapping", cfg)
        return ToolResult(True, f"Tone mapping set to '{cfg['mode']}'.", deltas=[delta], data={"tone_mapping": cfg})


class SetColorGradingTool(ToolBase):
    """Apply lift-gamma-gain color grading with temperature/tint controls."""

    name = "set_color_grading"
    description = (
        "Apply cinematic color grading. Lift shadows, gamma mid-tones, gain "
        "highlights, plus temperature (warm-cool) and tint (green-magenta)."
    )
    category = "viewport"

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "enabled": {"type": "boolean", "default": True, "description": "Toggle color grading"},
                "lift": {
                    "type": "array",
                    "items": {"type": "number"},
                    "default": [0.0, 0.0, 0.0],
                    "description": "Shadow offset RGB (-1..1 per channel)",
                },
                "gamma": {
                    "type": "array",
                    "items": {"type": "number"},
                    "default": [1.0, 1.0, 1.0],
                    "description": "Mid-tone gamma RGB (0.25..4 per channel)",
                },
                "gain": {
                    "type": "array",
                    "items": {"type": "number"},
                    "default": [1.0, 1.0, 1.0],
                    "description": "Highlight gain RGB (0..4 per channel)",
                },
                "temperature": {"type": "number", "default": 0.0, "description": "Temperature shift: -1 cool, 0 neutral, +1 warm"},
                "tint": {"type": "number", "default": 0.0, "description": "Tint shift: -1 green, 0 neutral, +1 magenta"},
                "contrast": {"type": "number", "default": 1.0, "description": "Contrast multiplier (0.5..2)"},
                "saturation": {"type": "number", "default": 1.0, "description": "Saturation multiplier (0 = monochrome, 2 = vivid)"},
            },
        }

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        cfg = {
            "enabled": bool(arguments.get("enabled", True)),
            "lift": [float(x) for x in arguments.get("lift", [0.0, 0.0, 0.0])],
            "gamma": [float(x) for x in arguments.get("gamma", [1.0, 1.0, 1.0])],
            "gain": [float(x) for x in arguments.get("gain", [1.0, 1.0, 1.0])],
            "temperature": float(arguments.get("temperature", 0.0)),
            "tint": float(arguments.get("tint", 0.0)),
            "contrast": float(arguments.get("contrast", 1.0)),
            "saturation": float(arguments.get("saturation", 1.0)),
        }
        delta = _write_postfx(scene, "color_grading", cfg)
        return ToolResult(True, "Color grading updated.", deltas=[delta], data={"color_grading": cfg})


class SetVignetteTool(ToolBase):
    """Darken the frame edges for cinematic framing."""

    name = "set_vignette"
    description = "Apply a vignette that darkens the image edges for cinematic framing or portrait-style focus."
    category = "viewport"

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "enabled": {"type": "boolean", "default": True, "description": "Toggle vignette"},
                "strength": {"type": "number", "default": 0.4, "description": "Darkening strength (0..1)"},
                "radius": {"type": "number", "default": 0.5, "description": "Vignette radius (0 = full frame, 1 = tiny center)"},
                "softness": {"type": "number", "default": 0.6, "description": "Edge softness (0 = hard circle, 1 = feathered)"},
                "color": {"type": "string", "default": "#000000", "description": "Vignette color"},
            },
        }

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        cfg = {
            "enabled": bool(arguments.get("enabled", True)),
            "strength": float(arguments.get("strength", 0.4)),
            "radius": float(arguments.get("radius", 0.5)),
            "softness": float(arguments.get("softness", 0.6)),
            "color": str(arguments.get("color", "#000000")),
        }
        delta = _write_postfx(scene, "vignette", cfg)
        on_off = "enabled" if cfg["enabled"] else "disabled"
        return ToolResult(True, f"Vignette {on_off}.", deltas=[delta], data={"vignette": cfg})


class SetFilmGrainTool(ToolBase):
    """Add film grain / noise texture over the final image."""

    name = "set_film_grain"
    description = "Overlay film-grain noise for a tactile analog-cinema look."
    category = "viewport"

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "enabled": {"type": "boolean", "default": False, "description": "Toggle film grain"},
                "strength": {"type": "number", "default": 0.08, "description": "Grain amplitude (0..1)"},
                "size": {"type": "number", "default": 1.0, "description": "Grain pixel size (1 = 1px, >1 = coarser)"},
                "animated": {"type": "boolean", "default": True, "description": "Animate grain every frame to avoid banding"},
                "luminance_only": {"type": "boolean", "default": True, "description": "If true, only affect brightness (no color grain)"},
            },
        }

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        cfg = {
            "enabled": bool(arguments.get("enabled", False)),
            "strength": float(arguments.get("strength", 0.08)),
            "size": float(arguments.get("size", 1.0)),
            "animated": bool(arguments.get("animated", True)),
            "luminance_only": bool(arguments.get("luminance_only", True)),
        }
        delta = _write_postfx(scene, "film_grain", cfg)
        on_off = "enabled" if cfg["enabled"] else "disabled"
        return ToolResult(True, f"Film grain {on_off}.", deltas=[delta], data={"film_grain": cfg})


class SetDOFTool(ToolBase):
    """Configure depth-of-field bokeh blur."""

    name = "set_depth_of_field"
    description = (
        "Apply depth-of-field blur so only objects near the focal plane "
        "remain sharp. Great for cinematic close-ups and product shots."
    )
    category = "viewport"

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "enabled": {"type": "boolean", "default": False, "description": "Toggle DOF effect"},
                "focus_distance": {"type": "number", "default": 5.0, "description": "Distance from camera to focal plane"},
                "focal_length": {"type": "number", "default": 50.0, "description": "Lens focal length in mm (shorter = deeper focus)"},
                "fstop": {"type": "number", "default": 2.8, "description": "Aperture f-stop (smaller = more blur)"},
                "blur_count": {"type": "integer", "default": 4, "description": "Bokeh sample count (higher = smoother = slower)"},
            },
        }

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        cfg = {
            "enabled": bool(arguments.get("enabled", False)),
            "focus_distance": float(arguments.get("focus_distance", 5.0)),
            "focal_length": float(arguments.get("focal_length", 50.0)),
            "fstop": float(arguments.get("fstop", 2.8)),
            "blur_count": int(arguments.get("blur_count", 4)),
        }
        delta = _write_postfx(scene, "dof", cfg)
        on_off = "enabled" if cfg["enabled"] else "disabled"
        return ToolResult(True, f"Depth of field {on_off}.", deltas=[delta], data={"dof": cfg})


class SetChromaticAberrationTool(ToolBase):
    """Add RGB-split chromatic aberration at edges."""

    name = "set_chromatic_aberration"
    description = "Split RGB channels at screen edges for a stylized lens/retro look."
    category = "viewport"

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "enabled": {"type": "boolean", "default": False, "description": "Toggle chromatic aberration"},
                "strength": {"type": "number", "default": 0.002, "description": "Split amount (0 = none, typical 0.001..0.01)"},
                "radial": {"type": "boolean", "default": True, "description": "If true, stronger at screen edges; if false, uniform"},
            },
        }

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        cfg = {
            "enabled": bool(arguments.get("enabled", False)),
            "strength": float(arguments.get("strength", 0.002)),
            "radial": bool(arguments.get("radial", True)),
        }
        delta = _write_postfx(scene, "chromatic_aberration", cfg)
        on_off = "enabled" if cfg["enabled"] else "disabled"
        return ToolResult(True, f"Chromatic aberration {on_off}.", deltas=[delta], data={"chromatic_aberration": cfg})


class ResetPostfxTool(ToolBase):
    """Clear all post-processing overrides back to viewport defaults."""

    name = "reset_postfx"
    description = "Reset all post-processing effects (bloom, tone mapping, grading, vignette, grain, DOF, CA) to defaults."
    category = "viewport"

    def schema(self) -> Dict[str, Any]:
        return {"type": "object", "properties": {}}

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        scene.post_processing = {}
        snapshot = {"post_processing": {}, "background": scene.background}
        delta = SceneDelta(action="update", target_id="scene", payload=snapshot, snapshot=snapshot)
        return ToolResult(True, "All post-processing effects reset to defaults.", deltas=[delta], data={"post_processing": {}})


class ApplyPostFxTool(ToolBase):
    """Compound post-processing tool that applies multiple effects at once.

    Accepts a flat argument dict with keys for each effect (bloom, color_grading,
    vignette, grain, depth_of_field, chromatic_aberration, tone_mapping) and
    writes each as a sub-key on scene.post_processing. Used by the intent
    parser's "cinematic look", "noir", and other style presets.
    """

    name = "apply_post_fx"
    description = (
        "Apply a batch of post-processing effects in a single call. "
        "Supports: bloom (bool/float), color_grading (str preset or dict), "
        "vignette (bool), grain (float), depth_of_field (bool), chromatic_aberration (bool), "
        "tone_mapping (str)."
    )
    category = "viewport"

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "bloom": {"type": ["boolean", "number"], "description": "Enable bloom (bool) or set intensity (float)"},
                "color_grading": {"type": ["string", "object"], "description": "Preset name (cinematic/noir/warm/cool) or grading dict"},
                "vignette": {"type": ["boolean", "number"], "description": "Enable vignette (bool) or set strength (float)"},
                "grain": {"type": ["boolean", "number"], "description": "Enable grain (bool) or set strength (float)"},
                "depth_of_field": {"type": "boolean", "description": "Enable depth of field"},
                "chromatic_aberration": {"type": "boolean", "description": "Enable chromatic aberration"},
                "tone_mapping": {"type": "string", "description": "Tone mapping operator: aces_filmic, filmic, reinhard, linear, none"},
            },
        }

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        if not hasattr(scene, "post_processing") or scene.post_processing is None:
            scene.post_processing = {}

        applied: List[str] = []

        # Bloom
        if "bloom" in arguments:
            val = arguments["bloom"]
            if isinstance(val, bool):
                scene.post_processing["bloom"] = {
                    "enabled": val, "strength": 0.85 if val else 0.0,
                    "threshold": 0.9, "knee": 0.2, "radius": 0.5,
                }
            elif isinstance(val, (int, float)):
                scene.post_processing["bloom"] = {
                    "enabled": True, "strength": float(val),
                    "threshold": 0.9, "knee": 0.2, "radius": 0.5,
                }
            applied.append("bloom")

        # Color grading — supports string presets or a full dict
        if "color_grading" in arguments:
            val = arguments["color_grading"]
            if isinstance(val, str):
                presets: Dict[str, Dict[str, Any]] = {
                    "cinematic": {"enabled": True, "temperature": 15, "contrast": 1.1, "saturation": 1.1, "lift": [0.02, 0.0, -0.02], "gamma": [1.0, 1.0, 1.0], "gain": [1.1, 1.05, 1.0]},
                    "noir": {"enabled": True, "temperature": -10, "contrast": 1.4, "saturation": 0.0, "lift": [0.0, 0.0, 0.0], "gamma": [1.0, 1.0, 1.0], "gain": [1.2, 1.2, 1.2]},
                    "warm": {"enabled": True, "temperature": 20, "contrast": 1.05, "saturation": 1.15, "lift": [0.0, 0.0, 0.0], "gamma": [1.0, 1.0, 1.0], "gain": [1.1, 1.0, 0.9]},
                    "cool": {"enabled": True, "temperature": -20, "contrast": 1.05, "saturation": 1.1, "lift": [0.0, 0.0, 0.02], "gamma": [1.0, 1.0, 1.0], "gain": [0.9, 1.0, 1.1]},
                }
                scene.post_processing["color_grading"] = presets.get(val, presets["cinematic"])
            elif isinstance(val, dict):
                scene.post_processing["color_grading"] = val
            applied.append("color_grading")

        # Vignette
        if "vignette" in arguments:
            val = arguments["vignette"]
            if isinstance(val, bool):
                scene.post_processing["vignette"] = {"enabled": val, "strength": 0.4 if val else 0.0, "radius": 0.5, "softness": 0.6}
            elif isinstance(val, (int, float)):
                scene.post_processing["vignette"] = {"enabled": True, "strength": float(val), "radius": 0.5, "softness": 0.6}
            applied.append("vignette")

        # Film grain
        if "grain" in arguments:
            val = arguments["grain"]
            if isinstance(val, bool):
                scene.post_processing["film_grain"] = {"enabled": val, "strength": 0.08 if val else 0.0, "size": 1.0, "animated": True}
            elif isinstance(val, (int, float)):
                scene.post_processing["film_grain"] = {"enabled": True, "strength": float(val), "size": 1.0, "animated": True}
            applied.append("grain")

        # Depth of field
        if "depth_of_field" in arguments:
            val = arguments["depth_of_field"]
            scene.post_processing["dof"] = {"enabled": bool(val), "focus_distance": 5.0, "focal_length": 50.0, "fstop": 2.8}
            applied.append("depth_of_field")

        # Chromatic aberration
        if "chromatic_aberration" in arguments:
            val = arguments["chromatic_aberration"]
            scene.post_processing["chromatic_aberration"] = {"enabled": bool(val), "strength": 0.002, "radial": True}
            applied.append("chromatic_aberration")

        # Tone mapping
        if "tone_mapping" in arguments:
            val = arguments["tone_mapping"]
            scene.post_processing["tone_mapping"] = {"enabled": True, "mode": str(val), "exposure": 1.0}
            applied.append("tone_mapping")

        snapshot = {"post_processing": dict(scene.post_processing), "background": scene.background}
        delta = SceneDelta(action="update", target_id="scene", payload=snapshot, snapshot=snapshot)
        desc = f"Applied post-FX: {', '.join(applied)}" if applied else "No post-FX effects to apply."
        return ToolResult(True, desc, deltas=[delta], data={"applied": applied, "post_processing": scene.post_processing})
