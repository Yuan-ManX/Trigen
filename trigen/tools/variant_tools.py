"""Variant tools — save / load / list / randomize named scene snapshots.

Variants capture the current scene as a named JSON snapshot. ``save_variant``
records the live scene; ``load_variant`` replaces the scene with a stored
snapshot; ``list_variants`` enumerates saved variants; ``randomize_variant``
loads a stored variant then jitters material hue + object positions to spawn
a fresh alternative arrangement. The store persists to ``variants.json`` in
the workspace.
"""

from __future__ import annotations

import colorsys
import logging
import random
from typing import Any, Dict, List, Optional

from trigen.scene import Scene, SceneObject
from trigen.tools.base import SceneDelta, ToolBase, ToolResult
from trigen.variants import Variant, variant_store

logger = logging.getLogger("trigen.tools.variant")


_SAVE_VARIANT_PARAMS = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "description": "Unique variant name"},
        "description": {"type": "string", "description": "Optional note (not persisted)"},
    },
    "required": ["name"],
}


_LOAD_VARIANT_PARAMS = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "description": "Name of the variant to load"},
    },
    "required": ["name"],
}


_LIST_VARIANTS_PARAMS = {
    "type": "object",
    "properties": {},
    "required": [],
}


_RANDOMIZE_VARIANT_PARAMS = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "description": "Name of the variant to use as the base"},
        "hue_jitter": {
            "type": "number",
            "description": "Max hue rotation in degrees (default 30)",
        },
        "pos_jitter": {
            "type": "number",
            "description": "Max position offset per axis in world units (default 0.5)",
        },
        "seed": {"type": "integer", "description": "Optional random seed for reproducibility"},
    },
    "required": ["name"],
}


def _normalize_variant_name(name: str) -> str:
    return name.strip().lower().replace(" ", "_")


def _hex_to_rgb(hex_str: str) -> tuple:
    h = hex_str.lstrip("#")
    if len(h) != 6:
        return (0.8, 0.8, 0.8)
    try:
        return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    except ValueError:
        return (0.8, 0.8, 0.8)


def _rgb_to_hex(rgb: tuple) -> str:
    r, g, b = rgb
    return "#{:02x}{:02x}{:02x}".format(
        max(0, min(255, int(r * 255))),
        max(0, min(255, int(g * 255))),
        max(0, min(255, int(b * 255))),
    )


def _jitter_color(hex_str: str, max_hue_deg: float, rng: random.Random) -> str:
    """Rotate the HSV hue of a hex color by a random amount up to max_hue_deg."""
    r, g, b = _hex_to_rgb(hex_str)
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    delta = rng.uniform(-max_hue_deg, max_hue_deg) / 360.0
    h = (h + delta) % 1.0
    nr, ng, nb = colorsys.hsv_to_rgb(h, s, v)
    return _rgb_to_hex((nr, ng, nb))


class SaveVariantTool(ToolBase):
    """Snapshot the current scene as a named variant."""

    name = "save_variant"
    description = "Save the current scene as a named variant snapshot for later recall or randomization."

    def schema(self) -> Dict[str, Any]:
        return _SAVE_VARIANT_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        raw_name = str(arguments.get("name", "")).strip()
        if not raw_name:
            return ToolResult(success=False, message="Missing 'name' argument")
        name = _normalize_variant_name(raw_name)
        scene_dict = scene.to_dict()
        collection = variant_store.get()
        # Track prior variant as parent if user is overwriting an existing entry.
        parent = collection.variants[name].parent if name in collection.variants else None
        collection.variants[name] = Variant(
            name=name,
            scene_dict=scene_dict,
            parent=parent,
        )
        variant_store.save()
        return ToolResult(
            success=True,
            message=f"Variant '{name}' saved ({len(scene_dict.get('objects', []))} objects)",
            data={
                "name": name,
                "objects": len(scene_dict.get("objects", [])),
                "lights": len(scene_dict.get("lights", [])),
                "cameras": len(scene_dict.get("cameras", [])),
            },
        )


class LoadVariantTool(ToolBase):
    """Replace the current scene with a previously saved variant."""

    name = "load_variant"
    description = "Load a previously saved variant by name, replacing the current scene."

    def schema(self) -> Dict[str, Any]:
        return _LOAD_VARIANT_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        raw_name = str(arguments.get("name", "")).strip()
        if not raw_name:
            return ToolResult(success=False, message="Missing 'name' argument")
        name = _normalize_variant_name(raw_name)
        collection = variant_store.get()
        variant = collection.variants.get(name)
        if variant is None:
            available = sorted(collection.variants.keys())
            return ToolResult(
                success=False,
                message=f"Unknown variant '{name}'. Available: {', '.join(available) or '(none)'}",
            )
        # Replace scene contents in place so the orchestrator's reference stays valid.
        new_scene = Scene.from_dict(variant.scene_dict)
        scene.objects = list(new_scene.objects)
        scene.lights = list(new_scene.lights)
        scene.cameras = list(new_scene.cameras)
        scene.groups = list(new_scene.groups)
        scene.background = new_scene.background
        scene.environment = new_scene.environment
        scene.fog = new_scene.fog
        scene.grid_visible = new_scene.grid_visible
        scene.grid_size = new_scene.grid_size
        scene.annotations = list(new_scene.annotations)
        return ToolResult(
            success=True,
            message=f"Variant '{name}' loaded ({len(scene.objects)} objects restored)",
            deltas=[SceneDelta(action="replace", snapshot=scene.to_dict())],
            data={"name": name, "objects": len(scene.objects)},
        )


class ListVariantsTool(ToolBase):
    """List all saved scene variants."""

    name = "list_variants"
    description = "List all saved scene variants in the workspace."

    def schema(self) -> Dict[str, Any]:
        return _LIST_VARIANTS_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        collection = variant_store.get()
        items = [
            {
                "name": v.name,
                "objects": len(v.scene_dict.get("objects", [])),
                "parent": v.parent,
                "created_at": v.created_at,
            }
            for v in sorted(collection.variants.values(), key=lambda x: x.name)
        ]
        if not items:
            return ToolResult(
                success=True,
                message="No variants saved yet",
                data={"variants": [], "count": 0},
            )
        summary = ", ".join(v["name"] for v in items)
        return ToolResult(
            success=True,
            message=f"{len(items)} variant(s): {summary}",
            data={"variants": items, "count": len(items)},
        )


class RandomizeVariantTool(ToolBase):
    """Load a variant then jitter material hue and object positions to spawn an alternative."""

    name = "randomize_variant"
    description = "Load a saved variant then jitter material hue and object positions to spawn a fresh alternative arrangement."

    def schema(self) -> Dict[str, Any]:
        return _RANDOMIZE_VARIANT_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        raw_name = str(arguments.get("name", "")).strip()
        if not raw_name:
            return ToolResult(success=False, message="Missing 'name' argument")
        name = _normalize_variant_name(raw_name)
        collection = variant_store.get()
        variant = collection.variants.get(name)
        if variant is None:
            available = sorted(collection.variants.keys())
            return ToolResult(
                success=False,
                message=f"Unknown variant '{name}'. Available: {', '.join(available) or '(none)'}",
            )

        try:
            hue_jitter = float(arguments.get("hue_jitter", 30.0))
            pos_jitter = float(arguments.get("pos_jitter", 0.5))
        except (TypeError, ValueError):
            return ToolResult(success=False, message="hue_jitter and pos_jitter must be numbers")
        seed = arguments.get("seed")
        rng = random.Random(int(seed)) if isinstance(seed, int) else random.Random()

        # Load the variant into the scene first.
        new_scene = Scene.from_dict(variant.scene_dict)

        # Jitter material hue and position for each object.
        jittered_count = 0
        for obj in new_scene.objects:
            obj.material.color = _jitter_color(obj.material.color, hue_jitter, rng)
            if obj.material.emissive and obj.material.emissive != "#000000":
                obj.material.emissive = _jitter_color(obj.material.emissive, hue_jitter, rng)
            obj.transform.position = [
                float(obj.transform.position[0]) + rng.uniform(-pos_jitter, pos_jitter),
                float(obj.transform.position[1]) + rng.uniform(-pos_jitter, pos_jitter),
                float(obj.transform.position[2]) + rng.uniform(-pos_jitter, pos_jitter),
            ]
            jittered_count += 1

        # Commit to the live scene.
        scene.objects = list(new_scene.objects)
        scene.lights = list(new_scene.lights)
        scene.cameras = list(new_scene.cameras)
        scene.groups = list(new_scene.groups)
        scene.background = new_scene.background
        scene.environment = new_scene.environment
        scene.fog = new_scene.fog
        scene.grid_visible = new_scene.grid_visible
        scene.grid_size = new_scene.grid_size
        scene.annotations = list(new_scene.annotations)

        return ToolResult(
            success=True,
            message=f"Variant '{name}' loaded and jittered ({jittered_count} objects, hue±{hue_jitter}°, pos±{pos_jitter})",
            deltas=[SceneDelta(action="replace", snapshot=scene.to_dict())],
            data={
                "name": name,
                "jittered": jittered_count,
                "hue_jitter": hue_jitter,
                "pos_jitter": pos_jitter,
                "seed": seed,
            },
        )
