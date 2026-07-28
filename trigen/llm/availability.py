"""Model availability checker.

Reports which models in the catalog are actually usable right now — i.e.
have a configured API key, are locally available (Ollama running), or are
the built-in offline default. The frontend uses this to dim unavailable
models in the selector and to surface a quick-look status panel.

This module is intentionally side-effect free: it only reads environment
variables and probes the local Ollama daemon. It never modifies state.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List

from trigen.llm.ollama_connector import connector as ollama_connector
from trigen.llm.router import Modality, ProviderType, router as model_router

logger = logging.getLogger("trigen.llm.availability")


@dataclass
class ModelAvailability:
    """Availability status for a single model."""

    id: str
    label: str
    provider: str
    available: bool
    reason: str = ""
    modalities: List[str] = field(default_factory=list)
    is_local: bool = False
    is_open_source: bool = False
    is_generation: bool = False


class AvailabilityChecker:
    """Evaluates which models in the catalog can be invoked right now.

    A model is considered available when:
      - It is the trigen-default offline engine (always available)
      - It is an Ollama model and the daemon is reachable with that model
        installed, or the daemon is reachable at all (model may be pulled)
      - Its API key environment variable is set to a non-empty value
      - It is a custom-provider model with a stored API key
    """

    def __init__(self) -> None:
        self._ollama_reachable: bool | None = None
        self._ollama_model_names: set[str] = set()

    async def _probe_ollama(self) -> None:
        """Probe the Ollama daemon once and cache the result."""
        if self._ollama_reachable is not None:
            return
        try:
            models = await ollama_connector.list_models()
            self._ollama_reachable = True
            self._ollama_model_names = {m.name for m in models}
        except Exception:
            self._ollama_reachable = False
            self._ollama_model_names = set()

    async def check_all(self) -> List[ModelAvailability]:
        """Return availability for every model in the catalog."""
        await self._probe_ollama()
        result: List[ModelAvailability] = []
        for entry in model_router.list_models():
            avail = self._evaluate(entry)
            result.append(avail)
        return result

    def _evaluate(self, entry: Any) -> ModelAvailability:
        """Evaluate a single ModelEntry."""
        # Trigen default is always available (offline rule engine)
        if entry.id == "trigen-default":
            return ModelAvailability(
                id=entry.id,
                label=entry.label,
                provider=entry.provider.value,
                available=True,
                reason="Offline rule engine",
                modalities=[m.value for m in entry.modalities],
                is_local=True,
            )

        is_generation = model_router.is_generation_model(entry.id)

        # Custom-provider models: API key stored in the registry
        if entry.id.startswith("custom/"):
            try:
                from trigen.llm.provider_registry import registry

                key = registry.resolve_api_key(entry.id)
                return ModelAvailability(
                    id=entry.id,
                    label=entry.label,
                    provider=entry.provider.value,
                    available=bool(key),
                    reason="Custom provider — key configured" if key else "No API key in registry",
                    modalities=[m.value for m in entry.modalities],
                    is_local=entry.is_local,
                    is_open_source=entry.is_open_source,
                    is_generation=is_generation,
                )
            except Exception as exc:
                return ModelAvailability(
                    id=entry.id,
                    label=entry.label,
                    provider=entry.provider.value,
                    available=False,
                    reason=f"Registry error: {exc}",
                    modalities=[m.value for m in entry.modalities],
                    is_local=entry.is_local,
                    is_open_source=entry.is_open_source,
                    is_generation=is_generation,
                )

        # Ollama models: probe daemon reachability
        if entry.provider == ProviderType.OLLAMA:
            if self._ollama_reachable:
                # Strip the "ollama/" prefix to compare with daemon names
                short_name = entry.id.split("/", 1)[-1] if "/" in entry.id else entry.id
                installed = short_name in self._ollama_model_names or entry.id in self._ollama_model_names
                reason = "Installed locally" if installed else "Daemon reachable — model can be pulled"
                return ModelAvailability(
                    id=entry.id,
                    label=entry.label,
                    provider=entry.provider.value,
                    available=True,
                    reason=reason,
                    modalities=[m.value for m in entry.modalities],
                    is_local=True,
                    is_open_source=entry.is_open_source,
                    is_generation=is_generation,
                )
            return ModelAvailability(
                id=entry.id,
                label=entry.label,
                provider=entry.provider.value,
                available=False,
                reason="Ollama daemon not running",
                modalities=[m.value for m in entry.modalities],
                is_local=True,
                is_open_source=entry.is_open_source,
                is_generation=is_generation,
            )

        # Cloud models: check API key in environment
        api_key = os.environ.get(entry.api_key_env, "") if entry.api_key_env else ""
        return ModelAvailability(
            id=entry.id,
            label=entry.label,
            provider=entry.provider.value,
            available=bool(api_key),
            reason="API key configured" if api_key else f"Set {entry.api_key_env} to enable",
            modalities=[m.value for m in entry.modalities],
            is_local=entry.is_local,
            is_open_source=entry.is_open_source,
            is_generation=is_generation,
        )


# Global checker instance
checker = AvailabilityChecker()
