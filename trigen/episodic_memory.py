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

# Maximum quality score at which a turn is considered a failure worth
# remembering as an anti-pattern. Below this threshold the tool chain is
# cached so future similar requests can be advised against reusing it.
# Gap between 41 and 69 is intentionally neither cached: middling turns
# don't carry a strong enough signal in either direction.
_ANTI_PATTERN_MAX_QUALITY = 40

# Cap the pattern cache size so it does not grow unbounded over long use.
_MAX_PATTERNS = 60

# Mirror cap for the anti-pattern cache.
_MAX_ANTI_PATTERNS = 30

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
class PinnedFact:
    """A user-scoped fact the Agent chose to remember explicitly.

    Pinned facts survive session resets and are injected into the LLM
    system note so the Agent can personalize its reasoning across
    sessions. Each fact carries an optional category (e.g. 'project',
    'preference', 'constraint') and a timestamp.
    """

    text: str
    category: str = "general"
    pinned_at: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "category": self.category,
            "pinned_at": self.pinned_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PinnedFact":
        return cls(
            text=str(data.get("text", "")),
            category=str(data.get("category", "general")),
            pinned_at=float(data.get("pinned_at", 0.0)),
        )


@dataclass
class EpisodicMemory:
    """Cross-session user preferences + successful plan-pattern cache."""

    preferences: Dict[str, Counter] = field(default_factory=dict)
    patterns: Dict[str, PatternEntry] = field(default_factory=dict)
    pinned_facts: List[PinnedFact] = field(default_factory=list)
    last_updated: float = 0.0
    # Anti-patterns: cached failed tool chains keyed by intent signature.
    # When a turn's quality score falls below the anti-pattern threshold,
    # the chain is recorded here so future similar requests can avoid it.
    # Mirror structure of ``patterns`` but with a low quality score.
    anti_patterns: Dict[str, PatternEntry] = field(default_factory=dict)
    # Most recent successful tool chain (names only). Used by the
    # orchestrator's recency-bias path: when the next turn's intent
    # category overlaps with the last successful one, these tools are
    # kept in the active schema set even when no keyword signal fires.
    last_successful_tools: List[str] = field(default_factory=list)
    # Last successful intent signature (for similarity comparison).
    last_successful_signature: str = ""

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

        Side effects:
          - Preferences are always extracted (regardless of quality).
          - Successful turns (quality >= _PATTERN_CACHE_MIN_QUALITY) cache
            a positive pattern AND update ``last_successful_tools`` so the
            next turn's tool-selection can bias toward the same chain.
          - Poor turns (quality <= _ANTI_PATTERN_MAX_QUALITY) cache an
            anti-pattern so future similar requests can avoid the chain.
        """
        try:
            self._extract_preferences(user_message, plan_steps, results)
            tool_names = [getattr(s, "tool_name", "") for s in plan_steps if getattr(s, "tool_name", "")]
            if quality >= _PATTERN_CACHE_MIN_QUALITY:
                self._cache_pattern(user_message, plan_steps, quality)
                # Track the most recent successful chain for recency bias.
                self.last_successful_tools = tool_names[:8]
                self.last_successful_signature = _signature(user_message)
            elif quality <= _ANTI_PATTERN_MAX_QUALITY and tool_names:
                self._cache_anti_pattern(user_message, tool_names, quality)
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

    def _cache_anti_pattern(
        self,
        user_message: str,
        tool_names: List[str],
        quality: int,
    ) -> None:
        """Record a failed tool chain so future similar requests can avoid it.

        Lower quality wins (most negative signal); otherwise the existing
        entry's hit count is bumped. Capped at ``_MAX_ANTI_PATTERNS``.
        """
        sig = _signature(user_message)
        if not sig or not tool_names:
            return
        existing = self.anti_patterns.get(sig)
        if existing is not None:
            if quality < existing.quality:
                existing.tool_names = list(tool_names)
                existing.quality = quality
            existing.hits += 1
            existing.last_used = time.time()
            return
        if len(self.anti_patterns) >= _MAX_ANTI_PATTERNS:
            oldest_sig = min(
                self.anti_patterns, key=lambda k: self.anti_patterns[k].last_used
            )
            self.anti_patterns.pop(oldest_sig, None)
        self.anti_patterns[sig] = PatternEntry(
            signature=sig,
            tool_names=list(tool_names),
            sample_arguments=[],
            quality=quality,
            hits=1,
            last_used=time.time(),
        )

    def lookup_anti_pattern(self, user_message: str) -> Optional[PatternEntry]:
        """Return the cached anti-pattern for a message (exact signature)."""
        sig = _signature(user_message)
        return self.anti_patterns.get(sig)

    def lookup_similar_pattern(self, user_message: str, min_overlap: int = 2) -> Optional[PatternEntry]:
        """Fuzzy pattern recall: find the most similar cached positive pattern.

        Used when an exact-signature lookup misses. Tokenizes the request
        and finds the cached pattern with the highest token overlap. Returns
        None when no pattern shares at least ``min_overlap`` tokens.

        Keeps the recall path cheap (no embeddings, no LLM call) — purely
        set-intersection scoring. Hit count is bumped on a successful match
        so frequently-recalled patterns surface higher in future rankings.
        """
        sig = _signature(user_message)
        if not sig:
            return None
        query_tokens = set(sig.split())
        if not query_tokens:
            return None
        best: Optional[PatternEntry] = None
        best_overlap = 0
        for entry in self.patterns.values():
            entry_tokens = set(entry.signature.split())
            if not entry_tokens:
                continue
            overlap = len(query_tokens & entry_tokens)
            # Tie-break: prefer higher quality, then higher hit count.
            if overlap > best_overlap or (
                overlap == best_overlap and best is not None
                and (entry.quality > best.quality
                     or (entry.quality == best.quality and entry.hits > best.hits))
            ):
                if overlap >= min_overlap:
                    best = entry
                    best_overlap = overlap
        if best is not None:
            best.hits += 1
            best.last_used = time.time()
        return best

    # ------------------------------------------------------------------
    # Pinned facts — explicit Agent memory
    # ------------------------------------------------------------------

    _MAX_PINNED_FACTS = 50

    def add_fact(self, text: str, category: str = "general") -> PinnedFact:
        """Pin an explicit fact the Agent wants to remember.

        Deduplicates on text (case-insensitive) so the same fact is never
        pinned twice. Trims to the most-recent ``_MAX_PINNED_FACTS`` so the
        note injected into the LLM stays bounded.
        """
        text = (text or "").strip()
        if not text:
            return PinnedFact(text="", category=category, pinned_at=time.time())
        category = (category or "general").strip().lower() or "general"
        normalized = text.lower()
        # Replace an existing fact with the same text (refresh category/timestamp).
        self.pinned_facts = [
            f for f in self.pinned_facts if f.text.lower() != normalized
        ]
        fact = PinnedFact(text=text, category=category, pinned_at=time.time())
        self.pinned_facts.append(fact)
        # Trim to the most-recent N.
        if len(self.pinned_facts) > self._MAX_PINNED_FACTS:
            self.pinned_facts = self.pinned_facts[-self._MAX_PINNED_FACTS:]
        self.last_updated = time.time()
        return fact

    def list_facts(self, category: Optional[str] = None) -> List[PinnedFact]:
        """Return pinned facts, newest first, optionally filtered by category."""
        facts = list(self.pinned_facts)
        if category:
            cat = category.strip().lower()
            facts = [f for f in facts if f.category == cat]
        facts.sort(key=lambda f: f.pinned_at, reverse=True)
        return facts

    def clear_facts(self, category: Optional[str] = None) -> int:
        """Remove pinned facts. If ``category`` is given, only that category
        is cleared. Returns the number of facts removed."""
        before = len(self.pinned_facts)
        if category is None:
            self.pinned_facts = []
        else:
            cat = category.strip().lower()
            self.pinned_facts = [f for f in self.pinned_facts if f.category != cat]
        removed = before - len(self.pinned_facts)
        if removed:
            self.last_updated = time.time()
        return removed

    def remove_fact(self, text: str) -> bool:
        """Remove a single pinned fact by exact (case-insensitive) text match."""
        normalized = (text or "").strip().lower()
        if not normalized:
            return False
        before = len(self.pinned_facts)
        self.pinned_facts = [
            f for f in self.pinned_facts if f.text.lower() != normalized
        ]
        if len(self.pinned_facts) != before:
            self.last_updated = time.time()
            return True
        return False

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
        # Pinned facts — explicit Agent memory, surfaced verbatim.
        if self.pinned_facts:
            facts_sorted = sorted(
                self.pinned_facts, key=lambda f: f.pinned_at, reverse=True
            )
            # Cap at the most-recent 8 to keep the note compact.
            for f in facts_sorted[:8]:
                lines.append(f"Pinned fact [{f.category}]: {f.text}")
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
            "anti_patterns": {k: v.to_dict() for k, v in self.anti_patterns.items()},
            "pinned_facts": [f.to_dict() for f in self.pinned_facts],
            "last_successful_tools": list(self.last_successful_tools),
            "last_successful_signature": self.last_successful_signature,
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
        for sig, pdata in (data.get("anti_patterns") or {}).items():
            try:
                mem.anti_patterns[sig] = PatternEntry.from_dict(pdata)
            except Exception:
                continue
        for fdata in (data.get("pinned_facts") or []):
            try:
                mem.pinned_facts.append(PinnedFact.from_dict(fdata))
            except Exception:
                continue
        mem.last_successful_tools = list(data.get("last_successful_tools") or [])
        mem.last_successful_signature = str(data.get("last_successful_signature") or "")
        mem.last_updated = float(data.get("last_updated", 0.0))
        return mem

    def anti_pattern_warning(self, user_message: str) -> Optional[str]:
        """Return a warning note when the request matches a cached anti-pattern.

        Returns None when no anti-pattern matches, so the orchestrator can
        skip injecting an empty note. The warning is advisory: it tells the
        LLM which tool chain previously underperformed for a similar request
        without blocking the turn.
        """
        entry = self.lookup_anti_pattern(user_message)
        if entry is None:
            return None
        return (
            f"Episodic caution: a similar past request underperformed "
            f"(quality={entry.quality}, hits={entry.hits}) with tools "
            f"[{', '.join(entry.tool_names)}]. Consider a different path "
            f"unless the scene state clearly warrants retrying it."
        )


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
