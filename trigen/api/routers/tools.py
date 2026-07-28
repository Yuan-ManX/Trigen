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
        )
        for t in raw
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
