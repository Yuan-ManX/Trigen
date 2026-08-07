"""Workflow registry — saveable Agentic tool-graph recipes.

A Workflow captures a named, ordered sequence of (tool, arguments) steps
that the Agent can save and replay later. Distinct from macros (which
record ad-hoc user-defined recipes), Workflows are intended to be the
curated, shareable unit of an Agentic Workflow Template: a ComfyUI-style
saveable tool-graph fused with the Hermes-style tool loop. Each step is a
single Agent tool call, and invoking a Workflow replays the steps
sequentially through the same executor pipeline used for normal tool
calls, emitting the merged SceneDelta stream.

Persistence is a single JSON file under the workspace so it works without
a database and is easy to inspect. The store mirrors the macro_store /
episodic_store singleton pattern: process-local, lazily loaded,
thread-safe save/load.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

logger = logging.getLogger("trigen.workflows")


@dataclass
class WorkflowStep:
    """A single step inside a workflow — a tool name + its arguments."""

    tool: str
    arguments: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {"tool": self.tool, "arguments": self.arguments}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorkflowStep":
        return cls(
            tool=str(data.get("tool", "")),
            arguments=dict(data.get("arguments", {})),
        )


@dataclass
class Workflow:
    """A named, reusable Agentic tool-graph recipe."""

    name: str
    description: str = ""
    steps: List[WorkflowStep] = field(default_factory=list)
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
    def from_dict(cls, data: Dict[str, Any]) -> "Workflow":
        return cls(
            name=str(data.get("name", "")),
            description=str(data.get("description", "")),
            steps=[WorkflowStep.from_dict(s) for s in data.get("steps", [])],
            created_at=float(data.get("created_at", time.time())),
            uses=int(data.get("uses", 0)),
        )


@dataclass
class WorkflowCollection:
    """All workflows in a workspace, keyed by name."""

    workflows: Dict[str, Workflow] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {"workflows": {k: v.to_dict() for k, v in self.workflows.items()}}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorkflowCollection":
        return cls(
            workflows={
                k: Workflow.from_dict(v)
                for k, v in dict(data.get("workflows", {})).items()
            }
        )


class _WorkflowStore:
    """Process-local workflow store with JSON persistence."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._collection: Optional[WorkflowCollection] = None
        self._path: Optional[str] = None

    def init(self, workspace_dir: str) -> None:
        """Initialize the store path and load any existing data."""
        with self._lock:
            self._path = os.path.join(workspace_dir, "workflows.json")
            self._collection = self._load_locked()

    def _load_locked(self) -> WorkflowCollection:
        if not self._path or not os.path.exists(self._path):
            return WorkflowCollection()
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                return WorkflowCollection.from_dict(json.load(f))
        except Exception:
            logger.exception("Failed loading workflows; starting fresh")
            return WorkflowCollection()

    def get(self) -> WorkflowCollection:
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
                logger.exception("Failed saving workflows")

    def reset(self) -> None:
        with self._lock:
            self._collection = WorkflowCollection()
            if self._path and os.path.exists(self._path):
                try:
                    os.remove(self._path)
                except Exception:
                    logger.exception("Failed removing workflows file")


# Module-level singleton.
workflow_store = _WorkflowStore()
