"""Health check router."""

from __future__ import annotations

from fastapi import APIRouter

from trigen.api.models.schemas import HealthResponse
from trigen.api.services.agent_service import AgentService

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Health check endpoint, returning service status and Agent information."""
    agent = AgentService.get()
    return HealthResponse(
        status="ok",
        version="1.0.0",
        llm_configured=agent.llm_configured,
        sessions=agent.session_count,
        tools=agent.tool_count,
    )
