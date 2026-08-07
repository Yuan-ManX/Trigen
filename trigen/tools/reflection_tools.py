"""Agent reflection tools.

Gives the Agent a durable memory of its own recent turns. Every completed
turn already produces a narrative self-assessment (``reflection`` thinking
phase) which ``AgentService.chat_stream`` folds into the per-session
reflection store. This tool lets the Agent read that history back so it can
ground its next reply in what it just did, what failed, and what it learned
— closing the loop between execution and reflection.

1. ``ReflectOnSessionTool`` — summarises the most recent turn reflections for
   a session (goals, tool chains, outcomes, quality verdicts) so the Agent
   can reason about its own trajectory and avoid repeating mistakes.

Read-only: never mutates the scene.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from trigen.scene import Scene
from trigen.tools.base import ToolBase, ToolResult


class ReflectOnSessionTool(ToolBase):
    """Read the Agent's durable turn reflections for a session."""

    name = "reflect_on_session"
    description = (
        "Read the Agent's own recent turn reflections for a session: the goals, "
        "the tool chains executed, the narrative outcomes, and the quality "
        "verdicts. Use this to ground your next reply in what you just did, "
        "what failed, and what you would do differently. Read-only."
    )
    category = "intelligence"

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "Session whose reflections to read. Defaults to 'default'.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max recent reflections to return (default 5, capped at 20).",
                },
            },
        }

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        from trigen.reflection import reflection_store

        session_id = str(arguments.get("session_id") or "default")
        try:
            limit = int(arguments.get("limit") or 5)
        except (TypeError, ValueError):
            limit = 5
        limit = max(1, min(limit, 20))

        entries = reflection_store.get(session_id, limit=limit)
        summary = reflection_store.summary(session_id)
        if not entries:
            return ToolResult(
                success=True,
                message=(
                    "No turn reflections recorded yet for this session. "
                    "Reflections are captured automatically after each completed turn."
                ),
                deltas=[],
                data={
                    "session_id": session_id,
                    "reflections": [],
                    "summary": summary,
                },
            )

        # Build a compact, legible summary the Agent can reason from.
        lines: List[str] = []
        for i, r in enumerate(entries, start=1):
            tools = ", ".join(r["tool_calls"]) or "none"
            verdict = (r.get("quality") or {}).get("verdict", "unknown")
            score = (r.get("quality") or {}).get("score", -1)
            outcome = (r.get("outcome") or "").strip()
            lines.append(
                f"{len(entries) - i + 1}. Goal: {r.get('goal', '')[:120]} | "
                f"Tools: {tools} | Verdict: {verdict} ({score}/100)"
                + (f" | {outcome[:160]}" if outcome else "")
            )

        return ToolResult(
            success=True,
            message=(
                f"Read {len(entries)} recent reflection(s) for session '{session_id}': "
                + "; ".join(lines)
            ),
            deltas=[],
            data={
                "session_id": session_id,
                "reflections": entries,
                "summary": summary,
                "digest": lines,
            },
        )