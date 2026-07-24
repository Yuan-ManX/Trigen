"""Pydantic data models defining API request/response schemas.
Pydantic 数据模型，定义 API 请求/响应 Schema。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Chat request / 对话请求."""

    message: str = Field(..., description="用户输入消息")
    session_id: str = Field(default="default", description="会话 ID")


class ChatResponse(BaseModel):
    """Chat response (non-streaming) / 对话响应（非流式）."""

    content: str
    session_id: str
    scene: Optional[Dict[str, Any]] = None


class HealthResponse(BaseModel):
    """Health check response / 健康检查响应."""

    status: str = "ok"
    version: str = "1.0.0"
    llm_configured: bool = False
    sessions: int = 0
    tools: int = 0


class SceneResponse(BaseModel):
    """Scene response / 场景响应."""

    session_id: str
    objects: List[Dict[str, Any]] = Field(default_factory=list)
    lights: List[Dict[str, Any]] = Field(default_factory=list)
    cameras: List[Dict[str, Any]] = Field(default_factory=list)
    groups: List[Dict[str, Any]] = Field(default_factory=list)
    background: str = "#0a0a0f"
    environment: Optional[str] = None
    fog: Optional[Dict[str, Any]] = None
    grid_visible: bool = True
    grid_size: float = 40.0


class WSMessage(BaseModel):
    """WebSocket outbound message / WebSocket 出站消息."""

    type: str
    data: Dict[str, Any] = Field(default_factory=dict)


class WSIncoming(BaseModel):
    """WebSocket inbound message / WebSocket 入站消息."""

    type: str = "message"
    data: Dict[str, Any] = Field(default_factory=dict)


class ToolSchema(BaseModel):
    """Single tool schema / 单个工具 schema."""

    name: str
    description: str
    parameters: Dict[str, Any] = Field(default_factory=dict)


class ToolsResponse(BaseModel):
    """Tools listing response / 工具列表响应."""

    tools: List[ToolSchema]
    count: int


class PresetsResponse(BaseModel):
    """Presets listing response / 预设列表响应."""

    geometry_types: List[str]
    material_presets: List[str]
    light_types: List[str]
