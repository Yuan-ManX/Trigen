"""Chat router — WebSocket streaming plus REST fallback."""

from __future__ import annotations

import base64
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from trigen.api.models.schemas import ChatRequest, ChatResponse, WSIncoming
from trigen.api.services.agent_service import AgentService
from trigen.api.services.session_service import SessionService

logger = logging.getLogger("trigen.api.chat")  # Chat router logger
router = APIRouter(tags=["chat"])  # Chat router

# Matches ``[Image: media_id]`` tags embedded by the frontend when a user
# attaches an uploaded image to a chat message. The media_id corresponds to
# a file persisted under ``<workspace>/uploads/`` by the upload endpoint.
_IMAGE_TAG_RE = re.compile(r"\[Image:\s*(img_[A-Za-z0-9_]+)\s*\]")

# Supported upload extensions mapped to their MIME types.
_EXT_MIME = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
}


def _resolve_image_tags(
    message: str, workspace_dir: str
) -> tuple[str, List[Dict[str, str]]]:
    """Resolve ``[Image: media_id]`` tags to base64 image attachments.

    For each tag, looks up the corresponding file under
    ``<workspace>/uploads/`` and reads it as base64. Tags that cannot be
    resolved (missing file) are left in the message as-is so the LLM sees a
    hint that an image was intended. Successfully resolved tags are stripped
    from the message text.

    Returns ``(clean_message, images)`` where ``images`` is a list of
    ``{"base64": ..., "mime": ...}`` dicts ready for the orchestrator.
    """
    images: List[Dict[str, str]] = []
    uploads_dir = os.path.join(workspace_dir, "uploads")

    def _replace(match: re.Match) -> str:
        media_id = match.group(1)
        # Search for a file matching the media_id with any known extension.
        for ext, mime in _EXT_MIME.items():
            candidate = os.path.join(uploads_dir, f"{media_id}{ext}")
            if os.path.isfile(candidate):
                try:
                    with open(candidate, "rb") as fh:
                        b64 = base64.b64encode(fh.read()).decode("ascii")
                    images.append({"base64": b64, "mime": mime})
                    return ""  # strip the tag from the message
                except Exception:
                    logger.warning("Failed reading upload %s", candidate, exc_info=True)
                    return match.group(0)  # leave tag in place
        logger.debug("Upload not found for media_id=%s", media_id)
        return match.group(0)  # leave tag in place

    clean = _IMAGE_TAG_RE.sub(_replace, message).strip()
    return clean, images


@router.websocket("/chat/ws")
async def chat_ws(websocket: WebSocket) -> None:
    """WebSocket chat endpoint, streaming Agent events.

    Supports an ``interrupt`` inbound message that cancels the currently
    running generation turn, so the user can stop a runaway plan without
    dropping the socket. On interrupt, a clean ``done`` (with an
    ``interrupted`` flag) event is emitted and the connection stays open.
    """
    await websocket.accept()  # Accept WebSocket connection
    agent = AgentService.get()
    session_svc = SessionService.get()

    # Holds the streaming task for the current turn so an interrupt can
    # cancel it mid-flight while keeping the socket alive.
    stream_task: Optional[asyncio.Task] = None
    current_session: Optional[str] = None

    async def _stream(message: str, session_id: str, model: Optional[str]) -> None:
        _, images = _resolve_image_tags(message, agent.config.workspace_dir)
        interrupted = False
        try:
            async for event in agent.chat_stream(
                message, session_id, model=model, images=images
            ):
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
        except asyncio.CancelledError:
            interrupted = True
            await websocket.send_text(
                json.dumps({
                    "type": "done",
                    "data": {
                        "content": "",
                        "session_id": session_id,
                        "interrupted": True,
                        "message": "Generation interrupted by user.",
                    },
                })
            )
        except Exception as e:
            logger.exception("Agent streaming error")
            try:
                await websocket.send_text(
                    json.dumps({"type": "error", "data": {"message": str(e)}})
                )
            except Exception:
                pass  # Ignore on send failure
        finally:
            nonlocal stream_task
            stream_task = None
            current_session = None

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

            if incoming.type == "interrupt":
                # Cancel the running turn (if any) and continue serving.
                if stream_task is not None and not stream_task.done():
                    stream_task.cancel()
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
            current_session = session_id
            stream_task = asyncio.create_task(_stream(message, session_id, model))
    except WebSocketDisconnect:
        # If the client disconnects mid-turn, stop the running task.
        if stream_task is not None and not stream_task.done():
            stream_task.cancel()
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

    # Resolve image tags in the REST path too so POST /api/chat works with
    # uploaded images the same way the WebSocket path does.
    clean_message, images = _resolve_image_tags(req.message, agent.config.workspace_dir)
    await session_svc.log_user_message(req.session_id, clean_message)

    final_content = ""  # Final reply content
    final_scene: Dict[str, Any] = {}  # Final scene data
    try:
        async for event in agent.chat_stream(
            clean_message, req.session_id, model=req.model, images=images
        ):
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
