"""Agent service layer, encapsulating invocation and lifecycle management
of AgentOrchestrator. Agent 服务层，封装 AgentOrchestrator 的调用与生命周期管理。"""

from __future__ import annotations

import logging
from typing import Any, AsyncIterator, Dict, List, Optional

from trigen.config import AgentConfig
from trigen.orchestrator import AgentOrchestrator, AgentEvent, EventType
from trigen.scene import GEOMETRY_DEFAULTS, MATERIAL_PRESETS

logger = logging.getLogger("trigen.api.agent")


class AgentService:
    """Agent orchestration service, global singleton.
    Agent 编排服务，全局单例。"""

    _instance: Optional["AgentService"] = None
    _orchestrator: Optional[AgentOrchestrator] = None

    @classmethod
    def get(cls) -> "AgentService":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self.config = AgentConfig()

    @property
    def orchestrator(self) -> AgentOrchestrator:
        if self._orchestrator is None:
            self._orchestrator = AgentOrchestrator(self.config)
            logger.info(
                "AgentOrchestrator 已初始化，LLM 配置状态: %s",
                self.config.llm.is_configured,
            )
        return self._orchestrator

    @property
    def llm_configured(self) -> bool:
        return self.config.llm.is_configured

    @property
    def session_count(self) -> int:
        if self._orchestrator:
            return len(self._orchestrator._sessions)
        return 0

    @property
    def tool_count(self) -> int:
        return len(self.orchestrator.list_tools())

    def list_tools(self) -> List[Dict[str, Any]]:
        return self.orchestrator.list_tools()

    def list_presets(self) -> Dict[str, List[str]]:
        return {
            "geometry_types": list(GEOMETRY_DEFAULTS.keys()),
            "material_presets": list(MATERIAL_PRESETS.keys()),
            "light_types": ["ambient", "directional", "point", "spot", "hemisphere"],
        }

    async def chat_stream(
        self, message: str, session_id: str = "default"
    ) -> AsyncIterator[AgentEvent]:
        """Streaming chat, yielding a sequence of AgentEvents.
        流式对话，产出 AgentEvent 序列。"""
        async for event in self.orchestrator.run(message, session_id):
            yield event

    def get_scene(self, session_id: str) -> Dict[str, Any]:
        """Get the current scene of the specified session.
        获取指定会话的当前场景。"""
        scene = self.orchestrator.get_scene(session_id)
        return scene.to_dict()

    def reset_session(self, session_id: str) -> None:
        """Reset the specified session. 重置指定会话。"""
        self.orchestrator.reset_session(session_id)
