"""Tools and presets router.

Exposes the Agent tool catalog and preset enumerations to the frontend
so it can render dynamic UI based on available capabilities. Also provides
a direct tool execution endpoint so individual tools can be invoked
without a full chat round-trip — useful for editor panels, quick actions,
and pipeline composition.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from trigen.api.models.schemas import PresetsResponse, ToolsResponse, ToolSchema
from trigen.api.services.agent_service import AgentService
from trigen.scene_autosave import autosave_scene

logger = logging.getLogger("trigen.api.tools")
router = APIRouter(tags=["tools"])


@router.get("/tools", response_model=ToolsResponse)
async def list_tools() -> ToolsResponse:
    """List all Agent-callable tools with their schemas."""
    agent = AgentService.get()
    raw = agent.list_tools()
    tools = [
        ToolSchema(
            name=t.get("name", ""),
            description=t.get("description", ""),
            parameters=t.get("parameters", {}),
            category=t.get("category", "general"),
            requires_approval=bool(t.get("requires_approval", False)),
        )
        for t in raw
    ]
    return ToolsResponse(tools=tools, count=len(tools))


@router.get("/tools/categories")
async def list_tool_categories() -> Dict[str, Any]:
    """List all tools grouped by their functional category.

    Returns a dict keyed by category name whose values are lists of tool
    descriptors (name / description / parameters / category /
    requires_approval). Also includes a ``categories`` summary list with
    per-category counts so the frontend can render a browsable tool
    catalog without re-grouping client-side.
    """
    agent = AgentService.get()
    grouped = agent.orchestrator.registry.categories()
    summary = [
        {"category": cat, "count": len(items)}
        for cat, items in sorted(grouped.items())
    ]
    return {
        "categories": grouped,
        "summary": summary,
        "total_categories": len(grouped),
        "total_tools": sum(len(items) for items in grouped.values()),
    }


@router.get("/tools/search", response_model=ToolsResponse)
async def search_tools(q: str) -> ToolsResponse:
    """Search tools by name, description, or category.

    Performs a case-insensitive substring match against each tool's name,
    description, and category, returning the matching tool schemas. When
    ``q`` is empty, every tool is returned (equivalent to ``GET /tools``).
    Useful for Command Palette / quick-action lookups where the frontend
    needs to filter the catalog by a free-text query.
    """
    agent = AgentService.get()
    query = (q or "").strip().lower()
    raw = agent.list_tools()
    if not query:
        tools = [
            ToolSchema(
                name=t.get("name", ""),
                description=t.get("description", ""),
                parameters=t.get("parameters", {}),
                category=t.get("category", "general"),
                requires_approval=bool(t.get("requires_approval", False)),
            )
            for t in raw
        ]
        return ToolsResponse(tools=tools, count=len(tools))
    matched = []
    for t in raw:
        name = str(t.get("name", "")).lower()
        description = str(t.get("description", "")).lower()
        category = str(t.get("category", "general")).lower()
        if query in name or query in description or query in category:
            matched.append(t)
    tools = [
        ToolSchema(
            name=t.get("name", ""),
            description=t.get("description", ""),
            parameters=t.get("parameters", {}),
            category=t.get("category", "general"),
            requires_approval=bool(t.get("requires_approval", False)),
        )
        for t in matched
    ]
    return ToolsResponse(tools=tools, count=len(tools))


@router.get("/presets", response_model=PresetsResponse)
async def list_presets() -> PresetsResponse:
    """List available geometry, material, and light presets."""
    agent = AgentService.get()
    presets = agent.list_presets()
    return PresetsResponse(
        geometry_types=presets["geometry_types"],
        material_presets=presets["material_presets"],
        light_types=presets["light_types"],
    )


# Default parameter presets for the newer generative tool families. These give
# the frontend a data source to render parameterized forms without duplicating
# tool schemas client-side. Grouped by tool name, matching the registry.
_TOOL_PRESETS: Dict[str, Dict[str, Any]] = {
    "voxel_sculpt": {
        "label": "Voxel Sculpt",
        "category": "procedural",
        "operations": ["sphere", "box", "pyramid", "add", "remove", "paint"],
        "defaults": {
            "operation": "sphere",
            "size": 1,
            "color": "#ff6600",
            "radius": 3,
            "dimensions": [5, 5, 5],
        },
    },
    "create_particle_system": {
        "label": "Particle System",
        "category": "creation",
        "effects": ["fire", "smoke", "sparks", "fountain", "explosion", "dust", "magic"],
        "defaults": {
            "effect_type": "fire",
            "intensity": 1.0,
            "scale": 1.0,
            "position": [0, 0, 0],
        },
    },
    "generate_lod_chain": {
        "label": "LOD Chain",
        "category": "creation",
        "defaults": {"levels": 3, "reduction_factor": 0.5, "auto_tag": True},
    },
    "repair_mesh": {
        "label": "Mesh Repair",
        "category": "creation",
        "fixes": ["fill_holes", "cap_openings", "remove_duplicates", "fix_normals", "thicken_thin_walls", "all"],
        "defaults": {"min_wall_thickness": 0.05, "report_only": False},
    },
    "self_evaluate": {
        "label": "Self Evaluate",
        "category": "intelligence",
        "criteria": ["composition", "lighting", "color_harmony", "complexity", "goal_alignment"],
        "defaults": {"auto_fix": False},
    },
    "consensus_vote": {
        "label": "Consensus Vote",
        "category": "intelligence",
        "strategies": ["majority", "best_of_3", "first_success"],
        "defaults": {"strategy": "majority", "max_models": 3},
    },
    "set_bloom": {
        "label": "Bloom Effect",
        "category": "viewport",
        "presets": {
            "subtle": {"strength": 0.4, "threshold": 0.95, "radius": 0.3},
            "cinematic": {"strength": 0.85, "threshold": 0.9, "radius": 0.5},
            "neon": {"strength": 1.6, "threshold": 0.6, "radius": 0.7},
            "dream": {"strength": 1.2, "threshold": 0.5, "radius": 0.9},
        },
        "defaults": {"enabled": True, "strength": 0.85, "threshold": 0.9, "radius": 0.5},
    },
    "set_color_grading": {
        "label": "Color Grading",
        "category": "viewport",
        "presets": {
            "warm_sunset": {"temperature": 0.6, "tint": -0.1, "saturation": 1.1, "contrast": 1.05},
            "cool_night": {"temperature": -0.5, "tint": 0.1, "saturation": 0.9, "contrast": 1.1},
            "cinematic_teal_orange": {"temperature": 0.3, "saturation": 1.15, "contrast": 1.15},
            "noir": {"saturation": 0.0, "contrast": 1.3, "temperature": -0.2},
            "vintage_film": {"temperature": 0.4, "saturation": 0.85, "contrast": 0.95},
        },
        "defaults": {"enabled": True, "temperature": 0.0, "tint": 0.0, "contrast": 1.0, "saturation": 1.0},
    },
    "set_vignette": {
        "label": "Vignette",
        "category": "viewport",
        "presets": {
            "subtle": {"strength": 0.25, "radius": 0.6, "softness": 0.7},
            "cinematic": {"strength": 0.45, "radius": 0.45, "softness": 0.6},
            "portrait": {"strength": 0.6, "radius": 0.35, "softness": 0.5},
        },
        "defaults": {"enabled": True, "strength": 0.4, "radius": 0.5, "softness": 0.6},
    },
    "set_film_grain": {
        "label": "Film Grain",
        "category": "viewport",
        "presets": {
            "fine": {"strength": 0.04, "size": 0.8},
            "classic_35mm": {"strength": 0.08, "size": 1.0},
            "super_8": {"strength": 0.18, "size": 2.2},
        },
        "defaults": {"enabled": False, "strength": 0.08, "size": 1.0, "animated": True},
    },
    "set_depth_of_field": {
        "label": "Depth of Field",
        "category": "viewport",
        "presets": {
            "portrait_50mm": {"focus_distance": 5.0, "focal_length": 50.0, "fstop": 1.8},
            "product_85mm": {"focus_distance": 3.0, "focal_length": 85.0, "fstop": 2.8},
            "cinematic_35mm": {"focus_distance": 8.0, "focal_length": 35.0, "fstop": 2.0},
            "macro": {"focus_distance": 1.5, "focal_length": 100.0, "fstop": 2.8},
        },
        "defaults": {"enabled": False, "focus_distance": 5.0, "focal_length": 50.0, "fstop": 2.8},
    },
    "noise_deform": {
        "label": "Noise Displacement",
        "category": "procedural",
        "presets": {
            "subtle_water": {"scale": 2.0, "strength": 0.1, "octaves": 2},
            "rocky_terrain": {"scale": 1.2, "strength": 0.4, "octaves": 5},
            "asteroid": {"scale": 0.8, "strength": 0.2, "octaves": 4},
            "cloud_like": {"scale": 3.0, "strength": 0.15, "octaves": 3},
        },
        "defaults": {"scale": 1.5, "strength": 0.25, "octaves": 3, "seed": 42},
    },
    "hex_grid_pattern": {
        "label": "Hex Grid Pattern",
        "category": "procedural",
        "presets": {
            "small_tile": {"cell_radius": 0.5, "rows": 6, "columns": 8},
            "large_city": {"cell_radius": 1.5, "rows": 10, "columns": 12},
        },
        "defaults": {"geometry_type": "cylinder", "rows": 6, "columns": 8, "size": 0.5},
    },
    "fibonacci_lattice": {
        "label": "Fibonacci Lattice",
        "category": "procedural",
        "presets": {
            "small_flower": {"count": 30, "radius": 2.0},
            "full_sunflower": {"count": 120, "radius": 5.0},
        },
        "defaults": {"count": 60, "radius": 4.0, "geometry_type": "sphere"},
    },
    "generate_maze": {
        "label": "Maze Generator",
        "category": "procedural",
        "presets": {
            "small_room": {"rows": 5, "cols": 5},
            "classic": {"rows": 10, "cols": 14},
            "epic": {"rows": 20, "cols": 28},
        },
        "defaults": {"rows": 8, "columns": 10, "cell_size": 1.5},
    },
    "honeycomb_truss": {
        "label": "Honeycomb Truss",
        "category": "procedural",
        "presets": {
            "small_panel": {"cells_x": 4, "cells_z": 3},
            "large_sandwich": {"cells_x": 10, "cells_z": 8},
        },
        "defaults": {"cells_x": 6, "cells_z": 5, "cell_radius": 0.6},
    },
}


@router.get("/presets/tools")
async def list_tool_presets() -> Dict[str, Any]:
    """List default parameter presets for the newer generative tool families.

    Returns per-tool defaults (operations, effect types, criteria, strategies)
    so the frontend can render parameterized tool forms without duplicating
    tool schemas client-side. Complements the base ``/presets`` endpoint.
    """
    return {
        "tools": _TOOL_PRESETS,
        "count": len(_TOOL_PRESETS),
    }


# Smart compose scene templates
SCENE_TEMPLATES = [
    {"id": "solar_system", "name": "Solar System", "description": "Sun with 8 orbiting planets and orbital rings"},
    {"id": "city_block", "name": "City Block", "description": "Grid of buildings with varying heights on a ground plane"},
    {"id": "studio", "name": "Studio", "description": "Three-point lighting setup with a display platform"},
    {"id": "crystal_cluster", "name": "Crystal Cluster", "description": "Random glowing polyhedra in a dark atmosphere"},
    {"id": "product_showcase", "name": "Product Showcase", "description": "Pedestal with spotlight and rim lighting"},
]


@router.get("/presets/templates")
async def list_scene_templates() -> dict:
    """List available smart compose scene templates.

    Response includes both the static ``smart_compose`` presets and the
    skill-aligned templates that can be materialized via the
    ``invoke_skill`` tool. Each entry carries the target invocation so
    the frontend can turn a template click into the right Agent call.
    """
    try:
        agent = AgentService.get()
        # Pull the detailed template catalog from the list_scene_templates
        # tool rather than duplicating the data here. If the tool is
        # unavailable (e.g. during early startup) we fall back to the
        # static presets defined below.
        registry = agent.orchestrator.registry
        tool = registry.get("list_scene_templates")
        if tool is not None:
            result = await tool.execute(agent.get_scene("default"), {})
            if result.success:
                data = getattr(result, "data", None) or {}
                templates = data.get("templates") or data.get("items") or []
                return {
                    "templates": templates,
                    "count": len(templates),
                    "source": "agent_tool",
                }
    except Exception:
        logger.exception("list_scene_templates: falling back to static presets")

    return {
        "templates": SCENE_TEMPLATES,
        "count": len(SCENE_TEMPLATES),
        "source": "static",
    }


class ExecuteToolRequest(BaseModel):
    """Request body for direct tool execution."""

    tool_name: str = Field(..., description="Name of the tool to execute")
    arguments: Dict[str, Any] = Field(
        default_factory=dict, description="Tool arguments as defined by its schema"
    )
    session_id: str = Field("default", description="Session id for scene isolation")


class BatchToolStep(BaseModel):
    """A single step within a batch tool execution request."""

    tool_name: str = Field(..., description="Name of the tool to execute")
    arguments: Dict[str, Any] = Field(
        default_factory=dict, description="Tool arguments for this step"
    )


class BatchToolRequest(BaseModel):
    """Request body for batch (multi-step) tool execution.

    Executes an ordered list of tool calls against the same session scene,
    so the frontend can compose multi-step workflows (e.g. create + transform
    + material) in a single REST round-trip without going through the LLM
    chat flow. Each step sees the scene mutations produced by prior steps.
    """

    steps: List[BatchToolStep] = Field(
        ..., description="Ordered list of tool calls to execute sequentially"
    )
    session_id: str = Field("default", description="Session id for scene isolation")
    stop_on_error: bool = Field(
        True, description="When True, abort remaining steps on the first failure"
    )


@router.post("/tools/execute")
async def execute_tool(req: ExecuteToolRequest) -> Dict[str, Any]:
    """Execute a single tool directly against the session scene.

    This bypasses the LLM chat flow and runs the tool immediately, returning
    the tool result and the updated scene. Useful for editor-side panels,
    quick actions, and pipeline composition where the LLM is not needed
    to decide which tool to call.
    """
    agent = AgentService.get()
    orch = agent.orchestrator
    registry = orch.registry

    tool = registry.get(req.tool_name)
    if tool is None:
        raise HTTPException(
            status_code=404,
            detail=f"Tool '{req.tool_name}' not found. Available: {[t.name for t in registry.all()]}",
        )

    scene = orch.get_scene(req.session_id)
    try:
        result = await tool.execute(scene, req.arguments)
    except Exception as exc:
        logger.exception("Direct tool execution failed: %s", req.tool_name)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    # Persist the live scene (best-effort) so direct edits survive restarts.
    autosave_scene(req.session_id, scene)

    return {
        "tool": req.tool_name,
        "success": result.success,
        "message": result.message,
        "deltas": [d.__dict__ if hasattr(d, "__dict__") else d for d in result.deltas],
        "data": result.data,
        "scene": scene.to_dict(),
    }


@router.post("/tools/batch")
async def batch_execute_tools(req: BatchToolRequest) -> Dict[str, Any]:
    """Execute multiple tool calls sequentially against the same session scene.

    Each step sees the mutations produced by prior steps, enabling the
    frontend to compose multi-step workflows (create + transform + material,
    array + mirror, etc.) in a single REST round-trip. When
    ``stop_on_error`` is True the batch aborts on the first failing step;
    otherwise all steps run and per-step success/failure is reported.

    Returns the aggregated per-step results, the final scene snapshot, and
    overall success/failure counts so the UI can render a progress summary.
    """
    agent = AgentService.get()
    orch = agent.orchestrator
    registry = orch.registry
    scene = orch.get_scene(req.session_id)

    # Push scene history so the batch's mutations are undo-able via the
    # editor's undo stack.
    orch.push_scene_history(req.session_id)

    step_results: List[Dict[str, Any]] = []
    succeeded = 0
    failed = 0
    aborted = False

    for idx, step in enumerate(req.steps):
        tool = registry.get(step.tool_name)
        if tool is None:
            failed += 1
            step_results.append({
                "index": idx,
                "tool": step.tool_name,
                "success": False,
                "message": f"Tool '{step.tool_name}' not found",
                "deltas": [],
                "data": None,
            })
            if req.stop_on_error:
                aborted = True
                break
            continue

        try:
            result = await tool.execute(scene, step.arguments)
        except Exception as exc:
            logger.exception("Batch step %d (%s) failed", idx, step.tool_name)
            failed += 1
            step_results.append({
                "index": idx,
                "tool": step.tool_name,
                "success": False,
                "message": str(exc),
                "deltas": [],
                "data": None,
            })
            if req.stop_on_error:
                aborted = True
                break
            continue

        if result.success:
            succeeded += 1
        else:
            failed += 1
            if req.stop_on_error:
                step_results.append({
                    "index": idx,
                    "tool": step.tool_name,
                    "success": result.success,
                    "message": result.message,
                    "deltas": [d.__dict__ if hasattr(d, "__dict__") else d for d in result.deltas],
                    "data": result.data,
                })
                aborted = True
                break

        step_results.append({
            "index": idx,
            "tool": step.tool_name,
            "success": result.success,
            "message": result.message,
            "deltas": [d.__dict__ if hasattr(d, "__dict__") else d for d in result.deltas],
            "data": result.data,
        })

    # Persist the live scene (best-effort) after the batch completes.
    autosave_scene(req.session_id, scene)

    return {
        "session_id": req.session_id,
        "total_steps": len(req.steps),
        "executed_steps": len(step_results),
        "succeeded": succeeded,
        "failed": failed,
        "aborted": aborted,
        "steps": step_results,
        "scene": scene.to_dict(),
    }


# Template pattern for chain step argument references. Matches tokens like
# ``{{step_0.result.id}}`` or ``{{step_2.data.name}}`` so a later step can
# pull values produced by an earlier step's tool result.
import re as _re

_CHAIN_TEMPLATE_RE = _re.compile(r"\{\{\s*(step_\d+)\.([^}]+?)\s*\}\}")


def _resolve_chain_template_value(value: Any, step_results: List[Dict[str, Any]]) -> Any:
    """Resolve ``{{step_N.path.to.value}}`` references inside ``value``.

    Walks dicts / lists recursively, replacing every template token with the
    value found at the corresponding path inside the referenced step's
    stored result dict. When a path cannot be resolved, the token is left
    untouched so the failure is visible in the executed arguments. String
    values containing a single token that resolves to a non-string are
    returned as the raw value (so a ``{{step_0.result.id}}`` inside a string
    field yields the actual id with its native type, not a stringified one).
    """
    if isinstance(value, str):
        matches = list(_CHAIN_TEMPLATE_RE.finditer(value))
        if not matches:
            return value
        # Single-token string: return the raw resolved value to preserve type.
        if len(matches) == 1 and matches[0].group(0).strip() == value.strip():
            return _resolve_step_path(matches[0].group(1), matches[0].group(2), step_results)
        # Multiple tokens / surrounding text: interpolate as strings.
        def _sub(match: "_re.Match") -> str:
            resolved = _resolve_step_path(match.group(1), match.group(2), step_results)
            if isinstance(resolved, str):
                return resolved
            return _json_dumps_safe(resolved)
        return _CHAIN_TEMPLATE_RE.sub(_sub, value)
    if isinstance(value, dict):
        return {k: _resolve_chain_template_value(v, step_results) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve_chain_template_value(v, step_results) for v in value]
    return value


def _resolve_step_path(step_key: str, path: str, step_results: List[Dict[str, Any]]) -> Any:
    """Walk ``step_results[<index>][<path parts>]`` and return the leaf value.

    Returns the original ``{{...}}`` token as a string when the step index
    is out of range or the path cannot be followed, so the caller can see
    that the reference was unresolved rather than silently dropping it.
    """
    try:
        idx = int(step_key.split("_", 1)[1])
    except (ValueError, IndexError):
        return "{{" + f"{step_key}.{path}" + "}}"
    if idx < 0 or idx >= len(step_results):
        return "{{" + f"{step_key}.{path}" + "}}"
    current: Any = step_results[idx]
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list):
            try:
                current = current[int(part)]
            except (ValueError, IndexError):
                return "{{" + f"{step_key}.{path}" + "}}"
        else:
            return "{{" + f"{step_key}.{path}" + "}}"
    return current


def _json_dumps_safe(value: Any) -> str:
    """Best-effort JSON serialization for template interpolation."""
    try:
        return json.dumps(value)
    except Exception:
        return str(value)


class ChainToolStep(BaseModel):
    """A single step within a chain tool execution request.

    Unlike a batch step, a chain step's ``arguments`` may contain template
    references like ``{{step_0.result.id}}`` that are resolved against the
    results of prior steps before execution, enabling data flow between
    steps (e.g. create an object, then transform it by id).
    """

    tool_name: str = Field(..., description="Name of the tool to execute")
    arguments: Dict[str, Any] = Field(
        default_factory=dict,
        description="Tool arguments; may contain {{step_N.result.path}} template refs",
    )


class ChainToolRequest(BaseModel):
    """Request body for chained tool execution with data flow between steps.

    Like ``BatchToolRequest`` but each step's arguments are first resolved
    against previous steps' results, so the output of one tool (e.g. the
    id of a created object) can feed into the next tool's arguments (e.g.
    a transform applied to that id). Use this when steps are dependent;
    use ``/tools/batch`` when steps are independent.
    """

    steps: List[ChainToolStep] = Field(
        ..., description="Ordered tool calls; later steps may reference earlier results"
    )
    session_id: str = Field("default", description="Session id for scene isolation")
    stop_on_error: bool = Field(
        True, description="When True, abort remaining steps on the first failure"
    )


@router.post("/tools/chain")
async def chain_execute_tools(req: ChainToolRequest) -> Dict[str, Any]:
    """Execute a chain of tools with data flow between steps.

    Each step's arguments are scanned for ``{{step_N.result.path}}``
    template references, which are resolved against the stored result of
    step ``N`` before the tool runs. This lets a later step consume the
    output of an earlier step — e.g. ``step_0`` creates an object and
    ``step_1`` transforms it by referencing ``{{step_0.result.id}}``.

    Unresolved references are left as literal strings in the executed
    arguments so the failure is visible. When ``stop_on_error`` is True
    the chain aborts on the first failing step. Returns the per-step
    results (with both the resolved arguments and the raw tool result),
    the final scene snapshot, and overall success/failure counts.
    """
    agent = AgentService.get()
    orch = agent.orchestrator
    registry = orch.registry
    scene = orch.get_scene(req.session_id)

    # Push scene history so the chain's mutations are undo-able.
    orch.push_scene_history(req.session_id)

    step_results: List[Dict[str, Any]] = []
    succeeded = 0
    failed = 0
    aborted = False

    for idx, step in enumerate(req.steps):
        # Resolve template references against prior step results.
        resolved_args = _resolve_chain_template_value(step.arguments, step_results)

        tool = registry.get(step.tool_name)
        if tool is None:
            failed += 1
            entry = {
                "index": idx,
                "tool": step.tool_name,
                "success": False,
                "message": f"Tool '{step.tool_name}' not found",
                "arguments": resolved_args,
                "raw_arguments": step.arguments,
                "deltas": [],
                "data": None,
                "result": None,
            }
            step_results.append(entry)
            if req.stop_on_error:
                aborted = True
                break
            continue

        try:
            result = await tool.execute(scene, resolved_args)
        except Exception as exc:
            logger.exception("Chain step %d (%s) failed", idx, step.tool_name)
            failed += 1
            entry = {
                "index": idx,
                "tool": step.tool_name,
                "success": False,
                "message": str(exc),
                "arguments": resolved_args,
                "raw_arguments": step.arguments,
                "deltas": [],
                "data": None,
                "result": None,
            }
            step_results.append(entry)
            if req.stop_on_error:
                aborted = True
                break
            continue

        if result.success:
            succeeded += 1
        else:
            failed += 1

        # Store the result payload under "result" so {{step_N.result.X}}
        # references resolve against the tool's data. Also keep "data" as
        # an alias for parity with the batch endpoint shape.
        result_payload = result.data if isinstance(result.data, dict) else {"value": result.data}
        entry = {
            "index": idx,
            "tool": step.tool_name,
            "success": result.success,
            "message": result.message,
            "arguments": resolved_args,
            "raw_arguments": step.arguments,
            "deltas": [d.__dict__ if hasattr(d, "__dict__") else d for d in result.deltas],
            "data": result.data,
            "result": result_payload,
        }
        step_results.append(entry)
        if not result.success and req.stop_on_error:
            aborted = True
            break

    # Persist the live scene (best-effort) after the chain completes.
    autosave_scene(req.session_id, scene)

    return {
        "session_id": req.session_id,
        "total_steps": len(req.steps),
        "executed_steps": len(step_results),
        "succeeded": succeeded,
        "failed": failed,
        "aborted": aborted,
        "steps": step_results,
        "scene": scene.to_dict(),
    }


class ExportCodeRequest(BaseModel):
    """Request body for scene-to-code export.

    Convenience wrapper around the ``export_code`` tool so the frontend can
    hit a dedicated REST endpoint without going through ``/tools/execute``.
    The generated source (Three.js / React+R3F / standalone HTML) is
    persisted to the workspace exports directory and returned inline.
    """

    format: str = Field(
        "three_js",
        description="Target code format: three_js | react_r3f | html",
    )
    filename: str = Field(
        "",
        description="Optional output file name (without extension). "
        "Defaults to trigen_scene_<timestamp>.",
    )
    include_animation: bool = Field(
        True,
        description="Emit an animation loop playing per-object animation descriptors.",
    )
    session_id: str = Field("default", description="Session id for scene isolation")


@router.post("/export/code")
async def export_code(req: ExportCodeRequest) -> Dict[str, Any]:
    """Export the current session scene as ready-to-run source code.

    Calls the registered ``export_code`` tool against the session scene and
    returns the generated code inline along with metadata (format, line count,
    file path). The frontend uses this to power the "Export code" panel
    without spinning up a chat turn.
    """
    agent = AgentService.get()
    orch = agent.orchestrator
    registry = orch.registry

    tool = registry.get("export_code")
    if tool is None:
        raise HTTPException(
            status_code=404,
            detail="export_code tool is not registered on the server",
        )

    scene = orch.get_scene(req.session_id)
    arguments: Dict[str, Any] = {
        "format": req.format,
        "include_animation": req.include_animation,
    }
    if req.filename:
        arguments["filename"] = req.filename

    try:
        result = await tool.execute(scene, arguments)
    except Exception as exc:
        logger.exception("Code export failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if not result.success:
        # Surface tool-level failure as a 400 with the message
        raise HTTPException(status_code=400, detail=result.message)

    return {
        "tool": "export_code",
        "success": result.success,
        "message": result.message,
        "data": result.data,
    }


@router.get("/skills")
async def list_skills() -> Dict[str, Any]:
    """List all available creative skills with their parameter schemas.

    Skills are higher-level recipes that expand into ordered tool-call
    sequences (e.g. spiral staircase, colonnade, forest). The frontend
    renders this catalog in the sidebar so users can one-click invoke
    a multi-step composition without scripting each tool call.
    """
    from trigen.skills import build_default_registry

    reg = build_default_registry()
    skills = reg.schemas()
    return {"skills": skills, "count": len(skills)}


class InvokeSkillRequest(BaseModel):
    """Request body for direct skill invocation."""

    skill: str = Field(..., description="Skill name to invoke")
    arguments: Dict[str, Any] = Field(
        default_factory=dict, description="Skill-specific parameters"
    )
    session_id: str = Field("default", description="Session id for scene isolation")


@router.post("/skills/invoke")
async def invoke_skill(req: InvokeSkillRequest) -> Dict[str, Any]:
    """Invoke a creative skill directly, expanding it into tool steps and
    executing them against the session scene.

    Bypasses the LLM chat flow: the frontend calls this when a user
    one-clicks a skill from the sidebar catalog. Returns the aggregated
    result, the updated scene, and per-step outcome counts so the UI can
    report how many sub-steps succeeded.
    """
    agent = AgentService.get()
    orch = agent.orchestrator
    tool = orch.registry.get("invoke_skill")
    if tool is None:
        raise HTTPException(status_code=404, detail="invoke_skill tool is not registered")

    scene = orch.get_scene(req.session_id)
    # Push scene history so the skill's mutations are undo-able.
    orch.push_scene_history(req.session_id)
    arguments = {"skill": req.skill, "arguments": req.arguments}
    try:
        result = await tool.execute(scene, arguments)
    except Exception as exc:
        logger.exception("Skill invocation failed: %s", req.skill)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {
        "skill": req.skill,
        "success": result.success,
        "message": result.message,
        "data": result.data,
        "deltas": [d.__dict__ if hasattr(d, "__dict__") else d for d in result.deltas],
        "scene": scene.to_dict(),
    }


@router.get("/suggestions")
async def get_suggestions(
    session_id: str = "default",
    count: int = 4,
    direction: str = "any",
) -> Dict[str, Any]:
    """Generate proactive creative suggestions for the current scene.

    Returns 2-5 next-step suggestions tailored to the scene's content,
    lighting, and palette so the frontend can surface a "You might try…"
    strip in the editor. Accepts an optional creative-direction hint
    (lighting / motion / material / composition / population) to bias
    the returned suggestions toward the user's current focus.
    """
    from trigen.suggestions import generate_suggestions

    agent = AgentService.get()
    orch = agent.orchestrator
    scene = orch.get_scene(session_id)
    tool = orch.registry.get("suggest_next_actions")
    if tool is not None:
        result = await tool.execute(
            scene, {"count": count, "direction": direction}
        )
        data = getattr(result, "data", None) or {}
        suggestions = data.get("suggestions") or []
        return {
            "suggestions": suggestions,
            "count": len(suggestions),
            "direction": data.get("direction", direction),
            "source": "suggest_next_actions",
        }
    # Fall back to the plain suggestions engine if the tool is not
    # registered (e.g. older workspace state).
    suggestions = generate_suggestions(scene.to_dict())
    return {"suggestions": suggestions, "count": len(suggestions), "source": "fallback"}


# ---------------------------------------------------------------------------
# Streaming batch execution over WebSocket
# ---------------------------------------------------------------------------


@router.websocket("/tools/batch/ws")
async def batch_execute_tools_ws(websocket: WebSocket) -> None:
    """WebSocket endpoint that streams per-step progress for batch tool runs.

    Accepts a single JSON message matching the ``BatchToolRequest`` shape
    (``steps``, ``session_id``, ``stop_on_error``) and emits a ``step``
    event after each step completes, followed by a final ``done`` event
    with the aggregated summary and final scene snapshot. This mirrors
    the REST ``POST /api/tools/batch`` endpoint but streams progress so
    the frontend can render a live progress bar / per-step status list.
    """
    await websocket.accept()
    agent = AgentService.get()
    try:
        raw = await websocket.receive_text()
        req = json.loads(raw)
        steps = req.get("steps", [])
        session_id = req.get("session_id", "default")
        stop_on_error = bool(req.get("stop_on_error", True))
    except Exception as exc:
        await websocket.send_text(json.dumps({
            "type": "error",
            "data": {"message": f"Invalid batch request: {exc}"},
        }))
        await websocket.close()
        return

    orch = agent.orchestrator
    registry = orch.registry
    scene = orch.get_scene(session_id)
    orch.push_scene_history(session_id)

    step_results: List[Dict[str, Any]] = []
    succeeded = 0
    failed = 0
    aborted = False
    total = len(steps)

    for idx, step in enumerate(steps):
        tool_name = step.get("tool_name", "")
        arguments = step.get("arguments", {}) or {}
        tool = registry.get(tool_name)
        if tool is None:
            failed += 1
            entry = {
                "index": idx,
                "tool": tool_name,
                "success": False,
                "message": f"Tool '{tool_name}' not found",
                "deltas": [],
                "data": None,
            }
            step_results.append(entry)
            await websocket.send_text(json.dumps({
                "type": "step",
                "data": {
                    **entry,
                    "progress": idx + 1,
                    "total": total,
                    "succeeded": succeeded,
                    "failed": failed,
                },
            }))
            if stop_on_error:
                aborted = True
                break
            continue

        try:
            result = await tool.execute(scene, arguments)
        except Exception as exc:
            logger.exception("WS batch step %d (%s) failed", idx, tool_name)
            failed += 1
            entry = {
                "index": idx,
                "tool": tool_name,
                "success": False,
                "message": str(exc),
                "deltas": [],
                "data": None,
            }
            step_results.append(entry)
            await websocket.send_text(json.dumps({
                "type": "step",
                "data": {
                    **entry,
                    "progress": idx + 1,
                    "total": total,
                    "succeeded": succeeded,
                    "failed": failed,
                },
            }))
            if stop_on_error:
                aborted = True
                break
            continue

        if result.success:
            succeeded += 1
        else:
            failed += 1
        entry = {
            "index": idx,
            "tool": tool_name,
            "success": result.success,
            "message": result.message,
            "deltas": [d.__dict__ if hasattr(d, "__dict__") else d for d in result.deltas],
            "data": result.data,
        }
        step_results.append(entry)
        if not result.success and stop_on_error:
            aborted = True
            await websocket.send_text(json.dumps({
                "type": "step",
                "data": {
                    **entry,
                    "progress": idx + 1,
                    "total": total,
                    "succeeded": succeeded,
                    "failed": failed,
                },
            }))
            break
        await websocket.send_text(json.dumps({
            "type": "step",
            "data": {
                **entry,
                "progress": idx + 1,
                "total": total,
                "succeeded": succeeded,
                "failed": failed,
            },
        }))

    await websocket.send_text(json.dumps({
        "type": "done",
        "data": {
            "session_id": session_id,
            "total_steps": total,
            "executed_steps": len(step_results),
            "succeeded": succeeded,
            "failed": failed,
            "aborted": aborted,
            "steps": step_results,
            "scene": scene.to_dict(),
        },
    }))
    await websocket.close()
