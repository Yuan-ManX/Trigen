"""Health check router / 健康检查路由."""

from __future__ import annotations

from fastapi import APIRouter

from trigen.api.models.schemas import HealthResponse
from trigen.api.services.agent_service import AgentService

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Health check endpoint, returning service status and Agent information.
    健康检查端点，返回服务状态与 Agent 信息。"""
    agent = AgentService.get()
    return HealthResponse(
        status="ok",
        version="1.0.0",
        llm_configured=agent.llm_configured,
        sessions=agent.session_count,
        tools=agent.tool_count,
    )
