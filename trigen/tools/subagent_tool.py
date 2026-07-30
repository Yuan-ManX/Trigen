"""Sub-agent dispatch tool.

Spawns an isolated, single-turn LLM conversation that receives a read-only
snapshot of the current scene (compact summary, no mutation) and a task
prompt from the caller. The sub-agent's reply is returned as the tool's
text result — it never touches the scene directly, so the main agent's
memory and scene state stay clean.

Use cases: delegate analysis tasks ("describe the visual balance of this
scene"), generate naming suggestions, propose a color palette, or run a
quick sanity check on a planned composition before committing edits.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from trigen.config import LLMConfig
from trigen.llm.client import LLMClient
from trigen.scene import Scene
from trigen.tools.base import ToolBase, ToolResult

logger = logging.getLogger("trigen.tools.subagent")


_SUBAGENT_SYSTEM = (
    "You are a focused Trigen sub-agent. You receive a read-only snapshot of "
    "the current 3D scene and a specific task from the orchestrating agent. "
    "Analyze, suggest, or reason about the scene as requested. You cannot "
    "modify the scene directly — return a concise, actionable text answer. "
    "Stay on-topic and do not ask follow-up questions."
)

_SUBAGENT_PARAMS = {
    "type": "object",
    "properties": {
        "task": {
            "type": "string",
            "description": "The instruction for the sub-agent (e.g. 'evaluate the lighting balance' "
            "or 'suggest a color palette for the remaining objects').",
        },
        "model": {
            "type": "string",
            "description": "Optional model id to use for the sub-agent. If omitted, the default "
            "configured model is used.",
        },
    },
    "required": ["task"],
}


class DispatchSubagentTool(ToolBase):
    """Dispatch a read-only sub-agent conversation.

    The sub-agent runs a single non-streaming ``complete()`` call with a
    compact scene summary injected as context. It does not have access to
    tools and cannot mutate the scene — its text reply is returned to the
    main agent, which decides what to do with it.
    """

    name = "dispatch_subagent"
    description = (
        "Dispatch a read-only sub-agent to analyze the current scene or "
        "reason about a task. The sub-agent receives a compact scene summary "
        "and returns a text answer; it cannot modify the scene. Use for "
        "analysis, suggestions, or sanity checks."
    )

    def __init__(self, config: Optional[LLMConfig] = None) -> None:
        self.llm_config = config or LLMConfig()

    def schema(self) -> Dict[str, Any]:
        return _SUBAGENT_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        task = arguments.get("task", "").strip()
        if not task:
            return ToolResult(success=False, message="Missing 'task' argument for sub-agent.")

        model = arguments.get("model") or None
        client = LLMClient(self.llm_config)

        # Build a compact, read-only scene summary so the sub-agent has
        # context without seeing the full scene JSON.
        scene_dict = scene.to_dict()
        obj_lines: list[str] = []
        for obj in scene_dict.get("objects", []):
            geo = obj.get("geometry", {})
            mat = obj.get("material", {})
            pos = obj.get("transform", {}).get("position", [0, 0, 0])
            obj_lines.append(
                f"- {obj.get('name','?')} ({geo.get('type','?')}) "
                f"color={mat.get('color','?')} pos={pos}"
            )
        light_lines: list[str] = []
        for light in scene_dict.get("lights", []):
            light_lines.append(
                f"- {light.get('name','?')} ({light.get('type','?')}) "
                f"intensity={light.get('intensity','?')}"
            )
        summary = (
            f"Scene summary: {len(obj_lines)} objects, {len(light_lines)} lights, "
            f"background={scene_dict.get('background','?')}\n"
            f"Objects:\n" + ("\n".join(obj_lines) if obj_lines else "(empty)") + "\n"
            f"Lights:\n" + ("\n".join(light_lines) if light_lines else "(empty)")
        )

        messages = [
            {"role": "system", "content": _SUBAGENT_SYSTEM},
            {"role": "user", "content": f"{summary}\n\nTask: {task}"},
        ]

        try:
            response = await client.complete(messages=messages, system=_SUBAGENT_SYSTEM, model=model)
        except Exception as exc:
            logger.exception("Sub-agent complete() failed")
            return ToolResult(success=False, message=f"Sub-agent call failed: {exc}")

        content = response.content or ""
        if response.finish_reason == "error":
            return ToolResult(success=False, message=f"Sub-agent error: {content}")

        return ToolResult(
            success=True,
            message=content,
            data={
                "task": task,
                "model": model or self.llm_config.model,
                "finish_reason": response.finish_reason,
            },
        )
