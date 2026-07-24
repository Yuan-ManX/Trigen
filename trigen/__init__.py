"""Trigen 全栈统一包 / Trigen unified package.

三生构维，智衍万物。统一封装 Agent 智能体核心与后端 API 服务，
以对话为入口编排几何、材质、灯光三元核心，自主完成 3D 内容创作。

From Three, AI Generates Everything.
This unified package encapsulates the Agent core and backend API service,
orchestrating geometry, material, and lighting through conversational interaction.
"""

__version__ = "1.0.0"

# Agent 核心导出 / Agent core exports
from trigen.config import AgentConfig
from trigen.orchestrator import AgentOrchestrator, AgentEvent, EventType
from trigen.memory import ConversationMemory
from trigen.planner import TaskPlanner
from trigen.executor import TaskExecutor

# API 入口 / API entry
from trigen.api.main import app

__all__ = [
    "AgentConfig",
    "AgentOrchestrator",
    "AgentEvent",
    "EventType",
    "ConversationMemory",
    "TaskPlanner",
    "TaskExecutor",
    "app",
]
