"""Scene router."""

from __future__ import annotations

import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from trigen.api.services.agent_service import AgentService

logger = logging.getLogger("trigen.api.scene")  # Scene router logger
router = APIRouter(tags=["scene"])  # Scene router


@router.get("/scene/{session_id}")
async def get_scene(session_id: str) -> JSONResponse:
    """Get the full scene of the specified session."""
    agent = AgentService.get()
    scene = agent.get_scene(session_id)
    return JSONResponse(content={"session_id": session_id, **scene})


@router.post("/scene/{session_id}/reset")
async def reset_scene(session_id: str) -> JSONResponse:
    """Reset the scene and conversation of the specified session."""
    agent = AgentService.get()
    agent.reset_session(session_id)
    # Re-fetch the default scene after reset
    scene = agent.get_scene(session_id)
    return JSONResponse(content={"session_id": session_id, "reset": True, **scene})
