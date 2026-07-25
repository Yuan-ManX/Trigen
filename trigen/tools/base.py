"""Tool base classes and registry.

All agent tools inherit from ToolBase and are uniformly registered, discovered,
and dispatched via ToolRegistry. Tool execution returns a ToolResult carrying
the scene mutations and user-facing text descriptions.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from trigen.scene import Scene


@dataclass
class SceneDelta:
    """Scene mutations produced by tool execution, for incremental frontend updates."""

    action: str  # create / update / delete / create_light / update_light / delete_light / export
    target_id: Optional[str] = None
    payload: Dict[str, Any] = field(default_factory=dict)
    snapshot: Optional[Dict[str, Any]] = None  # Full scene snapshot (optional)


@dataclass
class ToolResult:
    """Tool execution result."""

    success: bool
    message: str
    deltas: List[SceneDelta] = field(default_factory=list)
    data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "message": self.message,
            "deltas": [d.__dict__ if isinstance(d, SceneDelta) else d for d in self.deltas],
            "data": self.data,
        }


class ToolBase(ABC):
    """Abstract base class for tools."""

    name: str = ""
    description: str = ""

    @abstractmethod
    def schema(self) -> Dict[str, Any]:
        """Return the parameter schema in OpenAI function calling format."""

    @abstractmethod
    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        """Execute the tool on the given scene."""


class ToolRegistry:
    """Tool registry that manages tool instances and exposes queries."""

    def __init__(self):
        self._tools: Dict[str, ToolBase] = {}

    def register(self, tool: ToolBase) -> None:
        if not tool.name:
            raise ValueError(f"Tool {tool.__class__.__name__} is missing the name attribute")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[ToolBase]:
        return self._tools.get(name)

    def all(self) -> List[ToolBase]:
        return list(self._tools.values())

    def schemas(self) -> List[Dict[str, Any]]:
        """Return the OpenAI schemas for all tools."""
        return [
            {"name": t.name, "description": t.description, "parameters": t.schema()}
            for t in self._tools.values()
        ]
