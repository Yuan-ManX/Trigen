"""Agent router.

Exposes agent-level operations that sit outside the chat stream:
plan preview (no execution), cooperative turn interruption, tool/skill
documentation, and multimodal image upload for chat input.
"""

from __future__ import annotations

import base64
import logging
import os
import time
import uuid
from typing import Any, Dict, Optional

from fastapi import APIRouter, UploadFile, File
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


class ExplainRequest(BaseModel):
    """Request body for the explain endpoint."""

    kind: str = Field(..., description="One of: 'tool' or 'skill'")
    name: str = Field(..., description="Tool or skill name to explain")


@router.post("/agent/plan")
async def agent_plan(req: PlanRequest) -> JSONResponse:
    """Produce a structured plan for ``message`` without executing any tools.

    Runs a single LLM pass, collects tool calls + reasoning, and returns
    the structured TaskPlan payload (goal / assumptions / risks / steps)
    plus per-step ``requires_approval`` flags and a ``has_destructive_steps``
    summary so the frontend can surface a confirmation dialog. The scene is
    NOT mutated and no tools fire — this is a preview. Falls back to the
    offline rule parser when no LLM is configured.
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


@router.post("/agent/explain")
async def agent_explain(req: ExplainRequest) -> JSONResponse:
    """Explain a tool or skill before running it.

    Returns the name, description, full parameter schema, and approval flag
    (for tools) so the frontend can render inline documentation and help the
    user understand what an Agent-proposed step will do. This is read-only
    and never mutates the scene.
    """
    kind = req.kind.lower()
    name = req.name.strip()
    if kind == "tool":
        agent = AgentService.get()
        for schema in agent.list_tools():
            if schema.get("name") == name:
                tool = agent.orchestrator.registry.get(name)
                approval = bool(getattr(tool, "requires_approval", False)) if tool else False
                return JSONResponse(content={
                    "kind": "tool",
                    "name": schema["name"],
                    "description": schema["description"],
                    "parameters": schema["parameters"],
                    "requires_approval": approval,
                })
        return JSONResponse(status_code=404, content={"error": f"Tool not found: {name}"})
    if kind == "skill":
        from trigen.skills import build_default_registry
        reg = build_default_registry()
        for schema in reg.schemas():
            if schema.get("name") == name:
                return JSONResponse(content={
                    "kind": "skill",
                    "name": schema["name"],
                    "description": schema["description"],
                    "category": schema.get("category", ""),
                    "parameters": schema["parameters"],
                })
        return JSONResponse(status_code=404, content={"error": f"Skill not found: {name}"})
    return JSONResponse(status_code=400, content={"error": f"kind must be 'tool' or 'skill', got {kind}"})


@router.post("/agent/upload/image")
async def agent_upload_image(file: UploadFile = File(...)) -> JSONResponse:
    """Accept an image upload for multimodal chat input.

    Persists the uploaded image under the workspace uploads directory and
    returns a ``media_id`` plus a data URL the frontend can preview and the
    chat flow can forward to a vision model or the img2threejs tool. Limits
    uploads to 8 MB and image MIME types.
    """
    allowed = {"image/png", "image/jpeg", "image/webp", "image/gif"}
    if file.content_type not in allowed:
        return JSONResponse(
            status_code=400,
            content={"error": f"Unsupported file type: {file.content_type}. Allowed: {sorted(allowed)}"},
        )
    data = await file.read()
    max_bytes = 8 * 1024 * 1024
    if len(data) > max_bytes:
        return JSONResponse(status_code=413, content={"error": "Image exceeds 8 MB limit"})
    agent = AgentService.get()
    uploads_dir = os.path.join(agent.config.workspace_dir, "uploads")
    os.makedirs(uploads_dir, exist_ok=True)
    ext = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp", "image/gif": "gif"}[file.content_type]
    media_id = f"img_{int(time.time())}_{uuid.uuid4().hex[:6]}"
    filename = f"{media_id}.{ext}"
    path = os.path.join(uploads_dir, filename)
    with open(path, "wb") as fh:
        fh.write(data)
    b64 = base64.b64encode(data).decode("ascii")
    data_url = f"data:{file.content_type};base64,{b64}"
    logger.info("Uploaded image %s (%d bytes) -> %s", media_id, len(data), path)
    return JSONResponse(content={
        "media_id": media_id,
        "filename": filename,
        "mime_type": file.content_type,
        "size": len(data),
        "data_url": data_url,
        "path": path,
    })


@router.get("/agent/status")
async def agent_status() -> JSONResponse:
    """Report agent capabilities and online/offline mode.

    Returns whether a conversational LLM is configured (online mode) or
    the agent is running on the offline rule engine, the list of
    available chat models, the fallback chain, and a capability summary
    (tool count, skill count, category list). The frontend uses this to
    render a mode indicator and disable LLM-dependent UI when offline.
    """
    agent = AgentService.get()
    orch = agent.orchestrator
    config = agent.config
    from trigen.llm.router import router as model_router

    available_chat_models = model_router.list_available_chat_models()
    # "online" requires a real LLM with credentials — trigen-default is the
    # offline rule engine, so exclude it from the online determination.
    real_chat_models = [m for m in available_chat_models if m != "trigen-default"]
    online = bool(real_chat_models) or config.llm.is_configured
    primary = None
    if config.llm.is_configured:
        primary = config.llm.model or None
    fallback_chain = model_router.build_fallback_chain(primary)
    # Filter the chain to models with credentials (mirror _find_available_alternative)
    usable_chain = [
        m for m in fallback_chain
        if m != "trigen-default"
        and not model_router.is_generation_model(m)
        and model_router.resolve(m).get("api_key")
    ]
    # Category summary
    grouped = orch.registry.categories()
    categories = [
        {"category": cat, "count": len(items)}
        for cat, items in sorted(grouped.items())
    ]
    # Skill count
    try:
        from trigen.skills import build_default_registry
        skill_count = len(build_default_registry().all())
    except Exception:
        skill_count = 0
    return JSONResponse(content={
        "online": online,
        "mode": "online" if online else "offline",
        "llm_configured": config.llm.is_configured,
        "primary_model": primary,
        "available_chat_models": available_chat_models,
        "fallback_chain": fallback_chain,
        "usable_fallback_chain": usable_chain,
        "capabilities": {
            "tools": len(orch.registry.all()),
            "skills": skill_count,
            "categories": categories,
            "total_categories": len(grouped),
        },
        "config": {
            "max_iterations": config.max_iterations,
            "memory_window": config.memory_window,
            "max_tokens_per_turn": config.max_tokens_per_turn,
        },
    })
