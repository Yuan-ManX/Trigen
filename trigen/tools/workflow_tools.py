"""Workflow tools — save, invoke, list, delete Agentic Workflow Templates.

A Workflow is a saveable, named tool-graph recipe: an ordered sequence of
(tool, arguments) steps. ``save_workflow`` records a new recipe;
``invoke_workflow`` replays it through the same executor pipeline used
for normal tool calls, emitting the merged SceneDelta stream;
``list_workflows`` / ``delete_workflow`` manage the catalog. The store
persists to ``workflows.json`` in the workspace so recipes survive
restarts.

Each step is a single Agent tool call, and invoking the workflow runs the
steps sequentially against the live scene.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from trigen.scene import Scene
from trigen.tools.base import SceneDelta, ToolBase, ToolRegistry, ToolResult
from trigen.workflows import Workflow, WorkflowStep, workflow_store

logger = logging.getLogger("trigen.tools.workflow")


_SAVE_WORKFLOW_PARAMS = {
    "type": "object",
    "properties": {
        "name": {
            "type": "string",
            "description": "Unique workflow name (lowercase, underscore-separated)",
        },
        "description": {
            "type": "string",
            "description": "Human-readable summary of what the workflow accomplishes",
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


_INVOKE_WORKFLOW_PARAMS = {
    "type": "object",
    "properties": {
        "name": {
            "type": "string",
            "description": "Name of the previously saved workflow to replay",
        },
    },
    "required": ["name"],
}


_LIST_WORKFLOWS_PARAMS = {
    "type": "object",
    "properties": {},
    "required": [],
}


_DELETE_WORKFLOW_PARAMS = {
    "type": "object",
    "properties": {
        "name": {
            "type": "string",
            "description": "Name of the workflow to delete",
        },
    },
    "required": ["name"],
}


def _normalize_workflow_name(name: str) -> str:
    """Normalize a workflow name to lowercase with underscores/hyphens."""
    return name.strip().lower().replace(" ", "_")


class SaveWorkflowTool(ToolBase):
    """Save a new Agentic Workflow Template from an ordered tool-call sequence."""

    name = "save_workflow"
    description = (
        "Save a reusable Agentic Workflow Template (named tool-call sequence) "
        "that can be invoked later by name."
    )

    def schema(self) -> Dict[str, Any]:
        return _SAVE_WORKFLOW_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        raw_name = str(arguments.get("name", "")).strip()
        if not raw_name:
            return ToolResult(success=False, message="Missing 'name' argument")
        name = _normalize_workflow_name(raw_name)
        description = str(arguments.get("description", "")).strip()
        raw_steps = arguments.get("steps")
        if not isinstance(raw_steps, list) or not raw_steps:
            return ToolResult(success=False, message="'steps' must be a non-empty array")

        steps: List[WorkflowStep] = []
        for i, step in enumerate(raw_steps):
            if not isinstance(step, dict):
                return ToolResult(success=False, message=f"Step {i + 1} must be an object")
            tool_name = str(step.get("tool", "")).strip()
            if not tool_name:
                return ToolResult(success=False, message=f"Step {i + 1} missing 'tool'")
            step_args = step.get("arguments")
            if not isinstance(step_args, dict):
                step_args = {}
            steps.append(WorkflowStep(tool=tool_name, arguments=dict(step_args)))

        workflow = Workflow(
            name=name,
            description=description,
            steps=steps,
        )
        collection = workflow_store.get()
        collection.workflows[name] = workflow
        workflow_store.save()
        return ToolResult(
            success=True,
            message=f"Workflow '{name}' saved with {len(steps)} step(s)",
            data={"name": name, "steps": len(steps), "description": description},
        )


class InvokeWorkflowTool(ToolBase):
    """Invoke a previously saved Agentic Workflow Template by name."""

    name = "invoke_workflow"
    description = (
        "Invoke a previously saved Agentic Workflow Template by name, replaying "
        "its tool-call sequence against the live scene."
    )

    def __init__(self, registry: Optional[ToolRegistry] = None):
        self._registry = registry

    def schema(self) -> Dict[str, Any]:
        return _INVOKE_WORKFLOW_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        raw_name = str(arguments.get("name", "")).strip()
        if not raw_name:
            return ToolResult(success=False, message="Missing 'name' argument")
        name = _normalize_workflow_name(raw_name)

        collection = workflow_store.get()
        workflow = collection.workflows.get(name)
        if workflow is None:
            available = sorted(collection.workflows.keys())
            return ToolResult(
                success=False,
                message=f"Unknown workflow '{name}'. Available: {', '.join(available) or '(none)'}",
            )

        # Resolve the tool registry: prefer the injected one, otherwise build
        # a default registry on the fly (used by direct execution tests).
        registry = self._registry
        if registry is None:
            try:
                from trigen.orchestrator import AgentOrchestrator
                registry = AgentOrchestrator().registry
            except Exception:
                logger.exception("Failed to build fallback orchestrator registry for workflow invocation")
                return ToolResult(success=False, message="Tool registry unavailable")

        # Validate that every step's tool exists before executing.
        missing = [s.tool for s in workflow.steps if registry.get(s.tool) is None]
        if missing:
            return ToolResult(
                success=False,
                message=f"Workflow '{name}' references unknown tool(s): {', '.join(missing)}",
            )

        # Execute steps through the executor (lazy import to avoid circular dependency).
        from trigen.executor import TaskExecutor
        from trigen.planner import TaskPlan, TaskStep

        task_steps: List[TaskStep] = [
            TaskStep(
                tool_name=s.tool,
                arguments=dict(s.arguments),
                tool_call_id=f"workflow_{name}_{i}",
                description=f"Workflow {name} step {i + 1}",
            )
            for i, s in enumerate(workflow.steps)
        ]
        plan = TaskPlan(steps=task_steps, reasoning=f"Invoke workflow {name}")
        executor = TaskExecutor(registry, parallel=False)
        try:
            results = await executor.execute_plan(scene, plan)
        except Exception as exc:
            logger.exception("Workflow %s execution failed", name)
            return ToolResult(success=False, message=f"Workflow '{name}' execution failed: {exc}")

        deltas: List[SceneDelta] = executor.collect_deltas(results)
        succeeded = sum(1 for r in results if r.success)
        failed = len(results) - succeeded

        # Bump the use counter and persist.
        workflow.uses += 1
        workflow_store.save()

        message = f"Workflow '{name}' executed {len(results)} step(s): {succeeded} succeeded, {failed} failed"
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


class ListWorkflowsTool(ToolBase):
    """List all saved Agentic Workflow Templates with step counts and use counts."""

    name = "list_workflows"
    description = "List all saved Agentic Workflow Templates in the workspace with step counts and use counts."

    def schema(self) -> Dict[str, Any]:
        return _LIST_WORKFLOWS_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        collection = workflow_store.get()
        items = [
            {
                "name": w.name,
                "description": w.description,
                "steps": len(w.steps),
                "uses": w.uses,
            }
            for w in sorted(collection.workflows.values(), key=lambda x: x.name)
        ]
        if not items:
            return ToolResult(
                success=True,
                message="No workflows saved yet",
                data={"workflows": [], "count": 0},
            )
        summary = ", ".join(f"{w['name']} ({w['steps']} steps)" for w in items)
        return ToolResult(
            success=True,
            message=f"{len(items)} workflow(s): {summary}",
            data={"workflows": items, "count": len(items)},
        )


class DeleteWorkflowTool(ToolBase):
    """Delete an Agentic Workflow Template by name."""

    name = "delete_workflow"
    description = "Delete a previously saved Agentic Workflow Template by name."

    def schema(self) -> Dict[str, Any]:
        return _DELETE_WORKFLOW_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        raw_name = str(arguments.get("name", "")).strip()
        if not raw_name:
            return ToolResult(success=False, message="Missing 'name' argument")
        name = _normalize_workflow_name(raw_name)
        collection = workflow_store.get()
        if name not in collection.workflows:
            return ToolResult(success=False, message=f"Workflow '{name}' not found")
        del collection.workflows[name]
        workflow_store.save()
        return ToolResult(
            success=True,
            message=f"Workflow '{name}' deleted",
            data={"name": name},
        )
