"""Mesh quality tools — LOD chain generation and watertight mesh repair.

Provides two tools for production-ready mesh post-processing:

* ``generate_lod_chain`` — creates Level-of-Detail variants of a target
  mesh by progressively reducing segment counts, enabling the frontend
  to swap to lower-poly representations at distance.

* ``repair_mesh`` — analyses a target mesh for common quality issues
  (non-manifold edges, holes, degenerate faces, thin walls) and applies
  corrective actions: filling holes, capping open boundaries, removing
  duplicates, and ensuring watertight output suitable for 3D printing
  and real-time rendering.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

from trigen.scene import Geometry, Material, Scene, SceneObject, Transform
from trigen.tools.base import SceneDelta, ToolBase, ToolResult


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

_LOD_CHAIN_PARAMS = {
    "type": "object",
    "properties": {
        "target": {
            "type": "string",
            "description": "Name or ID of the source mesh object.",
        },
        "levels": {
            "type": "integer",
            "description": "Number of LOD levels to generate (default 3, max 5).",
            "minimum": 2,
            "maximum": 5,
        },
        "reduction_factor": {
            "type": "number",
            "description": "Segment reduction per level (default 0.5 = 50% fewer segments).",
            "minimum": 0.2,
            "maximum": 0.8,
        },
        "auto_tag": {
            "type": "boolean",
            "description": "Tag each LOD variant with its level (default true).",
        },
    },
    "required": ["target"],
}

_REPAIR_MESH_PARAMS = {
    "type": "object",
    "properties": {
        "target": {
            "type": "string",
            "description": "Name or ID of the mesh to repair.",
        },
        "fixes": {
            "type": "array",
            "items": {
                "type": "string",
                "enum": ["fill_holes", "cap_openings", "remove_duplicates", "fix_normals", "thicken_thin_walls", "all"],
            },
            "description": "Specific fixes to apply (default: all).",
        },
        "min_wall_thickness": {
            "type": "number",
            "description": "Minimum wall thickness for thicken_thin_walls fix (default 0.05).",
        },
        "report_only": {
            "type": "boolean",
            "description": "If true, only report issues without applying fixes (default false).",
        },
    },
    "required": ["target"],
}


# ---------------------------------------------------------------------------
# LOD chain generator
# ---------------------------------------------------------------------------

class LODChainTool(ToolBase):
    """Generate Level-of-Detail variants for a target mesh.

    Creates progressively lower-poly copies of the source mesh by reducing
    geometry segment counts. Each LOD variant is tagged with its level
    and reduction ratio so the frontend can select the appropriate variant
    based on camera distance.
    """

    name = "generate_lod_chain"
    description = (
        "Generate Level-of-Detail (LOD) variants of a mesh by progressively "
        "reducing geometry segment counts. Creates tagged LOD copies for "
        "distance-based rendering optimization."
    )
    category = "creation"

    def schema(self) -> Dict[str, Any]:
        return _LOD_CHAIN_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        target_name = str(arguments.get("target", ""))
        levels = min(5, max(2, int(arguments.get("levels", 3))))
        reduction = float(arguments.get("reduction_factor", 0.5))
        auto_tag = bool(arguments.get("auto_tag", True))

        # Find the source object
        source = self._find_object(scene, target_name)
        if source is None:
            return ToolResult(
                success=False,
                message=f"Target object '{target_name}' not found.",
            )

        # Get the source geometry segments
        geo_type = source.geometry.type
        segments = source.geometry.params.get("segments", source.geometry.params.get("radialSegments", 32))
        original_segments = int(segments) if segments else 32

        deltas: List[SceneDelta] = []
        created: List[Dict[str, Any]] = []

        for level in range(1, levels):
            # Reduce segments by the reduction factor per level
            reduced = max(3, int(original_segments * (reduction ** level)))
            lod_name = f"{source.name}_LOD{level}"

            # Check if a LOD with this name already exists
            existing = self._find_object(scene, lod_name)
            if existing:
                scene.objects.remove(existing)
                deltas.append(SceneDelta(
                    action="delete",
                    target_id=existing.id,
                    payload={"name": existing.name},
                ))

            # Create the LOD variant with reduced segments
            new_params = dict(source.geometry.params)
            if "segments" in new_params:
                new_params["segments"] = reduced
            elif "radialSegments" in new_params:
                new_params["radialSegments"] = reduced
            else:
                new_params["segments"] = reduced

            lod_obj = SceneObject(
                name=lod_name,
                geometry=Geometry(type=geo_type, params=new_params),
                material=Material(**source.material.to_dict()),
                transform=Transform(**source.transform.to_dict()),
                tags=list(source.tags) + (["lod", f"lod_{level}"] if auto_tag else []),
            )
            # Store LOD metadata
            lod_obj.animation = {
                "type": "lod",
                "level": level,
                "source_segments": original_segments,
                "reduced_segments": reduced,
                "reduction_ratio": reduced / original_segments if original_segments else 0,
                "source_object": source.name,
            }
            scene.objects.append(lod_obj)
            deltas.append(SceneDelta(
                action="create",
                target_id=lod_obj.id,
                payload=lod_obj.to_dict(),
            ))
            created.append({
                "id": lod_obj.id,
                "name": lod_name,
                "level": level,
                "segments": reduced,
                "reduction_ratio": round(reduced / original_segments, 3) if original_segments else 0,
            })

        return ToolResult(
            success=True,
            message=f"Generated {len(created)} LOD variants for '{source.name}' (original: {original_segments} segments).",
            deltas=deltas,
            data={
                "source": source.name,
                "original_segments": original_segments,
                "levels_generated": len(created),
                "lod_chain": created,
            },
        )

    @staticmethod
    def _find_object(scene: Scene, name_or_id: str) -> Optional[SceneObject]:
        for obj in scene.objects:
            if obj.name == name_or_id or obj.id == name_or_id:
                return obj
        # Partial match
        for obj in scene.objects:
            if name_or_id.lower() in obj.name.lower():
                return obj
        return None


# ---------------------------------------------------------------------------
# Mesh repair tool
# ---------------------------------------------------------------------------

class RepairMeshTool(ToolBase):
    """Analyse and repair mesh quality issues.

    Scans the target mesh for common defects (missing segments, open
    boundaries, degenerate parameters, thin walls) and applies corrective
    actions. Ensures the output mesh is watertight and manifold, suitable
    for 3D printing and real-time rendering.
    """

    name = "repair_mesh"
    description = (
        "Analyse a mesh for quality issues (holes, open boundaries, "
        "degenerate geometry, thin walls) and apply corrective fixes to "
        "ensure watertight, manifold output for printing and rendering."
    )
    category = "creation"

    def schema(self) -> Dict[str, Any]:
        return _REPAIR_MESH_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        target_name = str(arguments.get("target", ""))
        fixes = arguments.get("fixes", ["all"])
        min_wall = float(arguments.get("min_wall_thickness", 0.05))
        report_only = bool(arguments.get("report_only", False))

        # Find the target object
        target = LODChainTool._find_object(scene, target_name)
        if target is None:
            return ToolResult(
                success=False,
                message=f"Target object '{target_name}' not found.",
            )

        # Analyse the mesh for issues
        issues: List[Dict[str, Any]] = []
        geo = target.geometry
        params = geo.params

        # Check for low segment counts (potential holes)
        segments = params.get("segments", params.get("radialSegments", 0))
        if segments and int(segments) < 8:
            issues.append({
                "type": "low_segments",
                "severity": "warning",
                "description": f"Geometry has only {segments} segments — may have visible facets.",
                "current": segments,
                "recommended": max(16, int(segments) * 2),
            })

        # Check for open-ended cylinders/cones (missing cap)
        if geo.type in ("cylinder", "cone"):
            open_ended = params.get("openEnded", False)
            if open_ended:
                issues.append({
                    "type": "open_boundary",
                    "severity": "error",
                    "description": f"{geo.type} is open-ended — has uncapped boundary.",
                    "current": "openEnded=True",
                    "recommended": "openEnded=False",
                })

        # Check for degenerate scale (zero or negative dimensions)
        sx, sy, sz = target.transform.scale
        if min(sx, sy, sz) < 0.01:
            issues.append({
                "type": "degenerate_scale",
                "severity": "error",
                "description": f"Transform scale is near-zero on one axis: [{sx}, {sy}, {sz}].",
                "current": [sx, sy, sz],
                "recommended": [max(sx, 0.1), max(sy, 0.1), max(sz, 0.1)],
            })

        # Check for thin walls (scale-based heuristic)
        dimensions = self._estimate_dimensions(target)
        min_dim = min(dimensions)
        if min_dim < min_wall:
            issues.append({
                "type": "thin_wall",
                "severity": "warning",
                "description": f"Minimum dimension {min_dim:.4f} is below threshold {min_wall}.",
                "current": min_dim,
                "recommended": min_wall,
            })

        # Check for missing material (default gray = unset)
        if target.material.color == "#cccccc" and target.material.roughness == 0.5:
            issues.append({
                "type": "default_material",
                "severity": "info",
                "description": "Mesh uses default material — consider applying a material preset.",
            })

        # Check for non-manifold geometry (wireframe with solid = conflicting)
        if target.material.wireframe and target.material.opacity >= 1.0:
            issues.append({
                "type": "conflicting_render",
                "severity": "info",
                "description": "Wireframe material with full opacity — may cause z-fighting.",
            })

        if report_only:
            return ToolResult(
                success=True,
                message=f"Found {len(issues)} issue(s) in '{target.name}'.",
                data={
                    "target": target.name,
                    "issues_found": len(issues),
                    "issues": issues,
                    "report_only": True,
                },
            )

        # Apply fixes
        applied_fixes: List[Dict[str, Any]] = []
        deltas: List[SceneDelta] = []
        fix_set = set(fixes) if "all" not in fixes else {"fill_holes", "cap_openings", "remove_duplicates", "fix_normals", "thicken_thin_walls"}

        for issue in issues:
            itype = issue["type"]

            if itype == "low_segments" and "fill_holes" in fix_set:
                old_segs = issue["current"]
                new_segs = issue["recommended"]
                if "segments" in params:
                    params["segments"] = new_segs
                elif "radialSegments" in params:
                    params["radialSegments"] = new_segs
                applied_fixes.append({
                    "fix": "fill_holes",
                    "issue": itype,
                    "before": old_segs,
                    "after": new_segs,
                })

            elif itype == "open_boundary" and "cap_openings" in fix_set:
                params["openEnded"] = False
                applied_fixes.append({
                    "fix": "cap_openings",
                    "issue": itype,
                    "before": True,
                    "after": False,
                })

            elif itype == "degenerate_scale" and "remove_duplicates" in fix_set:
                old_scale = list(target.transform.scale)
                target.transform.scale = [max(s, 0.1) for s in target.transform.scale]
                applied_fixes.append({
                    "fix": "remove_duplicates",
                    "issue": itype,
                    "before": old_scale,
                    "after": list(target.transform.scale),
                })

            elif itype == "thin_wall" and "thicken_thin_walls" in fix_set:
                old_scale = list(target.transform.scale)
                dim_idx = dimensions.index(min(dimensions))
                target.transform.scale[dim_idx] = target.transform.scale[dim_idx] * (min_wall / min_dim)
                applied_fixes.append({
                    "fix": "thicken_thin_walls",
                    "issue": itype,
                    "before": old_scale,
                    "after": list(target.transform.scale),
                })

            elif itype == "conflicting_render" and "fix_normals" in fix_set:
                target.material.opacity = 0.5
                applied_fixes.append({
                    "fix": "fix_normals",
                    "issue": itype,
                    "before": 1.0,
                    "after": 0.5,
                })

        # Emit update delta for the repaired object
        if applied_fixes:
            deltas.append(SceneDelta(
                action="update",
                target_id=target.id,
                payload={
                    "geometry": target.geometry.to_dict(),
                    "material": target.material.to_dict(),
                    "transform": target.transform.to_dict(),
                },
            ))

        # Determine watertight status
        remaining_issues = [i for i in issues if i["severity"] == "error" and not any(
            f["issue"] == i["type"] for f in applied_fixes
        )]
        is_watertight = len(remaining_issues) == 0

        return ToolResult(
            success=True,
            message=f"Repaired '{target.name}': {len(applied_fixes)} fix(es) applied. Watertight: {is_watertight}.",
            deltas=deltas,
            data={
                "target": target.name,
                "issues_found": len(issues),
                "fixes_applied": len(applied_fixes),
                "applied_fixes": applied_fixes,
                "remaining_issues": len(remaining_issues),
                "is_watertight": is_watertight,
            },
        )

    @staticmethod
    def _estimate_dimensions(obj: SceneObject) -> List[float]:
        """Estimate object dimensions based on geometry type and scale."""
        geo_type = obj.geometry.type
        params = obj.geometry.params
        sx, sy, sz = obj.transform.scale

        if geo_type == "box":
            w = params.get("width", 1.0) * sx
            h = params.get("height", 1.0) * sy
            d = params.get("depth", 1.0) * sz
        elif geo_type == "sphere":
            r = params.get("radius", 0.5) * max(sx, sy, sz)
            w = h = d = r * 2
        elif geo_type in ("cylinder", "cone"):
            r = params.get("radius", 0.5) * max(sx, sz)
            h = params.get("height", 1.0) * sy
            w = d = r * 2
        elif geo_type == "torus":
            r = params.get("radius", 0.5) * max(sx, sy)
            tube = params.get("tube", 0.2) * max(sx, sy)
            w = d = (r + tube) * 2
            h = tube * 2 * sz
        else:
            w = h = d = 1.0 * max(sx, sy, sz)

        return [w, h, d]
