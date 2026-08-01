"""Agent router.

Exposes agent-level operations that sit outside the chat stream:
plan preview (no execution) and cooperative turn interruption.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from trigen.api.services.agent_service import AgentService

logger = logging.getLogger("trigen.api.agent")  # Agent router logger
router = APIRouter(tags=["agent"])  # Agent router


class PlanRequest(BaseModel):
    """Request body for the plan-only endpoint."""

    message: str = Field(..., description="User input to plan for")
    session_id: str = Field(default="default", description="Session ID")
    model: Optional[str] = Field(default=None, description="LLM model override")


class InterruptRequest(BaseModel):
    """Request body for the interrupt endpoint."""

    session_id: str = Field(..., description="Session ID to interrupt")


@router.post("/agent/plan")
async def agent_plan(req: PlanRequest) -> JSONResponse:
    """Produce a structured plan for ``message`` without executing any tools.

    Runs a single LLM pass, collects tool calls + reasoning, and returns
    the structured TaskPlan payload (goal / assumptions / risks / steps).
    The scene is NOT mutated and no tools fire — this is a preview.
    """
    agent = AgentService.get()
    try:
        result = await agent.orchestrator.plan_only(
            req.message, req.session_id, model=req.model
        )
    except Exception as e:
        logger.exception("agent/plan error")
        return JSONResponse(
            status_code=500,
            content={"error": str(e), "plan": None},
        )
    return JSONResponse(content=result)


@router.post("/agent/interrupt")
async def agent_interrupt(req: InterruptRequest) -> JSONResponse:
    """Request cancellation of the currently running turn for a session.

    The flag is consumed at the next iteration boundary of ``_run_turn``.
    Returns immediately; the running turn (if any) will emit an
    ``interrupted`` thinking event and then a ``done`` event.
    """
    agent = AgentService.get()
    agent.orchestrator.request_interrupt(req.session_id)
    return JSONResponse(
        content={
            "session_id": req.session_id,
            "interrupted": True,
            "note": "Interrupt will take effect at the next iteration boundary.",
        }
    )
