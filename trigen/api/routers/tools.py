"""Tools and presets router.

Exposes the Agent tool catalog and preset enumerations to the frontend
so it can render dynamic UI based on available capabilities.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse

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
