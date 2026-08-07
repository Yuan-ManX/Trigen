"""Frontend-editor coverage gap tools.

Four Agent-callable tools that close remaining gaps between the backend
tool registry and the frontend editor surface:

  * ``list_scene_templates`` — enumerate the smart_compose templates plus
    the skill-aligned templates shown in the frontend SceneTemplates modal
    so the Agent can answer "what templates are available?" without an LLM
    round-trip.
  * ``orbit_viewport`` — start or stop an automatic orbit of the viewport
    camera around the scene origin (or a named target). Emits an
    ``editor_orbit_viewport`` delta the frontend dispatches to the camera
    rig.
  * ``set_layer_visibility`` — show or hide every object on a named layer
    in one call. Complements ``set_object_layer`` (which assigns a single
    object to a layer) with bulk visibility control for an entire layer.
  * ``list_skills`` — enumerate the registered creative skills so the
    Agent can answer "what skills are available?" without an LLM
    round-trip. Mirrors the ``invoke_skill`` tool's static skill catalog.
"""

from __future__ import annotations

from typing import Any, Dict, List

from trigen.scene import Scene
from trigen.tools.base import SceneDelta, ToolBase, ToolResult


# ---------------------------------------------------------------------------
# 1. list_scene_templates
# ---------------------------------------------------------------------------

_LIST_SCENE_TEMPLATES_PARAMS = {
    "type": "object",
    "properties": {
        "include_skills": {
            "type": "boolean",
            "description": "Include skill-aligned templates in the result (default true)",
        },
    },
    "required": [],
}


# Static catalog mirroring web/src/components/toolbar/SceneTemplates.tsx.
# Kept in sync so the Agent's answer matches what the user sees in the
# frontend "Scene Templates" modal. Each entry carries the same id / name /
# description / objects fields surfaced by the modal so an LLM can pick a
# template by name and route it back through smart_compose or invoke_skill.
_SCENE_TEMPLATES: List[Dict[str, Any]] = [
    # smart_compose templates — invoked via the smart_compose tool
    {
        "id": "solar_system",
        "name": "Solar System",
        "description": "Glowing sun with 8 orbiting planets and rings",
        "objects": "17 objects",
        "invokes": {"tool": "smart_compose", "template": "solar_system"},
    },
    {
        "id": "city_block",
        "name": "City Block",
        "description": "Grid of varied buildings on a ground plane",
        "objects": "12+ objects",
        "invokes": {"tool": "smart_compose", "template": "city_block"},
    },
    {
        "id": "studio",
        "name": "Studio Lighting",
        "description": "3-point lighting setup with platform and subject",
        "objects": "8 objects",
        "invokes": {"tool": "smart_compose", "template": "studio"},
    },
    {
        "id": "crystal_cluster",
        "name": "Crystal Cluster",
        "description": "Random glowing crystals in a dark environment",
        "objects": "10+ objects",
        "invokes": {"tool": "smart_compose", "template": "crystal_cluster"},
    },
    {
        "id": "product_showcase",
        "name": "Product Showcase",
        "description": "Pedestal with product under dramatic spotlight",
        "objects": "6 objects",
        "invokes": {"tool": "smart_compose", "template": "product_showcase"},
    },
]

# Skill-aligned templates — invoked through the invoke_skill tool.
_SKILL_TEMPLATES: List[Dict[str, Any]] = [
    {
        "id": "spiral_staircase",
        "name": "Spiral Staircase",
        "description": "Central pillar with steps spiraling upward, stone material",
        "objects": "17 objects",
        "invokes": {"tool": "invoke_skill", "skill": "spiral_staircase"},
    },
    {
        "id": "colonnade",
        "name": "Colonnade",
        "description": "Row of marble columns on a plinth, classical architecture",
        "objects": "9 objects",
        "invokes": {"tool": "invoke_skill", "skill": "colonnade"},
    },
    {
        "id": "forest",
        "name": "Forest",
        "description": "Scattered trees with trunks and leafy crowns on a ground plane",
        "objects": "24+ objects",
        "invokes": {"tool": "invoke_skill", "skill": "forest"},
    },
    {
        "id": "crystal_garden",
        "name": "Crystal Garden",
        "description": "Cluster of glowing polyhedra on a reflective floor",
        "objects": "10+ objects",
        "invokes": {"tool": "invoke_skill", "skill": "crystal_garden"},
    },
    {
        "id": "dna_helix",
        "name": "DNA Helix",
        "description": "Double helix of spheres connected by rungs, rotating",
        "objects": "50+ objects",
        "invokes": {"tool": "invoke_skill", "skill": "dna_helix"},
    },
    {
        "id": "spiral_galaxy",
        "name": "Spiral Galaxy",
        "description": "Central bulge with two spiral arms of stars, dark sky",
        "objects": "120+ stars",
        "invokes": {"tool": "invoke_skill", "skill": "spiral_galaxy"},
    },
    {
        "id": "studio_lighting_skill",
        "name": "Studio Lighting Rig",
        "description": "Three-point key/fill/rim light rig with a display platform",
        "objects": "4 lights + platform",
        "invokes": {"tool": "invoke_skill", "skill": "studio_lighting"},
    },
    {
        "id": "atom",
        "name": "Atom Model",
        "description": "Glowing nucleus with three electron orbits and shells",
        "objects": "7 objects",
        "invokes": {"tool": "invoke_skill", "skill": "atom"},
    },
    {
        "id": "gear_assembly",
        "name": "Gear Assembly",
        "description": "Row of interlocking metal gears with radial teeth that visually mesh",
        "objects": "3 gears + teeth + axles",
        "invokes": {"tool": "invoke_skill", "skill": "gear_assembly"},
    },
    {
        "id": "molecule",
        "name": "Molecule",
        "description": "Ball-and-stick molecule: central atom with satellites and bond cylinders",
        "objects": "1 center + 4 satellites + 4 bonds",
        "invokes": {"tool": "invoke_skill", "skill": "molecule"},
    },
    {
        "id": "snowman",
        "name": "Snowman",
        "description": "Three stacked snow spheres with carrot nose, coal eyes, stick arms, and top hat",
        "objects": "3 spheres + nose + eyes + arms + hat",
        "invokes": {"tool": "invoke_skill", "skill": "snowman"},
    },
    {
        "id": "bridge",
        "name": "Suspension Bridge",
        "description": "Deck, piers, towers, main cables, and hangers over a water plane",
        "objects": "Deck + 2 towers + cables + hangers + water",
        "invokes": {"tool": "invoke_skill", "skill": "bridge"},
    },
    {
        "id": "zen_garden",
        "name": "Zen Garden",
        "description": "Raked sand garden with scattered stones, moss patches, and a muted backdrop",
        "objects": "Sand plane + 5 stones + 3 moss patches",
        "invokes": {"tool": "invoke_skill", "skill": "zen_garden"},
    },
]


class ListSceneTemplatesTool(ToolBase):
    """List every available scene template.

    Returns the same catalog the frontend SceneTemplates modal renders so
    the Agent can answer "which templates are available?" deterministically
    without an LLM round-trip. Each entry includes the ``invokes`` field
    describing the tool + argument pair that materializes the template
    (``smart_compose`` for the 5 base templates, ``invoke_skill`` for the
    skill-aligned templates).
    """

    name = "list_scene_templates"
    description = (
        "List every available scene template (smart_compose presets + skill-aligned "
        "templates) with id, name, description, and the tool invocation that materializes it."
    )

    def schema(self) -> Dict[str, Any]:
        return _LIST_SCENE_TEMPLATES_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        include_skills = bool(arguments.get("include_skills", True))
        items: List[Dict[str, Any]] = list(_SCENE_TEMPLATES)
        if include_skills:
            items.extend(_SKILL_TEMPLATES)

        by_id: Dict[str, Dict[str, Any]] = {}
        for entry in items:
            by_id[entry["id"]] = entry

        names = ", ".join(f"{e['name']} ({e['id']})" for e in items[:8])
        if len(items) > 8:
            names += f", ... ({len(items)} total)"
        return ToolResult(
            success=True,
            message=f"{len(items)} scene template(s) available: {names}",
            data={"templates": items, "count": len(items), "by_id": by_id},
        )


# ---------------------------------------------------------------------------
# 2. orbit_viewport
# ---------------------------------------------------------------------------

_ORBIT_VIEWPORT_PARAMS = {
    "type": "object",
    "properties": {
        "target": {
            "type": "string",
            "description": "Optional object id or name to orbit around. Defaults to the scene origin ([0, 0.5, 0]).",
        },
        "radius": {
            "type": "number",
            "description": "Orbit radius in world units (default 5.0)",
        },
        "height": {
            "type": "number",
            "description": "Camera height above the orbit center (default 2.0)",
        },
        "speed": {
            "type": "number",
            "description": "Angular speed in radians/second (default 0.5; negative reverses direction)",
        },
        "duration": {
            "type": "number",
            "description": "Optional duration in seconds. When 0 or omitted, the orbit runs until stop_camera_flythrough / orbit_viewport(stop=true) is called.",
        },
        "loop": {
            "type": "boolean",
            "description": "Whether to loop the orbit (default true when duration > 0, otherwise true as well)",
        },
        "stop": {
            "type": "boolean",
            "description": "If true, stop any active orbit and return the camera to its prior position (default false).",
        },
    },
    "required": [],
}


class OrbitViewportTool(ToolBase):
    """Start or stop an automatic orbit of the viewport camera.

    Emits an ``editor_orbit_viewport`` delta the frontend dispatches to the
    camera rig. Distinct from ``set_viewport_camera`` (a one-shot camera
    placement) and ``camera_flythrough`` (waypoint-based): orbit_viewport
    keeps the camera circling a target at a fixed radius, which is the
    standard "turntable" presentation mode for 3D showcases.
    """

    name = "orbit_viewport"
    description = (
        "Start or stop a turntable orbit of the viewport camera around a target "
        "(object id/name or world origin). Useful for showcasing a model. "
        "Set stop=true to dismiss an active orbit."
    )

    def schema(self) -> Dict[str, Any]:
        return _ORBIT_VIEWPORT_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        stop = bool(arguments.get("stop", False))
        if stop:
            return ToolResult(
                success=True,
                message="Viewport orbit stopped",
                deltas=[SceneDelta(action="editor_orbit_viewport", payload={"stop": True})],
                data={"stop": True},
            )

        # Resolve target — defaults to scene origin.
        target_id = str(arguments.get("target", "")).strip()
        target_point: List[float] = [0.0, 0.5, 0.0]
        target_label = "origin"
        if target_id:
            obj = scene.find_object(target_id)
            if obj is None:
                return ToolResult(
                    success=False,
                    message=f"Orbit target not found: {target_id}",
                )
            pos = obj.transform.position
            target_point = [float(pos[0]), float(pos[1]), float(pos[2])]
            target_label = obj.name

        try:
            radius = float(arguments.get("radius", 5.0))
            height = float(arguments.get("height", 2.0))
            speed = float(arguments.get("speed", 0.5))
            duration = float(arguments.get("duration", 0.0))
        except (TypeError, ValueError):
            return ToolResult(success=False, message="radius/height/speed/duration must be numbers")

        if radius <= 0:
            return ToolResult(success=False, message="radius must be > 0")

        loop = bool(arguments.get("loop", True))

        payload: Dict[str, Any] = {
            "target": target_point,
            "target_label": target_label,
            "radius": radius,
            "height": height,
            "speed": speed,
            "duration": duration,
            "loop": loop,
            "stop": False,
        }
        label = f"orbiting {target_label} at radius {radius:.2f}"
        if duration > 0:
            label += f" for {duration:.1f}s"
        else:
            label += " (until stopped)"
        return ToolResult(
            success=True,
            message=f"Viewport orbit started: {label}",
            deltas=[SceneDelta(action="editor_orbit_viewport", payload=payload)],
            data=payload,
        )


# ---------------------------------------------------------------------------
# 3. set_layer_visibility
# ---------------------------------------------------------------------------

_SET_LAYER_VISIBILITY_PARAMS = {
    "type": "object",
    "properties": {
        "layer": {
            "type": "string",
            "description": "Layer name whose objects should be shown or hidden",
        },
        "visible": {
            "type": "boolean",
            "description": "Visibility state to apply to every object on the layer (default true)",
        },
    },
    "required": ["layer"],
}


def _layer_of(obj: Any) -> str:
    """Return the layer name tagged on an object (default 'default')."""
    for t in getattr(obj, "tags", []) or []:
        if isinstance(t, str) and t.startswith("layer:"):
            return t[len("layer:"):]
    return "default"


class SetLayerVisibilityTool(ToolBase):
    """Show or hide every object on a named layer in one call.

    Complements ``set_object_layer`` (which assigns a single object to a
    layer) with bulk visibility control: hide the "annotations" layer, show
    the "structural" layer, etc. Objects not on the named layer are
    untouched.
    """

    name = "set_layer_visibility"
    description = (
        "Show or hide every object on a named layer at once. Use for bulk "
        "visibility control of structural / decorative / annotation layers."
    )

    def schema(self) -> Dict[str, Any]:
        return _SET_LAYER_VISIBILITY_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        layer = str(arguments.get("layer", "")).strip()
        if not layer:
            return ToolResult(success=False, message="layer name is required")
        visible = bool(arguments.get("visible", True))

        deltas: List[SceneDelta] = []
        toggled: List[str] = []
        for obj in scene.objects:
            if _layer_of(obj) != layer:
                continue
            if obj.visible == visible:
                continue
            obj.visible = visible
            deltas.append(SceneDelta(action="update", target_id=obj.id, payload={"visible": visible}))
            toggled.append(obj.name)

        if not toggled:
            return ToolResult(
                success=True,
                message=f"Layer '{layer}' has no objects needing visibility={visible}",
                data={"layer": layer, "visible": visible, "toggled": 0},
            )

        state = "visible" if visible else "hidden"
        names = ", ".join(toggled[:5])
        if len(toggled) > 5:
            names += f", ... ({len(toggled)} total)"
        return ToolResult(
            success=True,
            message=f"Layer '{layer}' is now {state}: {names}",
            deltas=deltas,
            data={"layer": layer, "visible": visible, "toggled": len(toggled), "objects": toggled},
        )


# ---------------------------------------------------------------------------
# 4. list_skills
# ---------------------------------------------------------------------------

_LIST_SKILLS_PARAMS = {
    "type": "object",
    "properties": {
        "category": {
            "type": "string",
            "description": "Optional category filter (architecture / nature / abstract / lighting / layout)",
        },
    },
    "required": [],
}


class ListSkillsTool(ToolBase):
    """List every registered creative skill.

    Mirrors the ``invoke_skill`` tool's static skill catalog so the Agent
    can answer "what skills are available?" deterministically without an
    LLM round-trip. Each entry carries the skill name, description,
    category, and parameter schema so the Agent can compose valid
    ``invoke_skill`` arguments in the next turn.
    """

    name = "list_skills"
    description = (
        "List every registered creative skill (multi-tool recipe) with name, "
        "description, category, and parameter schema. Use to discover what "
        "skills can be invoked via invoke_skill."
    )

    def schema(self) -> Dict[str, Any]:
        return _LIST_SKILLS_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        # Lazy import to avoid a circular dependency at module import time
        # (skill_tool imports build_default_registry lazily, but listing
        # the registry here keeps the catalog fresh).
        from trigen.skills import build_default_registry

        category = str(arguments.get("category", "")).strip() or None
        reg = build_default_registry()
        items: List[Dict[str, Any]] = []
        for skill in reg.all():
            if category and skill.category != category:
                continue
            items.append({
                "name": skill.name,
                "description": skill.description,
                "category": skill.category,
                "icon": skill.icon,
                "parameters": skill.schema(),
            })
        items.sort(key=lambda s: (s["category"], s["name"]))

        if not items:
            return ToolResult(
                success=True,
                message=f"No skills found" + (f" in category '{category}'" if category else ""),
                data={"skills": [], "count": 0, "category": category},
            )

        names = ", ".join(s["name"] for s in items[:8])
        if len(items) > 8:
            names += f", ... ({len(items)} total)"
        return ToolResult(
            success=True,
            message=f"{len(items)} skill(s) available: {names}",
            data={"skills": items, "count": len(items), "category": category},
        )
