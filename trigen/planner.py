"""Task planner / 任务规划器.

Parses the LLM's tool-call sequence into ordered task steps, supporting
intent recognition and execution-plan generation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List

from trigen.llm.client import ToolCall

logger = logging.getLogger("trigen.planner")


@dataclass
class TaskStep:
    """A single execution step / 单个执行步骤."""

    tool_name: str
    arguments: Dict[str, Any]
    tool_call_id: str = ""
    description: str = ""


@dataclass
class TaskPlan:
    """Execution plan / 执行计划."""

    steps: List[TaskStep] = field(default_factory=list)
    reasoning: str = ""

    @property
    def is_empty(self) -> bool:
        return not self.steps


# Tools that can be safely executed in parallel within a single batch
# 可在同一批次内安全并行执行的工具
_PARALLEL_SAFE_TOOLS = {
    "apply_material",
    "apply_material_preset",
    "transform_object",
    "modify_geometry",
    "set_background",
    "set_fog",
    "select_object",
    "focus_object",
}


class TaskPlanner:
    """Parses LLM responses into an executable plan.
    将 LLM 响应解析为可执行计划。"""

    def from_tool_calls(self, tool_calls: List[ToolCall], reasoning: str = "") -> TaskPlan:
        steps: List[TaskStep] = []
        for tc in tool_calls:
            steps.append(
                TaskStep(
                    tool_name=tc.name,
                    arguments=tc.arguments,
                    tool_call_id=tc.id,
                    description=f"调用 {tc.name}",
                )
            )
        return TaskPlan(steps=steps, reasoning=reasoning)

    def build_context_message(self, scene_snapshot: Dict[str, Any]) -> str:
        """Build the current scene context message so the LLM can perceive
        the scene state. 构建当前场景上下文消息，供 LLM 感知场景状态。"""
        objs = scene_snapshot.get("objects", [])
        lights = scene_snapshot.get("lights", [])
        groups = scene_snapshot.get("groups", [])
        bg = scene_snapshot.get("background", "#0a0a0f")
        lines = [
            f"当前场景状态：{len(objs)} 个对象，{len(lights)} 盏灯光，"
            f"背景色 {bg}。"
        ]
        for o in objs:
            geo = o.get("geometry", {})
            tf = o.get("transform", {})
            mat = o.get("material", {})
            pos = tf.get("position", [0, 0, 0])
            scale = tf.get("scale", [1, 1, 1])
            color = mat.get("color", "#cccccc")
            metal = mat.get("metalness", 0)
            rough = mat.get("roughness", 0.5)
            lines.append(
                f"  - {o.get('name')}（id={o.get('id')}，{geo.get('type')}）"
                f" 位置=({pos[0]:.2f},{pos[1]:.2f},{pos[2]:.2f})"
                f" 缩放=({scale[0]:.2f},{scale[1]:.2f},{scale[2]:.2f})"
                f" 材质={color} 金属={metal:.2f} 粗糙={rough:.2f}"
            )
        for l in lights:
            lines.append(
                f"  - {l.get('name')}（{l.get('type')}，强度={l.get('intensity')}，"
                f"颜色={l.get('color')}）"
            )
        for g in groups:
            lines.append(
                f"  - 分组 {g.get('name')}（id={g.get('id')}，"
                f"成员 {len(g.get('child_ids', []))} 个）"
            )
        return "\n".join(lines)
