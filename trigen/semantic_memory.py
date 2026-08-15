"""Long-term semantic memory layer for Trigen Agent.

Provides a queryable fact store that survives session restarts and lets the
Agent retrieve relevant prior knowledge before each turn — user preferences,
past scene designs that worked well, frequently-used object nicknames, etc.

Implementation is intentionally dependency-free so it works out of the box:

  * Storage: JSON file in the workspace (``<workspace>/semantic_memory.json``).
  * Index: inverted keyword index plus a simple TF-IDF-style scoring function
    for ranking without requiring embeddings. An optional vector-esque cosine
    similarity is layered on top via character n-gram overlap so the system
    still performs semantic-like retrieval for phrase queries.
  * Write path: facts are appended with optional tags + source (which turn /
    which tool produced them) so provenance can be shown in the UI.
  * Read path: ``recall(query, top_k)`` returns a ranked list of facts. The
    orchestrator prepends the top matches to the system prompt as a
    ``MEMORY DIGEST`` section, grounding the Agent in durable context.

A companion :class:`FuzzyNicknameIndex` maps free-form user nicknames
("the big blue cube") onto concrete object IDs so later references resolve
reliably even when the exact name was never uttered verbatim.
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
import threading
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, Iterable, List, Optional, Tuple

logger = logging.getLogger("trigen.semantic_memory")

DEFAULT_FACT_LIMIT = 500
_NGRAM = 3


# ---------------------------------------------------------------------------
# Core data model
# ---------------------------------------------------------------------------


@dataclass
class MemoryFact:
    """A single durable memory unit stored to disk."""

    id: str
    text: str
    tags: List[str] = field(default_factory=list)
    source: str = "agent"  # agent | user | tool | critique | reflection
    session_id: str = ""
    turn: int = 0
    access_count: int = 0
    created_at: float = 0.0
    updated_at: float = 0.0
    score_boost: float = 0.0  # explicit pin weight (see memory_tools.PinFactTool)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "MemoryFact":
        return cls(
            id=str(d.get("id", "")),
            text=str(d.get("text", "")),
            tags=list(d.get("tags", []) or []),
            source=str(d.get("source", "agent")),
            session_id=str(d.get("session_id", "")),
            turn=int(d.get("turn", 0)),
            access_count=int(d.get("access_count", 0)),
            created_at=float(d.get("created_at", 0) or 0),
            updated_at=float(d.get("updated_at", 0) or 0),
            score_boost=float(d.get("score_boost", 0) or 0),
        )


def _tokenize(text: str) -> List[str]:
    """Lowercase alphanumeric tokenizer that also keeps Chinese runs."""
    if not text:
        return []
    lowered = text.lower()
    tokens = re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]+", lowered)
    return [t for t in tokens if len(t) >= 1]


def _char_ngrams(text: str, n: int = _NGRAM) -> List[str]:
    if not text:
        return []
    t = text.lower().replace(" ", "")
    if len(t) < n:
        return [t]
    return [t[i : i + n] for i in range(len(t) - n + 1)]


class TfIdfRanker:
    """Dependency-free TF-IDF + n-gram cosine hybrid ranker."""

    def __init__(self) -> None:
        self.doc_freq: Dict[str, int] = {}
        self.num_docs: int = 0

    def fit(self, docs: Iterable[str]) -> None:
        self.doc_freq.clear()
        n = 0
        for d in docs:
            n += 1
            seen = set(_tokenize(d)) | set(_char_ngrams(d))
            for term in seen:
                self.doc_freq[term] = self.doc_freq.get(term, 0) + 1
        self.num_docs = n

    def score(self, query: str, doc: str) -> float:
        if not query or not doc:
            return 0.0
        q_tokens = _tokenize(query) + _char_ngrams(query)
        d_tokens = _tokenize(doc) + _char_ngrams(doc)
        if not q_tokens or not d_tokens:
            return 0.0

        # Term frequencies in document
        d_tf: Dict[str, float] = {}
        for t in d_tokens:
            d_tf[t] = d_tf.get(t, 0.0) + 1.0
        dnorm = math.sqrt(sum(v * v for v in d_tf.values())) or 1.0

        total = 0.0
        for t in q_tokens:
            df = self.doc_freq.get(t, 0)
            idf = math.log((self.num_docs + 1) / (df + 1)) + 1.0
            tf_q = 1.0  # query tf = 1 per occurrence
            tf_d = d_tf.get(t, 0.0)
            total += tf_q * idf * (tf_d / dnorm)
        return total


# ---------------------------------------------------------------------------
# Fuzzy nickname -> object id index
# ---------------------------------------------------------------------------


class FuzzyNicknameIndex:
    """Maps natural-language aliases to concrete object IDs.

    Supports free-form nicknames the user might invent ("the small red ball",
    "big cube on the left"). When the Agent creates an object, it registers
    the object's canonical name, user-visible nicknames, and salient tags
    (color, material, size). At lookup time the index scores every stored
    nickname against the query using n-gram overlap + token containment and
    returns the best match above a loose threshold.
    """

    def __init__(self) -> None:
        self._entries: Dict[str, Dict[str, Any]] = {}  # object_id -> entry
        self._lock = threading.Lock()

    def register(
        self,
        object_id: str,
        canonical_name: str,
        *,
        aliases: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
    ) -> None:
        with self._lock:
            existing = self._entries.get(object_id, {})
            merged_aliases = list(set(list(existing.get("aliases", [])) + list(aliases or []) + [canonical_name]))
            merged_tags = list(set(list(existing.get("tags", [])) + list(tags or [])))
            self._entries[object_id] = {
                "object_id": object_id,
                "canonical": canonical_name,
                "aliases": merged_aliases,
                "tags": merged_tags,
                "updated_at": time.time(),
            }

    def forget(self, object_id: str) -> None:
        with self._lock:
            self._entries.pop(object_id, None)

    def lookup(self, query: str, top_k: int = 3) -> List[Tuple[str, float, str]]:
        """Return (object_id, score, canonical_name) tuples sorted by score."""
        if not query:
            return []
        query = query.strip().lower()
        results: List[Tuple[str, float, str]] = []
        with self._lock:
            for entry in self._entries.values():
                score = 0.0
                haystacks = [entry.get("canonical", "")] + list(entry.get("aliases", [])) + list(entry.get("tags", []))
                for h in haystacks:
                    h = h.lower()
                    if not h:
                        continue
                    if h == query:
                        score = max(score, 1.0)
                    elif query in h:
                        score = max(score, 0.85 + 0.1 * (1.0 - abs(len(h) - len(query)) / max(len(h), len(query), 1)))
                    else:
                        # n-gram overlap
                        q_grams = set(_char_ngrams(query))
                        h_grams = set(_char_ngrams(h))
                        if q_grams and h_grams:
                            overlap = q_grams & h_grams
                            score = max(score, len(overlap) / max(len(q_grams), 1))
                if score > 0.15:
                    results.append((entry["object_id"], score, entry.get("canonical", "")))
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]

    def to_dict(self) -> Dict[str, Any]:
        with self._lock:
            return {k: dict(v) for k, v in self._entries.items()}

    def load_dict(self, data: Dict[str, Any]) -> None:
        with self._lock:
            self._entries = {str(k): dict(v) for k, v in (data or {}).items()}


# ---------------------------------------------------------------------------
# Top-level semantic memory store
# ---------------------------------------------------------------------------


class SemanticMemoryStore:
    """Durable, queryable fact store with nickname resolution sidecar."""

    def __init__(self, workspace_dir: Optional[str] = None, max_facts: int = DEFAULT_FACT_LIMIT) -> None:
        self.workspace_dir = workspace_dir or os.path.join(os.getcwd(), ".trigen_workspace")
        os.makedirs(self.workspace_dir, exist_ok=True)
        self.max_facts = max_facts
        self._file = os.path.join(self.workspace_dir, "semantic_memory.json")
        self._lock = threading.RLock()
        self.facts: List[MemoryFact] = []
        self.nicknames = FuzzyNicknameIndex()
        self._ranker = TfIdfRanker()
        self._load()

    # ---- persistence ----------------------------------------------------

    def _load(self) -> None:
        if not os.path.exists(self._file):
            return
        try:
            with open(self._file, "r", encoding="utf-8") as f:
                raw = json.load(f)
            self.facts = [MemoryFact.from_dict(x) for x in raw.get("facts", [])]
            self.nicknames.load_dict(raw.get("nicknames", {}))
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Failed to load semantic memory: %s", exc)
            self.facts = []
            self.nicknames = FuzzyNicknameIndex()
        self._refit_ranker()

    def save(self) -> None:
        with self._lock:
            payload = {
                "facts": [f.to_dict() for f in self.facts],
                "nicknames": self.nicknames.to_dict(),
                "saved_at": time.time(),
            }
            tmp = self._file + ".tmp"
            try:
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(payload, f, ensure_ascii=False, indent=2)
                os.replace(tmp, self._file)
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("Failed to persist semantic memory: %s", exc)

    def _refit_ranker(self) -> None:
        self._ranker.fit([f.text for f in self.facts])

    # ---- write API ------------------------------------------------------

    def remember(
        self,
        text: str,
        *,
        tags: Optional[List[str]] = None,
        source: str = "agent",
        session_id: str = "",
        turn: int = 0,
    ) -> MemoryFact:
        if not text or not text.strip():
            raise ValueError("empty fact text")
        fact = MemoryFact(
            id=f"mem_{int(time.time()*1000):x}_{abs(hash(text)) & 0xFFFF:x}",
            text=text.strip(),
            tags=list(tags or []),
            source=source,
            session_id=session_id,
            turn=turn,
            created_at=time.time(),
            updated_at=time.time(),
        )
        with self._lock:
            self.facts.append(fact)
            # Evict oldest un-pinned facts when over cap
            if len(self.facts) > self.max_facts:
                pinned = [f for f in self.facts if f.score_boost > 0]
                unpinned = [f for f in self.facts if f.score_boost <= 0]
                if unpinned:
                    unpinned.sort(key=lambda f: (f.updated_at, f.access_count))
                    drop = len(self.facts) - self.max_facts
                    unpinned = unpinned[drop:]
                self.facts = pinned + unpinned
            self._refit_ranker()
        self.save()
        return fact

    def pin(self, fact_id: str, boost: float = 2.0) -> bool:
        with self._lock:
            for f in self.facts:
                if f.id == fact_id:
                    f.score_boost = max(f.score_boost, boost)
                    f.updated_at = time.time()
                    self.save()
                    return True
        return False

    def forget(self, fact_id: Optional[str] = None, *, text_prefix: Optional[str] = None) -> int:
        removed = 0
        with self._lock:
            if fact_id:
                before = len(self.facts)
                self.facts = [f for f in self.facts if f.id != fact_id]
                removed = before - len(self.facts)
            elif text_prefix:
                before = len(self.facts)
                self.facts = [f for f in self.facts if not f.text.startswith(text_prefix)]
                removed = before - len(self.facts)
            if removed:
                self._refit_ranker()
                self.save()
        return removed

    # ---- read API -------------------------------------------------------

    def recall(
        self,
        query: str,
        *,
        top_k: int = 8,
        tags: Optional[List[str]] = None,
        session_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        with self._lock:
            if not self.facts:
                return []
            scored: List[Tuple[float, MemoryFact]] = []
            for f in self.facts:
                if tags and not any(t in (f.tags or []) for t in tags):
                    continue
                if session_id and f.session_id != session_id:
                    # Prefer same-session but still consider cross-session pinned facts.
                    if f.score_boost <= 0 and f.session_id:
                        continue
                base = self._ranker.score(query, f.text)
                tag_bonus = 0.0
                if tags:
                    hits = sum(1 for t in tags if t in (f.tags or []))
                    tag_bonus = 0.1 * hits / max(len(tags), 1)
                # Access recency: recently accessed facts get a tiny bonus so
                # frequently-relevant memories stay top-of-mind.
                recency = 0.02 * min(f.access_count, 10)
                total = base + tag_bonus + recency + float(f.score_boost)
                scored.append((total, f))
            scored.sort(key=lambda x: x[0], reverse=True)
            results = []
            for score, fact in scored[:top_k]:
                if score <= 0 and not fact.score_boost > 0:
                    continue
                fact.access_count += 1
                fact.updated_at = time.time()
                results.append(
                    {
                        "id": fact.id,
                        "text": fact.text,
                        "score": round(score, 4),
                        "tags": list(fact.tags),
                        "source": fact.source,
                        "session_id": fact.session_id,
                        "turn": fact.turn,
                        "pinned": fact.score_boost > 0,
                    }
                )
            if results:
                self.save()
        return results

    def all(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [f.to_dict() for f in self.facts]

    def count(self) -> int:
        with self._lock:
            return len(self.facts)

    # ---- nickname sidecar ----------------------------------------------

    def register_object(
        self,
        object_id: str,
        canonical_name: str,
        *,
        aliases: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
    ) -> None:
        self.nicknames.register(object_id, canonical_name, aliases=aliases, tags=tags)
        self.save()

    def resolve_object(self, query: str, top_k: int = 3) -> List[Tuple[str, float, str]]:
        return self.nicknames.lookup(query, top_k=top_k)


# Module-level singleton so the orchestrator and tools share one store.
_store: Optional[SemanticMemoryStore] = None
_store_lock = threading.Lock()


def get_store(workspace_dir: Optional[str] = None) -> SemanticMemoryStore:
    global _store
    if _store is None:
        with _store_lock:
            if _store is None:
                _store = SemanticMemoryStore(workspace_dir=workspace_dir)
    return _store
