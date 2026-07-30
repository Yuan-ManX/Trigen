"""Lifecycle hook registry for the Agent orchestrator.

External code (telemetry, logging, audit, integrations) can register
callbacks that fire at well-defined points in a conversation turn
without touching the orchestrator's core loop. Hooks are observers
only: they receive an immutable payload dict and cannot alter the
flow or mutate the event stream. A failing hook is logged and skipped
so a misbehaving integration can never break a turn.

Hook events
-----------
- ``BEFORE_TURN``   — fired once at the start of ``run()``.
- ``AFTER_TURN``    — fired once when the DONE event is emitted.
- ``TOOL_CALL``     — fired for every TOOL_CALL event.
- ``TOOL_RESULT``   — fired for every TOOL_RESULT event.
- ``SCENE_UPDATE``  — fired for every SCENE_UPDATE event.
- ``ERROR``         — fired for every ERROR event.

Callbacks may be sync or async. The registry awaits coroutine results
and runs sync callbacks inline. Registration returns an integer id that
``unregister`` accepts.
"""

from __future__ import annotations

import inspect
import logging
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("trigen.hooks")


class HookEvent(str, Enum):
    """Lifecycle events a hook can subscribe to."""

    BEFORE_TURN = "before_turn"
    AFTER_TURN = "after_turn"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    SCENE_UPDATE = "scene_update"
    ERROR = "error"


HookCallback = Callable[[Dict[str, Any]], Any]


class HookRegistry:
    """Holds hook callbacks per event and fires them safely.

    A single registry instance lives on each ``AgentOrchestrator``
    (``orchestrator.hooks``); external code registers against that
    instance.
    """

    def __init__(self) -> None:
        self._hooks: Dict[HookEvent, List[HookCallback]] = {e: [] for e in HookEvent}
        self._counter = 0

    def register(self, event: HookEvent, callback: HookCallback) -> int:
        """Register a callback for ``event``. Returns an id for unregister."""
        self._counter += 1
        callback._trigen_hook_id = self._counter  # type: ignore[attr-defined]
        self._hooks[event].append(callback)
        return self._counter

    def unregister(self, hook_id: int) -> bool:
        """Remove a previously registered callback by its id."""
        for event, callbacks in self._hooks.items():
            for i, cb in enumerate(callbacks):
                if getattr(cb, "_trigen_hook_id", None) == hook_id:
                    callbacks.pop(i)
                    return True
        return False

    def clear(self, event: Optional[HookEvent] = None) -> int:
        """Drop callbacks for one event (or all when ``event`` is None)."""
        if event is not None:
            n = len(self._hooks[event])
            self._hooks[event] = []
            return n
        n = sum(len(v) for v in self._hooks.values())
        self._hooks = {e: [] for e in HookEvent}
        return n

    def count(self, event: Optional[HookEvent] = None) -> int:
        if event is not None:
            return len(self._hooks[event])
        return sum(len(v) for v in self._hooks.values())

    async def fire(self, event: HookEvent, payload: Dict[str, Any]) -> None:
        """Fire every callback for ``event``.

        Sync callbacks run inline; async callbacks are awaited. Any
        exception raised by a callback is logged and swallowed so the
        orchestrator's turn is never disrupted by a faulty hook.
        """
        callbacks = list(self._hooks.get(event, []))
        for cb in callbacks:
            try:
                result = cb(payload)
                if inspect.isawaitable(result):
                    await result
            except Exception as exc:  # pragma: no cover — defensive
                logger.warning("Hook %s for %s failed: %s", cb, event.value, exc)
