"""Multi-format export tool.

Exports the current scene to GLB / OBJ / STL files, building meshes with
trimesh and serializing them. Exported files are written to workspace/exports
and a downloadable URL is returned.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, Optional

from trigen.scene import Scene
from trigen.tools.base import SceneDelta, ToolBase, ToolResult

logger = logging.getLogger("trigen.tools.export")


_EXPORT_PARAMS = {
    "type": "object",
    "properties": {
        "format": {
            "type": "string",
            "enum": ["glb", "obj", "stl"],
            "description": "Export format",
        },
        "filename": {"type": "string", "description": "File name (without extension)"},
    },
    "required": ["format"],
}


class ExportSceneTool(ToolBase):
    """Scene export tool."""

    name = "export_scene"
    description = "Export the current scene as a GLB / OBJ / STL format file."

    def __init__(self, workspace_dir: str = ""):
        self.workspace_dir = workspace_dir or os.path.expanduser("~/.trigen/workspace")

    def schema(self) -> Dict[str, Any]:
        return _EXPORT_PARAMS

    def _build_trimesh_scene(self, scene: Scene):
        """Convert a Trigen scene into a trimesh.Scene."""
        try:
            import trimesh
            import numpy as np
        except ImportError as exc:
            raise RuntimeError("trimesh not installed, cannot export") from exc

        meshes = []
        for obj in scene.objects:
            geo = obj.geometry
            gtype = geo.type
            p = geo.params
            mesh: Optional["trimesh.Trimesh"] = None

            try:
                if gtype == "box":
                    mesh = trimesh.creation.box(
                        extents=[p.get("width", 1), p.get("height", 1), p.get("depth", 1)]
                    )
                elif gtype == "sphere":
                    mesh = trimesh.creation.icosphere(
                        radius=p.get("radius", 0.6), subdivisions=2
                    )
                elif gtype == "cylinder":
                    mesh = trimesh.creation.cylinder(
                        radius=p.get("radiusBottom", 0.5),
                        height=p.get("height", 1.2),
                        sections=p.get("radialSegments", 32),
                    )
                elif gtype == "cone":
                    mesh = trimesh.creation.cone(
                        radius=p.get("radius", 0.6),
                        height=p.get("height", 1.2),
                        sections=p.get("radialSegments", 32),
                    )
                elif gtype == "torus":
                    mesh = trimesh.creation.torus(
                        major_radius=p.get("radius", 0.6),
                        minor_radius=p.get("tube", 0.2),
                        major_sections=p.get("tubularSegments", 48),
                        minor_sections=p.get("radialSegments", 12),
                    )
                elif gtype == "plane":
                    mesh = trimesh.creation.box(
                        extents=[p.get("width", 2), 0.001, p.get("height", 2)]
                    )
                elif gtype == "icosahedron":
                    mesh = trimesh.creation.icosphere(
                        radius=p.get("radius", 0.6), subdivisions=1
                    )
                elif gtype == "dodecahedron":
                    mesh = trimesh.creation.dodecahedron(radius=p.get("radius", 0.6))
                elif gtype == "octahedron":
                    mesh = trimesh.creation.icosphere(
                        radius=p.get("radius", 0.6), subdivisions=0
                    )
                elif gtype == "tetrahedron":
                    mesh = trimesh.creation.icosphere(
                        radius=p.get("radius", 0.6), subdivisions=0
                    )
                elif gtype == "ring":
                    # Approximate ring as a thin annulus via cylinder difference
                    inner = p.get("innerRadius", 0.4)
                    outer = p.get("outerRadius", 0.7)
                    outer_cyl = trimesh.creation.cylinder(radius=outer, height=0.01)
                    inner_cyl = trimesh.creation.cylinder(radius=inner, height=0.02)
                    try:
                        mesh = outer_cyl.difference(inner_cyl)
                    except Exception:
                        mesh = outer_cyl
                elif gtype == "capsule":
                    # Approximate capsule as cylinder + two spheres
                    r = p.get("radius", 0.4)
                    length = p.get("length", 0.8)
                    cyl = trimesh.creation.cylinder(radius=r, height=length)
                    top = trimesh.creation.icosphere(radius=r, subdivisions=1)
                    top.apply_translation([0, length / 2, 0])
                    bot = trimesh.creation.icosphere(radius=r, subdivisions=1)
                    bot.apply_translation([0, -length / 2, 0])
                    try:
                        mesh = trimesh.util.concatenate([cyl, top, bot])
                    except Exception:
                        mesh = cyl
                elif gtype == "tube":
                    # Approximate tube as a torus segment
                    mesh = trimesh.creation.torus(
                        major_radius=p.get("radius", 0.3) if p.get("radius") else 0.5,
                        minor_radius=0.05,
                        major_sections=24,
                        minor_sections=8,
                    )
                else:
                    mesh = trimesh.creation.box(extents=[1, 1, 1])
            except Exception as e:
                logger.warning("Failed to build %s mesh: %s, falling back to cube", gtype, e)
                mesh = trimesh.creation.box(extents=[1, 1, 1])

            if mesh is not None:
                # Apply transform
                tf = obj.transform
                pos = np.array(tf.position, dtype=float)
                scale = np.array(tf.scale, dtype=float)
                mesh.apply_scale(scale)
                # Simplified rotation: apply Z-axis only
                rz = tf.rotation[2] if len(tf.rotation) == 3 else 0
                if rz:
                    mesh.apply_transform(
                        trimesh.transformations.rotation_matrix(rz, [0, 0, 1])
                    )
                mesh.apply_translation(pos)
                # Apply color
                color_hex = obj.material.color.lstrip("#")
                try:
                    rgba = [
                        int(color_hex[i : i + 2], 16) for i in (0, 2, 4)
                    ] + [int(obj.material.opacity * 255)]
                    mesh.visual = trimesh.visual.ColorVisuals(mesh, face_colors=rgba)
                except Exception:
                    pass
                meshes.append(mesh)

        if not meshes:
            return None
        return trimesh.Scene(meshes)

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        fmt = arguments.get("format", "glb").lower()
        filename = arguments.get("filename", f"trigen_scene_{int(time.time())}")

        if not scene.objects:
            return ToolResult(success=False, message="Scene is empty, cannot export")

        try:
            tm_scene = self._build_trimesh_scene(scene)
            if tm_scene is None:
                return ToolResult(success=False, message="Scene mesh build failed")
        except RuntimeError as e:
            return ToolResult(success=False, message=str(e))
        except Exception as e:
            return ToolResult(success=False, message=f"Mesh build exception: {e}")

        os.makedirs(os.path.join(self.workspace_dir, "exports"), exist_ok=True)
        ext = "glb" if fmt == "glb" else fmt
        filepath = os.path.join(self.workspace_dir, "exports", f"{filename}.{ext}")

        try:
            if fmt == "glb":
                data = tm_scene.export(file_type="glb")
            elif fmt == "obj":
                data = tm_scene.export(file_type="obj")
            elif fmt == "stl":
                data = tm_scene.export(file_type="stl")
            else:
                return ToolResult(success=False, message=f"Unsupported format: {fmt}")
            with open(filepath, "wb") as f:
                f.write(data if isinstance(data, bytes) else data.encode("utf-8"))
        except Exception as e:
            return ToolResult(success=False, message=f"Export failed: {e}")

        size_kb = os.path.getsize(filepath) / 1024
        return ToolResult(
            success=True,
            message=f"Scene exported as {filename}.{ext} ({size_kb:.1f} KB), path: {filepath}",
            deltas=[SceneDelta(action="export", payload={"format": fmt, "filename": f"{filename}.{ext}", "path": filepath, "size_kb": round(size_kb, 1)})],
            data={"path": filepath, "filename": f"{filename}.{ext}", "format": fmt, "size_kb": round(size_kb, 1)},
        )
