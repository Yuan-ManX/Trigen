"""Agent orchestrator — Trigen intelligent body's central scheduling core.

Unified串联 LLM 推理、任务规划、工具执行与对话记忆，以流式事件驱动
前端实时更新。支持多轮工具调用循环、并行执行与思考过程透出，直至 LLM
给出最终文本回复。

Unifies LLM reasoning, task planning, tool execution, and conversation
memory, driving real-time frontend updates via streaming events. Supports
multi-round tool-call loops, parallel execution, and thinking-process
exposure until the LLM yields its final text reply.

Event stream / 事件流:
  thinking     — Agent 思考过程 / Agent reasoning trace
  text_delta   — LLM 文本片段 / LLM text fragment
  tool_call    — 工具调用开始 / Tool call start
  tool_result  — 工具执行结果 / Tool execution result
  scene_update — 场景变更 / Scene mutation
  done         — 本轮对话结束 / End of this conversation turn
  error        — 异常 / Error
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
from trigen.scene import Scene, LightObject
from trigen.tools import (
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
    ModifyGeometryTool,
    ModifyLightTool,
    SelectObjectTool,
    SetBackgroundTool,
    SetFogTool,
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
    """Agent output event / Agent 输出事件."""

    type: EventType
    data: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {"type": self.type.value, "data": self.data}

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)


class AgentOrchestrator:
    """Trigen Agent orchestrator / Trigen Agent 编排器."""

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
        # Geometry creation & editing / 几何创建与编辑
        registry.register(CreateObjectTool())
        registry.register(TransformObjectTool())
        registry.register(ModifyGeometryTool())
        registry.register(DuplicateObjectTool())
        registry.register(DeleteObjectTool())
        registry.register(ListObjectsTool())
        # Material / 材质
        registry.register(ApplyMaterialTool())
        registry.register(ApplyMaterialPresetTool())
        # Lighting / 灯光
        registry.register(AddLightTool())
        registry.register(ModifyLightTool())
        registry.register(DeleteLightTool())
        # Scene organization / 场景组织
        registry.register(GroupObjectsTool())
        registry.register(UngroupObjectsTool())
        registry.register(SetBackgroundTool())
        registry.register(SetFogTool())
        registry.register(ArrangeLayoutTool())
        # Editor control / 编辑器控制
        registry.register(SelectObjectTool())
        registry.register(FocusObjectTool())
        # Export / 导出
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
            # 默认场景：一束方向光 + 环境光
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
        """Expose all registered tool schemas / 暴露全部已注册工具 schema."""
        return self.registry.schemas()

    async def run(self, user_message: str, session_id: str = "default") -> AsyncIterator[AgentEvent]:
        """Run a conversation turn, streaming out events.
        运行一轮对话，流式产出事件."""
        start_ts = time.time()
        memory = self.get_memory(session_id)
        scene = self.get_scene(session_id)
        memory.add_user(user_message)

        # If LLM is not configured, run in offline rule mode
        # 若 LLM 未配置，走降级模式
        if not self.config.llm.is_configured:
            async for event in self._run_offline(user_message, scene, session_id):
                yield event
            return

        tool_schemas = self.registry.schemas()
        scene_context = self.planner.build_context_message(scene.to_dict())
        messages = memory.to_openai_messages()
        # Inject scene context before the latest user message
        # 注入场景上下文到最新用户消息前
        messages.insert(-1, {"role": "system", "content": scene_context})

        # Emit a thinking event describing the plan
        # 发出思考事件描述计划
        yield AgentEvent(
            type=EventType.THINKING,
            data={
                "phase": "understanding",
                "content": f"理解用户意图：{user_message[:120]}",
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
            # 无工具调用 → 本轮结束
            if not tool_calls_collected:
                break

            # Emit thinking event for the planning phase
            # 发出规划阶段思考事件
            yield AgentEvent(
                type=EventType.THINKING,
                data={
                    "phase": "planning",
                    "content": f"规划执行 {len(tool_calls_collected)} 个工具调用",
                    "tools": [tc.name for tc in tool_calls_collected],
                    "iteration": iteration,
                },
            )

            # Plan and execute tools / 规划并执行工具
            plan = self.planner.from_tool_calls(tool_calls_collected, reasoning=full_text)
            # Append assistant message (with tool_calls structure) to LLM messages
            # 向 LLM messages 追加 assistant 消息（含 tool_calls 结构）
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
                # 向 messages 追加 tool 结果
                if step:
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": step.tool_call_id,
                            "content": result.message,
                        }
                    )

            # Scene mutation event / 场景变更事件
            deltas = self.executor.collect_deltas(results)
            if deltas:
                yield AgentEvent(
                    type=EventType.SCENE_UPDATE,
                    data={
                        "deltas": [d.__dict__ if hasattr(d, "__dict__") else d for d in deltas],
                        "scene": scene.to_dict(),
                    },
                )

            # Update scene context / 更新场景上下文
            messages.append(
                {"role": "system", "content": self.planner.build_context_message(scene.to_dict())}
            )
            full_text = ""

        elapsed = round(time.time() - start_ts, 2)
        memory.add_assistant(full_text)

        # Emit final thinking event summarizing the turn
        # 发出本轮总结思考事件
        yield AgentEvent(
            type=EventType.THINKING,
            data={
                "phase": "complete",
                "content": f"本轮完成，共 {iteration + 1} 次迭代，耗时 {elapsed}s",
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
        LLM 未配置时的降级模式：基于关键词的规则引擎。"""
        msg = user_message.lower()
        text = "（离线模式：未配置 LLM API Key，使用规则引擎响应。配置 TRIGEN_LLM_API_KEY 后可获得完整智能体能力。）\n\n"

        yield AgentEvent(
            type=EventType.THINKING,
            data={"phase": "understanding", "content": "离线规则引擎解析用户指令"},
        )

        # Create objects / 创建对象
        geo_map = {
            "立方体": "box", "cube": "box", "方块": "box", "盒子": "box",
            "球": "sphere", "sphere": "sphere", "球体": "sphere",
            "圆柱": "cylinder", "cylinder": "cylinder", "柱子": "cylinder",
            "圆锥": "cone", "cone": "cone",
            "圆环": "torus", "torus": "torus", "环": "torus",
            "平面": "plane", "plane": "plane", "地面": "plane",
            "二十面体": "icosahedron", "icosahedron": "icosahedron",
            "十二面体": "dodecahedron", "dodecahedron": "dodecahedron",
            "八面体": "octahedron", "octahedron": "octahedron",
            "四面体": "tetrahedron", "tetrahedron": "tetrahedron",
            "扭结": "torusKnot", "knot": "torusKnot",
            "胶囊": "capsule", "capsule": "capsule",
            "圆环面": "ring", "ring": "ring",
        }
        created = []
        matched_types = set()

        # Color detection / 颜色检测
        color_map = {
            "红": "#e84a4a", "red": "#e84a4a",
            "绿": "#3acc66", "green": "#3acc66",
            "蓝": "#3a7aff", "blue": "#3a7aff",
            "黄": "#ffc933", "yellow": "#ffc933",
            "紫": "#9a3aff", "purple": "#9a3aff",
            "橙": "#ff8a3a", "orange": "#ff8a3a",
            "粉": "#ff7acc", "pink": "#ff7acc",
            "白": "#ffffff", "white": "#ffffff",
            "黑": "#1a1a1a", "black": "#1a1a1a",
            "青": "#00F0FF", "cyan": "#00F0FF",
            "金": "#ffc933", "gold": "#ffc933",
            "银": "#c0c0c8", "silver": "#c0c0c8",
        }
        detected_color = None
        for color_kw, color_hex in color_map.items():
            if color_kw in msg:
                detected_color = color_hex
                break

        # Material preset detection / 材质预设检测
        preset_map = {
            "金属": "metal", "metal": "metal",
            "玻璃": "glass", "glass": "glass",
            "木头": "wood", "wood": "wood",
            "塑料": "plastic", "plastic": "plastic",
            "橡胶": "rubber", "rubber": "rubber",
            "陶瓷": "ceramic", "ceramic": "ceramic",
            "大理石": "marble", "marble": "marble",
            "霓虹": "neon", "neon": "neon",
            "发光": "emissive", "emissive": "emissive",
            "线框": "wireframe", "wireframe": "wireframe",
        }
        detected_preset = None
        for preset_kw, preset_name in preset_map.items():
            if preset_kw in msg:
                detected_preset = preset_name
                break

        for kw, geo_type in geo_map.items():
            if kw in msg and geo_type not in matched_types:
                matched_types.add(geo_type)
                tool = self.registry.get("create_object")
                args: Dict[str, Any] = {"geometry_type": geo_type}
                if detected_color:
                    args["color"] = detected_color
                if detected_preset == "metal":
                    args["metalness"] = 1.0
                    args["roughness"] = 0.25
                elif detected_preset == "glass":
                    args["opacity"] = 0.35
                    args["roughness"] = 0.05
                result = await tool.execute(scene, args)
                created.append(result)
                yield AgentEvent(
                    type=EventType.TOOL_CALL,
                    data={"id": "", "name": "create_object", "arguments": args},
                )
                yield AgentEvent(
                    type=EventType.TOOL_RESULT,
                    data={"name": "create_object", "success": result.success, "message": result.message, "data": result.data},
                )
                if result.deltas:
                    yield AgentEvent(
                        type=EventType.SCENE_UPDATE,
                        data={"deltas": [d.__dict__ for d in result.deltas], "scene": scene.to_dict()},
                    )
                text += f"已创建 {geo_type}。\n"

        # Export / 导出
        if any(k in msg for k in ["导出", "export", "glb", "obj", "stl"]):
            fmt = "glb"
            if "obj" in msg:
                fmt = "obj"
            elif "stl" in msg:
                fmt = "stl"
            tool = self.registry.get("export_scene")
            result = await tool.execute(scene, {"format": fmt})
            yield AgentEvent(
                type=EventType.TOOL_RESULT,
                data={"name": "export_scene", "success": result.success, "message": result.message, "data": result.data},
            )
            text += result.message + "\n"

        # List / 列表
        if any(k in msg for k in ["列表", "list", "查看", "有哪些", "场景"]):
            tool = self.registry.get("list_objects")
            result = await tool.execute(scene, {})
            yield AgentEvent(
                type=EventType.TOOL_RESULT,
                data={"name": "list_objects", "success": result.success, "message": result.message, "data": result.data},
            )
            text += result.message + "\n"

        # Arrange layout / 布局排列
        if any(k in msg for k in ["排列", "排布", "arrange", "布局"]):
            tool = self.registry.get("arrange_layout")
            layout_type = "grid"
            if "圆形" in msg or "circle" in msg:
                layout_type = "circle"
            elif "线性" in msg or "linear" in msg or "一排" in msg:
                layout_type = "linear"
            result = await tool.execute(scene, {"layout_type": layout_type})
            yield AgentEvent(
                type=EventType.TOOL_RESULT,
                data={"name": "arrange_layout", "success": result.success, "message": result.message, "data": result.data},
            )
            if result.deltas:
                yield AgentEvent(
                    type=EventType.SCENE_UPDATE,
                    data={"deltas": [d.__dict__ for d in result.deltas], "scene": scene.to_dict()},
                )
            text += result.message + "\n"

        # Background / 背景
        if any(k in msg for k in ["背景", "background"]):
            for color_kw, color_hex in color_map.items():
                if color_kw in msg:
                    tool = self.registry.get("set_background")
                    result = await tool.execute(scene, {"color": color_hex})
                    yield AgentEvent(
                        type=EventType.TOOL_RESULT,
                        data={"name": "set_background", "success": result.success, "message": result.message, "data": result.data},
                    )
                    if result.deltas:
                        yield AgentEvent(
                            type=EventType.SCENE_UPDATE,
                            data={"deltas": [d.__dict__ for d in result.deltas], "scene": scene.to_dict()},
                        )
                    text += result.message + "\n"
                    break

        if not created and "导出" not in msg and "list" not in msg and "查看" not in msg and "排列" not in msg and "背景" not in msg:
            text += "我已就绪。尝试说「创建一个球体」「加一个红色金属立方体」「圆形排列所有物体」「导出为 GLB」等指令。"

        yield AgentEvent(type=EventType.TEXT_DELTA, data={"content": text, "iteration": 0})
        memory = self.get_memory(session_id)
        memory.add_assistant(text)
        yield AgentEvent(
            type=EventType.DONE,
            data={"content": text, "scene": scene.to_dict(), "session_id": session_id, "elapsed": 0.0},
        )
