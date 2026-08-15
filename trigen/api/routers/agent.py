"""Agent router.

Exposes agent-level operations that sit outside the chat stream:
plan preview (no execution), cooperative turn interruption, tool/skill
documentation, multimodal image upload for chat input, batch tool
execution with streaming SSE progress, and plan-then-run execution.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import time
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, UploadFile, File
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from trigen.api.services.agent_service import AgentService
from trigen.scene import Scene

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


class RunToolRequest(BaseModel):
    """Request body for direct tool execution.

    Runs a single registered Agent tool against the session's scene with
    the supplied arguments, bypassing the LLM and the plan loop. This is
    the "Agent as remote control" surface: the frontend Command Palette
    and Quick Actions can invoke any editor capability directly. The scene
    is mutated in place and the updated snapshot is returned so the
    frontend can swap it in.
    """

    name: str = Field(..., description="Registered tool name to execute")
    session_id: str = Field(default="default", description="Session whose scene to run against")
    arguments: Dict[str, Any] = Field(
        default_factory=dict,
        description="Tool arguments (validated against the tool's own schema)",
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


@router.post("/agent/run")
async def agent_run(req: RunToolRequest) -> JSONResponse:
    """Execute a single registered Agent tool directly against the scene.

    Body: ``{name, session_id?, arguments?}``. Resolves the tool, validates
    its arguments against the tool's own JSON schema, and runs it in place
    against the session's scene. Returns ``{result, scene, tool_call}``:
    the tool result payload, the mutated scene snapshot, and a tool_call
    record shaped like the streaming event so the frontend can render it
    uniformly. This is the direct-execution path used by the Command
    Palette — it bypasses the LLM and the plan loop entirely. Unknown
    tools return 404; a failed tool returns 422 with its message.
    """
    agent = AgentService.get()
    name = (req.name or "").strip()
    if not name:
        return JSONResponse(status_code=400, content={"error": "tool name is required"})
    tool = agent.orchestrator.registry.get(name)
    if tool is None:
        return JSONResponse(
            status_code=404,
            content={"error": f"Tool not registered: {name}"},
        )
    scene = agent.orchestrator.get_scene(req.session_id)
    args = dict(req.arguments or {})
    # Coerce argument types to match the tool schema before execution so
    # JSON payloads (all numbers are floats) map cleanly to integer params.
    try:
        schema = tool.schema()
        props = schema.get("properties", {}) if isinstance(schema, dict) else {}
        for key, value in list(args.items()):
            if value is None:
                args.pop(key, None)
                continue
            prop = props.get(key) or {}
            typ = prop.get("type")
            if typ == "integer" and isinstance(value, float) and value.is_integer():
                args[key] = int(value)
            elif typ == "boolean" and not isinstance(value, bool):
                args[key] = bool(value)
    except Exception:
        # Schema coercion is advisory; never block execution on it.
        logger.debug("agent/run schema coercion skipped for %s", name)
    try:
        result = await tool.execute(scene, args)
    except Exception as e:
        logger.exception("agent/run error executing %s", name)
        return JSONResponse(status_code=500, content={"error": str(e)})
    if not result.success:
        return JSONResponse(
            status_code=422,
            content={"error": result.message, "tool": name},
        )
    result_payload = result.to_dict() if hasattr(result, "to_dict") else {"message": result.message}
    deltas = getattr(result, "deltas", None) or []

    def _delta_dict(d):
        if hasattr(d, "to_dict"):
            return d.to_dict()
        if hasattr(d, "__dict__"):
            return d.__dict__
        return d

    tool_call = {
        "type": "tool_call",
        "name": name,
        "arguments": args,
        "result": result_payload,
        "deltas": [_delta_dict(d) for d in deltas],
        "direct": True,
        "ts": time.time(),
    }
    return JSONResponse(content={
        "session_id": req.session_id,
        "tool": name,
        "result": result_payload,
        "scene": scene.to_dict(),
        "tool_call": tool_call,
    })


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


# ---------------------------------------------------------------------------
# Scene-awareness polling — combined context endpoint that bundles the
# scene context analysis, agent state, and recent memory so the frontend
# can poll a single route to drive its scene-awareness UI. Also exposes
# a path-param suggest endpoint that returns proactive suggestions.
# ---------------------------------------------------------------------------


@router.get("/agent/context/{session_id}")
async def agent_context_get(
    session_id: str,
    memory_limit: int = 10,
) -> JSONResponse:
    """Return the scene context, agent state, and recent memory in one call.

    A combined polling endpoint for the frontend's scene-awareness UI.
    Bundles three blocks so a single round-trip is enough to render the
    current scene analysis (object/light counts, complexity, missing
    elements, suggested focus), the agent's online/offline mode, and the
    most recent conversation messages for the session. Read-only — does
    not mutate the scene or memory.

    ``memory_limit`` caps the number of recent messages returned (default
    10, capped at 50 to keep the payload small).
    """
    agent = AgentService.get()
    orch = agent.orchestrator
    config = agent.config
    scene = orch.get_scene(session_id)

    # --- scene context block (mirrors GET /scene/{session_id}/context) ---
    try:
        scene_context = orch._build_scene_context(scene)
    except Exception as e:
        logger.exception("agent/context scene analysis failed for session %s", session_id)
        scene_context = {"error": str(e)}

    # --- agent state block (lightweight subset of GET /agent/status) ---
    try:
        from trigen.llm.router import router as model_router

        available_chat_models = model_router.list_available_chat_models()
        real_chat_models = [m for m in available_chat_models if m != "trigen-default"]
        online = bool(real_chat_models) or config.llm.is_configured
        primary = None
        if config.llm.is_configured:
            primary = config.llm.model or None
    except Exception:
        online = config.llm.is_configured
        primary = None
        available_chat_models = []
    agent_state = {
        "online": online,
        "mode": "online" if online else "offline",
        "llm_configured": config.llm.is_configured,
        "primary_model": primary,
        "available_chat_models": available_chat_models,
    }

    # --- recent memory block (mirrors GET /chat/sessions/{id}/memory) ---
    recent_messages: list = []
    compacted_summary: str = ""
    message_count = 0
    try:
        from trigen.memory_persistence import persistence as memory_persistence

        memory = memory_persistence.load(session_id)
        if memory is not None:
            message_count = len(memory._messages)
            compacted_summary = memory._compacted_summary or ""
            cap = max(0, min(int(memory_limit), 50))
            recent = memory._messages[-cap:] if cap else []
            recent_messages = [
                {
                    "role": m.role,
                    "content": m.content,
                    "timestamp": m.timestamp,
                    "tool_name": m.tool_name,
                }
                for m in recent
            ]
    except Exception:
        logger.exception("agent/context memory load failed for session %s", session_id)

    return JSONResponse(content={
        "session_id": session_id,
        "scene_context": scene_context,
        "agent_state": agent_state,
        "memory": {
            "message_count": message_count,
            "compacted_summary": compacted_summary,
            "recent": recent_messages,
        },
    })


@router.post("/agent/suggest/{session_id}")
async def agent_suggest_for_scene(
    session_id: str,
    count: int = 3,
    direction: str = "any",
) -> JSONResponse:
    """Return proactive suggestions for the current scene state.

    Combines the orchestrator's ``_proactive_suggest`` (context-gap-based
    suggestions) with the registered ``suggest_next_actions`` tool's
    direction-aware suggestions so the frontend gets a single merged list
    from one POST. ``count`` caps the merged list (default 3). ``direction``
    biases the tool-side suggestions (lighting / motion / material /
    composition / population). Read-only — does not mutate the scene.
    """
    agent = AgentService.get()
    orch = agent.orchestrator
    scene = orch.get_scene(session_id)

    # Gap-based suggestions from the orchestrator's scene-awareness helper.
    try:
        context = orch._build_scene_context(scene)
        gap_suggestions = orch._proactive_suggest(scene, context, context, [])
    except Exception:
        logger.exception("agent/suggest proactive_suggest failed for session %s", session_id)
        context = {}
        gap_suggestions = []

    # Direction-aware suggestions from the suggest_next_actions tool.
    tool_suggestions: list = []
    tool = orch.registry.get("suggest_next_actions")
    if tool is not None:
        try:
            args: Dict[str, Any] = {"direction": direction}
            if count is not None:
                args["count"] = count
            result = await tool.execute(scene, args)
            if result.success:
                data = getattr(result, "data", None) or {}
                tool_suggestions = data.get("suggestions") or []
        except Exception:
            logger.exception("agent/suggest suggest_next_actions failed for session %s", session_id)

    # Merge, de-duping by suggestion name when both sources overlap.
    merged: list = []
    seen_names: set = set()
    for sug in list(gap_suggestions) + list(tool_suggestions):
        if not isinstance(sug, dict):
            continue
        name = sug.get("name") or sug.get("title") or ""
        if name and name in seen_names:
            continue
        if name:
            seen_names.add(name)
        merged.append(sug)

    cap = max(1, min(int(count) if count else 3, 10))
    merged = merged[:cap]

    return JSONResponse(content={
        "session_id": session_id,
        "suggestions": merged,
        "count": len(merged),
        "direction": direction,
        "context": context,
        "sources": {
            "gap_based": len(gap_suggestions),
            "tool_based": len(tool_suggestions),
        },
    })


# ---------------------------------------------------------------------------
# Unified Workspace bootstrap — single call that bundles everything the
# frontend needs on initial load: live scene, agent online/offline status
# + capability summary, tool catalog grouped by category, creative skill
# list, recent per-turn reflections, and saved Agentic Workflow Templates.
# Removing N round-trips on startup smooths first-paint and lets the UI
# render every right-panel tab from one payload.
# ---------------------------------------------------------------------------


@router.get("/agent/workspace")
async def agent_workspace_get(
    session_id: str = "default",
    reflection_limit: Optional[int] = 10,
) -> JSONResponse:
    """Bootstrap the full workspace state in one call.

    Bundles ``scene``, ``agent_status``, ``tool_categories``, ``skills``,
    ``recent_reflections`` and ``workflows`` so the frontend can render
    every panel from a single fetch on initial load. Each block mirrors
    the shape returned by its dedicated endpoint, so callers can also
    fetch any subset individually afterwards.
    """
    try:
        agent = AgentService.get()
        orch = agent.orchestrator
        config = agent.config

        # --- scene block (mirrors GET /scene/{session_id}) ---
        scene = agent.get_scene(session_id)
        history = orch.history_status(session_id)
        scene_block = {"session_id": session_id, **scene, "history": history}

        # --- agent_status block (mirrors GET /agent/status) ---
        from trigen.llm.router import router as model_router

        available_chat_models = model_router.list_available_chat_models()
        real_chat_models = [m for m in available_chat_models if m != "trigen-default"]
        online = bool(real_chat_models) or config.llm.is_configured
        primary = None
        if config.llm.is_configured:
            primary = config.llm.model or None
        fallback_chain = model_router.build_fallback_chain(primary)
        usable_chain = [
            m for m in fallback_chain
            if m != "trigen-default"
            and not model_router.is_generation_model(m)
            and model_router.resolve(m).get("api_key")
        ]
        grouped = orch.registry.categories()
        categories_summary = [
            {"category": cat, "count": len(items)}
            for cat, items in sorted(grouped.items())
        ]
        try:
            from trigen.skills import build_default_registry
            skill_count = len(build_default_registry().all())
        except Exception:
            skill_count = 0
        agent_status_block = {
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
                "categories": categories_summary,
                "total_categories": len(grouped),
            },
            "config": {
                "max_iterations": config.max_iterations,
                "memory_window": config.memory_window,
                "max_tokens_per_turn": config.max_tokens_per_turn,
            },
        }

        # --- tool_categories block (mirrors GET /tools/categories) ---
        tool_categories_block = {
            "categories": grouped,
            "summary": categories_summary,
            "total_categories": len(grouped),
            "total_tools": sum(len(items) for items in grouped.values()),
        }

        # --- skills block (mirrors GET /skills) ---
        try:
            from trigen.skills import build_default_registry
            skills_block = {
                "skills": [s.to_dict() for s in build_default_registry().all()],
                "count": skill_count,
            }
        except Exception:
            skills_block = {"skills": [], "count": 0}

        # --- recent_reflections block (mirrors GET /agent/reflection/{id}) ---
        try:
            from trigen.reflection import reflection_store
            reflections = reflection_store.get(session_id, limit=reflection_limit)
            reflection_summary = reflection_store.summary(session_id)
        except Exception:
            reflections = []
            reflection_summary = {}
        recent_reflections_block = {
            "reflections": reflections,
            "summary": reflection_summary,
        }

        # --- workflows block (mirrors GET /agent/workflows) ---
        try:
            from trigen.workflows import workflow_store
            wf_collection = workflow_store.get()
            wf_items = [
                w.to_dict()
                for w in sorted(wf_collection.workflows.values(), key=lambda x: x.name)
            ]
        except Exception:
            wf_items = []
        workflows_block = {"workflows": wf_items, "count": len(wf_items)}

        return JSONResponse(content={
            "session_id": session_id,
            "scene": scene_block,
            "agent_status": agent_status_block,
            "tool_categories": tool_categories_block,
            "skills": skills_block,
            "recent_reflections": recent_reflections_block,
            "workflows": workflows_block,
        })
    except Exception as e:
        logger.exception("agent/workspace GET error")
        return JSONResponse(status_code=500, content={"error": str(e)})


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
# Agent trace REST surface — per-session event replay for inspection.
# The trace store is populated by ``AgentService.chat_stream`` recording
# every streamed AgentEvent. These endpoints let the frontend render a
# turn-by-turn activity timeline / debugger without consuming the WS stream.
# ---------------------------------------------------------------------------


@router.get("/agent/trace/{session_id}")
async def agent_trace_get(
    session_id: str,
    limit: Optional[int] = None,
    since_seq: Optional[int] = None,
) -> JSONResponse:
    """Return the recorded event trace for ``session_id``.

    The trace is a bounded, in-memory ring buffer of every AgentEvent
    streamed through ``chat_stream`` for this session, each tagged with a
    ``turn`` marker (incremented after each ``done`` event). Optional
    query params:

    * ``limit`` — return only the most recent ``limit`` entries (capped at
      the buffer size). Useful for an initial "tail" view.
    * ``since_seq`` — return only entries whose ``seq`` is strictly greater
      than the supplied value, enabling incremental polling.

    The response also includes a ``summary`` block (entry count, turn
    count, last seq, first/last timestamps) so the frontend can render a
    status header without a second round-trip. Returns an empty entry
    list (not 404) for unknown sessions — a session with no recorded
    activity is a valid state.
    """
    from trigen.agent_trace import trace_store

    try:
        # Cap limit to the store's max to avoid huge payloads; negative
        # limits are treated as "no limit".
        cap = trace_store.max_per_session
        eff_limit: Optional[int] = None
        if limit is not None:
            if limit < 0:
                eff_limit = None
            else:
                eff_limit = min(limit, cap)
        entries = trace_store.get(session_id, limit=eff_limit, since_seq=since_seq)
        summary = trace_store.summary(session_id)
        return JSONResponse(content={
            "session_id": session_id,
            "entries": entries,
            "count": len(entries),
            "summary": summary,
        })
    except Exception as e:
        logger.exception("agent/trace GET error")
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.get("/agent/trace")
async def agent_trace_sessions() -> JSONResponse:
    """List every session that has a non-empty trace.

    Returns a ``sessions`` array of summary objects (session_id, count,
    turn, last_seq, first/last timestamps). Intended for a trace-browser
    or debug dashboard so the user can pick a session to inspect.
    """
    from trigen.agent_trace import trace_store

    try:
        sessions = trace_store.sessions()
        return JSONResponse(content={
            "sessions": sessions,
            "count": len(sessions),
        })
    except Exception as e:
        logger.exception("agent/trace sessions GET error")
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.delete("/agent/trace/{session_id}")
async def agent_trace_delete(session_id: str) -> JSONResponse:
    """Clear the recorded trace for one session.

    Removes every entry for ``session_id`` from the in-memory ring buffer
    and resets that session's turn / last-seq counters. Returns the number
    of entries removed. The trace store is not persisted, so a server
    restart has the same effect globally.
    """
    from trigen.agent_trace import trace_store

    try:
        removed = trace_store.clear(session_id)
        return JSONResponse(content={
            "session_id": session_id,
            "removed": removed,
        })
    except Exception as e:
        logger.exception("agent/trace DELETE error")
        return JSONResponse(status_code=500, content={"error": str(e)})


# ---------------------------------------------------------------------------
# Agent reflection REST surface — durable per-turn self-assessment.
# Drawn from the same stream as the trace: each completed turn's narrative
# reflection is folded into a structured record by ``chat_stream``. These
# endpoints let the frontend surface "what the Agent thinks it just did"
# and let the ``reflect_on_session`` tool ground responses in past turns.
# ---------------------------------------------------------------------------


@router.get("/agent/reflection/{session_id}")
async def agent_reflection_get(
    session_id: str,
    limit: Optional[int] = None,
) -> JSONResponse:
    """Return the recorded turn reflections for ``session_id``.

    Each entry is a structured record of one completed turn: ``goal`` (the
    user's message), ``tool_calls`` (the distinct tools that ran), ``outcome``
    (the orchestrator's narrative self-assessment), ``quality`` (the score /
    verdict block), ``elapsed``, and ``ts``. Entries are newest-first;
    ``limit`` caps the number returned. Returns an empty list (not 404) for
    unknown sessions — no reflections yet is a valid state.
    """
    from trigen.reflection import reflection_store

    try:
        entries = reflection_store.get(session_id, limit=limit)
        summary = reflection_store.summary(session_id)
        return JSONResponse(content={
            "session_id": session_id,
            "reflections": entries,
            "summary": summary,
        })
    except Exception as e:
        logger.exception("agent/reflection GET error")
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.delete("/agent/reflection/{session_id}")
async def agent_reflection_delete(session_id: str) -> JSONResponse:
    """Clear the recorded reflections for one session (or all when
    ``session_id`` is the literal ``"all"``)."""
    from trigen.reflection import reflection_store

    try:
        removed = reflection_store.clear(session_id)
        return JSONResponse(content={
            "session_id": session_id,
            "removed": removed,
        })
    except Exception as e:
        logger.exception("agent/reflection DELETE error")
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
# Agentic Workflow Templates REST surface — read/browse/delete saved
# tool-graph recipes. Save / invoke happen via the agent tool flow
# (save_workflow / invoke_workflow); these endpoints let the frontend
# render a workflow browser and prune saved recipes.
# ---------------------------------------------------------------------------


@router.get("/agent/workflows")
async def agent_workflows_get() -> JSONResponse:
    """Return all saved Agentic Workflow Templates in the workspace.

    Each entry includes the name, description, ordered steps (tool +
    arguments), creation timestamp, and use count. Read-only.
    """
    from trigen.workflows import workflow_store

    try:
        collection = workflow_store.get()
        items = [
            w.to_dict()
            for w in sorted(collection.workflows.values(), key=lambda x: x.name)
        ]
        return JSONResponse(content={"workflows": items, "count": len(items)})
    except Exception as e:
        logger.exception("agent/workflows GET error")
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.delete("/agent/workflows")
async def agent_workflows_delete(name: str = "") -> JSONResponse:
    """Delete a single Agentic Workflow Template by name (query param ``name``).

    If ``name`` is empty or unknown, returns 404. On success the workflow
    is removed from the in-memory store and the persisted JSON is rewritten.
    """
    from trigen.workflows import workflow_store

    try:
        normalized = name.strip().lower().replace(" ", "_")
        if not normalized:
            return JSONResponse(
                status_code=400,
                content={"error": "Query parameter 'name' is required"},
            )
        collection = workflow_store.get()
        if normalized not in collection.workflows:
            return JSONResponse(
                status_code=404,
                content={"error": f"Workflow '{normalized}' not found"},
            )
        del collection.workflows[normalized]
        workflow_store.save()
        return JSONResponse(content={"deleted": True, "name": normalized})
    except Exception as e:
        logger.exception("agent/workflows DELETE error")
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


# ---------------------------------------------------------------------------
# Scene checkpoint REST surface — persistent, revisioned version history.
# The store is populated by the checkpoint_scene tool (and the POST below);
# these endpoints let the frontend render a version-history timeline, create
# a new revision from the current scene, restore any revision, and diff two
# revisions without going through chat.
# ---------------------------------------------------------------------------


class CheckpointCreateRequest(BaseModel):
    """Request body for creating a scene checkpoint from the current scene."""

    session_id: str = Field(default="default", description="Session whose scene to snapshot")
    description: str = Field(default="", description="Optional human-readable label")


@router.get("/agent/checkpoints")
async def agent_checkpoints_get(limit: int = -1) -> JSONResponse:
    """List the scene's checkpoint history, newest-first.

    Each entry includes the revision number, description, semantic summary
    (geometry counts, palette, light rig), creation timestamp, and creator.
    The heavy scene payload is omitted for the list. ``limit`` caps the
    number of entries returned (negative = all).
    """
    from trigen.checkpoints import checkpoint_store

    try:
        history = checkpoint_store.get()
        cps = sorted(history.checkpoints, key=lambda c: c.revision, reverse=True)
        if limit >= 0:
            cps = cps[:limit] if limit else []
        items = [
            {
                "revision": c.revision,
                "description": c.description,
                "created_at": c.created_at,
                "created_by": c.created_by,
                "summary": c.summary,
            }
            for c in cps
        ]
        return JSONResponse(content={
            "checkpoints": items,
            "count": len(items),
            "total": len(history.checkpoints),
            "next_revision": history._next_revision,
        })
    except Exception as e:
        logger.exception("agent/checkpoints GET error")
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.post("/agent/checkpoints")
async def agent_checkpoints_create(req: CheckpointCreateRequest) -> JSONResponse:
    """Capture the current scene as a new immutable revision.

    The scene for ``session_id`` is snapshotted and appended to the history
    with the next revision number. A semantic summary is auto-generated.
    Returns the new revision's metadata plus the full scene snapshot.
    """
    from trigen.checkpoints import build_scene_summary, checkpoint_store
    from trigen.checkpoints import SceneCheckpoint

    try:
        service = AgentService.get()
        orch = service.orchestrator
        scene = orch.get_scene(req.session_id)
        scene_dict = scene.to_dict()
        summary = build_scene_summary(scene_dict)
        history = checkpoint_store.get()
        revision = history._next_revision
        history.checkpoints.append(
            SceneCheckpoint(
                revision=revision,
                scene_dict=scene_dict,
                description=req.description.strip(),
                summary=summary,
            )
        )
        history._next_revision = revision + 1
        checkpoint_store.save()
        return JSONResponse(content={
            "revision": revision,
            "description": req.description.strip(),
            "summary": summary,
            "scene": scene_dict,
            "total": len(history.checkpoints),
        })
    except Exception as e:
        logger.exception("agent/checkpoints POST error")
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.post("/agent/checkpoints/{revision}/restore")
async def agent_checkpoints_restore(revision: int, session_id: str = "default") -> JSONResponse:
    """Restore the live scene to a checkpoint revision.

    The scene for ``session_id`` is swapped in place (lossless) to the given
    revision. Checkpoints are immutable, so later revisions are preserved.
    Returns the restored scene snapshot plus the revision metadata.
    """
    from trigen.checkpoints import checkpoint_store

    try:
        history = checkpoint_store.get()
        target = next((c for c in history.checkpoints if c.revision == revision), None)
        if target is None:
            return JSONResponse(
                status_code=404,
                content={
                    "error": f"Checkpoint revision {revision} not found",
                    "available": sorted(c.revision for c in history.checkpoints),
                },
            )
        service = AgentService.get()
        orch = service.orchestrator
        scene = orch.get_scene(session_id)
        restored = Scene.from_dict(target.scene_dict)
        scene.__dict__.clear()
        scene.__dict__.update(restored.__dict__)
        return JSONResponse(content={
            "revision": target.revision,
            "description": target.description,
            "summary": target.summary,
            "scene": scene.to_dict(),
        })
    except Exception as e:
        logger.exception("agent/checkpoints restore error")
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.get("/agent/checkpoints/diff")
async def agent_checkpoints_diff(revision_a: int, revision_b: int) -> JSONResponse:
    """Diff two checkpoint revisions.

    Returns added / removed / changed object lists with ids and names, plus
    high-level counts, so the frontend can render a concise version-comparison.
    """
    from trigen.checkpoints import checkpoint_store, diff_checkpoint_scenes

    try:
        history = checkpoint_store.get()
        by_rev = {c.revision: c for c in history.checkpoints}
        ca = by_rev.get(revision_a)
        cb = by_rev.get(revision_b)
        if ca is None or cb is None:
            missing = [r for r in (revision_a, revision_b) if r not in by_rev]
            return JSONResponse(
                status_code=404,
                content={"error": f"Missing checkpoint revision(s): {missing}"},
            )
        diff = diff_checkpoint_scenes(ca.scene_dict, cb.scene_dict)
        return JSONResponse(content={
            "revision_a": revision_a,
            "revision_b": revision_b,
            **diff,
        })
    except Exception as e:
        logger.exception("agent/checkpoints diff error")
        return JSONResponse(status_code=500, content={"error": str(e)})


# ---------------------------------------------------------------------------
# Cinematic storyboard endpoints
# ---------------------------------------------------------------------------


class StoryComposeRequest(BaseModel):
    """Request body for composing/updating the cinematic storyboard."""

    session_id: str = Field(default="default", description="Session whose scene holds the storyboard")
    title: str = Field(default="Untitled scene", description="Short title for the sequence")
    shots: list = Field(default_factory=list, description="Ordered list of shot dictionaries")
    loop: bool = Field(default=True, description="Loop the sequence forever")


class StoryPlayRequest(BaseModel):
    """Request body for controlling storyboard playback."""

    session_id: str = Field(default="default", description="Session whose scene holds the storyboard")
    mode: str = Field(default="play", description="play / pause / stop")
    speed: Optional[float] = Field(default=None, description="Playback speed multiplier")
    index: Optional[int] = Field(default=None, description="Shot index to jump to (0-based)")


def _story_response(scene: Scene) -> Dict[str, Any]:
    """Snapshot the storyboard into a response payload."""
    sb = scene.storyboard
    if sb is None:
        return {"storyboard": None, "shots": [], "total_duration": 0.0}
    from trigen.storyboard import total_duration

    return {
        "storyboard": sb,
        "shots": sb.get("shots", []),
        "total_duration": total_duration(sb),
    }


@router.get("/agent/story")
async def agent_story_get(session_id: str = "default") -> JSONResponse:
    """Read the scene's cinematic storyboard.

    Returns the storyboard (title, shots, playback state) plus the total
    sequence duration. Never mutates the scene.
    """
    try:
        orch = AgentService.get().orchestrator
        scene = orch.get_scene(session_id)
        return JSONResponse(content={"session_id": session_id, **_story_response(scene)})
    except Exception as e:
        logger.exception("agent/story GET error")
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.post("/agent/story")
async def agent_story_compose(req: StoryComposeRequest) -> JSONResponse:
    """Compose or replace the scene's cinematic storyboard.

    Normalizes each shot (camera position, look-at target, fov, duration,
    easing) and stores the sequence on the scene. Returns the new storyboard
    plus the full scene snapshot so the frontend can swap it in.
    """
    from trigen.storyboard import new_storyboard

    try:
        if not isinstance(req.shots, list) or len(req.shots) == 0:
            return JSONResponse(status_code=400, content={"error": "At least one shot is required"})
        orch = AgentService.get().orchestrator
        scene = orch.get_scene(req.session_id)
        scene.storyboard = new_storyboard(req.title or "Untitled scene", req.shots, loop=req.loop)
        return JSONResponse(content={
            "session_id": req.session_id,
            **_story_response(scene),
            "scene": scene.to_dict(),
        })
    except Exception as e:
        logger.exception("agent/story compose error")
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.delete("/agent/story")
async def agent_story_clear(session_id: str = "default") -> JSONResponse:
    """Remove the scene's cinematic storyboard."""
    try:
        orch = AgentService.get().orchestrator
        scene = orch.get_scene(session_id)
        cleared = scene.storyboard is not None
        scene.storyboard = None
        return JSONResponse(content={
            "session_id": session_id,
            "cleared": cleared,
            **_story_response(scene),
        })
    except Exception as e:
        logger.exception("agent/story clear error")
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.post("/agent/story/play")
async def agent_story_play(req: StoryPlayRequest) -> JSONResponse:
    """Control storyboard playback (play / pause / stop).

    Playback state is stored on the storyboard so the frontend camera rig
    can drive itself. Optionally set the speed and starting shot index.
    """
    try:
        orch = AgentService.get().orchestrator
        scene = orch.get_scene(req.session_id)
        sb = scene.storyboard
        if sb is None:
            return JSONResponse(status_code=404, content={"error": "No storyboard composed yet"})
        if req.mode == "play":
            sb["playing"] = True
        elif req.mode == "pause":
            sb["playing"] = False
        elif req.mode == "stop":
            sb["playing"] = False
            sb["index"] = 0
        else:
            return JSONResponse(status_code=400, content={"error": "mode must be play/pause/stop"})
        if req.speed is not None:
            sb["speed"] = max(0.25, min(4.0, float(req.speed)))
        if req.index is not None and 0 <= int(req.index) < len(sb["shots"]):
            sb["index"] = int(req.index)
        return JSONResponse(content={
            "session_id": req.session_id,
            "playing": sb["playing"],
            **_story_response(scene),
        })
    except Exception as e:
        logger.exception("agent/story play error")
        return JSONResponse(status_code=500, content={"error": str(e)})


# ---------------------------------------------------------------------------
# Batch tool execution with streaming SSE progress + plan-then-run execution.
# These endpoints turn the Agent into a programmable remote control: the
# frontend Command Palette (or any external orchestrator) can submit an
# ordered list of tool calls and receive per-step progress events over SSE,
# or submit a natural-language message and watch the Agent plan it and then
# execute each planned step with live status. Both endpoints mutate the
# scene in place and stream a final ``done`` event carrying the full scene
# snapshot so the client can swap it in atomically.
# ---------------------------------------------------------------------------


class BatchStep(BaseModel):
    """A single tool call inside a batch execution request."""

    name: str = Field(..., description="Registered tool name to execute")
    arguments: Dict[str, Any] = Field(
        default_factory=dict,
        description="Tool arguments validated against the tool's schema.",
    )


class BatchRequest(BaseModel):
    """Request body for the batch tool-execution endpoint.

    Runs an ordered list of tool calls against the session's scene. Each
    step sees the scene as the previous step left it, so a batch can chain
    create -> transform -> material -> animate in one request. ``stop_on_error``
    (default true) aborts the batch on the first failing step; when false,
    failures are recorded and execution continues with the next step.
    """

    session_id: str = Field(default="default", description="Session whose scene to run against")
    steps: List[BatchStep] = Field(..., description="Ordered tool calls to execute")
    stop_on_error: bool = Field(default=True, description="Abort the batch on the first failing step")


class PlanRunRequest(BaseModel):
    """Request body for the plan-then-run endpoint.

    Submits a natural-language message, asks the Agent to plan it (single
    LLM pass, or the offline rule parser when no LLM is configured), and
    then executes each planned tool call in order with live SSE progress.
    ``auto_approve`` (default true) runs every step without prompting;
    when false the stream pauses after ``plan_ready`` and waits for the
    client to POST ``/agent/plan/run/confirm`` with the run_id (not yet
    wired — currently auto_approve=false still runs but emits an
    ``approval_skipped`` notice so the client can surface it).
    """

    message: str = Field(..., description="User input to plan and execute")
    session_id: str = Field(default="default", description="Session ID")
    model: Optional[str] = Field(default=None, description="LLM model override")
    auto_approve: bool = Field(default=True, description="Run every planned step without prompting")


def _coerce_tool_args(tool: Any, args: Dict[str, Any]) -> Dict[str, Any]:
    """Coerce JSON argument types to match the tool schema (advisory)."""
    out = dict(args or {})
    try:
        schema = tool.schema()
        props = schema.get("properties", {}) if isinstance(schema, dict) else {}
        for key, value in list(out.items()):
            if value is None:
                out.pop(key, None)
                continue
            prop = props.get(key) or {}
            typ = prop.get("type")
            if typ == "integer" and isinstance(value, float) and value.is_integer():
                out[key] = int(value)
            elif typ == "boolean" and not isinstance(value, bool):
                out[key] = bool(value)
    except Exception:
        logger.debug("schema coercion skipped for %s", getattr(tool, "name", "?"))
    return out


def _delta_dict(d: Any) -> Any:
    if hasattr(d, "to_dict"):
        return d.to_dict()
    if hasattr(d, "__dict__"):
        return d.__dict__
    return d


async def _execute_single_tool(
    agent: Any,
    name: str,
    session_id: str,
    raw_args: Dict[str, Any],
) -> Dict[str, Any]:
    """Resolve and run one tool, returning a structured result dict.

    Mirrors the validation + coercion + execution path of ``/agent/run``
    so batch and single-shot produce identical tool_call payloads.
    """
    tool = agent.orchestrator.registry.get(name)
    if tool is None:
        return {
            "success": False,
            "error": f"Tool not registered: {name}",
            "status_code": 404,
        }
    scene = agent.orchestrator.get_scene(session_id)
    args = _coerce_tool_args(tool, raw_args)
    try:
        result = await tool.execute(scene, args)
    except Exception as e:  # noqa: BLE001 — surface every tool error to the client
        logger.exception("batch step %s raised", name)
        return {
            "success": False,
            "error": str(e),
            "status_code": 500,
        }
    result_payload = result.to_dict() if hasattr(result, "to_dict") else {"message": result.message}
    deltas = getattr(result, "deltas", None) or []
    return {
        "success": result.success,
        "message": result.message,
        "result": result_payload,
        "deltas": [_delta_dict(d) for d in deltas],
        "tool_call": {
            "type": "tool_call",
            "name": name,
            "arguments": args,
            "result": result_payload,
            "deltas": [_delta_dict(d) for d in deltas],
            "direct": True,
            "ts": time.time(),
        },
        "status_code": 422 if not result.success else 200,
    }


@router.post("/agent/batch")
async def agent_batch(req: BatchRequest) -> EventSourceResponse:
    """Execute an ordered list of tool calls with streaming SSE progress.

    Emits one ``step_start`` event before each step, one ``step_result``
    event after each step (carrying the tool_call payload and deltas),
    and a final ``batch_done`` event with the summary + full scene
    snapshot. When ``stop_on_error`` is true and a step fails, the stream
    emits ``batch_error`` and terminates early. Each event's ``data`` is
    a JSON string so any SSE client can parse it uniformly.
    """
    agent = AgentService.get()
    steps = list(req.steps or [])
    if not steps:
        return EventSourceResponse(_batch_error_stream("steps must be a non-empty array"))

    async def event_gen():
        total = len(steps)
        completed = 0
        failed = 0
        results: List[Dict[str, Any]] = []
        t0 = time.time()
        for idx, step in enumerate(steps):
            step_event = {
                "event": "step_start",
                "data": json.dumps({
                    "index": idx,
                    "total": total,
                    "name": step.name,
                    "arguments": step.arguments,
                }),
            }
            yield step_event
            outcome = await _execute_single_tool(agent, step.name, req.session_id, step.arguments)
            completed += 1 if outcome["success"] else 0
            failed += 0 if outcome["success"] else 1
            results.append({
                "index": idx,
                "name": step.name,
                "success": outcome["success"],
                "message": outcome.get("message", ""),
                "error": outcome.get("error"),
                "tool_call": outcome.get("tool_call"),
            })
            yield {
                "event": "step_result",
                "data": json.dumps({
                    "index": idx,
                    "name": step.name,
                    "success": outcome["success"],
                    "message": outcome.get("message", ""),
                    "error": outcome.get("error"),
                    "tool_call": outcome.get("tool_call"),
                    "completed": completed,
                    "failed": failed,
                }),
            }
            if not outcome["success"] and req.stop_on_error:
                scene = agent.orchestrator.get_scene(req.session_id)
                yield {
                    "event": "batch_error",
                    "data": json.dumps({
                        "session_id": req.session_id,
                        "index": idx,
                        "name": step.name,
                        "error": outcome.get("error") or outcome.get("message", "step failed"),
                        "completed": completed,
                        "failed": failed,
                        "scene": scene.to_dict(),
                    }),
                }
                return
        scene = agent.orchestrator.get_scene(req.session_id)
        yield {
            "event": "batch_done",
            "data": json.dumps({
                "session_id": req.session_id,
                "total": total,
                "completed": completed,
                "failed": failed,
                "elapsed": round(time.time() - t0, 3),
                "results": results,
                "scene": scene.to_dict(),
            }),
        }

    return EventSourceResponse(event_gen())


async def _batch_error_stream(message: str):
    """Helper: emit a single batch_error event for invalid requests."""
    yield {
        "event": "batch_error",
        "data": json.dumps({"error": message, "completed": 0, "failed": 0}),
    }


@router.post("/agent/plan/run")
async def agent_plan_run(req: PlanRunRequest) -> EventSourceResponse:
    """Plan a message and then execute each planned step with SSE progress.

    Two-phase streaming endpoint. Phase one calls the orchestrator's
    ``plan_only`` to produce a structured plan (goal, steps, tool calls)
    without mutating the scene, and emits a ``plan_ready`` event. Phase
    two executes each planned tool call in order, emitting ``step_start``
    / ``step_result`` per step, then a final ``plan_done`` event with the
    full scene snapshot. When the plan has zero executable steps (e.g.
    the LLM returned only a text answer), the stream emits ``plan_empty``
    and terminates. Falls back to the offline rule parser when no LLM is
    configured so the endpoint works in offline mode too.
    """
    agent = AgentService.get()

    async def event_gen():
        t0 = time.time()
        # --- phase 1: plan ---
        try:
            plan_result = await agent.orchestrator.plan_only(
                req.message, req.session_id, model=req.model
            )
        except Exception as e:
            logger.exception("agent/plan/run plan phase error")
            yield {
                "event": "plan_error",
                "data": json.dumps({"error": str(e), "phase": "plan"}),
            }
            return

        plan = plan_result.get("plan") or {}
        steps = plan.get("steps") or []
        # Extract executable tool calls. Sources, in priority order:
        #   1. Top-level ``tool_calls`` array (offline mode canonical form):
        #      each item carries {name, arguments}.
        #   2. Per-step ``tool_call`` dict {name, arguments} (online mode).
        #   3. Per-step ``tool`` + ``arguments`` keys (offline plan steps).
        executable: List[Dict[str, Any]] = []
        seen_keys: set = set()
        top_level_calls = plan_result.get("tool_calls") or []
        if isinstance(top_level_calls, list):
            for tc in top_level_calls:
                if isinstance(tc, dict) and tc.get("name"):
                    name = str(tc["name"])
                    if name in seen_keys:
                        continue
                    seen_keys.add(name)
                    executable.append({"name": name, "arguments": tc.get("arguments", {}) or {}})
        for step in steps:
            if not isinstance(step, dict):
                continue
            tc = step.get("tool_call")
            if isinstance(tc, dict) and tc.get("name"):
                name = str(tc["name"])
                if name not in seen_keys:
                    seen_keys.add(name)
                    executable.append({"name": name, "arguments": tc.get("arguments", {}) or {}})
            elif isinstance(tc, list):
                for item in tc:
                    if isinstance(item, dict) and item.get("name"):
                        name = str(item["name"])
                        if name not in seen_keys:
                            seen_keys.add(name)
                            executable.append({"name": name, "arguments": item.get("arguments", {}) or {}})
            elif step.get("tool"):
                name = str(step["tool"])
                if name not in seen_keys:
                    seen_keys.add(name)
                    executable.append({"name": name, "arguments": step.get("arguments", {}) or {}})
        yield {
            "event": "plan_ready",
            "data": json.dumps({
                "session_id": req.session_id,
                "goal": plan.get("goal", req.message),
                "total_steps": len(steps),
                "executable_steps": len(executable),
                "has_destructive_steps": plan_result.get("has_destructive_steps", False),
                "steps_preview": [
                    {
                        "id": s.get("id", f"step_{i}"),
                        "description": s.get("description", ""),
                        "tool": (s.get("tool_call") or {}).get("name") if isinstance(s.get("tool_call"), dict) else None,
                    }
                    for i, s in enumerate(steps)
                ],
                "auto_approve": req.auto_approve,
            }),
        }

        if not executable:
            yield {
                "event": "plan_empty",
                "data": json.dumps({
                    "session_id": req.session_id,
                    "message": plan_result.get("message", "Plan produced no executable tool calls."),
                    "elapsed": round(time.time() - t0, 3),
                }),
            }
            return

        if not req.auto_approve:
            yield {
                "event": "approval_skipped",
                "data": json.dumps({
                    "note": "auto_approve=false is not yet wired to a confirmation gate; running the plan anyway.",
                    "executable_steps": len(executable),
                }),
            }

        # --- phase 2: execute each planned step ---
        total = len(executable)
        completed = 0
        failed = 0
        results: List[Dict[str, Any]] = []
        for idx, step in enumerate(executable):
            yield {
                "event": "step_start",
                "data": json.dumps({
                    "index": idx,
                    "total": total,
                    "name": step["name"],
                    "arguments": step["arguments"],
                    "phase": "execute",
                }),
            }
            outcome = await _execute_single_tool(agent, step["name"], req.session_id, step["arguments"])
            completed += 1 if outcome["success"] else 0
            failed += 0 if outcome["success"] else 1
            results.append({
                "index": idx,
                "name": step["name"],
                "success": outcome["success"],
                "message": outcome.get("message", ""),
                "error": outcome.get("error"),
                "tool_call": outcome.get("tool_call"),
            })
            yield {
                "event": "step_result",
                "data": json.dumps({
                    "index": idx,
                    "name": step["name"],
                    "success": outcome["success"],
                    "message": outcome.get("message", ""),
                    "error": outcome.get("error"),
                    "tool_call": outcome.get("tool_call"),
                    "completed": completed,
                    "failed": failed,
                    "phase": "execute",
                }),
            }
            # Plan-run continues through failures so a single bad step
            # does not abandon the rest of the user's intent.

        scene = agent.orchestrator.get_scene(req.session_id)
        yield {
            "event": "plan_done",
            "data": json.dumps({
                "session_id": req.session_id,
                "goal": plan.get("goal", req.message),
                "total": total,
                "completed": completed,
                "failed": failed,
                "elapsed": round(time.time() - t0, 3),
                "results": results,
                "scene": scene.to_dict(),
            }),
        }

    return EventSourceResponse(event_gen())


@router.post("/agent/batch/preview")
async def agent_batch_preview(req: BatchRequest) -> JSONResponse:
    """Validate a batch request without executing any tool.

    Resolves every tool name, reports missing tools, and returns the
    coerced-argument preview per step so the frontend can render a
    confirmation dialog before running ``/agent/batch``. Read-only —
    does not mutate the scene.
    """
    agent = AgentService.get()
    preview: List[Dict[str, Any]] = []
    missing: List[str] = []
    for idx, step in enumerate(req.steps or []):
        tool = agent.orchestrator.registry.get(step.name)
        if tool is None:
            missing.append(step.name)
            preview.append({
                "index": idx,
                "name": step.name,
                "valid": False,
                "error": "Tool not registered",
            })
            continue
        coerced = _coerce_tool_args(tool, step.arguments)
        requires_approval = bool(getattr(tool, "requires_approval", False))
        preview.append({
            "index": idx,
            "name": step.name,
            "valid": True,
            "requires_approval": requires_approval,
            "description": getattr(tool, "description", ""),
            "arguments": coerced,
        })
    return JSONResponse(content={
        "session_id": req.session_id,
        "total_steps": len(req.steps or []),
        "valid_steps": sum(1 for p in preview if p.get("valid")),
        "missing_tools": missing,
        "has_destructive_steps": any(p.get("requires_approval") for p in preview if p.get("valid")),
        "preview": preview,
    })
