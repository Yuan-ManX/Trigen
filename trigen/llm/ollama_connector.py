"""Ollama runtime connector.

Discovers models installed in the local Ollama daemon at runtime and merges
them into the Trigen model catalog. This mirrors the Ollama project's own
model-listing surface (`/api/tags`) so Trigen can surface every locally
available model — including custom pulled models — without manual catalog
edits.

The connector is lazy: it probes the Ollama HTTP endpoint on first use and
caches the result for a short TTL so repeated catalog queries remain fast.
When Ollama is not running, the connector silently returns an empty list so
the rest of the system continues to operate with the static catalog.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from trigen.llm.router import Modality, ModelEntry, ProviderType

logger = logging.getLogger("trigen.llm.ollama_connector")

# Default Ollama HTTP endpoint; overridable via environment
DEFAULT_OLLAMA_URL = "http://localhost:11434"

# Cache lifetime in seconds before re-probing the daemon
_CACHE_TTL = 30.0


@dataclass
class OllamaModelInfo:
    """Discovered Ollama model metadata."""

    name: str
    size_bytes: int
    digest: str
    family: str = ""
    parameter_size: str = ""
    quantization: str = ""


class OllamaConnector:
    """Probes the local Ollama daemon and exposes installed models.

    Uses httpx for async HTTP so the probe never blocks the event loop.
    The discovered models are converted into ModelEntry instances ready
    for registration with the ModelRouter.
    """

    def __init__(self, base_url: str = DEFAULT_OLLAMA_URL):
        self.base_url = base_url.rstrip("/")
        self._cache: Optional[List[OllamaModelInfo]] = None
        self._cache_ts: float = 0.0

    async def list_models(self, force_refresh: bool = False) -> List[OllamaModelInfo]:
        """Return installed Ollama models, using a short-lived cache."""
        now = time.time()
        if not force_refresh and self._cache is not None and (now - self._cache_ts) < _CACHE_TTL:
            return self._cache

        models = await self._probe()
        self._cache = models
        self._cache_ts = now
        return models

    async def _probe(self) -> List[OllamaModelInfo]:
        """Call the Ollama `/api/tags` endpoint to enumerate models."""
        try:
            import httpx
        except ImportError:
            logger.warning("httpx not available; Ollama discovery disabled")
            return []

        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get(f"{self.base_url}/api/tags")
                if resp.status_code != 200:
                    logger.debug("Ollama /api/tags returned %d", resp.status_code)
                    return []
                data = resp.json()
        except Exception as exc:
            logger.debug("Ollama daemon not reachable: %s", exc)
            return []

        models: List[OllamaModelInfo] = []
        for item in data.get("models", []):
            name = item.get("name") or item.get("model", "")
            if not name:
                continue
            details = item.get("details", {}) or {}
            models.append(
                OllamaModelInfo(
                    name=name,
                    size_bytes=int(item.get("size", 0) or 0),
                    digest=item.get("digest", ""),
                    family=details.get("family", ""),
                    parameter_size=details.get("parameter_size", ""),
                    quantization=details.get("quantization_level", ""),
                )
            )
        logger.info("Discovered %d Ollama models at %s", len(models), self.base_url)
        return models

    def to_model_entries(self, models: List[OllamaModelInfo]) -> List[ModelEntry]:
        """Convert discovered Ollama models into router ModelEntry items.

        Each model is registered under an `ollama/<name>` id so it can be
        selected from the frontend model selector. Vision-capable Ollama
        models (llava family) are tagged with the VISION modality.
        """
        entries: List[ModelEntry] = []
        for m in models:
            # Determine modality from model family
            modalities: List[Modality] = [Modality.TEXT]
            lower_name = m.name.lower()
            if "llava" in lower_name or "vision" in lower_name or "vl" in lower_name:
                modalities.append(Modality.VISION)

            # Build a human-friendly label
            label_parts = [m.name.split(":")[0].title()]
            if m.parameter_size:
                label_parts.append(m.parameter_size)
            label = " ".join(label_parts)

            description = f"Local Ollama model ({m.family or 'unknown'} family)"
            if m.quantization:
                description += f", {m.quantization}"

            entries.append(
                ModelEntry(
                    id=f"ollama/{m.name}",
                    label=label,
                    provider=ProviderType.OLLAMA,
                    base_url=f"{self.base_url}/v1",
                    api_key_env="OLLAMA_API_KEY",
                    description=description,
                    modalities=modalities,
                    max_tokens=4096,
                    context_window=32768,
                    openai_compatible=True,
                    is_open_source=True,
                    is_local=True,
                )
            )
        return entries


# Global connector instance
connector = OllamaConnector()
