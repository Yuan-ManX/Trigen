"""Macro tools — define, invoke, list, delete reusable tool-call sequences.

Macros are user-defined recipes captured as ordered (tool, arguments)
steps. ``define_macro`` records a new recipe; ``invoke_macro`` replays it
through the same executor pipeline used for normal tool calls. The store
persists to ``macros.json`` in the workspace so recipes survive restarts.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from trigen.scene import Scene
from trigen.tools.base import SceneDelta, ToolBase, ToolRegistry, ToolResult
from trigen.macros import Macro, MacroStep, macro_store

logger = logging.getLogger("trigen.tools.macro")


_DEFINE_MACRO_PARAMS = {
    "type": "object",
    "properties": {
        "name": {
            "type": "string",
            "description": "Unique macro name (lowercase, underscore-separated)",
        },
        "description": {
            "type": "string",
            "description": "Human-readable summary of what the macro does",
        },
        "steps": {
            "type": "array",
            "description": "Ordered tool-call steps to replay on invoke",
            "items": {
                "type": "object",
                "properties": {
                    "tool": {"type": "string", "description": "Tool name"},
                    "arguments": {
                        "type": "object",
                        "description": "Arguments to pass to the tool",
                        "additionalProperties": True,
                    },
                },
                "required": ["tool", "arguments"],
            },
        },
    },
    "required": ["name", "steps"],
}


_INVOKE_MACRO_PARAMS = {
    "type": "object",
    "properties": {
        "name": {
            "type": "string",
            "description": "Name of the previously defined macro to replay",
        },
    },
    "required": ["name"],
}


_LIST_MACROS_PARAMS = {
    "type": "object",
    "properties": {},
    "required": [],
}


_DELETE_MACRO_PARAMS = {
    "type": "object",
    "properties": {
        "name": {
            "type": "string",
            "description": "Name of the macro to delete",
        },
    },
    "required": ["name"],
}


def _normalize_macro_name(name: str) -> str:
    """Normalize a macro name to lowercase with underscores/hyphens."""
    return name.strip().lower().replace(" ", "_")


class DefineMacroTool(ToolBase):
    """Define a new reusable macro from an ordered tool-call sequence."""

    name = "define_macro"
    description = "Define a reusable named macro (tool-call recipe) that can be invoked later by name."

    def schema(self) -> Dict[str, Any]:
        return _DEFINE_MACRO_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        raw_name = str(arguments.get("name", "")).strip()
        if not raw_name:
            return ToolResult(success=False, message="Missing 'name' argument")
        name = _normalize_macro_name(raw_name)
        description = str(arguments.get("description", "")).strip()
        raw_steps = arguments.get("steps")
        if not isinstance(raw_steps, list) or not raw_steps:
            return ToolResult(success=False, message="'steps' must be a non-empty array")

        steps: List[MacroStep] = []
        for i, step in enumerate(raw_steps):
            if not isinstance(step, dict):
                return ToolResult(success=False, message=f"Step {i + 1} must be an object")
            tool_name = str(step.get("tool", "")).strip()
            if not tool_name:
                return ToolResult(success=False, message=f"Step {i + 1} missing 'tool'")
            step_args = step.get("arguments")
            if not isinstance(step_args, dict):
                step_args = {}
            steps.append(MacroStep(tool=tool_name, arguments=dict(step_args)))

        macro = Macro(
            name=name,
            description=description,
            steps=steps,
        )
        collection = macro_store.get()
        collection.macros[name] = macro
        macro_store.save()
        return ToolResult(
            success=True,
            message=f"Macro '{name}' defined with {len(steps)} step(s)",
            data={"name": name, "steps": len(steps), "description": description},
        )


class InvokeMacroTool(ToolBase):
    """Invoke a previously defined macro by name, replaying its steps."""

    name = "invoke_macro"
    description = "Invoke a previously defined macro by name, replaying its tool-call sequence."

    def __init__(self, registry: Optional[ToolRegistry] = None):
        self._registry = registry

    def schema(self) -> Dict[str, Any]:
        return _INVOKE_MACRO_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        raw_name = str(arguments.get("name", "")).strip()
        if not raw_name:
            return ToolResult(success=False, message="Missing 'name' argument")
        name = _normalize_macro_name(raw_name)

        collection = macro_store.get()
        macro = collection.macros.get(name)
        if macro is None:
            available = sorted(collection.macros.keys())
            return ToolResult(
                success=False,
                message=f"Unknown macro '{name}'. Available: {', '.join(available) or '(none)'}",
            )

        # Resolve the tool registry: prefer the injected one, otherwise build
        # a default registry on the fly (used by direct execution tests).
        registry = self._registry
        if registry is None:
            try:
                from trigen.orchestrator import AgentOrchestrator
                registry = AgentOrchestrator().registry
            except Exception:
                logger.exception("Failed to build fallback orchestrator registry for macro invocation")
                return ToolResult(success=False, message="Tool registry unavailable")

        # Validate that every step's tool exists before executing.
        missing = [s.tool for s in macro.steps if registry.get(s.tool) is None]
        if missing:
            return ToolResult(
                success=False,
                message=f"Macro '{name}' references unknown tool(s): {', '.join(missing)}",
            )

        # Execute steps through the executor (lazy import to avoid circular dependency).
        from trigen.executor import TaskExecutor
        from trigen.planner import TaskPlan, TaskStep

        task_steps: List[TaskStep] = [
            TaskStep(
                tool_name=s.tool,
                arguments=dict(s.arguments),
                tool_call_id=f"macro_{name}_{i}",
                description=f"Macro {name} step {i + 1}",
            )
            for i, s in enumerate(macro.steps)
        ]
        plan = TaskPlan(steps=task_steps, reasoning=f"Invoke macro {name}")
        executor = TaskExecutor(registry, parallel=False)
        try:
            results = await executor.execute_plan(scene, plan)
        except Exception as exc:
            logger.exception("Macro %s execution failed", name)
            return ToolResult(success=False, message=f"Macro '{name}' execution failed: {exc}")

        deltas: List[SceneDelta] = executor.collect_deltas(results)
        succeeded = sum(1 for r in results if r.success)
        failed = len(results) - succeeded

        # Bump the use counter and persist.
        macro.uses += 1
        macro_store.save()

        message = f"Macro '{name}' executed {len(results)} step(s): {succeeded} succeeded, {failed} failed"
        return ToolResult(
            success=failed == 0,
            message=message,
            deltas=deltas,
            data={
                "name": name,
                "steps": len(results),
                "succeeded": succeeded,
                "failed": failed,
                "step_messages": [r.message for r in results],
            },
        )


class ListMacrosTool(ToolBase):
    """List all defined macros with their step counts and use counts."""

    name = "list_macros"
    description = "List all defined macros in the workspace with step counts and use counts."

    def schema(self) -> Dict[str, Any]:
        return _LIST_MACROS_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        collection = macro_store.get()
        items = [
            {
                "name": m.name,
                "description": m.description,
                "steps": len(m.steps),
                "uses": m.uses,
            }
            for m in sorted(collection.macros.values(), key=lambda x: x.name)
        ]
        if not items:
            return ToolResult(
                success=True,
                message="No macros defined yet",
                data={"macros": [], "count": 0},
            )
        summary = ", ".join(f"{m['name']} ({m['steps']} steps)" for m in items)
        return ToolResult(
            success=True,
            message=f"{len(items)} macro(s): {summary}",
            data={"macros": items, "count": len(items)},
        )


class DeleteMacroTool(ToolBase):
    """Delete a macro by name."""

    name = "delete_macro"
    description = "Delete a previously defined macro by name."

    def schema(self) -> Dict[str, Any]:
        return _DELETE_MACRO_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        raw_name = str(arguments.get("name", "")).strip()
        if not raw_name:
            return ToolResult(success=False, message="Missing 'name' argument")
        name = _normalize_macro_name(raw_name)
        collection = macro_store.get()
        if name not in collection.macros:
            return ToolResult(success=False, message=f"Macro '{name}' not found")
        del collection.macros[name]
        macro_store.save()
        return ToolResult(
            success=True,
            message=f"Macro '{name}' deleted",
            data={"name": name},
        )
