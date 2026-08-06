"""Per-session agent trace store.

Captures a bounded, in-memory record of every AgentEvent streamed through
``AgentService.chat_stream`` so the frontend can retrieve a turn-by-turn
trace for inspection, replay, and debugging via ``GET /agent/trace/{session_id}``.

The store is a process-local ring buffer: per-session entries are capped
(default 200) and oldest evicted on overflow. It is intentionally not
persisted — a server restart clears the trace, which is the desired
behavior for a debugging surface.

Each trace entry is the AgentEvent's ``to_dict()`` payload
(``{type, data, seq, ts}``) augmented with a ``turn`` marker. The turn
counter increments after every ``done`` event, so all events of the first
turn share ``turn=1``, the second turn's events share ``turn=2``, etc.

A module-level singleton ``trace_store`` is exposed for import by the
agent service layer and the REST router.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Dict, List, Optional

logger = logging.getLogger("trigen.agent_trace")

# Hard cap on entries kept per session. Oldest entries are evicted when a
# session would exceed this bound. Chosen so a typical turn (~20 events)
# retains the last ~10 turns of context without unbounded memory growth.
DEFAULT_MAX_PER_SESSION = 200


class TraceStore:
    """Bounded, thread-safe, per-session ring buffer of agent events.

    The store is intentionally cheap: a dict of lists guarded by a lock.
    Recording happens on the hot path of every streamed event, so the
    critical section is a single list append (plus optional eviction).
    """

    def __init__(self, max_per_session: int = DEFAULT_MAX_PER_SESSION) -> None:
        self._max = max_per_session
        self._traces: Dict[str, List[Dict[str, Any]]] = {}
        # Per-session turn counter. Incremented after each DONE event so
        # entries can be grouped by turn without scanning for boundaries.
        self._turn: Dict[str, int] = {}
        # Per-session highest seq seen, so ``get(since_seq=...)`` can
        # efficiently slice the buffer for incremental polling.
        self._last_seq: Dict[str, int] = {}
        self._lock = threading.Lock()

    @property
    def max_per_session(self) -> int:
        return self._max

    def record(self, session_id: str, event_dict: Dict[str, Any]) -> None:
        """Append one event to the session's trace.

        ``event_dict`` is the AgentEvent ``to_dict()`` payload
        (``{type, data, seq, ts}``). A ``turn`` field is added in place
        so consumers can group entries by turn. When the buffer is full
        the oldest entry is evicted (FIFO ring).
        """
        if not session_id:
            return
        with self._lock:
            turn = self._turn.get(session_id, 1)
            entry = dict(event_dict)
            entry["turn"] = turn
            buf = self._traces.setdefault(session_id, [])
            buf.append(entry)
            seq = entry.get("seq")
            if isinstance(seq, int) and seq > self._last_seq.get(session_id, 0):
                self._last_seq[session_id] = seq
            # Evict oldest on overflow.
            while len(buf) > self._max:
                buf.pop(0)
            # Advance the turn counter after a DONE event so the *next*
            # recorded event starts a fresh turn.
            if entry.get("type") == "done":
                self._turn[session_id] = turn + 1

    def get(
        self,
        session_id: str,
        limit: Optional[int] = None,
        since_seq: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Return trace entries for ``session_id``.

        ``limit`` caps the number of returned entries (taking the most
        recent ``limit`` entries). ``since_seq`` returns only entries
        whose ``seq`` is strictly greater than the supplied value,
        enabling incremental polling. Both may be combined.
        """
        with self._lock:
            buf = list(self._traces.get(session_id, []))
        if since_seq is not None:
            buf = [e for e in buf if isinstance(e.get("seq"), int) and e["seq"] > since_seq]
        if limit is not None and limit >= 0:
            buf = buf[-limit:] if limit else []
        return buf

    def summary(self, session_id: str) -> Dict[str, Any]:
        """Return a compact summary of the session's trace.

        Includes entry count, turn count, first/last timestamps, and the
        highest seq seen. Used by the REST endpoint to give the frontend
        a cheap status probe without transferring the full buffer.
        """
        with self._lock:
            buf = self._traces.get(session_id, [])
            count = len(buf)
            turn = self._turn.get(session_id, 1)
            last_seq = self._last_seq.get(session_id, 0)
            first_ts = buf[0]["ts"] if buf and "ts" in buf[0] else None
            last_ts = buf[-1]["ts"] if buf and "ts" in buf[-1] else None
        return {
            "session_id": session_id,
            "count": count,
            "turn": turn,
            "last_seq": last_seq,
            "first_ts": first_ts,
            "last_ts": last_ts,
            "max_per_session": self._max,
        }

    def sessions(self) -> List[Dict[str, Any]]:
        """Return a summary for every session with a non-empty trace."""
        with self._lock:
            ids = list(self._traces.keys())
        return [self.summary(sid) for sid in ids if self._traces.get(sid)]

    def clear(self, session_id: Optional[str] = None) -> int:
        """Clear one session's trace (or all when ``session_id`` is None).

        Returns the number of entries removed.
        """
        with self._lock:
            if session_id is None:
                removed = sum(len(v) for v in self._traces.values())
                self._traces.clear()
                self._turn.clear()
                self._last_seq.clear()
                return removed
            buf = self._traces.pop(session_id, [])
            self._turn.pop(session_id, None)
            self._last_seq.pop(session_id, None)
            return len(buf)


# Module-level singleton, mirroring the pattern used by episodic_memory /
# macro_store / variant_store. Imported by the agent service and the
# /agent/trace router.
trace_store = TraceStore()
