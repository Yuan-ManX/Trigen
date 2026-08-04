"""Agent memory persistence.

Saves and restores conversation memory across sessions so the Agent
retains context when the server restarts or the user returns later.
Each session's messages, scene snapshot, and model selection are
persisted to a JSON file under the workspace directory.

The persistence layer is intentionally simple — one file per session —
so it works without a database and remains easy to inspect or migrate.
The ConversationMemory class gains load/save methods that serialize its
message list and compacted summary.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import asdict
from typing import Any, Dict, List, Optional

from trigen.memory import ConversationMemory, MessageRecord

logger = logging.getLogger("trigen.memory_persistence")


class MemoryPersistence:
    """Manages disk-based persistence of conversation memory.

    Each session is stored as a single JSON file containing the message
    history, compacted summary, and metadata (creation time, last
    accessed time, model used). Files live under the workspace directory
    so they coexist with exports and other artifacts.
    """

    def __init__(self, base_dir: str):
        self.base_dir = os.path.join(base_dir, "sessions")
        os.makedirs(self.base_dir, exist_ok=True)

    def _session_path(self, session_id: str) -> str:
        """Return the file path for a session's persisted memory."""
        # Sanitize session_id to prevent path traversal
        safe_id = session_id.replace("/", "_").replace("\\", "_").replace("..", "_")
        return os.path.join(self.base_dir, f"{safe_id}.json")

    def save(self, memory: ConversationMemory, model: str = "") -> None:
        """Persist a conversation memory to disk."""
        path = self._session_path(memory.session_id)
        data = {
            "session_id": memory.session_id,
            "model": model,
            "window_size": memory.window_size,
            "compacted_summary": memory._compacted_summary,
            "project_goal": memory.project_goal,
            "messages": [asdict(m) for m in memory._messages],
            "saved_at": time.time(),
        }
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as exc:
            logger.warning("Failed to persist session %s: %s", memory.session_id, exc)

    def load(self, session_id: str) -> Optional[ConversationMemory]:
        """Load a conversation memory from disk. Returns None if not found."""
        path = self._session_path(session_id)
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as exc:
            logger.warning("Failed to load session %s: %s", session_id, exc)
            return None

        memory = ConversationMemory(
            session_id=data.get("session_id", session_id),
            window_size=data.get("window_size", 12),
        )
        memory._compacted_summary = data.get("compacted_summary", "")
        memory.project_goal = data.get("project_goal", "")
        for msg_data in data.get("messages", []):
            memory._messages.append(
                MessageRecord(
                    role=msg_data.get("role", "user"),
                    content=msg_data.get("content", ""),
                    tool_call_id=msg_data.get("tool_call_id"),
                    tool_name=msg_data.get("tool_name"),
                    name=msg_data.get("name"),
                    timestamp=msg_data.get("timestamp", 0.0),
                )
            )
        logger.info("Loaded session %s with %d messages", session_id, len(memory._messages))
        return memory

    def list_sessions(self) -> List[Dict[str, Any]]:
        """List all persisted sessions with metadata."""
        sessions: List[Dict[str, Any]] = []
        if not os.path.exists(self.base_dir):
            return sessions
        for filename in os.listdir(self.base_dir):
            if not filename.endswith(".json"):
                continue
            path = os.path.join(self.base_dir, filename)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                sessions.append(
                    {
                        "session_id": data.get("session_id", filename[:-5]),
                        "model": data.get("model", ""),
                        "message_count": len(data.get("messages", [])),
                        "saved_at": data.get("saved_at", 0),
                        "compacted_summary": data.get("compacted_summary", ""),
                    }
                )
            except Exception:
                continue
        sessions.sort(key=lambda s: s.get("saved_at", 0), reverse=True)
        return sessions

    def delete(self, session_id: str) -> bool:
        """Delete a persisted session. Returns True if it existed."""
        path = self._session_path(session_id)
        if os.path.exists(path):
            os.remove(path)
            return True
        return False


# Global instance — initialized with workspace path
_WORKSPACE = os.environ.get(
    "TRIGEN_WORKSPACE",
    os.path.join(os.getcwd(), ".trigen", "workspace"),
)
persistence = MemoryPersistence(_WORKSPACE)
