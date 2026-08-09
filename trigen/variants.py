"""Scene variants — named snapshots of the current scene state.

Variants let the agent save the current scene under a name, restore it
later, or spawn jittered alternatives (randomized material hues and small
position offsets). Useful for design exploration: capture a base
arrangement, then spawn variations without losing the original. The store
mirrors the episodic_memory singleton pattern: process-local, lazily
loaded, thread-safe save/load.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("trigen.variants")


@dataclass
class Variant:
    """A named scene snapshot, optionally tracked against a parent variant."""

    name: str
    scene_dict: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    parent: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "scene": self.scene_dict,
            "created_at": self.created_at,
            "parent": self.parent,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Variant":
        return cls(
            name=str(data.get("name", "")),
            scene_dict=dict(data.get("scene", {})),
            created_at=float(data.get("created_at", time.time())),
            parent=data.get("parent"),
        )


@dataclass
class VariantCollection:
    """All scene variants in a workspace, keyed by name."""

    variants: Dict[str, Variant] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {"variants": {k: v.to_dict() for k, v in self.variants.items()}}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VariantCollection":
        return cls(
            variants={
                k: Variant.from_dict(v)
                for k, v in dict(data.get("variants", {})).items()
            }
        )


class _VariantStore:
    """Process-local variant store with JSON persistence."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._collection: Optional[VariantCollection] = None
        self._path: Optional[str] = None

    def init(self, workspace_dir: str) -> None:
        """Initialize the store path and load any existing data."""
        with self._lock:
            self._path = os.path.join(workspace_dir, "variants.json")
            self._collection = self._load_locked()

    def _load_locked(self) -> VariantCollection:
        if not self._path or not os.path.exists(self._path):
            return VariantCollection()
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                return VariantCollection.from_dict(json.load(f))
        except Exception:
            logger.exception("Failed loading variants; starting fresh")
            return VariantCollection()

    def get(self) -> VariantCollection:
        if self._collection is None:
            self.init(
                os.environ.get(
                    "TRIGEN_WORKSPACE",
                    os.path.join(os.getcwd(), ".trigen", "workspace"),
                )
            )
        assert self._collection is not None
        return self._collection

    def save(self) -> None:
        with self._lock:
            if not self._path or self._collection is None:
                return
            try:
                os.makedirs(os.path.dirname(self._path), exist_ok=True)
                with open(self._path, "w", encoding="utf-8") as f:
                    json.dump(self._collection.to_dict(), f, ensure_ascii=False, indent=2)
            except Exception:
                logger.exception("Failed saving variants")

    def reset(self) -> None:
        with self._lock:
            self._collection = VariantCollection()
            if self._path and os.path.exists(self._path):
                try:
                    os.remove(self._path)
                except Exception:
                    logger.exception("Failed removing variants file")


# Module-level singleton.
variant_store = _VariantStore()
