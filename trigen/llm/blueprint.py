"""Per-model generation blueprints.

A ``ModelBlueprint`` captures the tunable generation parameters a user
wants applied to a specific model id: temperature, max_tokens, stop
sequences, a prompt template, a system-prompt override, and a reasoning
effort hint. Blueprints are stored per model id and persisted to a JSON
file under the Trigen workspace so they survive process restarts.

Resolution order at call time (``LLMClient._resolve_params``):
  1. ``LLMConfig`` defaults (temperature / max_tokens from env or config)
  2. ``ModelEntry.blueprint`` (a model shipped with a default blueprint)
  3. Runtime ``BlueprintStore`` override (set via the API)

Later sources win. Fields that are ``None`` on the winning blueprint fall
back to the earlier source, so a user can override only ``temperature``
while leaving ``max_tokens`` untouched.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger("trigen.llm.blueprint")


@dataclass
class ModelBlueprint:
    """Tunable generation parameters for a single model id.

    All fields are optional; ``None`` means "inherit the default".
    """

    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    stop: Optional[List[str]] = None
    template: Optional[str] = None
    system_override: Optional[str] = None
    reasoning_effort: Optional[str] = None  # "low" | "medium" | "high"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ModelBlueprint":
        return cls(
            temperature=data.get("temperature"),
            max_tokens=data.get("max_tokens"),
            stop=list(data["stop"]) if data.get("stop") else None,
            template=data.get("template"),
            system_override=data.get("system_override"),
            reasoning_effort=data.get("reasoning_effort"),
        )

    def merge_over(self, base: "ModelBlueprint") -> "ModelBlueprint":
        """Return a new blueprint with self's non-None fields overriding base."""
        return ModelBlueprint(
            temperature=self.temperature if self.temperature is not None else base.temperature,
            max_tokens=self.max_tokens if self.max_tokens is not None else base.max_tokens,
            stop=self.stop if self.stop is not None else base.stop,
            template=self.template if self.template is not None else base.template,
            system_override=self.system_override if self.system_override is not None else base.system_override,
            reasoning_effort=self.reasoning_effort if self.reasoning_effort is not None else base.reasoning_effort,
        )


_EMPTY = ModelBlueprint()


class BlueprintStore:
    """Per-model-id blueprint registry with JSON persistence.

    Thread-safe (a single lock guards the in-memory dict and the write
    path). The persistence file is written best-effort: a failure to
    save logs a warning but never raises, so a bad filesystem state
    can't break the LLM call path.
    """

    def __init__(self, persist_path: Optional[str] = None) -> None:
        self._blueprints: Dict[str, ModelBlueprint] = {}
        self._persist_path = persist_path
        self._lock = threading.RLock()
        if persist_path:
            self._load()

    def _load(self) -> None:
        if not self._persist_path:
            return
        try:
            with open(self._persist_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            return
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to load blueprints from %s: %s", self._persist_path, exc)
            return
        if not isinstance(data, dict):
            return
        for model_id, bp_data in data.items():
            if isinstance(bp_data, dict):
                try:
                    self._blueprints[model_id] = ModelBlueprint.from_dict(bp_data)
                except Exception as exc:  # pragma: no cover — defensive
                    logger.warning("Skipping bad blueprint for %s: %s", model_id, exc)

    def _persist(self) -> None:
        if not self._persist_path:
            return
        try:
            os.makedirs(os.path.dirname(self._persist_path), exist_ok=True)
            payload = {mid: bp.to_dict() for mid, bp in self._blueprints.items()}
            with open(self._persist_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
        except OSError as exc:
            logger.warning("Failed to persist blueprints to %s: %s", self._persist_path, exc)

    def get(self, model_id: str) -> Optional[ModelBlueprint]:
        with self._lock:
            return self._blueprints.get(model_id)

    def set(self, model_id: str, blueprint: ModelBlueprint) -> None:
        with self._lock:
            # Drop all-None blueprints so the store stays clean.
            if blueprint == _EMPTY:
                self._blueprints.pop(model_id, None)
            else:
                self._blueprints[model_id] = blueprint
            self._persist()

    def delete(self, model_id: str) -> bool:
        with self._lock:
            existed = model_id in self._blueprints
            self._blueprints.pop(model_id, None)
            if existed:
                self._persist()
            return existed

    def all(self) -> Dict[str, ModelBlueprint]:
        with self._lock:
            return dict(self._blueprints)

    def all_as_dict(self) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            return {mid: bp.to_dict() for mid, bp in self._blueprints.items()}


# Global store instance — persists under the workspace directory
def _default_persist_path() -> str:
    workspace = os.environ.get(
        "TRIGEN_WORKSPACE",
        os.path.join(os.getcwd(), ".trigen", "workspace"),
    )
    return os.path.join(workspace, "model_blueprints.json")


store = BlueprintStore(persist_path=_default_persist_path())
