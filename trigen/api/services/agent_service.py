"""Agent service layer, encapsulating invocation and lifecycle management
of AgentOrchestrator."""

from __future__ import annotations

import logging
from typing import Any, AsyncIterator, Dict, List, Optional

from trigen.agent_trace import trace_store
from trigen.config import AgentConfig
from trigen.orchestrator import AgentOrchestrator, AgentEvent, EventType
from trigen.reflection import reflection_store
from trigen.scene import GEOMETRY_DEFAULTS, MATERIAL_PRESETS

logger = logging.getLogger("trigen.api.agent")


class AgentService:
    """Agent orchestration service, global singleton."""

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
                "AgentOrchestrator initialized, LLM configured: %s",
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
        self,
        message: str,
        session_id: str = "default",
        model: Optional[str] = None,
        images: Optional[List[Dict[str, str]]] = None,
    ) -> AsyncIterator[AgentEvent]:
        """Streaming chat, yielding a sequence of AgentEvents.

        Passes the model override and any resolved image attachments through
        to the orchestrator. ``images`` is a list of ``{"base64", "mime"}``
        dicts produced by the chat router's ``_resolve_image_tags`` helper.
        """
        # Per-call accumulator for the durable turn reflection. We fold the
        # streamed events into a compact record that is persisted on ``done``.
        refl_tools: List[str] = []
        refl_seen: set = set()
        refl_outcome: str = ""
        refl_quality: Dict[str, Any] = {}
        refl_elapsed: float = 0.0
        refl_turn: int = 0
        async for event in self.orchestrator.run(
            message, session_id, model=model, images=images
        ):
            # Record every streamed event to the per-session trace store
            # so GET /agent/trace/{session_id} can replay the turn. The
            # store is a bounded ring buffer; recording is cheap and
            # never raises into the stream.
            try:
                trace_store.record(session_id, event.to_dict())
            except Exception:  # pragma: no cover — defensive
                logger.exception("trace_store.record failed; continuing")
            # Fold reflection-relevant events into the accumulator.
            try:
                if event.type == EventType.TOOL_CALL:
                    name = event.data.get("name") or event.data.get("tool") or ""
                    if name and name not in refl_seen:
                        refl_seen.add(name)
                        refl_tools.append(name)
                elif event.type == EventType.THINKING:
                    data = event.data or {}
                    if data.get("phase") == "reflection":
                        refl_outcome = data.get("content", "") or refl_outcome
                        if data.get("quality"):
                            refl_quality = data["quality"]
                elif event.type == EventType.DONE:
                    data = event.data or {}
                    stats = data.get("stats") or {}
                    if stats.get("quality"):
                        refl_quality = stats["quality"]
                    refl_elapsed = float(stats.get("elapsed", 0.0) or 0.0)
                    refl_turn += 1
                    reflection_store.record(
                        session_id,
                        turn=refl_turn,
                        goal=message,
                        tool_calls=list(refl_tools),
                        outcome=refl_outcome,
                        quality=refl_quality,
                        elapsed=refl_elapsed,
                    )
                    # Reset the accumulator for the next turn.
                    refl_tools = []
                    refl_seen = set()
                    refl_outcome = ""
                    refl_quality = {}
                    refl_elapsed = 0.0
            except Exception:  # pragma: no cover — defensive
                logger.exception("reflection capture failed; continuing")
            yield event

    def get_scene(self, session_id: str) -> Dict[str, Any]:
        """Get the current scene of the specified session."""
        scene = self.orchestrator.get_scene(session_id)
        return scene.to_dict()

    def reset_session(self, session_id: str) -> None:
        """Reset the specified session."""
        self.orchestrator.reset_session(session_id)
