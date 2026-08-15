"""Procedural deformation tools.

Applies non-destructive geometric modifiers to existing scene objects:
noise displacement, bend, twist, taper, and wave deformations. Each tool
attaches a ``modifiers`` descriptor to the object so the viewport shader
reconstructs the deformed surface on-the-fly.
"""

from __future__ import annotations

from typing import Any, Dict, List

from trigen.scene import Scene
from trigen.tools.base import SceneDelta, ToolBase, ToolResult


class _ModifierTool(ToolBase):
    """Shared helper for all deformation modifier tools."""

    modifier_key: str = ""

    def _apply_modifier(
        self,
        scene: Scene,
        target: str,
        params: Dict[str, Any],
        label: str,
    ) -> ToolResult:
        obj = scene.find_object(target)
        if obj is None:
            return ToolResult(False, f"Object '{target}' not found.")
        modifiers = dict(getattr(obj, "modifiers", None) or {})
        modifiers[self.modifier_key] = params
        object.__setattr__(obj, "modifiers", modifiers)
        delta = SceneDelta(
            action="update",
            target_id=obj.id,
            payload={"modifiers": modifiers, **obj.to_dict()},
        )
        return ToolResult(
            True,
            f"Applied {label} modifier to '{obj.name}'.",
            deltas=[delta],
            data={"name": obj.name, "modifier": self.modifier_key, "params": params},
        )


class NoiseDeformTool(_ModifierTool):
    """Apply 3D simplex-noise displacement to an object surface."""

    name = "noise_deform"
    description = (
        "Displace an object's vertices with 3D simplex noise. Useful for "
        "terrain undulation, organic wobble, water ripples, and rocky "
        "asteroid surfaces."
    )
    category = "procedural"
    modifier_key = "noise"

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "required": ["target"],
            "properties": {
                "target": {"type": "string", "description": "Object name or id to deform"},
                "scale": {"type": "number", "default": 1.5, "description": "Noise frequency scale"},
                "strength": {"type": "number", "default": 0.25, "description": "Displacement amplitude"},
                "octaves": {"type": "integer", "default": 3, "description": "Fractal octave count"},
                "seed": {"type": "integer", "default": 42, "description": "Random seed for reproducible noise"},
                "animated": {"type": "boolean", "default": False, "description": "Animate noise over time"},
                "speed": {"type": "number", "default": 0.3, "description": "Animation speed when animated"},
            },
        }

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        target = arguments.get("target", "")
        params = {
            "scale": float(arguments.get("scale", 1.5)),
            "strength": float(arguments.get("strength", 0.25)),
            "octaves": int(arguments.get("octaves", 3)),
            "seed": int(arguments.get("seed", 42)),
            "animated": bool(arguments.get("animated", False)),
            "speed": float(arguments.get("speed", 0.3)),
        }
        return self._apply_modifier(scene, target, params, "noise displacement")


class BendModifierTool(_ModifierTool):
    """Bend an object around an axis."""

    name = "bend_object"
    description = (
        "Bend an object around a chosen axis. Useful for arches, curved "
        "railings, bent pipes, and domed shells."
    )
    category = "procedural"
    modifier_key = "bend"

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "required": ["target"],
            "properties": {
                "target": {"type": "string", "description": "Object name or id to bend"},
                "angle": {"type": "number", "default": 1.0, "description": "Bend angle in radians (positive and negative supported)"},
                "axis": {"type": "string", "enum": ["x", "y", "z"], "default": "y", "description": "Axis to bend around"},
                "bend_axis": {"type": "string", "enum": ["x", "y", "z"], "default": "z", "description": "Axis along which the bend is applied"},
                "limit": {"type": "number", "default": 0.0, "description": "Optional bend-range limit (0 = unlimited)"},
            },
        }

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        target = arguments.get("target", "")
        params = {
            "angle": float(arguments.get("angle", 1.0)),
            "axis": str(arguments.get("axis", "y")),
            "bend_axis": str(arguments.get("bend_axis", "z")),
            "limit": float(arguments.get("limit", 0.0)),
        }
        return self._apply_modifier(scene, target, params, "bend")


class TwistModifierTool(_ModifierTool):
    """Twist an object around an axis."""

    name = "twist_object"
    description = (
        "Twist an object helically around a chosen axis. Useful for drill "
        "bits, spiral staircases, candy canes, and DNA helix styling."
    )
    category = "procedural"
    modifier_key = "twist"

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "required": ["target"],
            "properties": {
                "target": {"type": "string", "description": "Object name or id to twist"},
                "angle": {"type": "number", "default": 3.1416, "description": "Total twist angle in radians (2*PI = full revolution)"},
                "axis": {"type": "string", "enum": ["x", "y", "z"], "default": "y", "description": "Axis to twist around"},
                "offset": {"type": "number", "default": 0.0, "description": "Twist offset along the axis"},
            },
        }

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        target = arguments.get("target", "")
        params = {
            "angle": float(arguments.get("angle", 3.1416)),
            "axis": str(arguments.get("axis", "y")),
            "offset": float(arguments.get("offset", 0.0)),
        }
        return self._apply_modifier(scene, target, params, "twist")


class TaperModifierTool(_ModifierTool):
    """Taper an object's cross-section along an axis."""

    name = "taper_object"
    description = (
        "Taper (shrink or expand) an object's cross-section along an axis. "
        "Useful for spires, obelisks, tapered columns, and stylized trees."
    )
    category = "procedural"
    modifier_key = "taper"

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "required": ["target"],
            "properties": {
                "target": {"type": "string", "description": "Object name or id to taper"},
                "start": {"type": "number", "default": 1.0, "description": "Scale factor at axis start"},
                "end": {"type": "number", "default": 0.3, "description": "Scale factor at axis end"},
                "axis": {"type": "string", "enum": ["x", "y", "z"], "default": "y", "description": "Axis along which the taper runs"},
                "curve": {"type": "number", "default": 1.0, "description": "Interpolation curve (1 = linear, <1 ease-in, >1 ease-out)"},
            },
        }

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        target = arguments.get("target", "")
        params = {
            "start": float(arguments.get("start", 1.0)),
            "end": float(arguments.get("end", 0.3)),
            "axis": str(arguments.get("axis", "y")),
            "curve": float(arguments.get("curve", 1.0)),
        }
        return self._apply_modifier(scene, target, params, "taper")


class WaveModifierTool(_ModifierTool):
    """Apply a sinusoidal wave deformation across a surface."""

    name = "wave_deform"
    description = (
        "Sinusoidal wave deformation across one axis. Useful for ocean "
        "surfaces, ribbon effects, rippled flags, and sine-wave terrain."
    )
    category = "procedural"
    modifier_key = "wave"

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "required": ["target"],
            "properties": {
                "target": {"type": "string", "description": "Object name or id to deform"},
                "amplitude": {"type": "number", "default": 0.2, "description": "Wave height amplitude"},
                "frequency": {"type": "number", "default": 2.0, "description": "Wave cycles per unit length"},
                "direction": {"type": "string", "enum": ["x", "z", "diagonal"], "default": "x", "description": "Wave travel direction"},
                "phase": {"type": "number", "default": 0.0, "description": "Initial phase offset in radians"},
                "animated": {"type": "boolean", "default": True, "description": "Animate wave phase over time"},
                "speed": {"type": "number", "default": 1.0, "description": "Animation speed multiplier"},
            },
        }

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        target = arguments.get("target", "")
        params = {
            "amplitude": float(arguments.get("amplitude", 0.2)),
            "frequency": float(arguments.get("frequency", 2.0)),
            "direction": str(arguments.get("direction", "x")),
            "phase": float(arguments.get("phase", 0.0)),
            "animated": bool(arguments.get("animated", True)),
            "speed": float(arguments.get("speed", 1.0)),
        }
        return self._apply_modifier(scene, target, params, "wave")


class ClearModifiersTool(ToolBase):
    """Remove all deformation modifiers from an object."""

    name = "clear_modifiers"
    description = "Remove all attached deformation modifiers (noise, bend, twist, taper, wave) from an object."
    category = "procedural"

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "required": ["target"],
            "properties": {
                "target": {"type": "string", "description": "Object name or id to strip modifiers from"},
            },
        }

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        target = arguments.get("target", "")
        obj = scene.find_object(target)
        if obj is None:
            return ToolResult(False, f"Object '{target}' not found.")
        object.__setattr__(obj, "modifiers", {})
        delta = SceneDelta(
            action="update",
            target_id=obj.id,
            payload={"modifiers": {}, **obj.to_dict()},
        )
        return ToolResult(
            True,
            f"Cleared all modifiers from '{obj.name}'.",
            deltas=[delta],
            data={"name": obj.name},
        )
