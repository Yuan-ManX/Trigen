"""Macro registry — reusable user-defined tool-call sequences.

Macros capture a named, ordered sequence of (tool, arguments) steps so the
agent can replay them on demand. This lets users teach the agent reusable
recipes (e.g. "studio_setup" = add 3 lights + set background) without
re-stating the full chain every turn. Persistence is a single JSON file
under the workspace so it works without a database and is easy to inspect.

The store mirrors the episodic_memory singleton pattern: process-local,
lazily loaded, thread-safe save/load.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

logger = logging.getLogger("trigen.macros")


@dataclass
class MacroStep:
    """A single step inside a macro — a tool name + its arguments."""

    tool: str
    arguments: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {"tool": self.tool, "arguments": self.arguments}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MacroStep":
        return cls(
            tool=str(data.get("tool", "")),
            arguments=dict(data.get("arguments", {})),
        )


@dataclass
class Macro:
    """A named, reusable tool-call sequence."""

    name: str
    description: str = ""
    steps: List[MacroStep] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    uses: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "steps": [s.to_dict() for s in self.steps],
            "created_at": self.created_at,
            "uses": self.uses,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Macro":
        return cls(
            name=str(data.get("name", "")),
            description=str(data.get("description", "")),
            steps=[MacroStep.from_dict(s) for s in data.get("steps", [])],
            created_at=float(data.get("created_at", time.time())),
            uses=int(data.get("uses", 0)),
        )


@dataclass
class MacroCollection:
    """All macros in a workspace, keyed by name."""

    macros: Dict[str, Macro] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {"macros": {k: v.to_dict() for k, v in self.macros.items()}}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MacroCollection":
        return cls(
            macros={
                k: Macro.from_dict(v)
                for k, v in dict(data.get("macros", {})).items()
            }
        )


class _MacroStore:
    """Process-local macro store with JSON persistence."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._collection: Optional[MacroCollection] = None
        self._path: Optional[str] = None

    def init(self, workspace_dir: str) -> None:
        """Initialize the store path and load any existing data."""
        with self._lock:
            self._path = os.path.join(workspace_dir, "macros.json")
            self._collection = self._load_locked()

    def _load_locked(self) -> MacroCollection:
        if not self._path or not os.path.exists(self._path):
            return MacroCollection()
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                return MacroCollection.from_dict(json.load(f))
        except Exception:
            logger.exception("Failed loading macros; starting fresh")
            return MacroCollection()

    def get(self) -> MacroCollection:
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
                logger.exception("Failed saving macros")

    def reset(self) -> None:
        with self._lock:
            self._collection = MacroCollection()
            if self._path and os.path.exists(self._path):
                try:
                    os.remove(self._path)
                except Exception:
                    logger.exception("Failed removing macros file")


# Module-level singleton.
macro_store = _MacroStore()
