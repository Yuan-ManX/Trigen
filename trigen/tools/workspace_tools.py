"""Advanced procedural modifiers, post-processing, workflow engine, and shape blending tools.

Provides extrusion, edge chamfering, post-fx stack management, named
workflow composition/execution, and morph blending between objects. All
tools follow the standard ToolBase contract: schema descriptions in
OpenAI function-calling format and async execute returning ToolResult
with SceneDelta payloads.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from trigen.scene import (
    Geometry,
    Material,
    Scene,
    SceneObject,
    Transform,
)
from trigen.tools.base import SceneDelta, ToolBase, ToolResult


def _ensure_scene_metadata(scene: Scene) -> Dict[str, Any]:
    """Return the scene's metadata dict, initializing it on first use."""
    metadata = getattr(scene, "metadata", None)
    if not isinstance(metadata, dict):
        metadata = {}
        scene.metadata = metadata  # type: ignore[attr-defined]
    return metadata


def _ensure_geometry_params(geometry: Geometry) -> Dict[str, Any]:
    """Return a geometry's params dict, guaranteeing it exists."""
    if not isinstance(geometry.params, dict):
        geometry.params = {}
    return geometry.params


# --- ExtrudeFaceTool --------------------------------------------------------

_EXTRUDE_FACE_PARAMS = {
    "type": "object",
    "properties": {
        "target": {
            "type": "string",
            "description": "Object id or name whose faces will be extruded",
        },
        "faces": {
            "type": "array",
            "items": {"type": "integer"},
            "description": "Face indices to extrude (default [0..5] for a 6-face box)",
            "default": [0, 1, 2, 3, 4, 5],
        },
        "distance": {
            "type": "number",
            "description": "Extrusion distance along face normals (default 0.5)",
            "default": 0.5,
        },
        "bevel": {
            "type": "number",
            "description": "Bevel radius applied to extruded edges (default 0.0)",
            "default": 0.0,
        },
    },
    "required": ["target"],
}


class ExtrudeFaceTool(ToolBase):
    """Procedural modifier: extrudes a set of faces of an object outward."""

    name = "extrude_face"
    description = (
        "Procedurally extrude specified faces of a mesh object outward by "
        "a given distance, with optional bevel. Extrusion segments are stored "
        "as procedural params so they remain editable."
    )

    def schema(self) -> Dict[str, Any]:
        return _EXTRUDE_FACE_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        target = str(arguments.get("target", "")).strip()
        if not target:
            return ToolResult(success=False, message="No target object provided")

        obj = scene.find_object(target)
        if obj is None:
            return ToolResult(success=False, message=f"Object not found: {target}")

        raw_faces = arguments.get("faces", [0, 1, 2, 3, 4, 5])
        if not isinstance(raw_faces, list):
            return ToolResult(success=False, message="'faces' must be an array of integers")
        faces: List[int] = []
        for f in raw_faces:
            try:
                faces.append(int(f))
            except (TypeError, ValueError):
                return ToolResult(success=False, message=f"Invalid face index: {f!r}")

        try:
            distance = float(arguments.get("distance", 0.5))
        except (TypeError, ValueError):
            return ToolResult(success=False, message="'distance' must be a number")

        try:
            bevel = float(arguments.get("bevel", 0.0))
        except (TypeError, ValueError):
            return ToolResult(success=False, message="'bevel' must be a number")

        params = _ensure_geometry_params(obj.geometry)
        extrusions: List[Dict[str, Any]] = params.get("extrusions")
        if not isinstance(extrusions, list):
            extrusions = []
            params["extrusions"] = extrusions

        segment: Dict[str, Any] = {
            "faces": faces,
            "distance": distance,
            "bevel": bevel,
        }
        extrusions.append(segment)

        payload = obj.to_dict()
        payload["geometry"]["params"]["extrusions"] = extrusions

        return ToolResult(
            success=True,
            message=(
                f"Extruded {len(faces)} face(s) on '{obj.name}' by "
                f"{distance} (bevel {bevel})"
            ),
            deltas=[SceneDelta(action="update", target_id=obj.id, payload=payload)],
            data={"object_id": obj.id, "segment": segment},
        )


# --- ChamferEdgesTool -------------------------------------------------------

_CHAMFER_EDGES_PARAMS = {
    "type": "object",
    "properties": {
        "target": {
            "type": "string",
            "description": "Object id or name whose edges will be chamfered",
        },
        "edges": {
            "type": "array",
            "items": {"type": "integer"},
            "description": "Edge indices to chamfer (empty means all edges)",
            "default": [],
        },
        "amount": {
            "type": "number",
            "description": "Chamfer offset amount (default 0.1)",
            "default": 0.1,
        },
        "segments": {
            "type": "integer",
            "description": "Number of chamfer subdivisions (default 2)",
            "default": 2,
        },
    },
    "required": ["target"],
}


class ChamferEdgesTool(ToolBase):
    """Procedural modifier: bevels edges of target object."""

    name = "chamfer_edges"
    description = (
        "Apply a procedural bevel (chamfer) to the specified edges of a mesh "
        "object. The amount and subdivision count are stored as editable "
        "params alongside the geometry."
    )

    def schema(self) -> Dict[str, Any]:
        return _CHAMFER_EDGES_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        target = str(arguments.get("target", "")).strip()
        if not target:
            return ToolResult(success=False, message="No target object provided")

        obj = scene.find_object(target)
        if obj is None:
            return ToolResult(success=False, message=f"Object not found: {target}")

        raw_edges = arguments.get("edges", [])
        if not isinstance(raw_edges, list):
            return ToolResult(success=False, message="'edges' must be an array of integers")
        edges: List[int] = []
        for e in raw_edges:
            try:
                edges.append(int(e))
            except (TypeError, ValueError):
                return ToolResult(success=False, message=f"Invalid edge index: {e!r}")

        try:
            amount = float(arguments.get("amount", 0.1))
        except (TypeError, ValueError):
            return ToolResult(success=False, message="'amount' must be a number")

        try:
            segments = int(arguments.get("segments", 2))
        except (TypeError, ValueError):
            return ToolResult(success=False, message="'segments' must be an integer")
        if segments < 1:
            segments = 1

        params = _ensure_geometry_params(obj.geometry)
        chamfers: List[Dict[str, Any]] = params.get("chamfers")
        if not isinstance(chamfers, list):
            chamfers = []
            params["chamfers"] = chamfers

        entry: Dict[str, Any] = {
            "edges": edges,
            "amount": amount,
            "segments": segments,
        }
        chamfers.append(entry)

        payload = obj.to_dict()
        payload["geometry"]["params"]["chamfers"] = chamfers

        edge_desc = "all edges" if not edges else f"{len(edges)} edge(s)"
        return ToolResult(
            success=True,
            message=(
                f"Chamfered {edge_desc} on '{obj.name}' with amount "
                f"{amount}, {segments} segment(s)"
            ),
            deltas=[SceneDelta(action="update", target_id=obj.id, payload=payload)],
            data={"object_id": obj.id, "chamfer": entry},
        )


# --- ApplyPostFxTool --------------------------------------------------------

_APPLY_POST_FX_PARAMS = {
    "type": "object",
    "properties": {
        "bloom": {
            "type": "boolean",
            "description": "Enable bloom / glow effect (default True)",
            "default": True,
        },
        "bloom_intensity": {
            "type": "number",
            "description": "Bloom strength multiplier (default 0.3)",
            "default": 0.3,
        },
        "vignette": {
            "type": "boolean",
            "description": "Enable vignette darkening at frame edges (default True)",
            "default": True,
        },
        "vignette_strength": {
            "type": "number",
            "description": "Vignette opacity 0..1 (default 0.4)",
            "default": 0.4,
        },
        "color_grading": {
            "type": "string",
            "enum": ["none", "neutral", "warm", "cool", "cinematic", "noir"],
            "description": "Color grading LUT preset (default 'neutral')",
            "default": "neutral",
        },
        "grain": {
            "type": "number",
            "description": "Film grain intensity (default 0.02)",
            "default": 0.02,
        },
        "chromatic_aberration": {
            "type": "number",
            "description": "RGB chromatic aberration offset strength (default 0.0)",
            "default": 0.0,
        },
        "dof": {
            "type": "boolean",
            "description": "Enable depth-of-field blur (default False)",
            "default": False,
        },
        "dof_focus": {
            "type": "number",
            "description": "Depth-of-field focal distance in world units (default 5.0)",
            "default": 5.0,
        },
    },
    "required": [],
}


class ApplyPostFxTool(ToolBase):
    """Post-processing stack: adds filmic effects."""

    name = "apply_post_fx"
    description = (
        "Configure the scene-wide post-processing stack: bloom, vignette, "
        "color grading LUT, film grain, chromatic aberration, and optional "
        "depth-of-field. Settings persist in scene metadata."
    )

    def schema(self) -> Dict[str, Any]:
        return _APPLY_POST_FX_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        bloom = bool(arguments.get("bloom", True))

        try:
            bloom_intensity = float(arguments.get("bloom_intensity", 0.3))
        except (TypeError, ValueError):
            return ToolResult(success=False, message="'bloom_intensity' must be a number")

        vignette = bool(arguments.get("vignette", True))

        try:
            vignette_strength = float(arguments.get("vignette_strength", 0.4))
        except (TypeError, ValueError):
            return ToolResult(success=False, message="'vignette_strength' must be a number")

        color_grading = str(arguments.get("color_grading", "neutral")).strip().lower()
        valid_grading = {"none", "neutral", "warm", "cool", "cinematic", "noir"}
        if color_grading not in valid_grading:
            return ToolResult(
                success=False,
                message=(
                    f"Invalid color_grading '{color_grading}'. "
                    f"Valid: {', '.join(sorted(valid_grading))}"
                ),
            )

        try:
            grain = float(arguments.get("grain", 0.02))
        except (TypeError, ValueError):
            return ToolResult(success=False, message="'grain' must be a number")

        try:
            chromatic_aberration = float(arguments.get("chromatic_aberration", 0.0))
        except (TypeError, ValueError):
            return ToolResult(success=False, message="'chromatic_aberration' must be a number")

        dof = bool(arguments.get("dof", False))

        try:
            dof_focus = float(arguments.get("dof_focus", 5.0))
        except (TypeError, ValueError):
            return ToolResult(success=False, message="'dof_focus' must be a number")

        post_fx: Dict[str, Any] = {
            "bloom": bloom,
            "bloom_intensity": bloom_intensity,
            "vignette": vignette,
            "vignette_strength": vignette_strength,
            "color_grading": color_grading,
            "grain": grain,
            "chromatic_aberration": chromatic_aberration,
            "dof": dof,
            "dof_focus": dof_focus,
        }

        metadata = _ensure_scene_metadata(scene)
        previous = metadata.get("post_fx")
        metadata["post_fx"] = post_fx

        return ToolResult(
            success=True,
            message=(
                f"Applied post-fx stack: bloom={bloom}, "
                f"vignette={vignette}, color_grading='{color_grading}', "
                f"dof={dof}"
            ),
            deltas=[SceneDelta(action="update", payload={"post_fx": post_fx})],
            data={"post_fx": post_fx, "previous": previous},
        )


# --- ComposeWorkflowTool ----------------------------------------------------

_COMPOSE_WORKFLOW_PARAMS = {
    "type": "object",
    "properties": {
        "workflow_name": {
            "type": "string",
            "description": "Unique name to store the workflow under (required)",
        },
        "steps": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "tool": {
                        "type": "string",
                        "description": "Tool name to invoke at this step",
                    },
                    "args": {
                        "type": "object",
                        "description": "Argument dict passed to the tool",
                    },
                },
                "required": ["tool", "args"],
            },
            "description": "Ordered list of tool call steps (required)",
        },
        "description": {
            "type": "string",
            "description": "Human-readable description of the workflow (optional)",
        },
        "tags": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Searchable tags for the workflow (optional)",
            "default": [],
        },
    },
    "required": ["workflow_name", "steps"],
}


class ComposeWorkflowTool(ToolBase):
    """Meta workflow engine: saves a named sequence of tool calls as a reusable recipe."""

    name = "compose_workflow"
    description = (
        "Persist a named, ordered recipe of tool calls in scene metadata. Each "
        "step specifies a tool name and its argument dict. Workflows can later "
        "be re-executed atomically via run_workflow."
    )

    def schema(self) -> Dict[str, Any]:
        return _COMPOSE_WORKFLOW_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        workflow_name = str(arguments.get("workflow_name", "")).strip()
        if not workflow_name:
            return ToolResult(success=False, message="'workflow_name' is required")

        raw_steps = arguments.get("steps")
        if not isinstance(raw_steps, list) or not raw_steps:
            return ToolResult(success=False, message="'steps' must be a non-empty array")

        steps: List[Dict[str, Any]] = []
        for i, step in enumerate(raw_steps):
            if not isinstance(step, dict):
                return ToolResult(
                    success=False,
                    message=f"Step #{i}: must be an object with 'tool' and 'args'",
                )
            tool_name = str(step.get("tool", "")).strip()
            args = step.get("args")
            if not tool_name:
                return ToolResult(
                    success=False,
                    message=f"Step #{i}: 'tool' name is required",
                )
            if not isinstance(args, dict):
                return ToolResult(
                    success=False,
                    message=f"Step #{i}: 'args' must be an object",
                )
            steps.append({"tool": tool_name, "args": dict(args)})

        description = str(arguments.get("description", "")) or ""
        raw_tags = arguments.get("tags", [])
        if not isinstance(raw_tags, list):
            return ToolResult(success=False, message="'tags' must be an array of strings")
        tags: List[str] = []
        for t in raw_tags:
            try:
                tags.append(str(t))
            except (TypeError, ValueError):
                return ToolResult(success=False, message="All tags must be strings")

        metadata = _ensure_scene_metadata(scene)
        workflows: Dict[str, Any] = metadata.get("workflows")
        if not isinstance(workflows, dict):
            workflows = {}
            metadata["workflows"] = workflows

        existing = workflows.get(workflow_name)
        workflow_payload: Dict[str, Any] = {
            "name": workflow_name,
            "steps": steps,
            "description": description,
            "tags": tags,
        }
        workflows[workflow_name] = workflow_payload

        msg = f"Saved workflow '{workflow_name}' with {len(steps)} step(s)"
        if existing is not None:
            msg += " (overwritten previous definition)"

        return ToolResult(
            success=True,
            message=msg,
            deltas=[SceneDelta(action="update", payload={"workflows": workflows})],
            data={"workflow": workflow_payload, "overwrote": existing is not None},
        )


# --- RunWorkflowTool --------------------------------------------------------

_RUN_WORKFLOW_PARAMS = {
    "type": "object",
    "properties": {
        "workflow_name": {
            "type": "string",
            "description": "Name of the saved workflow to execute (required)",
        },
        "overrides": {
            "type": "object",
            "description": (
                "Optional map from step index (as string key) to partial arg "
                "dicts merged on top of the saved step args"
            ),
            "default": {},
        },
    },
    "required": ["workflow_name"],
}


class RunWorkflowTool(ToolBase):
    """Executes a saved workflow by name."""

    name = "run_workflow"
    description = (
        "Run a previously saved workflow by name. Each step is applied "
        "directly to the scene within the single tool call. Optional "
        "overrides map step indices to partial arg dicts merged into the "
        "saved args. All deltas are collected and returned together."
    )

    def __init__(self, registry: Optional["ToolRegistry"] = None):
        self._registry = registry

    def schema(self) -> Dict[str, Any]:
        return _RUN_WORKFLOW_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        workflow_name = str(arguments.get("workflow_name", "")).strip()
        if not workflow_name:
            return ToolResult(success=False, message="'workflow_name' is required")

        metadata = _ensure_scene_metadata(scene)
        workflows: Any = metadata.get("workflows")
        if not isinstance(workflows, dict):
            return ToolResult(
                success=False,
                message=f"Workflow '{workflow_name}' not found (no workflows saved)",
            )

        workflow = workflows.get(workflow_name)
        if not isinstance(workflow, dict):
            return ToolResult(
                success=False,
                message=f"Workflow '{workflow_name}' not found",
            )

        steps = workflow.get("steps")
        if not isinstance(steps, list):
            return ToolResult(
                success=False,
                message=f"Workflow '{workflow_name}' has malformed steps",
            )

        raw_overrides = arguments.get("overrides", {})
        if not isinstance(raw_overrides, dict):
            return ToolResult(success=False, message="'overrides' must be an object")
        overrides: Dict[int, Dict[str, Any]] = {}
        for k, v in raw_overrides.items():
            try:
                idx = int(k)
            except (TypeError, ValueError):
                return ToolResult(
                    success=False,
                    message=f"Override key '{k}' is not a valid step index",
                )
            if not isinstance(v, dict):
                return ToolResult(
                    success=False,
                    message=f"Override for step {idx} must be an arg object",
                )
            overrides[idx] = v

        registry = self._registry
        if registry is None:
            try:
                from trigen.orchestrator import AgentOrchestrator

                registry = AgentOrchestrator().registry
            except Exception:
                return ToolResult(success=False, message="Tool registry unavailable")

        all_deltas: List[SceneDelta] = []
        all_data: Dict[str, Any] = {"steps": []}
        errors: List[str] = []
        successes = 0

        for i, step in enumerate(steps):
            if not isinstance(step, dict):
                errors.append(f"Step #{i}: malformed step data")
                all_data["steps"].append({"index": i, "success": False, "error": "malformed step"})
                continue

            tool_name = str(step.get("tool", "")).strip()
            base_args = step.get("args")
            if not isinstance(base_args, dict):
                base_args = {}

            merged_args: Dict[str, Any] = dict(base_args)
            step_override = overrides.get(i)
            if step_override:
                merged_args.update(step_override)

            tool = registry.get(tool_name)
            if tool is None:
                err = f"Step #{i}: unknown tool '{tool_name}'"
                errors.append(err)
                all_data["steps"].append(
                    {"index": i, "tool": tool_name, "success": False, "error": err}
                )
                continue

            try:
                result = await tool.execute(scene, merged_args)
            except Exception as exc:  # pragma: no cover - runtime safety net
                err = f"Step #{i}: tool execution error: {exc}"
                errors.append(err)
                all_data["steps"].append(
                    {"index": i, "tool": tool_name, "success": False, "error": err}
                )
                continue

            if result.success:
                successes += 1
                all_deltas.extend(result.deltas)
            else:
                errors.append(f"Step #{i}: {result.message}")

            all_data["steps"].append(
                {
                    "index": i,
                    "tool": tool_name,
                    "success": result.success,
                    "message": result.message,
                }
            )

        if successes == 0 and errors:
            return ToolResult(
                success=False,
                message=(
                    f"Workflow '{workflow_name}' failed: {len(errors)} step(s) had errors. "
                    + errors[0]
                ),
                deltas=all_deltas,
                data={**all_data, "errors": errors},
            )

        msg = (
            f"Executed workflow '{workflow_name}': {successes}/{len(steps)} "
            f"step(s) succeeded"
        )
        if errors:
            msg += f"; {len(errors)} warning(s): {errors[0]}"

        return ToolResult(
            success=True,
            message=msg,
            deltas=all_deltas,
            data={**all_data, "errors": errors, "success_count": successes},
        )


# --- BlendObjectsTool -------------------------------------------------------

_BLEND_OBJECTS_PARAMS = {
    "type": "object",
    "properties": {
        "source": {
            "type": "string",
            "description": "Source object id or name for the blend",
        },
        "target": {
            "type": "string",
            "description": "Target object id or name for the blend",
        },
        "factor": {
            "type": "number",
            "description": "Interpolation factor 0..1 between source and target (default 0.5)",
            "default": 0.5,
        },
        "keep_originals": {
            "type": "boolean",
            "description": "Whether the source and target objects remain in the scene (default True)",
            "default": True,
        },
    },
    "required": ["source", "target"],
}


class BlendObjectsTool(ToolBase):
    """Shape blend / morph between two objects."""

    name = "blend_objects"
    description = (
        "Create a new blend (morph) object that interpolates between a source "
        "and target shape at a given 0..1 factor. The blend geometry stores "
        "references to both originals plus the factor. Optionally removes "
        "source and target from the scene."
    )

    def schema(self) -> Dict[str, Any]:
        return _BLEND_OBJECTS_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        source_id_or_name = str(arguments.get("source", "")).strip()
        target_id_or_name = str(arguments.get("target", "")).strip()
        if not source_id_or_name:
            return ToolResult(success=False, message="'source' object is required")
        if not target_id_or_name:
            return ToolResult(success=False, message="'target' object is required")

        source_obj = scene.find_object(source_id_or_name)
        if source_obj is None:
            return ToolResult(success=False, message=f"Source object not found: {source_id_or_name}")

        target_obj = scene.find_object(target_id_or_name)
        if target_obj is None:
            return ToolResult(success=False, message=f"Target object not found: {target_id_or_name}")

        try:
            factor = float(arguments.get("factor", 0.5))
        except (TypeError, ValueError):
            return ToolResult(success=False, message="'factor' must be a number between 0 and 1")
        if factor < 0.0:
            factor = 0.0
        elif factor > 1.0:
            factor = 1.0

        keep_originals = bool(arguments.get("keep_originals", True))

        name = scene.next_auto_name("Blend")

        blend_obj = SceneObject(
            name=name,
            type="mesh",
            geometry=Geometry(
                type="blend",
                params={
                    "source_id": source_obj.id,
                    "target_id": target_obj.id,
                    "factor": factor,
                },
            ),
            material=Material(color="#cccccc"),
            transform=Transform(
                position=[
                    (source_obj.transform.position[i] + target_obj.transform.position[i]) / 2.0
                    for i in range(3)
                ]
            ),
        )
        scene.objects.append(blend_obj)

        deltas: List[SceneDelta] = [
            SceneDelta(action="create", target_id=blend_obj.id, payload=blend_obj.to_dict())
        ]

        removed: List[str] = []
        if not keep_originals:
            for ref_obj in (source_obj, target_obj):
                if scene.remove_object(ref_obj.id):
                    removed.append(ref_obj.id)
                    deltas.append(SceneDelta(action="delete", target_id=ref_obj.id))

        msg = (
            f"Created blend '{name}' between '{source_obj.name}' and "
            f"'{target_obj.name}' at factor {factor}"
        )
        if removed:
            msg += f"; removed {len(removed)} original object(s)"

        return ToolResult(
            success=True,
            message=msg,
            deltas=deltas,
            data={
                "blend_object": blend_obj.to_dict(),
                "source_id": source_obj.id,
                "target_id": target_obj.id,
                "factor": factor,
                "removed_ids": removed,
            },
        )
