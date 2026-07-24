"""对话路由 — WebSocket 流式 + REST 回退。

Chat router — WebSocket streaming plus REST fallback.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from trigen.api.models.schemas import ChatRequest, ChatResponse, WSIncoming
from trigen.api.services.agent_service import AgentService
from trigen.api.services.session_service import SessionService

logger = logging.getLogger("trigen.api.chat")  # 对话路由日志器 / Chat router logger
router = APIRouter(tags=["chat"])  # 对话路由器 / Chat router


@router.websocket("/chat/ws")
async def chat_ws(websocket: WebSocket) -> None:
    """WebSocket 对话端点，流式传输 Agent 事件。

    WebSocket chat endpoint, streaming Agent events.
    """
    await websocket.accept()  # 接受 WebSocket 连接 / Accept WebSocket connection
    agent = AgentService.get()
    session_svc = SessionService.get()

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                incoming = WSIncoming(**json.loads(raw))
            except Exception as e:
                await websocket.send_text(
                    json.dumps({"type": "error", "data": {"message": f"消息格式错误: {e}"}})
                )
                continue

            if incoming.type != "message":
                continue  # 跳过非消息类型 / Skip non-message types

            data = incoming.data
            message = str(data.get("message", "")).strip()
            session_id = str(data.get("session_id", "default"))

            if not message:
                continue  # 空消息跳过 / Skip empty message

            await session_svc.log_user_message(session_id, message)

            try:
                async for event in agent.chat_stream(message, session_id):
                    await websocket.send_text(event.to_json())
                    # 持久化导出资产 / Persist exported assets
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
                logger.exception("Agent 流式处理异常")
                await websocket.send_text(
                    json.dumps({"type": "error", "data": {"message": str(e)}})
                )
    except WebSocketDisconnect:
        logger.info("WebSocket 客户端断开")  # 客户端主动断开 / Client disconnected actively
    except Exception as e:
        logger.exception("WebSocket 异常")
        try:
            await websocket.send_text(
                json.dumps({"type": "error", "data": {"message": str(e)}})
            )
        except Exception:
            pass  # 发送异常时忽略 / Ignore on send failure


@router.post("/chat", response_model=ChatResponse)
async def chat_rest(req: ChatRequest) -> JSONResponse:
    """REST 对话端点（非流式），收集全部事件后返回最终结果。

    REST chat endpoint (non-streaming), collecting all events and returning the final result.
    """
    agent = AgentService.get()
    session_svc = SessionService.get()

    await session_svc.log_user_message(req.session_id, req.message)

    final_content = ""  # 最终回复内容 / Final reply content
    final_scene: Dict[str, Any] = {}  # 最终场景数据 / Final scene data
    try:
        async for event in agent.chat_stream(req.message, req.session_id):
            if event.type.value == "done":
                final_content = event.data.get("content", "")
                final_scene = event.data.get("scene", {})
                await session_svc.log_assistant_message(req.session_id, final_content)
    except Exception as e:
        logger.exception("REST 对话异常")
        return JSONResponse(
            status_code=500,
            content={"content": f"[错误] {e}", "session_id": req.session_id, "scene": None},
        )

    return JSONResponse(
        content={
            "content": final_content,
            "session_id": req.session_id,
            "scene": final_scene,
        }
    )
