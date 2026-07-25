"""Conversation memory management.

Maintains the context window for each conversation turn, supporting
sliding-window truncation, tool-call result persistence, and compaction
summaries for long-running sessions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class MessageRecord:
    """A single message record."""

    role: str  # user / assistant / tool / system
    content: str
    tool_call_id: Optional[str] = None
    tool_name: Optional[str] = None
    name: Optional[str] = None  # tool message source name
    timestamp: float = 0.0

    def to_openai(self) -> Dict[str, Any]:
        msg: Dict[str, Any] = {"role": self.role, "content": self.content}
        if self.name:
            msg["name"] = self.name
        if self.tool_call_id:
            msg["tool_call_id"] = self.tool_call_id
        return msg


class ConversationMemory:
    """Session-level conversation memory with sliding window and compaction."""

    def __init__(self, session_id: str, window_size: int = 12):
        self.session_id = session_id
        self.window_size = window_size
        self._messages: List[MessageRecord] = []
        self._compacted_summary: str = ""

    def add_user(self, content: str) -> None:
        import time

        self._messages.append(
            MessageRecord(role="user", content=content, timestamp=time.time())
        )
        self._trim()

    def add_assistant(self, content: str, tool_calls: Optional[List[Dict[str, Any]]] = None) -> None:
        import time

        rec = MessageRecord(role="assistant", content=content, timestamp=time.time())
        self._messages.append(rec)
        if tool_calls:
            # Record tool-call metadata (for debugging only, not directly added to OpenAI messages)
            for tc in tool_calls:
                self._messages.append(
                    MessageRecord(
                        role="assistant",
                        content="",
                        tool_call_id=tc.get("id"),
                        tool_name=tc.get("name"),
                    )
                )
        self._trim()

    def add_tool_result(self, tool_call_id: str, tool_name: str, result: str) -> None:
        self._messages.append(
            MessageRecord(
                role="tool",
                content=result,
                tool_call_id=tool_call_id,
                name=tool_name,
            )
        )
        self._trim()

    def to_openai_messages(self) -> List[Dict[str, Any]]:
        """Convert to OpenAI messages format, prepending a compaction summary
        if available."""
        messages: List[Dict[str, Any]] = []
        if self._compacted_summary:
            messages.append(
                {
                    "role": "system",
                    "content": f"Previous conversation summary: {self._compacted_summary}",
                }
            )
        messages.extend(
            m.to_openai() for m in self._messages if m.content or m.role == "tool"
        )
        return messages

    def recent_summary(self, n: int = 5) -> str:
        """Summary of the most recent n messages (for debugging)."""
        lines = []
        for m in self._messages[-n:]:
            prefix = m.role.upper()
            if m.tool_name:
                prefix = f"TOOL({m.tool_name})"
            content = m.content[:120] + "..." if len(m.content) > 120 else m.content
            lines.append(f"[{prefix}] {content}")
        return "\n".join(lines)

    def clear(self) -> None:
        self._messages.clear()
        self._compacted_summary = ""

    def _trim(self) -> None:
        # When exceeding 2x window, compact older messages into a summary
        if len(self._messages) > self.window_size * 2:
            keep = self._messages[-(self.window_size):]
            to_compact = self._messages[: -self.window_size]
            summary = self._build_compaction(to_compact)
            if self._compacted_summary:
                self._compacted_summary = f"{self._compacted_summary}\n{summary}"
            else:
                self._compacted_summary = summary
            self._messages = keep

    @staticmethod
    def _build_compaction(messages: List[MessageRecord]) -> str:
        """Build a brief compaction summary from dropped messages."""
        user_turns = [m.content for m in messages if m.role == "user" and m.content]
        assistant_turns = [
            m.content for m in messages if m.role == "assistant" and m.content
        ]
        parts = []
        if user_turns:
            parts.append("User asked: " + " / ".join(f'"{t[:60]}"' for t in user_turns[-3:]))
        if assistant_turns:
            parts.append("Assistant responded: " + " / ".join(f'"{t[:60]}"' for t in assistant_turns[-3:]))
        return "; ".join(parts) if parts else ""

    @property
    def message_count(self) -> int:
        return len(self._messages)

    @property
    def has_compaction(self) -> bool:
        return bool(self._compacted_summary)
