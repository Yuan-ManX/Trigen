"""Tools and presets router.

Exposes the Agent tool catalog and preset enumerations to the frontend
so it can render dynamic UI based on available capabilities. Also provides
a direct tool execution endpoint so individual tools can be invoked
without a full chat round-trip — useful for editor panels, quick actions,
and pipeline composition.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from trigen.api.models.schemas import PresetsResponse, ToolsResponse, ToolSchema
from trigen.api.services.agent_service import AgentService

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
    """List available smart compose scene templates."""
    return {"templates": SCENE_TEMPLATES, "count": len(SCENE_TEMPLATES)}


class ExecuteToolRequest(BaseModel):
    """Request body for direct tool execution."""

    tool_name: str = Field(..., description="Name of the tool to execute")
    arguments: Dict[str, Any] = Field(
        default_factory=dict, description="Tool arguments as defined by its schema"
    )
    session_id: str = Field("default", description="Session id for scene isolation")


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

    return {
        "tool": req.tool_name,
        "success": result.success,
        "message": result.message,
        "deltas": [d.__dict__ if hasattr(d, "__dict__") else d for d in result.deltas],
        "data": result.data,
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
async def get_suggestions(session_id: str = "default") -> Dict[str, Any]:
    """Generate proactive creative suggestions for the current scene.

    Returns 2-3 next-step suggestions tailored to the scene's content,
    lighting, and palette so the frontend can surface a "You might try…"
    strip in the editor.
    """
    from trigen.suggestions import generate_suggestions

    agent = AgentService.get()
    orch = agent.orchestrator
    scene = orch.get_scene(session_id)
    suggestions = generate_suggestions(scene.to_dict())
    return {"suggestions": suggestions, "count": len(suggestions)}
