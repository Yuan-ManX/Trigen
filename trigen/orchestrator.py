"""Agent orchestrator — Trigen intelligent body's central scheduling core.

Unifies LLM reasoning, task planning, tool execution, and conversation
memory, driving real-time frontend updates via streaming events. Supports
multi-round tool-call loops, parallel execution, and thinking-process
exposure until the LLM yields its final text reply.

Event stream:
  thinking     — Agent reasoning trace
  text_delta   — LLM text fragment
  tool_call    — Tool call start
  tool_result  — Tool execution result
  scene_update — Scene mutation
  done         — End of this conversation turn
  error        — Error
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, AsyncIterator, Dict, List, Optional

from trigen.config import AgentConfig
from trigen.executor import TaskExecutor
from trigen.memory import ConversationMemory
from trigen.planner import TaskPlanner
from trigen.llm.client import LLMClient, LLMStreamChunk
from trigen.llm.prompts import SYSTEM_PROMPT, build_scene_summary
from trigen.intent_parser import parse_message, ParsedIntent
from trigen.scene import Scene, LightObject
from trigen.tools import (
    AddCameraTool,
    AddLightTool,
    ApplyMaterialTool,
    ApplyMaterialPresetTool,
    ArrangeLayoutTool,
    CreateObjectTool,
    DeleteLightTool,
    DeleteObjectTool,
    DuplicateObjectTool,
    ExportSceneTool,
    FocusObjectTool,
    GroupObjectsTool,
    ListObjectsTool,
    ModifyCameraTool,
    ModifyGeometryTool,
    ModifyLightTool,
    SceneInfoTool,
    SelectObjectTool,
    SetBackgroundTool,
    SetFogTool,
    SetGridSizeTool,
    SetViewTool,
    SmartComposeTool,
    ToggleGridTool,
    TransformObjectTool,
    UngroupObjectsTool,
)
from trigen.tools.base import ToolRegistry

logger = logging.getLogger("trigen.orchestrator")


class EventType(str, Enum):
    THINKING = "thinking"
    TEXT_DELTA = "text_delta"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    SCENE_UPDATE = "scene_update"
    DONE = "done"
    ERROR = "error"


@dataclass
class AgentEvent:
    """Agent output event."""

    type: EventType
    data: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {"type": self.type.value, "data": self.data}

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)


class AgentOrchestrator:
    """Trigen Agent orchestrator."""

    def __init__(self, config: Optional[AgentConfig] = None):
        self.config = config or AgentConfig()
        self.config.ensure_workspace()
        self.llm = LLMClient(self.config.llm)
        self.registry = self._build_registry()
        self.planner = TaskPlanner()
        self.executor = TaskExecutor(self.registry)
        self._sessions: Dict[str, ConversationMemory] = {}
        self._scenes: Dict[str, Scene] = {}

    def _build_registry(self) -> ToolRegistry:
        registry = ToolRegistry()
        # Geometry creation & editing
        registry.register(CreateObjectTool())
        registry.register(TransformObjectTool())
        registry.register(ModifyGeometryTool())
        registry.register(DuplicateObjectTool())
        registry.register(DeleteObjectTool())
        registry.register(ListObjectsTool())
        # Material
        registry.register(ApplyMaterialTool())
        registry.register(ApplyMaterialPresetTool())
        # Lighting
        registry.register(AddLightTool())
        registry.register(ModifyLightTool())
        registry.register(DeleteLightTool())
        # Camera
        registry.register(AddCameraTool())
        registry.register(ModifyCameraTool())
        registry.register(SetViewTool())
        # Scene organization
        registry.register(GroupObjectsTool())
        registry.register(UngroupObjectsTool())
        registry.register(SetBackgroundTool())
        registry.register(SetFogTool())
        registry.register(ArrangeLayoutTool())
        # Scene inspection
        registry.register(SceneInfoTool())
        # Grid control
        registry.register(ToggleGridTool())
        registry.register(SetGridSizeTool())
        # Smart composition
        registry.register(SmartComposeTool())
        # Editor control
        registry.register(SelectObjectTool())
        registry.register(FocusObjectTool())
        # Export
        registry.register(ExportSceneTool(workspace_dir=self.config.workspace_dir))
        return registry

    def get_memory(self, session_id: str) -> ConversationMemory:
        if session_id not in self._sessions:
            self._sessions[session_id] = ConversationMemory(
                session_id=session_id, window_size=self.config.memory_window
            )
        return self._sessions[session_id]

    def get_scene(self, session_id: str) -> Scene:
        if session_id not in self._scenes:
            scene = Scene()
            # Default scene: a directional key light + ambient fill
            scene.lights.append(
                LightObject(name="KeyLight", type="directional", intensity=1.2, position=[5, 8, 5])
            )
            scene.lights.append(
                LightObject(name="Ambient", type="ambient", intensity=0.4, position=[0, 0, 0])
            )
            self._scenes[session_id] = scene
        return self._scenes[session_id]

    def reset_session(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)
        self._scenes.pop(session_id, None)

    def list_tools(self) -> List[Dict[str, Any]]:
        """Expose all registered tool schemas."""
        return self.registry.schemas()

    async def run(self, user_message: str, session_id: str = "default", model: Optional[str] = None) -> AsyncIterator[AgentEvent]:
        """Run a conversation turn, streaming out events. Overrides LLM model if provided."""
        start_ts = time.time()
        memory = self.get_memory(session_id)
        scene = self.get_scene(session_id)
        memory.add_user(user_message)

        # If LLM is not configured or model is "trigen-default", run in offline rule mode
        use_offline = not self.config.llm.is_configured or (model == "trigen-default")
        if use_offline:
            async for event in self._run_offline(user_message, scene, session_id):
                yield event
            return

        tool_schemas = self.registry.schemas()
        scene_context = self.planner.build_context_message(scene.to_dict())
        messages = memory.to_openai_messages()
        # Inject scene context before the latest user message
        messages.insert(-1, {"role": "system", "content": scene_context})

        # Emit a thinking event describing the plan
        yield AgentEvent(
            type=EventType.THINKING,
            data={
                "phase": "understanding",
                "content": f"Understanding user intent: {user_message[:120]}",
                "scene_summary": build_scene_summary(scene.to_dict()),
            },
        )

        full_text = ""
        iteration = 0
        for iteration in range(self.config.max_iterations):
            tool_calls_collected: List = []
            try:
                async for chunk in self.llm.stream(
                    messages=messages,
                    tools=tool_schemas,
                    system=SYSTEM_PROMPT,
                    model=model,
                ):
                    if chunk.content:
                        full_text += chunk.content
                        yield AgentEvent(
                            type=EventType.TEXT_DELTA,
                            data={"content": chunk.content, "iteration": iteration},
                        )
                    if chunk.tool_calls:
                        tool_calls_collected.extend(chunk.tool_calls)
                    if chunk.finish_reason and not chunk.tool_calls:
                        break
            except Exception as e:
                logger.exception("LLM streaming error")
                yield AgentEvent(type=EventType.ERROR, data={"message": str(e)})
                return

            # No tool calls → end of this turn
            if not tool_calls_collected:
                break

            # Emit thinking event for the planning phase
            yield AgentEvent(
                type=EventType.THINKING,
                data={
                    "phase": "planning",
                    "content": f"Planning to execute {len(tool_calls_collected)} tool calls",
                    "tools": [tc.name for tc in tool_calls_collected],
                    "iteration": iteration,
                },
            )

            # Plan and execute tools
            plan = self.planner.from_tool_calls(tool_calls_collected, reasoning=full_text)
            # Append assistant message (with tool_calls structure) to LLM messages
            assistant_msg: Dict[str, Any] = {"role": "assistant", "content": full_text or ""}
            assistant_msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": json.dumps(tc.arguments, ensure_ascii=False),
                    },
                }
                for tc in tool_calls_collected
            ]
            messages.append(assistant_msg)

            for step in plan.steps:
                yield AgentEvent(
                    type=EventType.TOOL_CALL,
                    data={
                        "id": step.tool_call_id,
                        "name": step.tool_name,
                        "arguments": step.arguments,
                    },
                )

            results = await self.executor.execute_plan(scene, plan)
            for i, result in enumerate(results):
                step = plan.steps[i] if i < len(plan.steps) else None
                yield AgentEvent(
                    type=EventType.TOOL_RESULT,
                    data={
                        "id": step.tool_call_id if step else "",
                        "name": step.tool_name if step else "",
                        "success": result.success,
                        "message": result.message,
                        "data": result.data,
                    },
                )
                # Append tool result to messages
                if step:
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": step.tool_call_id,
                            "content": result.message,
                        }
                    )

            # Scene mutation event
            deltas = self.executor.collect_deltas(results)
            if deltas:
                yield AgentEvent(
                    type=EventType.SCENE_UPDATE,
                    data={
                        "deltas": [d.__dict__ if hasattr(d, "__dict__") else d for d in deltas],
                        "scene": scene.to_dict(),
                    },
                )

            # Update scene context
            messages.append(
                {"role": "system", "content": self.planner.build_context_message(scene.to_dict())}
            )
            full_text = ""

        elapsed = round(time.time() - start_ts, 2)
        memory.add_assistant(full_text)

        # Emit final thinking event summarizing the turn
        yield AgentEvent(
            type=EventType.THINKING,
            data={
                "phase": "complete",
                "content": f"Turn complete, {iteration + 1} iterations, elapsed {elapsed}s",
                "elapsed": elapsed,
                "iterations": iteration + 1,
            },
        )

        yield AgentEvent(
            type=EventType.DONE,
            data={
                "content": full_text,
                "scene": scene.to_dict(),
                "session_id": session_id,
                "elapsed": elapsed,
            },
        )

    async def _run_offline(
        self, user_message: str, scene: Scene, session_id: str
    ) -> AsyncIterator[AgentEvent]:
        """Offline rule engine when LLM is not configured.

        Uses the intent parser to decompose user messages into structured
        tool-call intents, then executes them sequentially with thinking
        and scene-update events — mirroring the online LLM flow.
        """
        start_ts = time.time()
        scene_dict = scene.to_dict()
        scene_objects = scene_dict.get("objects", [])
        scene_lights = scene_dict.get("lights", [])

        # Phase 1: Understanding
        yield AgentEvent(
            type=EventType.THINKING,
            data={
                "phase": "understanding",
                "content": f"Parsing user instruction: {user_message[:120]}",
                "scene_summary": build_scene_summary(scene_dict),
            },
        )

        # Phase 2: Intent parsing
        intents, _ = parse_message(user_message, scene_objects, scene_lights)

        if not intents:
            text = (
                "(Offline mode) I couldn't parse that command. Try:\n"
                "- \"create a red cube\"\n"
                "- \"add a blue sphere\"\n"
                "- \"move the cube to [2, 0, 0]\"\n"
                "- \"apply metal material to the sphere\"\n"
                "- \"add a point light\"\n"
                "- \"create solar system\"\n"
                "- \"arrange in circle\"\n"
                "- \"export as GLB\""
            )
            yield AgentEvent(type=EventType.TEXT_DELTA, data={"content": text, "iteration": 0})
            memory = self.get_memory(session_id)
            memory.add_assistant(text)
            yield AgentEvent(
                type=EventType.DONE,
                data={"content": text, "scene": scene.to_dict(), "session_id": session_id, "elapsed": 0.0},
            )
            return

        # Phase 3: Planning
        tool_names = [i.tool_name for i in intents]
        yield AgentEvent(
            type=EventType.THINKING,
            data={
                "phase": "planning",
                "content": f"Planned {len(intents)} operation(s): {', '.join(tool_names)}",
                "tools": tool_names,
            },
        )

        text_parts: List[str] = []
        scene_changed = False

        # Phase 4: Execution
        for idx, intent in enumerate(intents):
            tool = self.registry.get(intent.tool_name)
            if tool is None:
                text_parts.append(f"Unknown tool: {intent.tool_name}")
                continue

            # Emit tool_call event (for tools that modify the scene)
            if intent.emit_tool_call:
                yield AgentEvent(
                    type=EventType.TOOL_CALL,
                    data={
                        "id": f"offline_{idx}",
                        "name": intent.tool_name,
                        "arguments": intent.arguments,
                    },
                )

            try:
                result = await tool.execute(scene, intent.arguments)
            except Exception as e:
                logger.exception("Offline tool %s execution error", intent.tool_name)
                from trigen.tools.base import ToolResult
                result = ToolResult(success=False, message=f"Execution error: {e}")

            yield AgentEvent(
                type=EventType.TOOL_RESULT,
                data={
                    "id": f"offline_{idx}",
                    "name": intent.tool_name,
                    "success": result.success,
                    "message": result.message,
                    "data": result.data,
                },
            )

            if result.deltas:
                scene_changed = True
                yield AgentEvent(
                    type=EventType.SCENE_UPDATE,
                    data={
                        "deltas": [d.__dict__ if hasattr(d, "__dict__") else d for d in result.deltas],
                        "scene": scene.to_dict(),
                    },
                )

            text_parts.append(result.message if result.success else f"Failed: {result.message}")

        # Phase 5: Complete
        elapsed = round(time.time() - start_ts, 2)
        yield AgentEvent(
            type=EventType.THINKING,
            data={
                "phase": "complete",
                "content": f"Turn complete, {len(intents)} operation(s), elapsed {elapsed}s",
                "elapsed": elapsed,
                "iterations": 1,
            },
        )

        full_text = "(Offline mode) " + "\n".join(text_parts)
        yield AgentEvent(type=EventType.TEXT_DELTA, data={"content": full_text, "iteration": 0})
        memory = self.get_memory(session_id)
        memory.add_assistant(full_text)
        yield AgentEvent(
            type=EventType.DONE,
            data={
                "content": full_text,
                "scene": scene.to_dict(),
                "session_id": session_id,
                "elapsed": elapsed,
            },
        )
