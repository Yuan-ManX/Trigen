"""Pydantic data models defining API request/response schemas."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Chat request."""

    message: str = Field(..., description="User input message")
    session_id: str = Field(default="default", description="Session ID")
    model: Optional[str] = Field(default=None, description="LLM model override")


class ChatResponse(BaseModel):
    """Chat response (non-streaming)."""

    content: str
    session_id: str
    scene: Optional[Dict[str, Any]] = None


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = "ok"
    version: str = "1.0.0"
    llm_configured: bool = False
    sessions: int = 0
    tools: int = 0


class SceneResponse(BaseModel):
    """Scene response."""

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
    """WebSocket outbound message."""

    type: str
    data: Dict[str, Any] = Field(default_factory=dict)


class WSIncoming(BaseModel):
    """WebSocket inbound message."""

    type: str = "message"
    data: Dict[str, Any] = Field(default_factory=dict)


class ToolSchema(BaseModel):
    """Single tool schema."""

    name: str
    description: str
    parameters: Dict[str, Any] = Field(default_factory=dict)


class ToolsResponse(BaseModel):
    """Tools listing response."""

    tools: List[ToolSchema]
    count: int


class PresetsResponse(BaseModel):
    """Presets listing response."""

    geometry_types: List[str]
    material_presets: List[str]
    light_types: List[str]
