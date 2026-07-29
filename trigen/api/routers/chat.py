"""Chat router — WebSocket streaming plus REST fallback."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from trigen.api.models.schemas import ChatRequest, ChatResponse, WSIncoming
from trigen.api.services.agent_service import AgentService
from trigen.api.services.session_service import SessionService

logger = logging.getLogger("trigen.api.chat")  # Chat router logger
router = APIRouter(tags=["chat"])  # Chat router


@router.websocket("/chat/ws")
async def chat_ws(websocket: WebSocket) -> None:
    """WebSocket chat endpoint, streaming Agent events."""
    await websocket.accept()  # Accept WebSocket connection
    agent = AgentService.get()
    session_svc = SessionService.get()

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                incoming = WSIncoming(**json.loads(raw))
            except Exception as e:
                await websocket.send_text(
                    json.dumps({"type": "error", "data": {"message": f"Invalid message format: {e}"}})
                )
                continue

            if incoming.type != "message":
                continue  # Skip non-message types

            data = incoming.data
            message = str(data.get("message", "")).strip()
            session_id = str(data.get("session_id", "default"))
            model = data.get("model")  # Optional model override from frontend

            if not message:
                continue  # Skip empty message

            await session_svc.log_user_message(session_id, message)

            try:
                async for event in agent.chat_stream(message, session_id, model=model):
                    await websocket.send_text(event.to_json())
                    # Persist exported assets
                    if event.type.value == "tool_result":
                        ed = event.data
                        if ed.get("name") == "export_scene" and ed.get("success"):
                            export_data = ed.get("data", {})
                            await session_svc.log_asset(
                                session_id,
                                export_data.get("filename", "export"),
                                export_data.get("format", "glb"),
                                export_data.get("path", ""),
                                int(export_data.get("size_kb", 0)),
                            )
                    if event.type.value == "done":
                        await session_svc.log_assistant_message(session_id, event.data.get("content", ""))
            except Exception as e:
                logger.exception("Agent streaming error")
                await websocket.send_text(
                    json.dumps({"type": "error", "data": {"message": str(e)}})
                )
    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")  # Client disconnected actively
    except Exception as e:
        logger.exception("WebSocket error")
        try:
            await websocket.send_text(
                json.dumps({"type": "error", "data": {"message": str(e)}})
            )
        except Exception:
            pass  # Ignore on send failure


@router.post("/chat", response_model=ChatResponse)
async def chat_rest(req: ChatRequest) -> JSONResponse:
    """REST chat endpoint (non-streaming), collecting all events and returning the final result."""
    agent = AgentService.get()
    session_svc = SessionService.get()

    await session_svc.log_user_message(req.session_id, req.message)

    final_content = ""  # Final reply content
    final_scene: Dict[str, Any] = {}  # Final scene data
    try:
        async for event in agent.chat_stream(req.message, req.session_id, model=req.model):
            if event.type.value == "done":
                final_content = event.data.get("content", "")
                final_scene = event.data.get("scene", {})
                await session_svc.log_assistant_message(req.session_id, final_content)
    except Exception as e:
        logger.exception("REST chat error")
        return JSONResponse(
            status_code=500,
            content={"content": f"[Error] {e}", "session_id": req.session_id, "scene": None},
        )

    return JSONResponse(
        content={
            "content": final_content,
            "session_id": req.session_id,
            "scene": final_scene,
        }
    )


@router.get("/chat/sessions")
async def list_sessions() -> Dict[str, Any]:
    """List all persisted conversation sessions."""
    agent = AgentService.get()
    sessions = agent.orchestrator.list_sessions()
    return {"sessions": sessions, "count": len(sessions)}


@router.delete("/chat/sessions/{session_id}")
async def delete_session(session_id: str) -> Dict[str, Any]:
    """Delete a persisted conversation session."""
    agent = AgentService.get()
    agent.orchestrator.reset_session(session_id)
    return {"deleted": True, "session_id": session_id}


@router.get("/chat/sessions/{session_id}/memory")
async def get_session_memory(session_id: str) -> Dict[str, Any]:
    """Retrieve the persisted memory for a session."""
    from trigen.memory_persistence import persistence as memory_persistence

    memory = memory_persistence.load(session_id)
    if memory is None:
        return JSONResponse(
            status_code=404,
            content={"error": f"Session '{session_id}' not found"},
        )
    return {
        "session_id": session_id,
        "message_count": len(memory._messages),
        "compacted_summary": memory._compacted_summary,
        "messages": [
            {
                "role": m.role,
                "content": m.content,
                "timestamp": m.timestamp,
                "tool_name": m.tool_name,
            }
            for m in memory._messages
        ],
    }
