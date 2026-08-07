"""Trigen scene data model.

Defines the unified representation of scene objects, materials, transforms,
lights, cameras, and groups, serving as the shared contract between agent
tools and frontend rendering.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Tuple


def _gen_id(prefix: str = "obj") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


@dataclass
class Transform:
    """Object spatial transform."""

    position: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    rotation: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])  # Euler angles (radians)
    scale: List[float] = field(default_factory=lambda: [1.0, 1.0, 1.0])

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Material:
    """Standard PBR material with extended physical properties.

    Beyond the base metalness/roughness model, supports the clearcoat,
    transmission, iridescence, and sheen layers used by modern PBR
    shaders (three.js MeshPhysicalMaterial). All extended fields default
    to physically-plausible zero values so existing scenes round-trip
    without changes — older payloads simply omit the new keys.
    """

    color: str = "#cccccc"
    metalness: float = 0.0
    roughness: float = 0.5
    opacity: float = 1.0
    wireframe: bool = False
    emissive: str = "#000000"
    emissive_intensity: float = 0.0
    flat_shading: bool = False
    side: str = "front"  # front / back / double
    # Clearcoat layer (car paint, lacquer). 0 = no clearcoat.
    clearcoat: float = 0.0
    clearcoat_roughness: float = 0.0
    # Transmission (glass, water). 0 = opaque, 1 = fully transmissive.
    transmission: float = 0.0
    thickness: float = 0.0  # volume thickness for refraction
    ior: float = 1.5  # index of refraction (1.0 = air, 1.5 = glass, 2.4 = diamond)
    # Iridescence (thin-film interference — soap bubbles, oil slicks).
    iridescence: float = 0.0
    iridescence_ior: float = 1.3
    iridescence_thickness_min: float = 100.0
    iridescence_thickness_max: float = 400.0
    # Sheen (velvet, fabric, dust). 0 = no sheen.
    sheen: float = 0.0
    sheen_color: str = "#000000"
    sheen_roughness: float = 1.0
    # Specular intensity scaling (controls dielectric specular highlight).
    specular_intensity: float = 1.0
    specular_color: str = "#ffffff"
    # Attenuation color + distance for volumetric absorption inside
    # transmissive materials (tinted glass, colored liquids).
    attenuation_color: str = "#ffffff"
    attenuation_distance: float = 0.0  # 0 = no attenuation

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Geometry:
    """Geometry description."""

    type: str = "box"  # box/sphere/cylinder/cone/torus/plane/...
    params: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {"type": self.type, "params": self.params}


@dataclass
class SceneObject:
    """A single object in the scene."""

    id: str = field(default_factory=lambda: _gen_id("obj"))
    name: str = "Object"
    type: str = "mesh"  # mesh / light / group / camera
    geometry: Geometry = field(default_factory=Geometry)
    material: Material = field(default_factory=Material)
    transform: Transform = field(default_factory=Transform)
    visible: bool = True
    locked: bool = False
    group_id: Optional[str] = None  # parent group id
    tags: List[str] = field(default_factory=list)
    animation: Optional[Dict[str, Any]] = None  # keyframe/orbit/wave/bounce descriptor

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "geometry": self.geometry.to_dict(),
            "material": self.material.to_dict(),
            "transform": self.transform.to_dict(),
            "visible": self.visible,
            "locked": self.locked,
            "group_id": self.group_id,
            "tags": list(self.tags),
            "animation": self.animation,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SceneObject":
        geo = Geometry(**data.get("geometry", {}))
        mat = Material(**data.get("material", {}))
        tf = Transform(**data.get("transform", {}))
        return cls(
            id=data.get("id", _gen_id("obj")),
            name=data.get("name", "Object"),
            type=data.get("type", "mesh"),
            geometry=geo,
            material=mat,
            transform=tf,
            visible=data.get("visible", True),
            locked=data.get("locked", False),
            group_id=data.get("group_id"),
            tags=list(data.get("tags", [])),
            animation=data.get("animation"),
        )


@dataclass
class LightObject:
    """Light object."""

    id: str = field(default_factory=lambda: _gen_id("light"))
    name: str = "Light"
    type: str = "directional"  # ambient/directional/point/spot/hemisphere
    color: str = "#ffffff"
    intensity: float = 1.0
    position: List[float] = field(default_factory=lambda: [5.0, 5.0, 5.0])
    target: Optional[List[float]] = None
    cast_shadow: bool = True
    # Spot-specific
    angle: float = 0.785398  # Math.PI/4
    penumbra: float = 0.2
    distance: float = 0.0  # 0 = infinite
    decay: float = 2.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "color": self.color,
            "intensity": self.intensity,
            "position": self.position,
            "target": self.target,
            "cast_shadow": self.cast_shadow,
            "angle": self.angle,
            "penumbra": self.penumbra,
            "distance": self.distance,
            "decay": self.decay,
            "_kind": "light",
        }


@dataclass
class CameraObject:
    """Camera object."""

    id: str = field(default_factory=lambda: _gen_id("cam"))
    name: str = "Camera"
    type: str = "perspective"  # perspective / orthographic
    position: List[float] = field(default_factory=lambda: [5.0, 4.0, 7.0])
    target: List[float] = field(default_factory=lambda: [0.0, 0.5, 0.0])
    fov: float = 45.0
    near: float = 0.1
    far: float = 1000.0
    animation: Optional[Dict[str, Any]] = None  # orbit/flythrough animation descriptor

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "position": self.position,
            "target": self.target,
            "fov": self.fov,
            "near": self.near,
            "far": self.far,
            "animation": self.animation,
            "_kind": "camera",
        }


@dataclass
class GroupObject:
    """Group object for organizing multiple objects."""

    id: str = field(default_factory=lambda: _gen_id("grp"))
    name: str = "Group"
    child_ids: List[str] = field(default_factory=list)
    visible: bool = True
    locked: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "child_ids": list(self.child_ids),
            "visible": self.visible,
            "locked": self.locked,
            "_kind": "group",
        }


@dataclass
class Scene:
    """Complete scene."""

    objects: List[SceneObject] = field(default_factory=list)
    lights: List[LightObject] = field(default_factory=list)
    cameras: List[CameraObject] = field(default_factory=list)
    groups: List[GroupObject] = field(default_factory=list)
    background: str = "#0a0a0f"
    environment: Optional[str] = None
    fog: Optional[Dict[str, Any]] = None  # {"color": "#0a0a0f", "near": 18, "far": 55}
    grid_visible: bool = True
    grid_size: float = 40.0
    # On-canvas annotations: text labels anchored to an object id or a
    # world-space position. Stored as plain dicts to keep the dataclass
    # forward-compatible with future annotation fields without costly
    # schema migrations.
    annotations: List[Dict[str, Any]] = field(default_factory=list)
    # Cinematic storyboard: a sequence of camera shots that plays as a
    # scripted camera tour. Stored as a plain dict (title + shots + playback
    # state) so the shape can evolve without dataclass churn. Mirrors the
    # annotations field's forward-compatibility approach.
    storyboard: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "objects": [o.to_dict() for o in self.objects],
            "lights": [l.to_dict() for l in self.lights],
            "cameras": [c.to_dict() for c in self.cameras],
            "groups": [g.to_dict() for g in self.groups],
            "background": self.background,
            "environment": self.environment,
            "fog": self.fog,
            "grid_visible": self.grid_visible,
            "grid_size": self.grid_size,
            "annotations": list(self.annotations),
            "storyboard": self.storyboard,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Scene":
        return cls(
            objects=[SceneObject.from_dict(o) for o in data.get("objects", [])],
            lights=[LightObject(**{k: v for k, v in l.items() if k != "_kind"}) for l in data.get("lights", [])],
            cameras=[CameraObject(**{k: v for k, v in c.items() if k != "_kind"}) for c in data.get("cameras", [])],
            groups=[GroupObject(**{k: v for k, v in g.items() if k != "_kind"}) for g in data.get("groups", [])],
            background=data.get("background", "#0a0a0f"),
            environment=data.get("environment"),
            fog=data.get("fog"),
            grid_visible=data.get("grid_visible", True),
            grid_size=data.get("grid_size", 40.0),
            annotations=list(data.get("annotations", [])),
            storyboard=data.get("storyboard"),
        )

    def find_object(self, identifier: str) -> Optional[SceneObject]:
        """Find an object by id or name."""
        for obj in self.objects:
            if obj.id == identifier or obj.name.lower() == identifier.lower():
                return obj
        return None

    def find_objects(self, identifiers: List[str]) -> List[SceneObject]:
        """Find multiple objects by id or name."""
        found: List[SceneObject] = []
        seen_ids = set()
        for identifier in identifiers:
            obj = self.find_object(identifier)
            if obj and obj.id not in seen_ids:
                found.append(obj)
                seen_ids.add(obj.id)
        return found

    def find_light(self, identifier: str) -> Optional[LightObject]:
        """Find a light by id or name."""
        for light in self.lights:
            if light.id == identifier or light.name.lower() == identifier.lower():
                return light
        return None

    def remove_object(self, identifier: str) -> bool:
        obj = self.find_object(identifier)
        if obj:
            self.objects.remove(obj)
            # Detach from any group
            for g in self.groups:
                if obj.id in g.child_ids:
                    g.child_ids.remove(obj.id)
            return True
        return False

    def remove_light(self, identifier: str) -> bool:
        light = self.find_light(identifier)
        if light:
            self.lights.remove(light)
            return True
        return False

    def next_auto_name(self, base: str) -> str:
        """Generate a non-conflicting name with auto-increment index."""
        existing = {o.name for o in self.objects}
        if base not in existing:
            return base
        idx = 2
        while f"{base}_{idx}" in existing:
            idx += 1
        return f"{base}_{idx}"


# Geometry default parameter table
GEOMETRY_DEFAULTS: Dict[str, Dict[str, Any]] = {
    "box": {"width": 1.0, "height": 1.0, "depth": 1.0, "widthSegments": 1, "heightSegments": 1, "depthSegments": 1},
    "sphere": {"radius": 0.6, "widthSegments": 32, "heightSegments": 16},
    "cylinder": {"radiusTop": 0.5, "radiusBottom": 0.5, "height": 1.2, "radialSegments": 32},
    "cone": {"radius": 0.6, "height": 1.2, "radialSegments": 32},
    "torus": {"radius": 0.6, "tube": 0.2, "radialSegments": 12, "tubularSegments": 48},
    "plane": {"width": 2.0, "height": 2.0, "widthSegments": 1, "heightSegments": 1},
    "torusKnot": {"radius": 0.6, "tube": 0.2, "tubularSegments": 64, "radialSegments": 8, "p": 2, "q": 3},
    "dodecahedron": {"radius": 0.6, "detail": 0},
    "icosahedron": {"radius": 0.6, "detail": 0},
    "octahedron": {"radius": 0.6, "detail": 0},
    "tetrahedron": {"radius": 0.6, "detail": 0},
    "ring": {"innerRadius": 0.4, "outerRadius": 0.7, "thetaSegments": 24},
    "capsule": {"radius": 0.4, "length": 0.8, "capSegments": 12, "radialSegments": 16},
    "tube": {"radius": 0.3, "tubularSegments": 64, "radialSegments": 8},
    # Lathe — surface of revolution swept along a 2D point profile.
    "lathe": {"points": [[0.0, 0.0], [0.4, 0.2], [0.3, 0.6], [0.0, 0.8]], "segments": 32, "phiStart": 0.0, "phiLength": 6.2832},
    # Extrude — 2D shape (closed polygon outline) pushed along the Z axis.
    "extrude": {"outline": [[-0.5, -0.5], [0.5, -0.5], [0.5, 0.5], [-0.5, 0.5]], "depth": 0.4, "bevelEnabled": True, "bevelThickness": 0.04, "bevelSize": 0.04, "bevelSegments": 3, "curveSegments": 12},
    # Text — SDF/freetype glyph geometry. ``text`` is the rendered string.
    "text": {"text": "Trigen", "size": 0.6, "height": 0.12, "curveSegments": 8, "bevelEnabled": False},
    # Spline — a Catmull-Rom curve mesh (open tube following control points).
    "spline": {"points": [[-1.0, 0.0, 0.0], [0.0, 0.6, 0.3], [1.0, 0.0, 0.0]], "tubularSegments": 64, "radius": 0.06, "radialSegments": 8, "closed": False},
}


# Friendly display name map
GEOMETRY_DISPLAY_NAMES: Dict[str, str] = {
    "box": "Cube",
    "sphere": "Sphere",
    "cylinder": "Cylinder",
    "cone": "Cone",
    "torus": "Torus",
    "plane": "Plane",
    "torusKnot": "TorusKnot",
    "dodecahedron": "Dodecahedron",
    "icosahedron": "Icosahedron",
    "octahedron": "Octahedron",
    "tetrahedron": "Tetrahedron",
    "ring": "Ring",
    "capsule": "Capsule",
    "tube": "Tube",
    "lathe": "Lathe",
    "extrude": "Extrude",
    "text": "Text",
    "spline": "Spline",
}


# Material presets
MATERIAL_PRESETS: Dict[str, Dict[str, Any]] = {
    "metal": {"color": "#9aa3ad", "metalness": 1.0, "roughness": 0.25, "opacity": 1.0},
    "gold": {"color": "#ffc933", "metalness": 1.0, "roughness": 0.18, "opacity": 1.0},
    "copper": {"color": "#c87533", "metalness": 1.0, "roughness": 0.3, "opacity": 1.0},
    "glass": {"color": "#aee3ff", "metalness": 0.0, "roughness": 0.05, "opacity": 0.35},
    "plastic": {"color": "#e84a4a", "metalness": 0.0, "roughness": 0.55, "opacity": 1.0},
    "wood": {"color": "#8a5a2b", "metalness": 0.0, "roughness": 0.85, "opacity": 1.0},
    "rubber": {"color": "#1a1a1a", "metalness": 0.0, "roughness": 0.95, "opacity": 1.0},
    "emissive": {"color": "#00F0FF", "metalness": 0.0, "roughness": 0.4, "opacity": 1.0, "emissive": "#00F0FF", "emissive_intensity": 1.5},
    "neon": {"color": "#FFB800", "metalness": 0.0, "roughness": 0.3, "opacity": 1.0, "emissive": "#FFB800", "emissive_intensity": 2.0},
    "ceramic": {"color": "#f5f1ea", "metalness": 0.05, "roughness": 0.35, "opacity": 1.0},
    "marble": {"color": "#e8e6e0", "metalness": 0.1, "roughness": 0.2, "opacity": 1.0},
    "wireframe": {"color": "#00F0FF", "metalness": 0.0, "roughness": 0.5, "opacity": 1.0, "wireframe": True},
    # Extended-PBR presets leveraging the clearcoat / transmission /
    # iridescence / sheen layers added in this revision.
    "carpaint": {"color": "#7a0d0d", "metalness": 0.85, "roughness": 0.3, "clearcoat": 1.0, "clearcoat_roughness": 0.08},
    "crystal": {"color": "#bfe9ff", "metalness": 0.0, "roughness": 0.02, "transmission": 0.95, "thickness": 0.6, "ior": 2.0, "attenuation_distance": 1.2},
    "bubble": {"color": "#ffffff", "metalness": 0.0, "roughness": 0.0, "transmission": 0.6, "iridescence": 1.0, "iridescence_ior": 1.33, "ior": 1.25, "opacity": 0.5},
    "velvet": {"color": "#5b1a66", "metalness": 0.0, "roughness": 0.9, "sheen": 1.0, "sheen_color": "#c486d6", "sheen_roughness": 0.3},
    "diamond": {"color": "#ffffff", "metalness": 0.0, "roughness": 0.0, "transmission": 1.0, "ior": 2.42, "thickness": 0.5},
    "oilsllick": {"color": "#101010", "metalness": 0.4, "roughness": 0.3, "iridescence": 1.0, "iridescence_ior": 1.5, "iridescence_thickness_min": 200.0, "iridescence_thickness_max": 700.0},
}
