"""Trigen unified package.

From Three, AI Generates Everything.
This unified package encapsulates the Agent core and backend API service,
orchestrating geometry, material, and lighting through conversational interaction.
"""

__version__ = "1.0.0"

# Agent core exports
from trigen.config import AgentConfig
from trigen.orchestrator import AgentOrchestrator, AgentEvent, EventType
from trigen.memory import ConversationMemory
from trigen.planner import TaskPlanner
from trigen.executor import TaskExecutor

# API entry
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
