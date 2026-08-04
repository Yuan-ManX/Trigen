"""Structured context compression for long-running sessions.

The base ``ConversationMemory`` already performs sliding-window compaction
by joining truncated message strings into a single summary line. That keeps
token usage bounded but loses structured signal: which tools were used, how
the scene evolved across turns, and which intent categories dominated the
session.

This module produces a richer, scene-aware compression artifact that the
orchestrator can inject as a system note when a session grows long. The
compressor is deliberately cheap (no LLM call) — it scans message + tool
metadata the orchestrator already tracks and emits a compact structured
summary. The summary is injected alongside (not replacing) the existing
compaction so both layers cooperate.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from trigen.memory import ConversationMemory


# Trigger compression once the raw message count crosses this threshold.
# Tuned to fire well before the sliding-window compaction kicks in (which
# runs at 2x window_size) so the structured note is available for the
# in-between turns where the window is full but not yet compacted.
_COMPRESS_TRIGGER = 16
# How many recent messages to always keep verbatim (never compress these).
_KEEP_RECENT = 6


@dataclass
class CompressionReport:
    """Structured summary of a session's trajectory."""

    scene_trajectory: str = ""
    tool_usage: Dict[str, int] = field(default_factory=dict)
    dominant_categories: List[str] = field(default_factory=list)
    user_themes: List[str] = field(default_factory=list)
    objects_referenced: List[str] = field(default_factory=list)
    summary_text: str = ""

    def to_system_note(self) -> str:
        """Render the report as a system note for the LLM.

        Returns an empty string when there is nothing meaningful to say so
        the caller can skip injection entirely.
        """
        if not self.summary_text:
            return ""
        return self.summary_text


def compress_session(
    memory: ConversationMemory,
    scene_snapshot: Optional[Dict[str, Any]] = None,
    tool_categories: Optional[Dict[str, str]] = None,
) -> CompressionReport:
    """Build a structured compression report from session memory.

    Parameters
    ----------
    memory
        The session's conversation memory. Read-only — never mutated.
    scene_snapshot
        Optional current scene dict, used to enrich the trajectory line
        with a live object count.
    tool_categories
        Optional mapping of tool name -> category. When provided, the
        report surfaces the dominant intent categories for this session.
    """
    messages = memory._messages  # noqa: SLF001 — intentional internal access
    report = CompressionReport()
    if len(messages) < _COMPRESS_TRIGGER:
        return report

    # Slice off the recent messages we want to preserve verbatim; only the
    # older tail is compressed so the agent keeps full fidelity on the
    # active turn pair.
    tail = messages[-_KEEP_RECENT:]
    head = messages[: -_KEEP_RECENT]

    tool_counter: Counter = Counter()
    category_counter: Counter = Counter()
    user_snippets: List[str] = []
    object_names: List[str] = []

    for m in head:
        if m.role == "user" and m.content:
            user_snippets.append(m.content.strip())
        if m.tool_name:
            tool_counter[m.tool_name] += 1
            if tool_categories and tool_categories.get(m.tool_name):
                category_counter[tool_categories[m.tool_name]] += 1
        # Collect referenced object names from tool-call payloads when the
        # message carries tool metadata (target / name args). We scan the
        # content for quoted names as a lightweight heuristic.
        if m.tool_name and m.content:
            for token in _extract_name_tokens(m.content):
                if token and token not in object_names:
                    object_names.append(token)

    report.tool_usage = dict(tool_counter.most_common(8))
    report.dominant_categories = [c for c, _ in category_counter.most_common(4)]
    report.user_themes = _extract_themes(user_snippets)
    report.objects_referenced = object_names[:12]

    # Build the human-readable trajectory line.
    parts: List[str] = []
    parts.append(
        f"Session so far: {len(head)} earlier messages compressed, "
        f"{len(tail)} recent retained verbatim."
    )
    if tool_counter:
        top_tools = ", ".join(f"{name}x{cnt}" for name, cnt in tool_counter.most_common(5))
        parts.append(f"Tool usage: {top_tools}")
    if report.dominant_categories:
        parts.append(f"Dominant intents: {', '.join(report.dominant_categories)}")
    if report.user_themes:
        parts.append(f"User themes: {', '.join(report.user_themes[:4])}")
    if scene_snapshot is not None:
        obj_count = len(scene_snapshot.get("objects", []))
        light_count = len(scene_snapshot.get("lights", []))
        parts.append(f"Live scene: {obj_count} objects, {light_count} lights")
    if memory.project_goal:
        parts.append(f"Active goal: {memory.project_goal[:100]}")

    report.summary_text = " | ".join(parts)
    report.scene_trajectory = report.summary_text
    return report


def _extract_name_tokens(content: str) -> List[str]:
    """Pull candidate object names out of a tool-result message.

    Looks for the common ``target`` / ``name`` JSON-ish patterns the tools
    emit. Intentionally permissive — false positives are harmless because
    the list is only used for a hint, never for resolution.
    """
    tokens: List[str] = []
    if not content:
        return tokens
    # Match "name": "value" or target: value patterns.
    import re

    for match in re.finditer(r'"?(?:name|target|object)"?\s*[:=]\s*"?([A-Za-z_][\w\- ]{1,40})"?', content):
        val = match.group(1).strip()
        if val and val not in tokens and not val.isdigit():
            tokens.append(val)
    return tokens


def _extract_themes(snippets: List[str]) -> List[str]:
    """Distill a few short theme labels from user message snippets.

    Uses keyword buckets aligned with the orchestrator's intent-category
    signals so the themes read naturally alongside the category list.
    """
    if not snippets:
        return []
    theme_buckets: Dict[str, Tuple[str, Tuple[str, ...]]] = {
        "modeling": ("modeling", ("create", "add", "make", "build", "建模", "创建", "新建")),
        "material": ("material design", ("material", "color", "paint", "metal", "glass", "材质", "颜色")),
        "lighting": ("lighting setup", ("light", "灯光", "阴影")),
        "animation": ("animation", ("animate", "keyframe", "动画", "关键帧")),
        "composition": ("scene composition", ("arrange", "group", "layout", "排列", "分组", "布局")),
        "inspection": ("scene review", ("list", "info", "analyze", "测量", "分析")),
    }
    text = " ".join(snippets).lower()
    hits: List[str] = []
    for _, (label, keywords) in theme_buckets.items():
        if any(kw in text for kw in keywords):
            hits.append(label)
    return hits


def should_compress(memory: ConversationMemory) -> bool:
    """Return True when the session has grown enough to warrant compression."""
    return memory.message_count >= _COMPRESS_TRIGGER
