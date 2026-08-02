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

    # Whether this tool has destructive side-effects (deletes geometry,
    # boolean-cuts, shatters, etc.) and should be surfaced for user
    # confirmation in the plan-preview flow. Defaults to False. Read by
    # ``AgentOrchestrator.plan_only`` to populate ``has_destructive_steps``.
    requires_approval: bool = False

    # Coarse functional category used for tool browsing, smart selection,
    # and the /api/tools/categories endpoint. The orchestrator's central
    # category map overrides this default at registration time so the
    # canonical taxonomy lives in a single place.
    category: str = "general"

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
            {
                "name": t.name,
                "description": t.description,
                "parameters": t.schema(),
                "category": t.category,
                "requires_approval": bool(t.requires_approval),
            }
            for t in self._tools.values()
        ]

    def schemas_for(self, names) -> List[Dict[str, Any]]:
        """Return the OpenAI schemas for the named tool subset, preserving
        registry order. Unknown names are skipped. Used by smart selection
        to inject only the relevant tool subset into the LLM call.
        """
        wanted = set(names)
        return [
            {
                "name": t.name,
                "description": t.description,
                "parameters": t.schema(),
                "category": t.category,
                "requires_approval": bool(t.requires_approval),
            }
            for t in self._tools.values()
            if t.name in wanted
        ]

    def by_category(self, category: str) -> List[ToolBase]:
        return [t for t in self._tools.values() if t.category == category]

    def categories(self) -> Dict[str, List[Dict[str, Any]]]:
        """Group every registered tool by its category for browsing.

        Returns a dict keyed by category name whose values are lists of
        ``{name, description, parameters, category, requires_approval}``
        entries (same shape as ``schemas()``).
        """
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for t in self._tools.values():
            grouped.setdefault(t.category, []).append(
                {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.schema(),
                    "category": t.category,
                    "requires_approval": bool(t.requires_approval),
                }
            )
        return grouped
