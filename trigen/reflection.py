"""Durable per-session reflection store.

Every chat turn already produces a short end-of-turn narrative written by
the orchestrator (the ``reflection`` thinking phase: what the Agent built,
what failed, the resulting scene, and what it would try next). That text is
streamed to the UI but discarded on process exit. This module captures those
reflections as structured, queryable records so the Agent's self-assessment
becomes a durable learning surface:

  - ``GET /agent/reflection/{session_id}`` inspects every turn's reflection.
  - The ``reflect_on_session`` tool summarises recent reflections so the
    Agent can ground its next reply in what it learned from prior turns.

The store is a process-local ring buffer (like ``TraceStore``): per-session
entries are capped and oldest evicted. It is intentionally not persisted —
reflections describe a live editing session and are reset on restart.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger("trigen.reflection")

# Hard cap on reflections kept per session. Typical edits span a handful of
# turns; a generous cap keeps the most recent history without unbounded growth.
DEFAULT_MAX_PER_SESSION = 40


class SessionReflection:
    """A structured record of one completed turn's self-assessment."""

    __slots__ = ("turn", "goal", "tool_calls", "outcome", "quality", "elapsed", "ts")

    def __init__(
        self,
        turn: int,
        goal: str,
        tool_calls: List[str],
        outcome: str,
        quality: Dict[str, Any],
        elapsed: float,
    ) -> None:
        self.turn = turn
        self.goal = goal
        self.tool_calls = tool_calls
        self.outcome = outcome
        self.quality = quality
        self.elapsed = elapsed
        self.ts = time.time()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "turn": self.turn,
            "goal": self.goal,
            "tool_calls": list(self.tool_calls),
            "outcome": self.outcome,
            "quality": dict(self.quality or {}),
            "elapsed": self.elapsed,
            "ts": self.ts,
        }


class ReflectionStore:
    """Bounded, thread-safe, per-session store of turn reflections."""

    def __init__(self, max_per_session: int = DEFAULT_MAX_PER_SESSION) -> None:
        self._max = max_per_session
        self._items: Dict[str, List[SessionReflection]] = {}
        self._lock = threading.Lock()

    def record(
        self,
        session_id: str,
        turn: int,
        goal: str,
        tool_calls: List[str],
        outcome: str,
        quality: Dict[str, Any],
        elapsed: float,
    ) -> None:
        """Append one reflection, evicting the oldest when over capacity."""
        if not session_id:
            return
        refl = SessionReflection(turn, goal, tool_calls, outcome, quality, elapsed)
        with self._lock:
            buf = self._items.setdefault(session_id, [])
            buf.append(refl)
            while len(buf) > self._max:
                buf.pop(0)

    def get(
        self,
        session_id: str,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Return reflections for ``session_id``, newest first."""
        with self._lock:
            buf = list(self._items.get(session_id, []))
        buf.reverse()
        if limit is not None and limit >= 0:
            buf = buf[:limit]
        return [r.to_dict() for r in buf]

    def summary(self, session_id: str) -> Dict[str, Any]:
        """Compact status probe for the session, without transferring the log."""
        with self._lock:
            buf = self._items.get(session_id, [])
            count = len(buf)
            last_turn = buf[-1].turn if buf else 0
            total_tools = sum(len(r.tool_calls) for r in buf)
        return {
            "session_id": session_id,
            "count": count,
            "last_turn": last_turn,
            "total_tool_calls": total_tools,
            "max_per_session": self._max,
        }

    def sessions(self) -> List[Dict[str, Any]]:
        with self._lock:
            ids = list(self._items.keys())
        return [self.summary(sid) for sid in ids if self._items.get(sid)]

    def clear(self, session_id: Optional[str] = None) -> int:
        with self._lock:
            if session_id is None:
                removed = sum(len(v) for v in self._items.values())
                self._items.clear()
                return removed
            buf = self._items.pop(session_id, [])
            return len(buf)


# Module-level singleton, mirroring TraceStore / episodic store.
reflection_store = ReflectionStore()