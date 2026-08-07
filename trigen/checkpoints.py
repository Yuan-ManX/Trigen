"""Scene checkpoints — a persistent, revisioned version history of the scene.

Checkpoints differ from variants and scene slots in a few deliberate ways:

* **Ordered & immutable** — every checkpoint gets a monotonically increasing
  ``revision`` (1, 2, 3, …). You can restore an earlier revision but never
  overwrite it, so the history reads as a true timeline of design evolution.
* **Semantic summaries** — each checkpoint stores a short auto-generated
  description (geometry counts, material palette, light rig, notable
  transforms) so the agent and the user can scan "what changed" without
  diffing raw JSON.
* **Diffable** — any two revisions can be compared to yield added / removed /
  kept objects, which powers the ``checkpoint_diff`` tool and the frontend's
  version comparison view.

The store mirrors the episodic_memory / variant_store singleton pattern:
process-local, lazily initialized, JSON-persisted to the workspace, and
guarded by a lock for thread safety.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("trigen.checkpoints")


def _geometry_label(geometry: Dict[str, Any]) -> str:
    """Human-readable label for a geometry dict (e.g. 'box', 'sphere')."""
    return str(geometry.get("type", "object"))


def _material_info(material: Dict[str, Any]) -> Dict[str, Any]:
    """Compact material fingerprint used for palette summaries."""
    color = material.get("color") or "#ffffff"
    return {"color": color, "roughness": material.get("roughness"), "metalness": material.get("metalness")}


def build_scene_summary(scene_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Produce a compact, human-readable summary of a serialized scene.

    Counts geometry types, collects the distinct material palette, tallies
    the light rig by type, and returns a short one-line prose description.
    Safe against missing keys — never raises on partial scene dicts.
    """
    objects = scene_dict.get("objects", []) or []
    lights = scene_dict.get("lights", []) or []

    geometry_counts: Dict[str, int] = {}
    palette: List[str] = []
    seen_colors: set = set()
    for obj in objects:
        label = _geometry_label((obj or {}).get("geometry", {}))
        geometry_counts[label] = geometry_counts.get(label, 0) + 1
        mat = (obj or {}).get("material", {}) or {}
        color = str(mat.get("color") or "#ffffff")
        if color not in seen_colors:
            seen_colors.add(color)
            palette.append(color)

    light_counts: Dict[str, int] = {}
    for light in lights:
        ltype = str((light or {}).get("type", "point"))
        light_counts[ltype] = light_counts.get(ltype, 0) + 1

    total = len(objects)
    if total == 0:
        prose = "empty scene"
    else:
        top = sorted(geometry_counts.items(), key=lambda kv: -kv[1])[:3]
        parts = ", ".join(f"{n} {label}" for label, n in top)
        prose = f"{total} object(s): {parts}"
    if palette:
        prose += f" · palette [{', '.join(palette[:5])}]"
    if light_counts:
        light_str = ", ".join(f"{n} {t}" for t, n in light_counts.items())
        prose += f" · {light_str} light(s)"

    return {
        "object_count": total,
        "geometry_counts": geometry_counts,
        "light_counts": light_counts,
        "palette": palette,
        "prose": prose,
    }


def diff_checkpoint_scenes(
    earlier: Dict[str, Any],
    later: Dict[str, Any],
) -> Dict[str, Any]:
    """Return a structural diff between two serialized scenes.

    Objects are matched by id. The result lists added, removed, and kept
    object ids/names plus high-level counts so callers can summarize "what
    changed" between two revisions.
    """
    earlier_objs = {(o or {}).get("id"): o for o in earlier.get("objects", [])}
    later_objs = {(o or {}).get("id"): o for o in later.get("objects", [])}

    added_ids = [oid for oid in later_objs if oid not in earlier_objs]
    removed_ids = [oid for oid in earlier_objs if oid not in later_objs]
    kept_ids = [oid for oid in earlier_objs if oid in later_objs]

    # Changed objects: same id but a different geometry/material/transform.
    changed_ids = []
    for oid in kept_ids:
        a = earlier_objs[oid]
        b = later_objs[oid]
        if a.get("geometry") != b.get("geometry") or a.get("material") != b.get("material") or a.get("transform") != b.get("transform"):
            changed_ids.append(oid)

    return {
        "added_count": len(added_ids),
        "removed_count": len(removed_ids),
        "changed_count": len(changed_ids),
        "kept_count": len(kept_ids),
        "added": [
            {"id": oid, "name": (later_objs[oid] or {}).get("name", "")}
            for oid in added_ids
        ],
        "removed": [
            {"id": oid, "name": (earlier_objs[oid] or {}).get("name", "")}
            for oid in removed_ids
        ],
        "changed": [
            {"id": oid, "name": (later_objs[oid] or {}).get("name", "")}
            for oid in changed_ids
        ],
    }


@dataclass
class SceneCheckpoint:
    """A single immutable revision of the scene."""

    revision: int
    scene_dict: Dict[str, Any] = field(default_factory=dict)
    description: str = ""
    created_at: float = field(default_factory=time.time)
    created_by: str = "agent"
    summary: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "revision": self.revision,
            "description": self.description,
            "created_at": self.created_at,
            "created_by": self.created_by,
            "summary": self.summary,
            # The full scene payload is stored so restore is lossless.
            "scene": self.scene_dict,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SceneCheckpoint":
        return cls(
            revision=int(data.get("revision", 1)),
            scene_dict=dict(data.get("scene", {})),
            description=str(data.get("description", "")),
            created_at=float(data.get("created_at", time.time())),
            created_by=str(data.get("created_by", "agent")),
            summary=dict(data.get("summary", {})),
        )


@dataclass
class CheckpointHistory:
    """All checkpoints in a workspace, ordered by revision."""

    _next_revision: int = 1
    checkpoints: List[SceneCheckpoint] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "next_revision": self._next_revision,
            "checkpoints": [c.to_dict() for c in self.checkpoints],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CheckpointHistory":
        history = cls(
            _next_revision=int(data.get("next_revision", 1)),
            checkpoints=[
                SceneCheckpoint.from_dict(c) for c in data.get("checkpoints", [])
            ],
        )
        # Recompute next_revision defensively so the history is always
        # monotonic even if the stored value was corrupted.
        if history.checkpoints:
            history._next_revision = max(
                history._next_revision,
                max(c.revision for c in history.checkpoints) + 1,
            )
        return history


class _CheckpointStore:
    """Process-local checkpoint store with JSON persistence."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._history: Optional[CheckpointHistory] = None
        self._path: Optional[str] = None

    def init(self, workspace_dir: str) -> None:
        with self._lock:
            self._path = os.path.join(workspace_dir, "checkpoints.json")
            self._history = self._load_locked()

    def _load_locked(self) -> CheckpointHistory:
        if not self._path or not os.path.exists(self._path):
            return CheckpointHistory()
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                return CheckpointHistory.from_dict(json.load(f))
        except Exception:
            logger.exception("Failed loading checkpoints; starting fresh")
            return CheckpointHistory()

    def get(self) -> CheckpointHistory:
        if self._history is None:
            self.init(
                os.environ.get(
                    "TRIGEN_WORKSPACE",
                    os.path.join(os.getcwd(), ".trigen", "workspace"),
                )
            )
        assert self._history is not None
        return self._history

    def save(self) -> None:
        with self._lock:
            if not self._path or self._history is None:
                return
            try:
                os.makedirs(os.path.dirname(self._path), exist_ok=True)
                with open(self._path, "w", encoding="utf-8") as f:
                    json.dump(self._history.to_dict(), f, ensure_ascii=False, indent=2)
            except Exception:
                logger.exception("Failed saving checkpoints")

    def reset(self) -> None:
        with self._lock:
            self._history = CheckpointHistory()
            if self._path and os.path.exists(self._path):
                try:
                    os.remove(self._path)
                except Exception:
                    logger.exception("Failed removing checkpoints file")


# Module-level singleton, mirroring the variant_store / macro_store pattern.
checkpoint_store = _CheckpointStore()