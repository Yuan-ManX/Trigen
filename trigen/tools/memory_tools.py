"""Agent explicit-memory tools.

Lets the Agent pin user-scoped facts it wants to remember across turns
and sessions (e.g. "the user is building a forest scene", "prefers
low-poly aesthetics", "the target platform is mobile"). Pinned facts
are injected into the LLM system note via the episodic memory store,
so they influence every subsequent turn without the user having to
repeat themselves.

These tools do not mutate the scene — they read/write the process-local
episodic memory store, which persists to a JSON file under the workspace.

1. ``PinFactTool`` — pin (or refresh) a fact the Agent chooses to remember.
2. ``RecallFactsTool`` — list pinned facts, optionally filtered by category.
3. ``ForgetFactTool`` — remove a single pinned fact by text, or clear a
   whole category.

All three follow the standard ``ToolBase`` contract.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from trigen.scene import Scene
from trigen.tools.base import ToolBase, ToolResult
from trigen.episodic_memory import store as episodic_store


_PIN_FACT_PARAMS = {
    "type": "object",
    "properties": {
        "text": {
            "type": "string",
            "description": (
                "The fact to remember, phrased as a concise statement. "
                "Examples: 'User is building a forest scene for a game.', "
                "'Prefers low-poly aesthetics.', 'Target platform is mobile WebGL.'. "
                "Will be deduplicated case-insensitively."
            ),
        },
        "category": {
            "type": "string",
            "description": (
                "Optional category bucket. Suggested values: 'project', "
                "'preference', 'constraint', 'style', 'audience', 'general'. "
                "Defaults to 'general'."
            ),
        },
    },
    "required": ["text"],
}


_RECALL_FACTS_PARAMS = {
    "type": "object",
    "properties": {
        "category": {
            "type": "string",
            "description": (
                "Optional category filter. If omitted, all pinned facts are returned. "
                "Common categories: 'project', 'preference', 'constraint', 'style', "
                "'audience', 'general'."
            ),
        },
        "limit": {
            "type": "integer",
            "description": "Optional cap on the number of facts returned (default 20).",
        },
    },
}


_FORGET_FACT_PARAMS = {
    "type": "object",
    "properties": {
        "text": {
            "type": "string",
            "description": (
                "The exact text of the fact to remove (case-insensitive match). "
                "If omitted, the entire ``category`` bucket is cleared."
            ),
        },
        "category": {
            "type": "string",
            "description": (
                "When ``text`` is omitted, clear every fact in this category. "
                "Ignored when ``text`` is supplied."
            ),
        },
    },
}


class PinFactTool(ToolBase):
    """Pin an explicit fact the Agent wants to remember across turns.

    The fact is persisted into the workspace's episodic memory file and
    surfaced to the LLM on subsequent turns as a system note. Use this
    when the user states a durable preference, project context, or
    constraint the Agent should respect for the rest of the session
    (and future sessions). Read-only with respect to the scene.
    """

    name = "pin_fact"
    description = (
        "Pin a durable fact about the user or project that the Agent should "
        "remember across turns and sessions — e.g. 'User is building a forest "
        "scene for a mobile game', 'Prefers low-poly aesthetics', 'Target "
        "platform is mobile WebGL'. Pinned facts are injected into the "
        "Agent's system context on every subsequent turn so the user does "
        "not have to repeat themselves. Use this whenever the user states a "
        "long-lived preference, constraint, or project context. Does not "
        "mutate the scene."
    )

    def schema(self) -> Dict[str, Any]:
        return _PIN_FACT_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        text = str(arguments.get("text", "")).strip()
        if not text:
            return ToolResult(
                success=False,
                message="pin_fact requires non-empty 'text'.",
                deltas=[],
                data={},
            )
        category = str(arguments.get("category", "general") or "general").strip()
        try:
            mem = episodic_store.get()
            fact = mem.add_fact(text, category)
            episodic_store.save()
        except Exception as exc:
            return ToolResult(
                success=False,
                message=f"Failed to pin fact: {exc}",
                deltas=[],
                data={},
            )
        return ToolResult(
            success=True,
            message=f"Pinned fact [{fact.category}]: {fact.text}",
            deltas=[],
            data={
                "fact": fact.to_dict(),
                "total_facts": len(mem.pinned_facts),
            },
        )


class RecallFactsTool(ToolBase):
    """List pinned facts the Agent has chosen to remember.

    Returns facts newest-first, optionally filtered by category. Use this
    at the start of a turn when the user references a prior preference or
    when the Agent needs to ground its reasoning in long-lived context.
    Read-only.
    """

    name = "recall_facts"
    description = (
        "List the pinned facts the Agent has explicitly chosen to remember "
        "across turns and sessions. Returns each fact's text, category, and "
        "pin timestamp, newest-first. Optionally filter by category. Use "
        "this when the user references a prior preference ('you know, the "
        "forest thing') or when grounding a creative decision in long-lived "
        "context. Does not mutate the scene."
    )

    def schema(self) -> Dict[str, Any]:
        return _RECALL_FACTS_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        category = arguments.get("category")
        category_str: Optional[str] = str(category).strip() if category else None
        try:
            limit_raw = arguments.get("limit")
            limit = int(limit_raw) if limit_raw is not None else 20
        except (TypeError, ValueError):
            limit = 20
        limit = max(1, min(100, limit))
        try:
            mem = episodic_store.get()
            facts = mem.list_facts(category_str)
        except Exception as exc:
            return ToolResult(
                success=False,
                message=f"Failed to recall facts: {exc}",
                deltas=[],
                data={},
            )
        trimmed: List[Dict[str, Any]] = [f.to_dict() for f in facts[:limit]]
        return ToolResult(
            success=True,
            message=f"Recalled {len(trimmed)} pinned fact(s)"
            + (f" in category '{category_str}'" if category_str else "")
            + ".",
            deltas=[],
            data={
                "facts": trimmed,
                "count": len(trimmed),
                "total": len(facts),
                "category": category_str,
            },
        )


class ForgetFactTool(ToolBase):
    """Remove a pinned fact by text, or clear a whole category.

    Useful when the user explicitly retracts a preference ('actually, I
    don't care about mobile anymore') or asks the Agent to forget
    something. Read-only with respect to the scene.
    """

    name = "forget_fact"
    description = (
        "Remove a pinned fact the Agent previously remembered. Either supply "
        "'text' (case-insensitive exact match) to remove a single fact, or "
        "supply 'category' (with no 'text') to clear every fact in that "
        "category. Use this when the user retracts a preference or asks the "
        "Agent to forget something. Does not mutate the scene."
    )

    def schema(self) -> Dict[str, Any]:
        return _FORGET_FACT_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        text = str(arguments.get("text", "")).strip()
        category = str(arguments.get("category", "") or "").strip()
        try:
            mem = episodic_store.get()
            if text:
                removed = mem.remove_fact(text)
                if not removed:
                    return ToolResult(
                        success=True,
                        message=f"No pinned fact matched: {text!r}",
                        deltas=[],
                        data={"removed": False, "text": text},
                    )
                episodic_store.save()
                return ToolResult(
                    success=True,
                    message=f"Forgot fact: {text}",
                    deltas=[],
                    data={"removed": True, "text": text, "remaining": len(mem.pinned_facts)},
                )
            # No text — clear by category (or all when category is empty).
            cleared = mem.clear_facts(category or None)
            episodic_store.save()
            scope = f"category '{category}'" if category else "all categories"
            return ToolResult(
                success=True,
                message=f"Cleared {cleared} fact(s) from {scope}.",
                deltas=[],
                data={"removed": cleared, "category": category or None},
            )
        except Exception as exc:
            return ToolResult(
                success=False,
                message=f"Failed to forget fact: {exc}",
                deltas=[],
                data={},
            )


__all__ = [
    "PinFactTool",
    "RecallFactsTool",
    "ForgetFactTool",
]
