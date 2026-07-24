"""工具基类与注册表 / Tool base classes and registry.

所有 Agent 工具继承 ToolBase，通过 ToolRegistry 统一注册、发现与调度。
工具执行返回 ToolResult，携带对场景的操作变更与面向用户的文本说明。
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
    """工具执行产生的场景变更，供前端增量更新。

    Scene mutations produced by tool execution, for incremental frontend updates.
    """

    action: str  # create / update / delete / create_light / update_light / delete_light / export
    target_id: Optional[str] = None
    payload: Dict[str, Any] = field(default_factory=dict)
    snapshot: Optional[Dict[str, Any]] = None  # 完整场景快照（可选） / Full scene snapshot (optional)


@dataclass
class ToolResult:
    """工具执行结果。

    Tool execution result.
    """

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
    """工具抽象基类。

    Abstract base class for tools.
    """

    name: str = ""
    description: str = ""

    @abstractmethod
    def schema(self) -> Dict[str, Any]:
        """返回 OpenAI function calling 格式的参数 schema。

        Return the parameter schema in OpenAI function calling format.
        """

    @abstractmethod
    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        """在给定场景上执行工具。

        Execute the tool on the given scene.
        """


class ToolRegistry:
    """工具注册表，管理工具实例并对外提供查询。

    Tool registry that manages tool instances and exposes queries.
    """

    def __init__(self):
        self._tools: Dict[str, ToolBase] = {}

    def register(self, tool: ToolBase) -> None:
        if not tool.name:
            raise ValueError(f"工具 {tool.__class__.__name__} 缺少 name 属性")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[ToolBase]:
        return self._tools.get(name)

    def all(self) -> List[ToolBase]:
        return list(self._tools.values())

    def schemas(self) -> List[Dict[str, Any]]:
        """返回全部工具的 OpenAI schema。

        Return the OpenAI schemas for all tools.
        """
        return [
            {"name": t.name, "description": t.description, "parameters": t.schema()}
            for t in self._tools.values()
        ]
