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


class DescribeSceneRequest(BaseModel):
    """Request body for the scene-description endpoint."""

    session_id: str = Field(default="default", description="Session ID whose scene to describe")
    focus: str = Field(
        default="all",
        description="Optional aspect to focus on: 'all' | 'layout' | 'palette' | 'lighting' | 'balance' | 'geometry'",
    )
    include_metrics: bool = Field(default=True, description="Include the structured metrics block")


class SuggestRequest(BaseModel):
    """Request body for the suggest-next-actions endpoint."""

    session_id: str = Field(default="default", description="Session ID whose scene to suggest for")
    count: Optional[int] = Field(default=None, description="Max suggestions to return (default 3, capped at 5)")
    direction: str = Field(
        default="any",
        description="Creative direction bias: 'any' | 'lighting' | 'motion' | 'material' | 'composition' | 'population'",
    )


class PinMemoryRequest(BaseModel):
    """Request body for the pin-fact endpoint."""

    text: str = Field(..., description="The fact text to pin (non-empty)")
    category: Optional[str] = Field(
        default=None,
        description="Optional category bucket (e.g. 'project', 'preference', 'constraint'). Defaults to 'general'.",
    )


class ForgetMemoryRequest(BaseModel):
    """Request body for the forget-fact endpoint."""

    text: Optional[str] = Field(
        default=None,
        description="If supplied, remove a single fact by case-insensitive exact match. If omitted, clear by category.",
    )
    category: Optional[str] = Field(
        default=None,
        description="When 'text' is omitted, clear every fact in this category (or all when also empty).",
    )


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


@router.post("/agent/plan/graph")
async def agent_plan_graph(req: PlanRequest) -> JSONResponse:
    """Plan-only preview enriched with the dependency DAG + critique + perception.

    Mirrors ``/agent/plan`` (single LLM pass, no execution, no scene
    mutation) but also returns:
      - ``graph``: the plan dependency DAG (``{nodes, edges, layers}``) for
        node-graph rendering. Each node carries ``status`` ("pending" here),
        ``dependencies``, ``tool``, ``label``, and ``arguments``.
      - ``critique``: pre-execution critique findings
        (``{summary, findings, pruned_step_ids}``) — advisory diagnostics
        for dead-after-delete, target-miss, redundant-repeat, and
        duplicate-create issues.
      - ``perception``: heuristic scene-perception findings
        (``{summary, findings, metrics}``) when the plan contains a
        multimodal 3D-generation step; ``null`` otherwise.

    The DAG node ``status`` is always ``"pending"`` at preview time; the
    frontend merges live ``plan_update`` transitions during a real run.
    """
    agent = AgentService.get()
    try:
        result = await agent.orchestrator.plan_graph(
            req.message, req.session_id, model=req.model
        )
    except Exception as e:
        logger.exception("agent/plan/graph error")
        return JSONResponse(
            status_code=500,
            content={
                "error": str(e),
                "plan": None,
                "graph": None,
                "critique": None,
                "perception": None,
            },
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


@router.post("/agent/describe_scene")
async def agent_describe_scene(req: DescribeSceneRequest) -> JSONResponse:
    """Generate a semantic description of the current scene.

    Resolves the session's scene, invokes the registered ``describe_scene``
    tool, and returns the natural-language description plus (optionally)
    the structured metrics block. Read-only — does not mutate the scene.
    Falls back to a fresh empty scene if the session is unknown.
    """
    agent = AgentService.get()
    tool = agent.orchestrator.registry.get("describe_scene")
    if tool is None:
        return JSONResponse(
            status_code=503,
            content={"error": "describe_scene tool is not registered"},
        )
    scene = agent.orchestrator.get_scene(req.session_id)
    args: Dict[str, Any] = {"focus": req.focus, "include_metrics": req.include_metrics}
    try:
        result = await tool.execute(scene, args)
    except Exception as e:
        logger.exception("agent/describe_scene error")
        return JSONResponse(status_code=500, content={"error": str(e)})
    if not result.success:
        return JSONResponse(status_code=500, content={"error": result.message})
    return JSONResponse(content=result.data)


@router.post("/agent/suggest")
async def agent_suggest(req: SuggestRequest) -> JSONResponse:
    """Propose actionable creative next steps for the current scene.

    Resolves the session's scene, invokes the registered
    ``suggest_next_actions`` tool, and returns the suggestion list. The
    count is capped at 5 by the tool. Read-only — does not mutate the
    scene. Falls back to a fresh empty scene if the session is unknown.
    """
    agent = AgentService.get()
    tool = agent.orchestrator.registry.get("suggest_next_actions")
    if tool is None:
        return JSONResponse(
            status_code=503,
            content={"error": "suggest_next_actions tool is not registered"},
        )
    scene = agent.orchestrator.get_scene(req.session_id)
    args: Dict[str, Any] = {"direction": req.direction}
    if req.count is not None:
        args["count"] = req.count
    try:
        result = await tool.execute(scene, args)
    except Exception as e:
        logger.exception("agent/suggest error")
        return JSONResponse(status_code=500, content={"error": str(e)})
    if not result.success:
        return JSONResponse(status_code=500, content={"error": result.message})
    return JSONResponse(content=result.data)


@router.get("/agent/memory")
async def agent_memory_get() -> JSONResponse:
    """Return the Agent's explicit (pinned) memory contents.

    Exposes the full episodic-memory dict (preferences, patterns,
    pinned_facts, last_updated) so the frontend MemoryPanel can render
    a live inspector. Read-only — does not mutate the store.
    """
    from trigen.episodic_memory import store as episodic_store

    try:
        mem = episodic_store.get()
        payload = mem.to_dict()
        payload["summary"] = {
            "total_facts": len(mem.pinned_facts),
            "categories": sorted({f.category for f in mem.pinned_facts}),
            "pattern_count": len(mem.patterns),
        }
        return JSONResponse(content=payload)
    except Exception as e:
        logger.exception("agent/memory GET error")
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.post("/agent/memory/pin")
async def agent_memory_pin(req: PinMemoryRequest) -> JSONResponse:
    """Pin a durable fact the Agent should remember across turns.

    Body: ``{text, category?}``. Deduplicates case-insensitively (refreshes
    the timestamp/category of an existing identical fact). Persists to the
    workspace episodic memory file. Returns the pinned fact and the new
    total fact count.
    """
    from trigen.episodic_memory import store as episodic_store

    text = (req.text or "").strip()
    if not text:
        return JSONResponse(
            status_code=400,
            content={"error": "'text' must be a non-empty string"},
        )
    category = (req.category or "general").strip().lower() or "general"
    try:
        mem = episodic_store.get()
        fact = mem.add_fact(text, category)
        episodic_store.save()
        return JSONResponse(content={
            "fact": fact.to_dict(),
            "total_facts": len(mem.pinned_facts),
        })
    except Exception as e:
        logger.exception("agent/memory/pin error")
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.delete("/agent/memory")
async def agent_memory_delete(req: ForgetMemoryRequest) -> JSONResponse:
    """Remove pinned fact(s) by text or by category.

    Body: ``{text?, category?}``. If ``text`` is supplied, remove a single
    matching fact (case-insensitive exact match) and return
    ``{removed: bool}``. Otherwise clear every fact in ``category`` (or
    all facts when ``category`` is also empty) and return the count
    removed. Persists the change to disk.
    """
    from trigen.episodic_memory import store as episodic_store

    text = (req.text or "").strip()
    category = (req.category or "").strip()
    try:
        mem = episodic_store.get()
        if text:
            removed = mem.remove_fact(text)
            if removed:
                episodic_store.save()
            return JSONResponse(content={
                "removed": removed,
                "text": text,
                "remaining": len(mem.pinned_facts),
            })
        cleared = mem.clear_facts(category or None)
        episodic_store.save()
        return JSONResponse(content={
            "removed": cleared,
            "category": category or None,
            "remaining": len(mem.pinned_facts),
        })
    except Exception as e:
        logger.exception("agent/memory DELETE error")
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.post("/agent/upload/image")
async def agent_upload_image(file: UploadFile = File(...)) -> JSONResponse:
    """Accept an image upload for multimodal chat input.

    Persists the uploaded image under the workspace uploads directory and
    returns a ``media_id`` plus a data URL the frontend can preview and the
    chat flow can forward to a vision model or the image-to-3D tool. Limits
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


@router.get("/agent/episodic")
async def agent_episodic_get() -> JSONResponse:
    """Return the cross-session episodic memory contents.

    Exposes the persisted preferences (preferred language, geometry,
    material preset, viewport, transform mode, render quality) and the
    successful plan-pattern cache so the frontend can render a memory
    inspector and the user can audit what the agent has learned. Read-only.
    """
    from trigen.episodic_memory import store as episodic_store

    try:
        mem = episodic_store.get()
        payload = mem.to_dict()
        # Surface a friendly preferences summary too so the frontend does
        # not have to re-derive the top-N values from the counters.
        payload["summary"] = {
            "language": mem._top("language"),
            "geometry_type": mem._top("geometry_type"),
            "material_preset": mem._top("material_preset"),
            "view": mem._top("view"),
            "transform_mode": mem._top("transform_mode"),
            "render_quality": mem._top("render_quality"),
        }
        payload["pattern_count"] = len(mem.patterns)
        return JSONResponse(content=payload)
    except Exception as e:
        logger.exception("agent/episodic GET error")
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.delete("/agent/episodic")
async def agent_episodic_delete() -> JSONResponse:
    """Wipe the cross-session episodic memory.

    Resets the in-memory store and removes the persisted JSON so subsequent
    sessions start fresh. Useful for privacy / debugging / starting over.
    """
    from trigen.episodic_memory import store as episodic_store

    try:
        episodic_store.reset()
        return JSONResponse(content={
            "reset": True,
            "note": "Episodic memory cleared; preferences and pattern cache wiped.",
        })
    except Exception as e:
        logger.exception("agent/episodic DELETE error")
        return JSONResponse(status_code=500, content={"error": str(e)})


# ---------------------------------------------------------------------------
# Macro registry REST surface — read/browse/delete user-defined macros.
# Definition and invocation happen via the agent tool flow (define_macro /
# invoke_macro); these endpoints exist so the frontend can render a macro
# browser and let users manage saved recipes without going through chat.
# ---------------------------------------------------------------------------


@router.get("/agent/macros")
async def agent_macros_get() -> JSONResponse:
    """Return all defined macros in the workspace.

    Each entry includes the name, description, ordered steps (tool +
    arguments), creation timestamp, and use count. Read-only.
    """
    from trigen.macros import macro_store

    try:
        collection = macro_store.get()
        items = [
            m.to_dict()
            for m in sorted(collection.macros.values(), key=lambda x: x.name)
        ]
        return JSONResponse(content={"macros": items, "count": len(items)})
    except Exception as e:
        logger.exception("agent/macros GET error")
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.delete("/agent/macros")
async def agent_macros_delete(name: str = "") -> JSONResponse:
    """Delete a single macro by name (query param ``name``).

    If ``name`` is empty or unknown, returns 404. On success the macro is
    removed from the in-memory store and the persisted JSON is rewritten.
    """
    from trigen.macros import macro_store

    try:
        normalized = name.strip().lower().replace(" ", "_")
        if not normalized:
            return JSONResponse(
                status_code=400,
                content={"error": "Query parameter 'name' is required"},
            )
        collection = macro_store.get()
        if normalized not in collection.macros:
            return JSONResponse(
                status_code=404,
                content={"error": f"Macro '{normalized}' not found"},
            )
        del collection.macros[normalized]
        macro_store.save()
        return JSONResponse(content={"deleted": True, "name": normalized})
    except Exception as e:
        logger.exception("agent/macros DELETE error")
        return JSONResponse(status_code=500, content={"error": str(e)})


# ---------------------------------------------------------------------------
# Scene-variant REST surface — read/browse/delete named scene snapshots.
# Save / load / randomize happen via the agent tool flow; these endpoints
# let the frontend render a variant browser and prune saved snapshots.
# ---------------------------------------------------------------------------


@router.get("/agent/variants")
async def agent_variants_get() -> JSONResponse:
    """Return all saved scene variants in the workspace.

    Each entry includes the name, full scene snapshot, parent variant,
    and creation timestamp. Read-only. The scene payloads can be large,
    so callers that only need the variant list should filter client-side.
    """
    from trigen.variants import variant_store

    try:
        collection = variant_store.get()
        items = [
            v.to_dict()
            for v in sorted(collection.variants.values(), key=lambda x: x.name)
        ]
        return JSONResponse(content={"variants": items, "count": len(items)})
    except Exception as e:
        logger.exception("agent/variants GET error")
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.delete("/agent/variants")
async def agent_variants_delete(name: str = "") -> JSONResponse:
    """Delete a single scene variant by name (query param ``name``).

    If ``name`` is empty or unknown, returns 404. On success the variant
    is removed from the in-memory store and the persisted JSON is rewritten.
    """
    from trigen.variants import variant_store

    try:
        normalized = name.strip().lower().replace(" ", "_")
        if not normalized:
            return JSONResponse(
                status_code=400,
                content={"error": "Query parameter 'name' is required"},
            )
        collection = variant_store.get()
        if normalized not in collection.variants:
            return JSONResponse(
                status_code=404,
                content={"error": f"Variant '{normalized}' not found"},
            )
        del collection.variants[normalized]
        variant_store.save()
        return JSONResponse(content={"deleted": True, "name": normalized})
    except Exception as e:
        logger.exception("agent/variants DELETE error")
        return JSONResponse(status_code=500, content={"error": str(e)})
