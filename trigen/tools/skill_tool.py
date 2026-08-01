"""Skill invocation tool.

Wraps the creative skill library so the LLM and direct tool execution
endpoint can invoke a skill by name. The tool expands the skill's
build_steps output into ordered tool-call steps and runs them through
the executor, returning the aggregated result.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from trigen.scene import Scene
from trigen.skills import build_default_registry
from trigen.tools.base import SceneDelta, ToolBase, ToolRegistry, ToolResult

logger = logging.getLogger("trigen.tools.skill")


_INVOKE_SKILL_PARAMS = {
    "type": "object",
    "properties": {
        "skill": {
            "type": "string",
            "description": "Skill name (spiral_staircase / colonnade / forest / crystal_garden / dna_helix / spiral_galaxy / studio_lighting)",
        },
        "arguments": {
            "type": "object",
            "description": "Skill-specific parameters as defined by the skill schema",
            "additionalProperties": True,
        },
    },
    "required": ["skill"],
}


# Shared skill registry — built lazily on first access so the import cost
# is paid only when a skill is actually invoked.
_skill_registry = None


def _get_skill_registry():
    global _skill_registry
    if _skill_registry is None:
        _skill_registry = build_default_registry()
    return _skill_registry


class InvokeSkillTool(ToolBase):
    """Invoke a creative skill by name, expanding it into ordered tool steps.

    The tool holds a reference to the orchestrator's tool registry so it
    can execute the expanded steps through the same executor pipeline
    used for normal tool calls. When constructed without a registry (e.g.
    for schema enumeration), it lazily resolves one on first execute.
    """

    name = "invoke_skill"
    description = "Invoke a named creative skill (multi-tool recipe) such as spiral_staircase, colonnade, forest, crystal_garden, dna_helix, spiral_galaxy, or studio_lighting."

    def __init__(self, registry: Optional[ToolRegistry] = None):
        self._registry = registry

    def schema(self) -> Dict[str, Any]:
        return _INVOKE_SKILL_PARAMS

    @staticmethod
    def list_skills() -> List[Dict[str, Any]]:
        """Return the skill schemas for catalog endpoints."""
        return _get_skill_registry().schemas()

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        skill_name = str(arguments.get("skill", "")).strip()
        if not skill_name:
            return ToolResult(success=False, message="Missing 'skill' argument")

        skill_args = arguments.get("arguments")
        if not isinstance(skill_args, dict):
            skill_args = {}

        skill = _get_skill_registry().get(skill_name)
        if skill is None:
            available = [s.name for s in _get_skill_registry().all()]
            return ToolResult(
                success=False,
                message=f"Unknown skill '{skill_name}'. Available: {', '.join(available)}",
            )

        # Resolve the tool registry: prefer the injected one, otherwise build
        # a default registry on the fly (used by direct execution tests).
        registry = self._registry
        if registry is None:
            # Build a default registry that includes the core tools skills depend on
            from trigen.orchestrator import AgentOrchestrator
            try:
                orchestrator = AgentOrchestrator()
                registry = orchestrator.registry
            except Exception:
                logger.exception("Failed to build fallback orchestrator registry for skill invocation")
                return ToolResult(success=False, message="Skill registry unavailable")

        # Expand the skill into ordered steps
        try:
            id_prefix = f"{skill_name}_{__import__('uuid').uuid4().hex[:4]}_"
            steps: List[TaskStep] = skill.build_steps(skill_args, id_prefix=id_prefix)
        except Exception as exc:
            logger.exception("Skill %s build_steps failed", skill_name)
            return ToolResult(success=False, message=f"Skill '{skill_name}' expansion failed: {exc}")

        if not steps:
            return ToolResult(success=False, message=f"Skill '{skill_name}' produced no steps")

        # Execute steps through the executor (lazy import to avoid circular dependency)
        from trigen.executor import TaskExecutor
        from trigen.planner import TaskPlan

        executor = TaskExecutor(registry, parallel=True)
        plan = TaskPlan(steps=steps, reasoning=f"Invoke skill {skill_name}")
        try:
            results = await executor.execute_plan(scene, plan)
        except Exception as exc:
            logger.exception("Skill %s execution failed", skill_name)
            return ToolResult(success=False, message=f"Skill '{skill_name}' execution failed: {exc}")

        deltas: List[SceneDelta] = executor.collect_deltas(results)
        succeeded = sum(1 for r in results if r.success)
        failed = len(results) - succeeded
        message = f"Skill '{skill_name}' executed {len(results)} step(s): {succeeded} succeeded, {failed} failed"
        return ToolResult(
            success=failed == 0,
            message=message,
            deltas=deltas,
            data={
                "skill": skill_name,
                "steps": len(results),
                "succeeded": succeeded,
                "failed": failed,
                "step_messages": [r.message for r in results],
            },
        )
