"""Episodic memory — cross-session learning for the Trigen Agent.

Captures two kinds of long-lived signal that survive individual session
 resets:

  1. **User preferences** — preferred language, most-used geometry types,
     favorite material presets, common transform modes. Extracted cheaply
     from each turn via heuristics and surfaced to the LLM as a system
     note so the agent can personalize its responses.
  2. **Plan-pattern cache** — when a turn's tool sequence succeeds with a
     good quality score, its intent signature (normalized user message) is
     mapped to the successful tool-call chain. Subsequent similar requests
     can reuse the cached plan as a hint, skipping re-planning when the
     LLM is offline and biasing tool selection when online.

Persistence is a single JSON file under the workspace so it works without
 a database and remains easy to inspect or wipe. The store is process-
 local and lazily loaded; concurrent writes are guarded by a simple
 in-process lock since the orchestrator is single-threaded per turn.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("trigen.episodic_memory")

# Minimum quality score required to cache a plan pattern. Below this the
# pattern is considered not-yet-reliable and skipped to avoid caching
# flaky sequences.
_PATTERN_CACHE_MIN_QUALITY = 70

# Cap the pattern cache size so it does not grow unbounded over long use.
_MAX_PATTERNS = 60

# Cap the per-preference counter history so old stale preferences decay.
_PREFERENCE_DECAY_KEEP = 8


@dataclass
class PatternEntry:
    """A cached successful plan pattern keyed by intent signature."""

    signature: str
    tool_names: List[str]
    sample_arguments: List[Dict[str, Any]]
    quality: int
    hits: int = 0
    last_used: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "signature": self.signature,
            "tool_names": list(self.tool_names),
            "sample_arguments": list(self.sample_arguments),
            "quality": self.quality,
            "hits": self.hits,
            "last_used": self.last_used,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PatternEntry":
        return cls(
            signature=data.get("signature", ""),
            tool_names=list(data.get("tool_names", [])),
            sample_arguments=list(data.get("sample_arguments", [])),
            quality=int(data.get("quality", 0)),
            hits=int(data.get("hits", 0)),
            last_used=float(data.get("last_used", 0.0)),
        )


@dataclass
class EpisodicMemory:
    """Cross-session user preferences + successful plan-pattern cache."""

    preferences: Dict[str, Counter] = field(default_factory=dict)
    patterns: Dict[str, PatternEntry] = field(default_factory=dict)
    last_updated: float = 0.0

    # ------------------------------------------------------------------
    # Preference extraction
    # ------------------------------------------------------------------

    def record_turn(
        self,
        user_message: str,
        plan_steps: List[Any],
        results: List[Any],
        quality: int,
    ) -> None:
        """Extract preferences and cache successful patterns from a turn.

        ``plan_steps`` is a list of TaskStep-like objects with
        ``tool_name`` and ``arguments``. ``results`` is a list of
        ToolResult-like objects with ``success``. ``quality`` is the 0-100
        turn-quality score from the orchestrator's self-assessment.
        """
        try:
            self._extract_preferences(user_message, plan_steps, results)
            if quality >= _PATTERN_CACHE_MIN_QUALITY:
                self._cache_pattern(user_message, plan_steps, quality)
            self.last_updated = time.time()
        except Exception:
            logger.exception("Episodic memory recording failed")

    def _extract_preferences(
        self,
        user_message: str,
        plan_steps: List[Any],
        results: List[Any],
    ) -> None:
        msg_lower = (user_message or "").lower()
        # Language preference: count CJK characters as a zh signal,
        # ascii-alpha words as an en signal. Whichever dominates sets
        # the preferred language hint for the agent's reply tone.
        cjk = len(re.findall(r"[\u4e00-\u9fff]", user_message or ""))
        ascii_words = len(re.findall(r"[a-zA-Z]+", user_message or ""))
        if cjk > 0 or ascii_words > 0:
            lang_counter = self.preferences.setdefault("language", Counter())
            if cjk >= ascii_words:
                lang_counter["zh"] += 1
            else:
                lang_counter["en"] += 1
            self._decay(lang_counter)

        # Tool-arg preferences: tally geometry_type / preset / view / mode
        # values from successful steps so the agent can favor them.
        for step, result in zip(plan_steps, results):
            success = getattr(result, "success", False)
            if not success:
                continue
            args = getattr(step, "arguments", {}) or {}
            tool = getattr(step, "tool_name", "")
            if tool == "create_object":
                geo = args.get("geometry_type")
                if isinstance(geo, str):
                    self._bump("geometry_type", geo)
            elif tool == "apply_material_preset":
                preset = args.get("preset")
                if isinstance(preset, str):
                    self._bump("material_preset", preset)
            elif tool == "set_view":
                view = args.get("view")
                if isinstance(view, str):
                    self._bump("view", view)
            elif tool == "set_transform_mode":
                mode = args.get("mode")
                if isinstance(mode, str):
                    self._bump("transform_mode", mode)
            elif tool == "set_render_quality":
                q = args.get("quality")
                if isinstance(q, str):
                    self._bump("render_quality", q)

    def _bump(self, key: str, value: str) -> None:
        counter = self.preferences.setdefault(key, Counter())
        counter[value] += 1
        self._decay(counter)

    @staticmethod
    def _decay(counter: Counter) -> None:
        """Keep only the top-N most common entries so stale preferences fade."""
        if len(counter) <= _PREFERENCE_DECAY_KEEP:
            return
        most_common = counter.most_common(_PREFERENCE_DECAY_KEEP)
        counter.clear()
        for k, v in most_common:
            counter[k] = v

    # ------------------------------------------------------------------
    # Pattern caching
    # ------------------------------------------------------------------

    def _cache_pattern(
        self,
        user_message: str,
        plan_steps: List[Any],
        quality: int,
    ) -> None:
        sig = _signature(user_message)
        if not sig or not plan_steps:
            return
        tool_names = [getattr(s, "tool_name", "") for s in plan_steps]
        if not any(tool_names):
            return
        sample_args = [
            (getattr(s, "arguments", {}) or {}) for s in plan_steps[:4]
        ]
        existing = self.patterns.get(sig)
        if existing is not None:
            # Update in place: prefer the higher-quality sample, bump hits.
            if quality > existing.quality:
                existing.tool_names = tool_names
                existing.sample_arguments = sample_args
                existing.quality = quality
            existing.hits += 1
            existing.last_used = time.time()
            return
        # Evict the oldest entry when the cache is full.
        if len(self.patterns) >= _MAX_PATTERNS:
            oldest_sig = min(
                self.patterns, key=lambda k: self.patterns[k].last_used
            )
            self.patterns.pop(oldest_sig, None)
        self.patterns[sig] = PatternEntry(
            signature=sig,
            tool_names=tool_names,
            sample_arguments=sample_args,
            quality=quality,
            hits=1,
            last_used=time.time(),
        )

    def lookup_pattern(self, user_message: str) -> Optional[PatternEntry]:
        """Return the cached pattern for a message, bumping its hit count."""
        sig = _signature(user_message)
        entry = self.patterns.get(sig)
        if entry is None:
            return None
        entry.hits += 1
        entry.last_used = time.time()
        return entry

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_system_note(self) -> str:
        """Format learned preferences as a system note for the LLM.

        Returns an empty string when no preferences have been recorded yet
        so the orchestrator can skip injecting an empty note.
        """
        lines: List[str] = []
        lang = self._top("language")
        if lang:
            lines.append(f"User's preferred reply language: {lang}.")
        geo = self._top("geometry_type")
        if geo:
            lines.append(f"Frequently created geometry: {geo}.")
        preset = self._top("material_preset")
        if preset:
            lines.append(f"Frequently applied material preset: {preset}.")
        view = self._top("view")
        if view:
            lines.append(f"Frequently used viewport: {view}.")
        mode = self._top("transform_mode")
        if mode:
            lines.append(f"Preferred transform mode: {mode}.")
        rq = self._top("render_quality")
        if rq:
            lines.append(f"Preferred render quality: {rq}.")
        if not lines:
            return ""
        return (
            "Learned user preferences (from prior sessions): "
            + " ".join(lines)
        )

    def _top(self, key: str) -> Optional[str]:
        counter = self.preferences.get(key)
        if not counter:
            return None
        most_common = counter.most_common(1)
        return most_common[0][0] if most_common else None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "preferences": {k: dict(v) for k, v in self.preferences.items()},
            "patterns": {k: v.to_dict() for k, v in self.patterns.items()},
            "last_updated": self.last_updated,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EpisodicMemory":
        mem = cls()
        for k, raw in (data.get("preferences") or {}).items():
            mem.preferences[k] = Counter(raw)
        for sig, pdata in (data.get("patterns") or {}).items():
            try:
                mem.patterns[sig] = PatternEntry.from_dict(pdata)
            except Exception:
                continue
        mem.last_updated = float(data.get("last_updated", 0.0))
        return mem


def _signature(user_message: str) -> str:
    """Normalize a user message into a repeatable intent signature.

    Lowercases, strips digits and punctuation, collapses whitespace, and
    drops filler words so paraphrases of the same intent map to the same
    key (e.g. "create 3 red cubes" and "create a red cube" share a
    signature prefix, though the count differs — we keep it simple and
    treat them as the same pattern for caching purposes).
    """
    if not user_message:
        return ""
    text = user_message.lower()
    # Keep CJK characters and ascii letters; drop everything else.
    text = re.sub(r"[^a-z\u4e00-\u9fff\s]", " ", text)
    # Remove common filler words so intent matches are robust.
    fillers = {
        "a", "an", "the", "please", "can", "you", "to", "for", "of",
        "make", "create", "add", "me", "my", "this", "that",
    }
    tokens = [t for t in text.split() if t and t not in fillers]
    sig = " ".join(tokens)
    # Truncate so very long messages do not produce unwieldy keys.
    return sig[:80].strip()


# ---------------------------------------------------------------------------
# Disk store — singleton loaded lazily, thread-safe save/load
# ---------------------------------------------------------------------------


class _EpisodicStore:
    """Process-local episodic memory store with JSON persistence."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._memory: Optional[EpisodicMemory] = None
        self._path: Optional[str] = None

    def init(self, workspace_dir: str) -> None:
        """Initialize the store path and load any existing data."""
        with self._lock:
            self._path = os.path.join(workspace_dir, "episodic_memory.json")
            self._memory = self._load_locked()

    def _load_locked(self) -> EpisodicMemory:
        if not self._path or not os.path.exists(self._path):
            return EpisodicMemory()
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                return EpisodicMemory.from_dict(json.load(f))
        except Exception:
            logger.exception("Failed loading episodic memory; starting fresh")
            return EpisodicMemory()

    def get(self) -> EpisodicMemory:
        if self._memory is None:
            # Fall back to a default workspace if init was never called.
            self.init(
                os.environ.get(
                    "TRIGEN_WORKSPACE",
                    os.path.join(os.getcwd(), ".trigen", "workspace"),
                )
            )
        assert self._memory is not None
        return self._memory

    def save(self) -> None:
        with self._lock:
            if not self._path or self._memory is None:
                return
            try:
                os.makedirs(os.path.dirname(self._path), exist_ok=True)
                with open(self._path, "w", encoding="utf-8") as f:
                    json.dump(self._memory.to_dict(), f, ensure_ascii=False, indent=2)
            except Exception:
                logger.exception("Failed saving episodic memory")

    def reset(self) -> None:
        with self._lock:
            self._memory = EpisodicMemory()
            if self._path and os.path.exists(self._path):
                try:
                    os.remove(self._path)
                except Exception:
                    logger.exception("Failed removing episodic memory file")


# Module-level singleton.
store = _EpisodicStore()
