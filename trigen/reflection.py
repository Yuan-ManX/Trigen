"""Durable per-session reflection store.

Every chat turn already produces a short end-of-turn narrative written by
the orchestrator (the ``reflection`` thinking phase: what the Agent built,
what failed, the resulting scene, and what it would try next). That text is
streamed to the UI and captured here as structured, queryable records so the
Agent's self-assessment becomes a durable learning surface:

  - ``GET /agent/reflection/{session_id}`` inspects every turn's reflection.
  - The ``reflect_on_session`` tool summarises recent reflections so the
    Agent can ground its next reply in what it learned from prior turns.

The store is a per-session ring buffer (capped and oldest evicted) persisted
to ``<workspace>/reflections.json`` — the same durable file backing that the
episodic memory store uses — so reflections survive process restarts and can
be injected into later turns as a compact memory digest.
"""

from __future__ import annotations

import json
import logging
import os
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

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SessionReflection":
        """Rebuild a reflection from a persisted dict."""
        obj = cls(
            turn=int(data.get("turn", 0)),
            goal=str(data.get("goal", "")),
            tool_calls=list(data.get("tool_calls", []) or []),
            outcome=str(data.get("outcome", "")),
            quality=dict(data.get("quality", {}) or {}),
            elapsed=float(data.get("elapsed", 0.0)),
        )
        obj.ts = float(data.get("ts", obj.ts))
        return obj


class ReflectionStore:
    """Bounded, thread-safe, per-session store of turn reflections.

    Persisted to ``<workspace>/reflections.json`` so reflections survive
    process restarts and can be injected into later turns as a memory digest.
    """

    def __init__(self, max_per_session: int = DEFAULT_MAX_PER_SESSION) -> None:
        self._max = max_per_session
        self._items: Dict[str, List[SessionReflection]] = {}
        self._lock = threading.Lock()
        self._path: Optional[str] = None

    def init(self, workspace_dir: str) -> None:
        """Set the persistence path and load any existing reflections."""
        with self._lock:
            self._path = os.path.join(workspace_dir, "reflections.json")
            self._items = self._load_locked()

    def _load_locked(self) -> Dict[str, List[SessionReflection]]:
        if not self._path or not os.path.exists(self._path):
            return {}
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            items: Dict[str, List[SessionReflection]] = {}
            if isinstance(raw, dict):
                for sid, buf in raw.items():
                    if not isinstance(buf, list):
                        continue
                    items[sid] = [SessionReflection.from_dict(r) for r in buf if isinstance(r, dict)]
            return items
        except Exception:
            logger.exception("Failed loading reflections; starting fresh")
            return {}

    def save(self) -> None:
        """Persist all reflections to disk (best-effort)."""
        with self._lock:
            if not self._path:
                return
            try:
                os.makedirs(os.path.dirname(self._path), exist_ok=True)
                payload = {
                    sid: [r.to_dict() for r in buf]
                    for sid, buf in self._items.items()
                }
                with open(self._path, "w", encoding="utf-8") as f:
                    json.dump(payload, f, ensure_ascii=False, indent=2)
            except Exception:
                logger.exception("Failed saving reflections")

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
        self.save()

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