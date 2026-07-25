"""Smart scene composition tool.

Generates a complete scene from a named template: solar_system, city_block,
studio, crystal_cluster, product_showcase. Each template creates multiple
objects, lights, and configures background/fog.
"""

from __future__ import annotations

import math
import random
from typing import Any, Dict, List, Tuple

from trigen.scene import (
    GEOMETRY_DEFAULTS,
    CameraObject,
    Geometry,
    LightObject,
    Material,
    Scene,
    SceneObject,
    Transform,
)
from trigen.tools.base import SceneDelta, ToolBase, ToolResult


_SMART_COMPOSE_PARAMS = {
    "type": "object",
    "properties": {
        "template": {
            "type": "string",
            "enum": [
                "solar_system",
                "city_block",
                "studio",
                "crystal_cluster",
                "product_showcase",
            ],
            "description": "Scene template name",
        },
        "clear_scene": {
            "type": "boolean",
            "description": "Whether to clear existing objects, lights, and groups before generating (default true)",
        },
        "seed": {
            "type": "integer",
            "description": "Random seed (if omitted, uses system random)",
        },
    },
    "required": ["template"],
}


def _make_object(name: str, geo_type: str, position: List[float], color: str = "#cccccc", **mat_kw: Any) -> SceneObject:
    """Helper to build a SceneObject with default geo params for the given type."""
    params = dict(GEOMETRY_DEFAULTS.get(geo_type, {}))
    mat = Material(color=color, **mat_kw)
    return SceneObject(
        name=name,
        type="mesh",
        geometry=Geometry(type=geo_type, params=params),
        material=mat,
        transform=Transform(position=[float(p) for p in position]),
    )


def _make_light(name: str, light_type: str, **kw: Any) -> LightObject:
    """Helper to build a LightObject."""
    return LightObject(name=name, type=light_type, **kw)


def _clear_scene(scene: Scene) -> Tuple[List[SceneDelta], int]:
    """Clear objects/lights/groups, returning delete deltas and cleared count."""
    deltas: List[SceneDelta] = []
    count = 0
    for obj in list(scene.objects):
        count += 1
        deltas.append(SceneDelta(action="delete", target_id=obj.id))
    for light in list(scene.lights):
        count += 1
        deltas.append(SceneDelta(action="delete_light", target_id=light.id))
    for group in list(scene.groups):
        count += 1
        deltas.append(SceneDelta(action="delete_group", target_id=group.id))
    scene.objects.clear()
    scene.lights.clear()
    scene.groups.clear()
    return deltas, count


# ------------------------------------------------------------------
# Templates
# ------------------------------------------------------------------

def _compose_solar_system(scene: Scene, rng: random.Random) -> Tuple[List[SceneDelta], List[str], List[str]]:
    """Solar system template: glowing sun + 8 planets with orbit rings."""
    deltas: List[SceneDelta] = []
    notes: List[str] = []

    scene.background = "#01010a"
    scene.fog = None

    # Sun
    sun = _make_object("Sun", "sphere", [0, 0, 0], color="#ffcc33",
                       emissive="#ffaa00", emissive_intensity=2.5)
    sun.geometry.params["radius"] = 1.6
    sun.geometry.params["widthSegments"] = 48
    sun.geometry.params["heightSegments"] = 24
    scene.objects.append(sun)
    deltas.append(SceneDelta(action="create", target_id=sun.id, payload=sun.to_dict()))

    # Point light at sun (no decay so planets stay lit)
    sun_light = _make_light("SunLight", "point", color="#fff2cc", intensity=2.5,
                            position=[0, 0, 0], distance=0, decay=0)
    scene.lights.append(sun_light)
    deltas.append(SceneDelta(action="create_light", target_id=sun_light.id, payload=sun_light.to_dict()))

    # Star ambient
    ambient = _make_light("StarAmbient", "ambient", color="#223355", intensity=0.25)
    scene.lights.append(ambient)
    deltas.append(SceneDelta(action="create_light", target_id=ambient.id, payload=ambient.to_dict()))

    planets = [
        ("Mercury", 0.25, 3.0,  "#9c9c9c"),
        ("Venus",   0.45, 4.2,  "#e0b070"),
        ("Earth",   0.50, 5.6,  "#3a7aff"),
        ("Mars",    0.35, 7.0,  "#c1440e"),
        ("Jupiter", 1.10, 9.5,  "#d8a878"),
        ("Saturn",  0.95, 12.0, "#e3c98f"),
        ("Uranus",  0.70, 14.5, "#7fdada"),
        ("Neptune", 0.68, 17.0, "#3a5aff"),
    ]
    for name, radius, orbit, color in planets:
        angle = rng.uniform(0, 2 * math.pi)
        pos = [orbit * math.cos(angle), 0, orbit * math.sin(angle)]
        planet = _make_object(name, "sphere", pos, color=color)
        planet.geometry.params["radius"] = radius
        planet.geometry.params["widthSegments"] = 32
        planet.geometry.params["heightSegments"] = 16
        scene.objects.append(planet)
        deltas.append(SceneDelta(action="create", target_id=planet.id, payload=planet.to_dict()))

        # Orbit ring
        ring = _make_object(f"{name}_Orbit", "ring", [0, 0, 0], color="#2a2a3a")
        ring.geometry.params = {
            "innerRadius": orbit - 0.02,
            "outerRadius": orbit + 0.02,
            "thetaSegments": 96,
        }
        ring.transform.rotation = [math.pi / 2, 0, 0]
        ring.material.opacity = 0.5
        ring.material.side = "double"
        scene.objects.append(ring)
        deltas.append(SceneDelta(action="create", target_id=ring.id, payload=ring.to_dict()))

    # Camera
    cam = CameraObject(name="SolarCamera", position=[0, 22, 28], target=[0, 0, 0], fov=50)
    scene.cameras.append(cam)
    deltas.append(SceneDelta(action="create_camera", target_id=cam.id, payload=cam.to_dict()))

    notes.append("Solar system: 1 glowing sun + 8 planets with orbit rings, deep space background")
    return deltas, ["background->#01010a", "fog->off"], notes


def _compose_city_block(scene: Scene, rng: random.Random) -> Tuple[List[SceneDelta], List[str], List[str]]:
    """City block template: grid of varied buildings + ground plane."""
    deltas: List[SceneDelta] = []
    notes: List[str] = []

    scene.background = "#87a8c8"
    scene.fog = {"color": "#87a8c8", "near": 25, "far": 80}

    # Ground
    ground = _make_object("Ground", "plane", [0, 0, 0], color="#3a3f4a")
    ground.geometry.params = {"width": 40, "height": 40, "widthSegments": 1, "heightSegments": 1}
    ground.transform.rotation = [-math.pi / 2, 0, 0]
    scene.objects.append(ground)
    deltas.append(SceneDelta(action="create", target_id=ground.id, payload=ground.to_dict()))

    # Buildings in a grid
    grid_n = 5
    spacing = 6.0
    start = -(grid_n - 1) * spacing / 2
    building_idx = 0
    building_colors = ["#6b7280", "#8a94a6", "#4b5563", "#9aa3b2", "#5c6573"]
    for r in range(grid_n):
        for c in range(grid_n):
            # Skip some cells to leave room for roads
            if rng.random() < 0.12:
                continue
            h = rng.uniform(2.0, 9.0)
            w = rng.uniform(2.0, 4.0)
            d = rng.uniform(2.0, 4.0)
            pos = [start + c * spacing, h / 2, start + r * spacing]
            color = rng.choice(building_colors)
            b = _make_object(f"Building_{building_idx + 1}", "box", pos, color=color,
                             metalness=0.2, roughness=0.7)
            b.geometry.params = {
                "width": w, "height": h, "depth": d,
                "widthSegments": 1, "heightSegments": 1, "depthSegments": 1,
            }
            scene.objects.append(b)
            deltas.append(SceneDelta(action="create", target_id=b.id, payload=b.to_dict()))
            building_idx += 1

    # Sun directional
    sun = _make_light("Sun", "directional", color="#fff4d6", intensity=1.4,
                      position=[18, 28, 12], target=[0, 0, 0])
    scene.lights.append(sun)
    deltas.append(SceneDelta(action="create_light", target_id=sun.id, payload=sun.to_dict()))

    # Sky ambient
    amb = _make_light("SkyAmbient", "ambient", color="#aac4e0", intensity=0.5)
    scene.lights.append(amb)
    deltas.append(SceneDelta(action="create_light", target_id=amb.id, payload=amb.to_dict()))

    cam = CameraObject(name="CityCamera", position=[22, 18, 22], target=[0, 2, 0], fov=50)
    scene.cameras.append(cam)
    deltas.append(SceneDelta(action="create_camera", target_id=cam.id, payload=cam.to_dict()))

    notes.append(f"City block: {building_idx} buildings + ground, sky background with fog")
    return deltas, [f"background->{scene.background}", f"fog->{scene.fog}"], notes


def _compose_studio(scene: Scene, rng: random.Random) -> Tuple[List[SceneDelta], List[str], List[str]]:
    """Studio template: 3-point lighting + platform + subject."""
    deltas: List[SceneDelta] = []
    notes: List[str] = []

    scene.background = "#1a1a22"
    scene.fog = {"color": "#1a1a22", "near": 18, "far": 55}

    # Platform
    platform = _make_object("Platform", "cylinder", [0, 0.1, 0], color="#2a2a32",
                            metalness=0.6, roughness=0.3)
    platform.geometry.params = {
        "radiusTop": 3.0, "radiusBottom": 3.0, "height": 0.2, "radialSegments": 64,
    }
    scene.objects.append(platform)
    deltas.append(SceneDelta(action="create", target_id=platform.id, payload=platform.to_dict()))

    # Subject
    subject = _make_object("Subject", "torusKnot", [0, 2.0, 0], color="#00F0FF",
                           metalness=1.0, roughness=0.15)
    subject.geometry.params = {
        "radius": 0.9, "tube": 0.28, "tubularSegments": 96, "radialSegments": 12, "p": 2, "q": 3,
    }
    scene.objects.append(subject)
    deltas.append(SceneDelta(action="create", target_id=subject.id, payload=subject.to_dict()))

    # 3-point lighting
    key_light = _make_light("KeyLight", "spot", color="#ffffff", intensity=2.0,
                            position=[5, 7, 5], target=[0, 1.5, 0],
                            angle=0.6, penumbra=0.4, distance=20, decay=1.5)
    scene.lights.append(key_light)
    deltas.append(SceneDelta(action="create_light", target_id=key_light.id, payload=key_light.to_dict()))

    fill_light = _make_light("FillLight", "spot", color="#aaccff", intensity=0.8,
                             position=[-5, 4, 3], target=[0, 1.5, 0],
                             angle=0.9, penumbra=0.6, distance=20, decay=1.5)
    scene.lights.append(fill_light)
    deltas.append(SceneDelta(action="create_light", target_id=fill_light.id, payload=fill_light.to_dict()))

    back_light = _make_light("BackLight", "spot", color="#ffd9a0", intensity=1.2,
                             position=[0, 6, -6], target=[0, 1.5, 0],
                             angle=0.7, penumbra=0.5, distance=20, decay=1.5)
    scene.lights.append(back_light)
    deltas.append(SceneDelta(action="create_light", target_id=back_light.id, payload=back_light.to_dict()))

    amb = _make_light("StudioAmbient", "ambient", color="#404050", intensity=0.2)
    scene.lights.append(amb)
    deltas.append(SceneDelta(action="create_light", target_id=amb.id, payload=amb.to_dict()))

    cam = CameraObject(name="StudioCamera", position=[6, 4, 6], target=[0, 1.5, 0], fov=40)
    scene.cameras.append(cam)
    deltas.append(SceneDelta(action="create_camera", target_id=cam.id, payload=cam.to_dict()))

    notes.append("Studio: 3-point lighting + platform + TorusKnot subject")
    return deltas, [f"background->{scene.background}", f"fog->{scene.fog}"], notes


def _compose_crystal_cluster(scene: Scene, rng: random.Random) -> Tuple[List[SceneDelta], List[str], List[str]]:
    """Crystal cluster template: random glowing crystals in a dark scene."""
    deltas: List[SceneDelta] = []
    notes: List[str] = []

    scene.background = "#06060c"
    scene.fog = {"color": "#06060c", "near": 12, "far": 40}

    palette = ["#00F0FF", "#FFB800", "#FF3ACC", "#9A3AFF", "#3AFFB0", "#3A7AFF"]
    geo_choices = ["octahedron", "cone", "icosahedron", "tetrahedron"]
    n = rng.randint(8, 14)

    for i in range(n):
        geo_type = rng.choice(geo_choices)
        color = rng.choice(palette)
        radius = rng.uniform(0.3, 0.9)
        pos = [rng.uniform(-4, 4), rng.uniform(0.2, 4.0), rng.uniform(-4, 4)]
        crystal = _make_object(f"Crystal_{i + 1}", geo_type, pos, color=color,
                               metalness=0.1, roughness=0.2,
                               emissive=color, emissive_intensity=rng.uniform(0.6, 1.6),
                               opacity=0.85)
        crystal.geometry.params = dict(GEOMETRY_DEFAULTS.get(geo_type, {}))
        crystal.geometry.params["radius"] = radius
        crystal.transform.rotation = [
            rng.uniform(0, math.pi), rng.uniform(0, math.pi), rng.uniform(0, math.pi),
        ]
        scene.objects.append(crystal)
        deltas.append(SceneDelta(action="create", target_id=crystal.id, payload=crystal.to_dict()))

    # Soft point light at center
    core = _make_light("CoreLight", "point", color="#ffffff", intensity=1.2,
                       position=[0, 2, 0], distance=12, decay=1.5)
    scene.lights.append(core)
    deltas.append(SceneDelta(action="create_light", target_id=core.id, payload=core.to_dict()))

    amb = _make_light("CrystalAmbient", "ambient", color="#1a1a2e", intensity=0.3)
    scene.lights.append(amb)
    deltas.append(SceneDelta(action="create_light", target_id=amb.id, payload=amb.to_dict()))

    cam = CameraObject(name="CrystalCamera", position=[7, 5, 7], target=[0, 1.5, 0], fov=45)
    scene.cameras.append(cam)
    deltas.append(SceneDelta(action="create_camera", target_id=cam.id, payload=cam.to_dict()))

    notes.append(f"Crystal cluster: {n} glowing crystals + dark background with fog")
    return deltas, [f"background->{scene.background}", f"fog->{scene.fog}"], notes


def _compose_product_showcase(scene: Scene, rng: random.Random) -> Tuple[List[SceneDelta], List[str], List[str]]:
    """Product showcase template: pedestal + product + spotlight."""
    deltas: List[SceneDelta] = []
    notes: List[str] = []

    scene.background = "#0c0c10"
    scene.fog = {"color": "#0c0c10", "near": 15, "far": 50}

    # Pedestal
    pedestal = _make_object("Pedestal", "cylinder", [0, 0.6, 0], color="#1f1f25",
                            metalness=0.8, roughness=0.25)
    pedestal.geometry.params = {
        "radiusTop": 1.2, "radiusBottom": 1.3, "height": 1.2, "radialSegments": 64,
    }
    scene.objects.append(pedestal)
    deltas.append(SceneDelta(action="create", target_id=pedestal.id, payload=pedestal.to_dict()))

    # Product
    product = _make_object("Product", "sphere", [0, 2.1, 0], color="#ffc933",
                           metalness=1.0, roughness=0.18)
    product.geometry.params = {"radius": 0.7, "widthSegments": 48, "heightSegments": 24}
    scene.objects.append(product)
    deltas.append(SceneDelta(action="create", target_id=product.id, payload=product.to_dict()))

    # Spotlight on product
    spot = _make_light("ShowcaseSpot", "spot", color="#ffffff", intensity=3.0,
                       position=[0, 7, 2], target=[0, 2.0, 0],
                       angle=0.5, penumbra=0.3, distance=15, decay=1.2)
    scene.lights.append(spot)
    deltas.append(SceneDelta(action="create_light", target_id=spot.id, payload=spot.to_dict()))

    # Rim light
    rim = _make_light("RimLight", "directional", color="#3a7aff", intensity=0.8,
                      position=[-4, 3, -4], target=[0, 2.0, 0])
    scene.lights.append(rim)
    deltas.append(SceneDelta(action="create_light", target_id=rim.id, payload=rim.to_dict()))

    amb = _make_light("ShowAmbient", "ambient", color="#202028", intensity=0.25)
    scene.lights.append(amb)
    deltas.append(SceneDelta(action="create_light", target_id=amb.id, payload=amb.to_dict()))

    cam = CameraObject(name="ShowcaseCamera", position=[4, 3, 4], target=[0, 1.6, 0], fov=35)
    scene.cameras.append(cam)
    deltas.append(SceneDelta(action="create_camera", target_id=cam.id, payload=cam.to_dict()))

    notes.append("Product showcase: pedestal + product + spotlight, dark background")
    return deltas, [f"background->{scene.background}", f"fog->{scene.fog}"], notes


_TEMPLATES = {
    "solar_system": _compose_solar_system,
    "city_block": _compose_city_block,
    "studio": _compose_studio,
    "crystal_cluster": _compose_crystal_cluster,
    "product_showcase": _compose_product_showcase,
}


class SmartComposeTool(ToolBase):
    """Smart scene composition tool."""

    name = "smart_compose"
    description = (
        "Generate a complete scene from a template (solar_system/city_block/studio/crystal_cluster/product_showcase), "
        "automatically creating objects, lights, background, and fog."
    )

    def schema(self) -> Dict[str, Any]:
        return _SMART_COMPOSE_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        template = arguments.get("template", "")

        # Special: _clear template just clears the scene without generating
        if template == "_clear":
            deltas: List[SceneDelta] = []
            clear_deltas, cleared_count = _clear_scene(scene)
            deltas.extend(clear_deltas)
            return ToolResult(
                success=True,
                message=f"Scene cleared ({cleared_count} items removed)",
                deltas=deltas,
                data={"template": "_clear", "cleared": cleared_count},
            )

        composer = _TEMPLATES.get(template)
        if not composer:
            return ToolResult(
                success=False,
                message=f"Unknown template: {template}, available: {', '.join(_TEMPLATES.keys())}",
            )

        # Random seed (None -> system random)
        seed = arguments.get("seed")
        rng = random.Random(seed) if seed is not None else random.Random()

        deltas: List[SceneDelta] = []
        cleared_note = ""
        if arguments.get("clear_scene", True):
            clear_deltas, cleared_count = _clear_scene(scene)
            deltas.extend(clear_deltas)
            if cleared_count:
                cleared_note = f"Cleared {cleared_count} existing items; "

        # Run template
        comp_deltas, env_changes, notes = composer(scene, rng)
        deltas.extend(comp_deltas)

        # Environment deltas
        deltas.append(SceneDelta(action="set_background", payload={"color": scene.background}))
        deltas.append(SceneDelta(action="set_fog", payload={"fog": scene.fog}))

        obj_count = len(scene.objects)
        light_count = len(scene.lights)
        cam_count = len(scene.cameras)
        message = (
            f"{cleared_note}Generated '{template}' scene: {obj_count} objects, "
            f"{light_count} lights, {cam_count} cameras. "
            + ("; ".join(notes) if notes else "")
            + f". Environment: {', '.join(env_changes)}"
        )

        return ToolResult(
            success=True,
            message=message,
            deltas=deltas,
            data={
                "template": template,
                "object_count": obj_count,
                "light_count": light_count,
                "camera_count": cam_count,
                "background": scene.background,
                "fog": scene.fog,
                "notes": notes,
            },
        )
