"""Scene-to-code exporter tool.

Converts the current Trigen scene into ready-to-run source code in one of
three flavors:

  - ``three_js``  — vanilla Three.js JavaScript (ES module) using the
    official three npm package. Renders the same PBR materials, lights,
    cameras, and fog the editor shows.
  - ``react_r3f`` — a React + @react-three/fiber TypeScript component that
    mirrors the scene as declarative JSX, suitable for dropping into any
    Vite/Next React app.
  - ``html``      — a single self-contained ``.html`` file that loads three
    from a CDN and renders the scene with no build step.

The generated code is returned in the tool result and also persisted to the
workspace ``exports`` directory so users can download or copy it. This makes
the Agent a one-shot "describe → scene → deployable code" pipeline, closing
the loop between natural-language creation and shippable runtime artefacts.
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Dict, List, Optional

from trigen.scene import Scene
from trigen.tools.base import SceneDelta, ToolBase, ToolResult

logger = logging.getLogger("trigen.tools.code_exporter")


_CODE_EXPORT_PARAMS = {
    "type": "object",
    "properties": {
        "format": {
            "type": "string",
            "enum": ["three_js", "react_r3f", "html"],
            "description": "Target code format: three_js (vanilla module), react_r3f (React+R3F TSX component), html (self-contained file).",
        },
        "filename": {
            "type": "string",
            "description": "Output file name (without extension). Defaults to trigen_scene_<timestamp>.",
        },
        "include_animation": {
            "type": "boolean",
            "description": "When true, emit an animation loop that plays any per-object animation descriptors. Default true.",
        },
    },
    "required": ["format"],
}


# Geometry type → Three.js constructor + param mapping. Each entry yields the
# constructor name and the ordered argument list (referencing params dict).
_THREE_GEOMETRY_MAP: Dict[str, tuple[str, List[str]]] = {
    "box": ("BoxGeometry", ["width", "height", "depth"]),
    "sphere": ("SphereGeometry", ["radius", "widthSegments", "heightSegments"]),
    "cylinder": ("CylinderGeometry", ["radiusTop", "radiusBottom", "height", "radialSegments"]),
    "cone": ("ConeGeometry", ["radius", "height", "radialSegments"]),
    "torus": ("TorusGeometry", ["radius", "tube", "radialSegments", "tubularSegments"]),
    "plane": ("PlaneGeometry", ["width", "height"]),
    "icosahedron": ("IcosahedronGeometry", ["radius", "detail"]),
    "dodecahedron": ("DodecahedronGeometry", ["radius", "detail"]),
    "octahedron": ("OctahedronGeometry", ["radius", "detail"]),
    "tetrahedron": ("TetrahedronGeometry", ["radius", "detail"]),
    "ring": ("RingGeometry", ["innerRadius", "outerRadius", "thetaSegments"]),
    "capsule": ("CapsuleGeometry", ["radius", "length"]),
    "torus_knot": ("TorusKnotGeometry", ["radius", "tube", "tubularSegments", "radialSegments"]),
}

_DEFAULT_PARAMS = {
    "box": {"width": 1, "height": 1, "depth": 1},
    "sphere": {"radius": 0.6, "widthSegments": 32, "heightSegments": 16},
    "cylinder": {"radiusTop": 0.5, "radiusBottom": 0.5, "height": 1.2, "radialSegments": 32},
    "cone": {"radius": 0.6, "height": 1.2, "radialSegments": 32},
    "torus": {"radius": 0.6, "tube": 0.2, "radialSegments": 12, "tubularSegments": 48},
    "plane": {"width": 2, "height": 2},
    "icosahedron": {"radius": 0.6, "detail": 0},
    "dodecahedron": {"radius": 0.6, "detail": 0},
    "octahedron": {"radius": 0.6, "detail": 0},
    "tetrahedron": {"radius": 0.6, "detail": 0},
    "ring": {"innerRadius": 0.4, "outerRadius": 0.7, "thetaSegments": 32},
    "capsule": {"radius": 0.4, "length": 0.8},
    "torus_knot": {"radius": 0.6, "tube": 0.2, "tubularSegments": 64, "radialSegments": 8},
}


def _js_array(values: List[float], precision: int = 4) -> str:
    """Format a list of numbers as a JS array literal."""
    return "[" + ", ".join(f"{float(v):.{precision}f}" for v in values) + "]"


def _sanitize_ident(name: str, fallback: str) -> str:
    """Turn an arbitrary object name into a JS-safe identifier."""
    if not name:
        return fallback
    safe = "".join(c if c.isalnum() else "_" for c in name)
    if not safe or safe[0].isdigit():
        safe = fallback + "_" + safe
    return safe


def _geometry_args(geo_type: str, params: Dict[str, Any]) -> str:
    """Build the constructor argument string for a Three.js geometry."""
    ctor, arg_names = _THREE_GEOMETRY_MAP.get(geo_type, ("BoxGeometry", ["width", "height", "depth"]))
    defaults = _DEFAULT_PARAMS.get(geo_type, {"width": 1, "height": 1, "depth": 1})
    parts: List[str] = []
    for arg in arg_names:
        val = params.get(arg, defaults.get(arg, 1))
        if isinstance(val, bool):
            parts.append("true" if val else "false")
        elif isinstance(val, (int, float)):
            # Emit integers without a trailing decimal when the default is int-like
            if isinstance(val, int) or float(val).is_integer():
                parts.append(str(int(val)))
            else:
                parts.append(f"{float(val):.4f}")
        else:
            parts.append(str(val))
    return f"new {ctor}({', '.join(parts)})"


# ---------------------------------------------------------------------------
# Vanilla Three.js (ES module) generator
# ---------------------------------------------------------------------------

def _build_three_js(scene: Scene, include_animation: bool) -> str:
    """Generate a vanilla Three.js ES module that recreates the scene."""
    lines: List[str] = []
    lines.append("// Generated by Trigen — AI-native 3D creation agent.")
    lines.append("// Vanilla Three.js scene reproduction (ES module).")
    lines.append("import * as THREE from 'three';")
    lines.append("")
    lines.append("/** Build and return a THREE.Scene from a Trigen scene description.")
    lines.append(" *  Plug this into your own renderer/camera rig, or call startTrigenScene()")
    lines.append(" *  for a self-contained viewer with orbit controls. */")
    lines.append("export function buildTrigenScene() {")
    lines.append("  const scene = new THREE.Scene();")
    lines.append("")
    # Background and fog
    if scene.background:
        lines.append(f"  scene.background = new THREE.Color('{scene.background}');")
    fog = scene.fog or {}
    if fog.get("enabled"):
        fog_color = fog.get("color", "#0a0a20")
        near = float(fog.get("near", 1))
        far = float(fog.get("far", 30))
        lines.append(f"  scene.fog = new THREE.Fog('{fog_color}', {near:.4f}, {far:.4f});")
    lines.append("")
    # Lights
    for i, light in enumerate(scene.lights):
        ltype = light.type
        color = light.color
        intensity = float(light.intensity)
        pos = light.position
        if ltype == "ambient":
            lines.append(f"  scene.add(new THREE.AmbientLight('{color}', {intensity:.4f}));")
        elif ltype == "directional":
            lines.append(
                f"  const lt_{i} = new THREE.DirectionalLight('{color}', {intensity:.4f});"
            )
            lines.append(f"  lt_{i}.position.set({_js_array(pos)});")
            lines.append(f"  scene.add(lt_{i});")
        elif ltype == "point":
            lines.append(
                f"  const lt_{i} = new THREE.PointLight('{color}', {intensity:.4f});"
            )
            lines.append(f"  lt_{i}.position.set({_js_array(pos)});")
            lines.append(f"  scene.add(lt_{i});")
        elif ltype == "spot":
            lines.append(
                f"  const lt_{i} = new THREE.SpotLight('{color}', {intensity:.4f});"
            )
            lines.append(f"  lt_{i}.position.set({_js_array(pos)});")
            lines.append(f"  scene.add(lt_{i});")
        elif ltype == "hemisphere":
            sky = color
            ground = light.params.get("ground_color", "#444444") if hasattr(light, "params") else "#444444"
            lines.append(
                f"  scene.add(new THREE.HemisphereLight('{sky}', '{ground}', {intensity:.4f}));"
            )
    lines.append("")
    # Meshes
    for i, obj in enumerate(scene.objects):
        var = f"mesh_{i}"
        geo_type = obj.geometry.type
        params = obj.geometry.params or {}
        geo_ctor = _geometry_args(geo_type, params)
        mat = obj.material
        # Choose material class — emissive / transparent → MeshStandardMaterial still works
        mat_args = [f"color: '{mat.color}'", f"metalness: {mat.metalness:.4f}", f"roughness: {mat.roughness:.4f}"]
        if mat.opacity < 1.0:
            mat_args.append(f"transparent: true")
            mat_args.append(f"opacity: {mat.opacity:.4f}")
        if mat.wireframe:
            mat_args.append(f"wireframe: true")
        if mat.flat_shading:
            mat_args.append(f"flatShading: true")
        if mat.emissive and mat.emissive != "#000000" and mat.emissive_intensity > 0:
            mat_args.append(f"emissive: '{mat.emissive}'")
            mat_args.append(f"emissiveIntensity: {mat.emissive_intensity:.4f}")
        side_map = {"front": "THREE.FrontSide", "back": "THREE.BackSide", "double": "THREE.DoubleSide"}
        if mat.side in ("back", "double"):
            mat_args.append(f"side: {side_map.get(mat.side, 'THREE.FrontSide')}")
        lines.append(f"  const {var}_geo = {geo_ctor};")
        lines.append(f"  const {var}_mat = new THREE.MeshStandardMaterial({{ {', '.join(mat_args)} }});")
        lines.append(f"  const {var} = new THREE.Mesh({var}_geo, {var}_mat);")
        tf = obj.transform
        lines.append(f"  {var}.position.set({_js_array(tf.position)});")
        lines.append(f"  {var}.rotation.set({_js_array(tf.rotation)});")
        lines.append(f"  {var}.scale.set({_js_array(tf.scale)});")
        if not obj.visible:
            lines.append(f"  {var}.visible = false;")
        lines.append(f"  {var}.name = {json.dumps(obj.name)};")
        lines.append(f"  scene.add({var});")
        lines.append("")
    lines.append("  return scene;")
    lines.append("}")
    lines.append("")
    # Optional self-contained viewer
    if include_animation:
        lines.append("/** Convenience: open a self-contained viewer that appends a canvas to")
        lines.append(" *  the given container element and renders the scene with orbit controls. */")
        lines.append("export function startTrigenScene(container = document.body) {")
        lines.append("  const scene = buildTrigenScene();")
        lines.append("  const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 1000);")
        lines.append("  camera.position.set(6, 5, 8);")
        lines.append("  const renderer = new THREE.WebGLRenderer({ antialias: true });")
        lines.append("  renderer.setPixelRatio(window.devicePixelRatio);")
        lines.append("  container.appendChild(renderer.domElement);")
        lines.append("  const resize = () => {")
        lines.append("    const w = container.clientWidth || window.innerWidth;")
        lines.append("    const h = container.clientHeight || window.innerHeight;")
        lines.append("    renderer.setSize(w, h);")
        lines.append("    camera.aspect = w / h;")
        lines.append("    camera.updateProjectionMatrix();")
        lines.append("  };")
        lines.append("  resize();")
        lines.append("  window.addEventListener('resize', resize);")
        lines.append("  function tick() {")
        lines.append("    requestAnimationFrame(tick);")
        lines.append("    scene.rotation.y += 0.0015;")
        lines.append("    renderer.render(scene, camera);")
        lines.append("  }")
        lines.append("  tick();")
        lines.append("  return { scene, camera, renderer };")
        lines.append("}")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# React + react-three-fiber generator
# ---------------------------------------------------------------------------

def _r3f_geometry_args(geo_type: str, params: Dict[str, Any]) -> str:
    """Build the R3F args array literal for a geometry element."""
    _, arg_names = _THREE_GEOMETRY_MAP.get(geo_type, ("boxGeometry", ["width", "height", "depth"]))
    defaults = _DEFAULT_PARAMS.get(geo_type, {"width": 1, "height": 1, "depth": 1})
    parts: List[str] = []
    for arg in arg_names:
        val = params.get(arg, defaults.get(arg, 1))
        if isinstance(val, bool):
            parts.append(str(val).lower())
        elif isinstance(val, (int, float)):
            if isinstance(val, int) or float(val).is_integer():
                parts.append(str(int(val)))
            else:
                parts.append(f"{float(val):.4f}")
        else:
            parts.append(json.dumps(str(val)))
    return "[" + ", ".join(parts) + "]"


def _r3f_geometry_element(geo_type: str, params: Dict[str, Any]) -> str:
    """Emit a single R3F geometry JSX element with its args bound."""
    ctor, _ = _THREE_GEOMETRY_MAP.get(geo_type, ("BoxGeometry", ["width", "height", "depth"]))
    # R3F element names are camelCase constructor names lowercased
    element = ctor[0].lower() + ctor[1:]
    args_str = _r3f_geometry_args(geo_type, params)
    return f"<{element} args={{{args_str}}} />"


def _build_react_r3f(scene: Scene, include_animation: bool) -> str:
    """Generate a React + @react-three/fiber TSX component recreating the scene."""
    lines: List[str] = []
    lines.append("// Generated by Trigen — AI-native 3D creation agent.")
    lines.append("// React + @react-three/fiber scene reproduction (TypeScript).")
    lines.append("import { Canvas, useFrame } from '@react-three/fiber';")
    lines.append("import { OrbitControls } from '@react-three/drei';")
    lines.append("import { useRef } from 'react';")
    lines.append("import * as THREE from 'three';")
    lines.append("")
    lines.append("interface TrigenSceneProps {")
    lines.append("  autoRotate?: boolean;")
    lines.append("}")
    lines.append("")
    # Per-object component — renders geometry by type switch + PBR material.
    # The descriptor is a plain JSON object so it can live in a separate file
    # or be fetched from an API; the component rebuilds the R3F element tree
    # from it at render time.
    lines.append("interface TrigenObjectData {")
    lines.append("  id: string;")
    lines.append("  name: string;")
    lines.append("  visible: boolean;")
    lines.append("  transform: { position: [number, number, number]; rotation: [number, number, number]; scale: [number, number, number] };")
    lines.append("  material: {")
    lines.append("    color: string;")
    lines.append("    metalness: number;")
    lines.append("    roughness: number;")
    lines.append("    opacity: number;")
    lines.append("    wireframe: boolean;")
    lines.append("    emissive: string;")
    lines.append("    emissive_intensity: number;")
    lines.append("    flat_shading: boolean;")
    lines.append("  };")
    lines.append("  geometry: { type: string; params: Record<string, number | boolean | string> };")
    lines.append("  animation?: { type: string; speed?: number; amplitude?: number };")
    lines.append("}")
    lines.append("")
    lines.append("function TrigenGeometry({ type, params }: { type: string; params: Record<string, unknown> }) {")
    lines.append("  const p = params as any;")
    lines.append("  switch (type) {")
    lines.append("    case 'box': return <boxGeometry args={[p.width ?? 1, p.height ?? 1, p.depth ?? 1]} />;")
    lines.append("    case 'sphere': return <sphereGeometry args={[p.radius ?? 0.6, p.widthSegments ?? 32, p.heightSegments ?? 16]} />;")
    lines.append("    case 'cylinder': return <cylinderGeometry args={[p.radiusTop ?? 0.5, p.radiusBottom ?? 0.5, p.height ?? 1.2, p.radialSegments ?? 32]} />;")
    lines.append("    case 'cone': return <coneGeometry args={[p.radius ?? 0.6, p.height ?? 1.2, p.radialSegments ?? 32]} />;")
    lines.append("    case 'torus': return <torusGeometry args={[p.radius ?? 0.6, p.tube ?? 0.2, p.radialSegments ?? 12, p.tubularSegments ?? 48]} />;")
    lines.append("    case 'plane': return <planeGeometry args={[p.width ?? 2, p.height ?? 2]} />;")
    lines.append("    case 'icosahedron': return <icosahedronGeometry args={[p.radius ?? 0.6, p.detail ?? 0]} />;")
    lines.append("    case 'dodecahedron': return <dodecahedronGeometry args={[p.radius ?? 0.6, p.detail ?? 0]} />;")
    lines.append("    case 'octahedron': return <octahedronGeometry args={[p.radius ?? 0.6, p.detail ?? 0]} />;")
    lines.append("    case 'tetrahedron': return <tetrahedronGeometry args={[p.radius ?? 0.6, p.detail ?? 0]} />;")
    lines.append("    case 'ring': return <ringGeometry args={[p.innerRadius ?? 0.4, p.outerRadius ?? 0.7, p.thetaSegments ?? 32]} />;")
    lines.append("    case 'capsule': return <capsuleGeometry args={[p.radius ?? 0.4, p.length ?? 0.8]} />;")
    lines.append("    case 'torus_knot': return <torusKnotGeometry args={[p.radius ?? 0.6, p.tube ?? 0.2, p.tubularSegments ?? 64, p.radialSegments ?? 8]} />;")
    lines.append("    default: return <boxGeometry args={[1, 1, 1]} />;")
    lines.append("  }")
    lines.append("}")
    lines.append("")
    lines.append("function TrigenObject({ object }: { object: TrigenObjectData }) {")
    lines.append("  const ref = useRef<THREE.Mesh>(null!);")
    if include_animation:
        lines.append("  useFrame((state) => {")
        lines.append("    const a = object.animation;")
        lines.append("    if (!a || !ref.current) return;")
        lines.append("    const t = state.clock.elapsedTime;")
        lines.append("    if (a.type === 'orbit') {")
        lines.append("      ref.current.rotation.y = t * (a.speed ?? 1);")
        lines.append("    } else if (a.type === 'bounce') {")
        lines.append("      ref.current.position.y = object.transform.position[1] + Math.abs(Math.sin(t * (a.speed ?? 1))) * (a.amplitude ?? 0.5);")
        lines.append("    } else if (a.type === 'wave') {")
        lines.append("      ref.current.position.y = object.transform.position[1] + Math.sin(t * (a.speed ?? 1) + object.transform.position[0]) * (a.amplitude ?? 0.3);")
        lines.append("    }")
        lines.append("  });")
    lines.append("  const m = object.material;")
    lines.append("  return (")
    lines.append("    <mesh")
    lines.append("      ref={ref}")
    lines.append("      position={object.transform.position}")
    lines.append("      rotation={object.transform.rotation}")
    lines.append("      scale={object.transform.scale}")
    lines.append("      visible={object.visible}")
    lines.append("      name={object.name}")
    lines.append("    >")
    lines.append("      <TrigenGeometry type={object.geometry.type} params={object.geometry.params} />")
    lines.append("      <meshStandardMaterial")
    lines.append("        color={m.color}")
    lines.append("        metalness={m.metalness}")
    lines.append("        roughness={m.roughness}")
    lines.append("        opacity={m.opacity}")
    lines.append("        transparent={m.opacity < 1}")
    lines.append("        wireframe={m.wireframe}")
    lines.append("        emissive={m.emissive}")
    lines.append("        emissiveIntensity={m.emissive_intensity}")
    lines.append("        flatShading={m.flat_shading}")
    lines.append("      />")
    lines.append("    </mesh>")
    lines.append("  );")
    lines.append("}")
    lines.append("")
    # Convert scene objects to descriptors (plain JSON, no JSX embedding).
    lines.append("const sceneObjects: TrigenObjectData[] = [")
    for obj in scene.objects:
        mat = obj.material
        anim = obj.animation or {}
        tf = obj.transform
        geo = obj.geometry
        lines.append("  {")
        lines.append(f"    id: {json.dumps(obj.id)},")
        lines.append(f"    name: {json.dumps(obj.name)},")
        lines.append(f"    visible: {str(obj.visible).lower()},")
        lines.append(f"    transform: {{ position: {_js_array(tf.position)} as [number, number, number], rotation: {_js_array(tf.rotation)} as [number, number, number], scale: {_js_array(tf.scale)} as [number, number, number] }},")
        lines.append(f"    material: {{ color: {json.dumps(mat.color)}, metalness: {mat.metalness:.4f}, roughness: {mat.roughness:.4f}, opacity: {mat.opacity:.4f}, wireframe: {str(mat.wireframe).lower()}, emissive: {json.dumps(mat.emissive)}, emissive_intensity: {mat.emissive_intensity:.4f}, flat_shading: {str(mat.flat_shading).lower()} }},")
        lines.append(f"    geometry: {{ type: {json.dumps(geo.type)}, params: {json.dumps(geo.params or {})} }},")
        if anim:
            lines.append(f"    animation: {{ type: {json.dumps(str(anim.get('type', '')))}, speed: {float(anim.get('speed', 1)):.4f}, amplitude: {float(anim.get('amplitude', 0.5)):.4f} }},")
        lines.append("  },")
    lines.append("];")
    lines.append("")
    # Scene component
    lines.append("export function TrigenScene({ autoRotate = true }: TrigenSceneProps) {")
    lines.append("  const groupRef = useRef<THREE.Group>(null!);")
    if include_animation:
        lines.append("  useFrame((_, delta) => {")
        lines.append("    if (autoRotate && groupRef.current) groupRef.current.rotation.y += delta * 0.15;")
        lines.append("  });")
    lines.append("  return (")
    lines.append("    <Canvas camera={{ position: [6, 5, 8], fov: 45 }}>")
    if scene.background:
        lines.append(f"      <color attach=\"background\" args=[{json.dumps(scene.background)}] />")
    fog = scene.fog or {}
    if fog.get("enabled"):
        fog_color = fog.get("color", "#0a0a20")
        near = float(fog.get("near", 1))
        far = float(fog.get("far", 30))
        lines.append(f"      <fog attach=\"fog\" args=[{json.dumps(fog_color)}, {near:.4f}, {far:.4f}] />")
    # Lights
    for light in scene.lights:
        ltype = light.type
        color = light.color
        intensity = float(light.intensity)
        pos = light.position
        if ltype == "ambient":
            lines.append(f"      <ambientLight color={json.dumps(color)} intensity={{{intensity:.4f}}} />")
        elif ltype == "directional":
            lines.append(f"      <directionalLight color={json.dumps(color)} intensity={{{intensity:.4f}}} position={{{_js_array(pos)}}} />")
        elif ltype == "point":
            lines.append(f"      <pointLight color={json.dumps(color)} intensity={{{intensity:.4f}}} position={{{_js_array(pos)}}} />")
        elif ltype == "spot":
            lines.append(f"      <spotLight color={json.dumps(color)} intensity={{{intensity:.4f}}} position={{{_js_array(pos)}}} />")
        elif ltype == "hemisphere":
            lines.append(f"      <hemisphereLight color={json.dumps(color)} intensity={{{intensity:.4f}}} />")
    lines.append("      <group ref={groupRef}>")
    lines.append("        {sceneObjects.map((o) => (<TrigenObject key={o.id} object={o} />))}")
    lines.append("      </group>")
    lines.append("      <OrbitControls />")
    lines.append("    </Canvas>")
    lines.append("  );")
    lines.append("}")
    lines.append("")
    lines.append("export default TrigenScene;")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Self-contained HTML generator (CDN three.js)
# ---------------------------------------------------------------------------

def _build_html(scene: Scene, include_animation: bool) -> str:
    """Generate a single self-contained HTML file using three.js from a CDN."""
    scene_dict = scene.to_dict()
    # Strip animation field to keep payload smaller if not requested
    if not include_animation:
        for obj in scene_dict.get("objects", []):
            obj["animation"] = None
    payload = json.dumps(scene_dict, ensure_ascii=False)
    # The HTML embeds the scene as a JSON blob and rebuilds meshes at runtime
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>Trigen Scene</title>
  <style>
    html, body {{ margin: 0; padding: 0; overflow: hidden; background: #050505; }}
    #info {{ position: absolute; top: 8px; left: 12px; color: #888; font: 11px monospace; }}
  </style>
</head>
<body>
  <div id="info">Trigen · scene viewer</div>
  <script type="importmap">
  {{
    "imports": {{
      "three": "https://unpkg.com/three@0.160.0/build/three.module.js",
      "three/addons/": "https://unpkg.com/three@0.160.0/examples/jsm/"
    }}
  }}
  </script>
  <script type="module">
    import * as THREE from 'three';
    import {{ OrbitControls }} from 'three/addons/controls/OrbitControls.js';

    const sceneData = {payload};

    const scene = new THREE.Scene();
    if (sceneData.background) scene.background = new THREE.Color(sceneData.background);
    if (sceneData.fog && sceneData.fog.enabled) {{
      scene.fog = new THREE.Fog(sceneData.fog.color || '#0a0a20', sceneData.fog.near ?? 1, sceneData.fog.far ?? 30);
    }}

    const GEO_MAP = {{
      box: (p) => new THREE.BoxGeometry(p.width ?? 1, p.height ?? 1, p.depth ?? 1),
      sphere: (p) => new THREE.SphereGeometry(p.radius ?? 0.6, p.widthSegments ?? 32, p.heightSegments ?? 16),
      cylinder: (p) => new THREE.CylinderGeometry(p.radiusTop ?? 0.5, p.radiusBottom ?? 0.5, p.height ?? 1.2, p.radialSegments ?? 32),
      cone: (p) => new THREE.ConeGeometry(p.radius ?? 0.6, p.height ?? 1.2, p.radialSegments ?? 32),
      torus: (p) => new THREE.TorusGeometry(p.radius ?? 0.6, p.tube ?? 0.2, p.radialSegments ?? 12, p.tubularSegments ?? 48),
      plane: (p) => new THREE.PlaneGeometry(p.width ?? 2, p.height ?? 2),
      icosahedron: (p) => new THREE.IcosahedronGeometry(p.radius ?? 0.6, p.detail ?? 0),
      dodecahedron: (p) => new THREE.DodecahedronGeometry(p.radius ?? 0.6, p.detail ?? 0),
      octahedron: (p) => new THREE.OctahedronGeometry(p.radius ?? 0.6, p.detail ?? 0),
      tetrahedron: (p) => new THREE.TetrahedronGeometry(p.radius ?? 0.6, p.detail ?? 0),
      ring: (p) => new THREE.RingGeometry(p.innerRadius ?? 0.4, p.outerRadius ?? 0.7, p.thetaSegments ?? 32),
      capsule: (p) => new THREE.CapsuleGeometry(p.radius ?? 0.4, p.length ?? 0.8),
      torus_knot: (p) => new THREE.TorusKnotGeometry(p.radius ?? 0.6, p.tube ?? 0.2, p.tubularSegments ?? 64, p.radialSegments ?? 8),
    }};

    (sceneData.lights || []).forEach((l) => {{
      const intensity = l.intensity ?? 1.0;
      if (l.type === 'ambient') scene.add(new THREE.AmbientLight(l.color || '#fff', intensity));
      else if (l.type === 'directional') {{ const x = new THREE.DirectionalLight(l.color || '#fff', intensity); x.position.set(...(l.position || [5,5,5])); scene.add(x); }}
      else if (l.type === 'point') {{ const x = new THREE.PointLight(l.color || '#fff', intensity); x.position.set(...(l.position || [5,5,5])); scene.add(x); }}
      else if (l.type === 'spot') {{ const x = new THREE.SpotLight(l.color || '#fff', intensity); x.position.set(...(l.position || [5,5,5])); scene.add(x); }}
      else if (l.type === 'hemisphere') scene.add(new THREE.HemisphereLight(l.color || '#fff', l.ground_color || '#444', intensity));
    }});

    const meshes = [];
    (sceneData.objects || []).forEach((o) => {{
      const g = o.geometry || {{ type: 'box', params: {{}} }};
      const ctor = GEO_MAP[g.type] || GEO_MAP.box;
      const geo = ctor(g.params || {{}});
      const m = o.material || {{}};
      const mat = new THREE.MeshStandardMaterial({{
        color: m.color || '#ccc',
        metalness: m.metalness ?? 0,
        roughness: m.roughness ?? 0.5,
        transparent: (m.opacity ?? 1) < 1,
        opacity: m.opacity ?? 1,
        wireframe: !!m.wireframe,
        emissive: m.emissive || '#000',
        emissiveIntensity: m.emissive_intensity ?? 0,
        flatShading: !!m.flat_shading,
      }});
      const mesh = new THREE.Mesh(geo, mat);
      const t = o.transform || {{}};
      mesh.position.set(...(t.position || [0,0,0]));
      mesh.rotation.set(...(t.rotation || [0,0,0]));
      mesh.scale.set(...(t.scale || [1,1,1]));
      mesh.visible = o.visible !== false;
      mesh.name = o.name || 'Object';
      scene.add(mesh);
      meshes.push({{ mesh, anim: o.animation, base: (t.position || [0,0,0])[1] }});
    }});

    const camera = new THREE.PerspectiveCamera(45, innerWidth / innerHeight, 0.1, 1000);
    camera.position.set(6, 5, 8);
    const renderer = new THREE.WebGLRenderer({{ antialias: true }});
    renderer.setPixelRatio(devicePixelRatio);
    renderer.setSize(innerWidth, innerHeight);
    document.body.appendChild(renderer.domElement);
    const controls = new OrbitControls(camera, renderer.domElement);
    addEventListener('resize', () => {{
      camera.aspect = innerWidth / innerHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(innerWidth, innerHeight);
    }});

    function tick(now) {{
      requestAnimationFrame(tick);
      const t = now * 0.001;
      meshes.forEach((entry) => {{
        const a = entry.anim;
        if (!a) return;
        if (a.type === 'orbit') entry.mesh.rotation.y = t * (a.speed ?? 1);
        else if (a.type === 'bounce') entry.mesh.position.y = entry.base + Math.abs(Math.sin(t * (a.speed ?? 1))) * (a.amplitude ?? 0.5);
        else if (a.type === 'wave') entry.mesh.position.y = entry.base + Math.sin(t * (a.speed ?? 1) + entry.mesh.position.x) * (a.amplitude ?? 0.3);
      }});
      controls.update();
      renderer.render(scene, camera);
    }}
    requestAnimationFrame(tick);
  </script>
</body>
</html>
"""


class CodeExporterTool(ToolBase):
    """Convert the current scene into ready-to-run source code."""

    name = "export_code"
    description = (
        "Export the current scene as ready-to-run source code. Supports three "
        "flavors: 'three_js' (vanilla ES module), 'react_r3f' (React + "
        "@react-three/fiber TSX component), and 'html' (self-contained HTML "
        "file with three.js from CDN). The generated code recreates the scene's "
        "geometry, PBR materials, lights, fog, and optional animation loop."
    )

    def __init__(self, workspace_dir: str = ""):
        self.workspace_dir = workspace_dir or os.path.expanduser("~/.trigen/workspace")

    def schema(self) -> Dict[str, Any]:
        return _CODE_EXPORT_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        fmt = str(arguments.get("format", "three_js")).lower()
        include_anim = bool(arguments.get("include_animation", True))
        filename = str(arguments.get("filename", f"trigen_scene_{int(time.time())}"))

        if fmt not in ("three_js", "react_r3f", "html"):
            return ToolResult(success=False, message=f"Unsupported code format: {fmt}")

        if not scene.objects:
            return ToolResult(success=False, message="Scene is empty, nothing to export")

        try:
            if fmt == "three_js":
                code = _build_three_js(scene, include_anim)
                ext = "js"
            elif fmt == "react_r3f":
                code = _build_react_r3f(scene, include_anim)
                ext = "tsx"
            else:  # html
                code = _build_html(scene, include_anim)
                ext = "html"
        except Exception as exc:
            logger.exception("Code export generation failed")
            return ToolResult(success=False, message=f"Code generation failed: {exc}")

        # Persist to workspace/exports for download
        try:
            exports_dir = os.path.join(self.workspace_dir, "exports")
            os.makedirs(exports_dir, exist_ok=True)
            filepath = os.path.join(exports_dir, f"{filename}.{ext}")
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(code)
        except Exception as exc:
            logger.warning("Could not persist code export: %s", exc)
            filepath = ""

        size_kb = len(code.encode("utf-8")) / 1024
        return ToolResult(
            success=True,
            message=(
                f"Scene exported as {fmt} code ({len(code.splitlines())} lines, "
                f"{size_kb:.1f} KB){' to ' + filepath if filepath else ''}"
            ),
            deltas=[
                SceneDelta(
                    action="export_code",
                    payload={
                        "format": fmt,
                        "filename": f"{filename}.{ext}",
                        "path": filepath,
                        "lines": len(code.splitlines()),
                        "size_kb": round(size_kb, 1),
                    },
                )
            ],
            data={
                "format": fmt,
                "filename": f"{filename}.{ext}",
                "path": filepath,
                "code": code,
                "lines": len(code.splitlines()),
                "size_kb": round(size_kb, 1),
            },
        )
