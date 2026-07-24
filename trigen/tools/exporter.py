"""多格式导出工具 / Multi-format export tool.

将当前场景导出为 GLB / OBJ / STL 格式文件，使用 trimesh 构建网格并序列化。
导出文件落盘到 workspace/exports，返回可下载 URL。
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
            "description": "导出格式",
        },
        "filename": {"type": "string", "description": "文件名（不含扩展名）"},
    },
    "required": ["format"],
}


class ExportSceneTool(ToolBase):
    """场景导出工具。

    Scene export tool.
    """

    name = "export_scene"
    description = "将当前场景导出为 GLB / OBJ / STL 格式文件。"

    def __init__(self, workspace_dir: str = ""):
        self.workspace_dir = workspace_dir or os.path.expanduser("~/.trigen/workspace")

    def schema(self) -> Dict[str, Any]:
        return _EXPORT_PARAMS

    def _build_trimesh_scene(self, scene: Scene):
        """将 Trigen 场景转为 trimesh.Scene。

        Convert a Trigen scene into a trimesh.Scene.
        """
        try:
            import trimesh
            import numpy as np
        except ImportError as exc:
            raise RuntimeError("未安装 trimesh，无法导出") from exc

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
                logger.warning("构建 %s 网格失败: %s，回退为立方体", gtype, e)
                mesh = trimesh.creation.box(extents=[1, 1, 1])

            if mesh is not None:
                # 应用变换 / Apply transform
                tf = obj.transform
                pos = np.array(tf.position, dtype=float)
                scale = np.array(tf.scale, dtype=float)
                mesh.apply_scale(scale)
                # 简化旋转：仅应用 Z 轴旋转 / Simplified rotation: apply Z-axis only
                rz = tf.rotation[2] if len(tf.rotation) == 3 else 0
                if rz:
                    mesh.apply_transform(
                        trimesh.transformations.rotation_matrix(rz, [0, 0, 1])
                    )
                mesh.apply_translation(pos)
                # 应用颜色 / Apply color
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
            return ToolResult(success=False, message="场景为空，无法导出")

        try:
            tm_scene = self._build_trimesh_scene(scene)
            if tm_scene is None:
                return ToolResult(success=False, message="场景网格构建失败")
        except RuntimeError as e:
            return ToolResult(success=False, message=str(e))
        except Exception as e:
            return ToolResult(success=False, message=f"网格构建异常: {e}")

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
                return ToolResult(success=False, message=f"不支持的格式: {fmt}")
            with open(filepath, "wb") as f:
                f.write(data if isinstance(data, bytes) else data.encode("utf-8"))
        except Exception as e:
            return ToolResult(success=False, message=f"导出失败: {e}")

        size_kb = os.path.getsize(filepath) / 1024
        return ToolResult(
            success=True,
            message=f"场景已导出为 {filename}.{ext}（{size_kb:.1f} KB），路径: {filepath}",
            deltas=[SceneDelta(action="export", payload={"format": fmt, "filename": f"{filename}.{ext}", "path": filepath, "size_kb": round(size_kb, 1)})],
            data={"path": filepath, "filename": f"{filename}.{ext}", "format": fmt, "size_kb": round(size_kb, 1)},
        )
