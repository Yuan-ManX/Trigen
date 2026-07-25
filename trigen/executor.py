"""Task executor.

Executes tool calls in planned order, collecting results and scene mutations,
supporting parallel batch execution and exception isolation.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List

from trigen.planner import TaskPlan, TaskStep
from trigen.scene import Scene
from trigen.tools.base import ToolRegistry, ToolResult, SceneDelta

logger = logging.getLogger("trigen.executor")


class TaskExecutor:
    """Sequentially (or batched-parallel) executes the tool calls in the task plan."""

    def __init__(self, registry: ToolRegistry, parallel: bool = True):
        self.registry = registry
        self.parallel = parallel

    async def execute_plan(self, scene: Scene, plan: TaskPlan) -> List[ToolResult]:
        if not self.parallel:
            return await self._execute_sequential(scene, plan)

        # Group steps into parallel-safe batches
        batches = self._group_batches(plan.steps)
        results: List[ToolResult] = []
        for batch in batches:
            if len(batch) == 1:
                results.append(await self._execute_step(scene, batch[0]))
            else:
                batch_results = await asyncio.gather(
                    *(self._execute_step(scene, step) for step in batch),
                    return_exceptions=False,
                )
                results.extend(batch_results)
        return results

    async def _execute_sequential(self, scene: Scene, plan: TaskPlan) -> List[ToolResult]:
        results: List[ToolResult] = []
        for step in plan.steps:
            results.append(await self._execute_step(scene, step))
        return results

    async def _execute_step(self, scene: Scene, step: TaskStep) -> ToolResult:
        tool = self.registry.get(step.tool_name)
        if tool is None:
            return ToolResult(success=False, message=f"Unknown tool: {step.tool_name}")
        try:
            result = await tool.execute(scene, step.arguments)
            logger.info(
                "Tool %s execution %s: %s",
                step.tool_name,
                "succeeded" if result.success else "failed",
                result.message,
            )
            return result
        except Exception as e:
            logger.exception("Tool %s execution exception", step.tool_name)
            return ToolResult(
                success=False,
                message=f"Tool {step.tool_name} execution exception: {e}",
            )

    def _group_batches(self, steps: List[TaskStep]) -> List[List[TaskStep]]:
        """Group consecutive parallel-safe steps into batches."""
        # Conservative: only batch steps that operate on distinct targets
        batches: List[List[TaskStep]] = []
        current: List[TaskStep] = []
        seen_targets = set()
        for step in steps:
            is_safe = step.tool_name in _PARALLEL_SAFE_TOOLS
            target = str(step.arguments.get("target", step.tool_name))
            conflict = target in seen_targets
            if is_safe and not conflict:
                current.append(step)
                seen_targets.add(target)
            else:
                if current:
                    batches.append(current)
                    current = []
                    seen_targets = set()
                batches.append([step])
        if current:
            batches.append(current)
        return batches

    def collect_deltas(self, results: List[ToolResult]) -> List[SceneDelta]:
        deltas: List[SceneDelta] = []
        for r in results:
            deltas.extend(r.deltas)
        return deltas


# Tools that can be safely executed in parallel within a single batch
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
