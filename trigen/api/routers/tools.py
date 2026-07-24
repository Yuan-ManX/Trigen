"""Tools and presets router / 工具与预设路由.

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
    """List all Agent-callable tools with their schemas.
    列出所有可被 Agent 调用的工具及其 schema。"""
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
    """List available geometry, material, and light presets.
    列出可用的几何、材质、灯光预设。"""
    agent = AgentService.get()
    presets = agent.list_presets()
    return PresetsResponse(
        geometry_types=presets["geometry_types"],
        material_presets=presets["material_presets"],
        light_types=presets["light_types"],
    )
