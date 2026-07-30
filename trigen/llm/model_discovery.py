"""Dynamic model discovery for runtime provider exploration.

This module fetches live model listings from providers that expose a
``/models`` endpoint (OpenRouter, Ollama, Together, Groq, etc.) and
registers them in the central ModelRouter at runtime. This lets Trigen
automatically pick up new models the moment they appear on a provider
platform, without requiring a catalog update.

Discovery is non-blocking: each provider is queried independently and
failures are logged but never crash the caller. The orchestrator invokes
``discover_all`` on startup and the frontend can trigger a refresh via
the ``/api/models/discover`` endpoint.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional, Tuple

from trigen.llm.router import (
    Modality,
    ModelEntry,
    ModelRouter,
    ProviderType,
    router as default_router,
)
from trigen.llm.key_store import store as key_store

logger = logging.getLogger("trigen.llm.discovery")


# ---------------------------------------------------------------------------
# Provider discovery adapters
# ---------------------------------------------------------------------------

async def _fetch_json(url: str, headers: Dict[str, str], timeout: float = 15.0) -> Optional[Any]:
    """Fetch JSON from a URL, returning None on any failure."""
    import httpx

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code >= 400:
                logger.debug("Discovery fetch %s returned HTTP %d", url, resp.status_code)
                return None
            return resp.json()
    except Exception as exc:
        logger.debug("Discovery fetch %s failed: %s", url, str(exc)[:100])
        return None


def _guess_modalities(model_id: str, labels: List[str] = None) -> List[Modality]:
    """Infer supported modalities from a model id or label hints."""
    text = (model_id + " " + " ".join(labels or [])).lower()
    modalities = [Modality.TEXT]

    vision_keywords = ["vision", "vl", "multimodal", "image", "llava", "pixtral",
                       "gpt-4o", "gpt-4-turbo", "claude-3", "gemini", "qwen-vl", "glm-4v"]
    if any(kw in text for kw in vision_keywords):
        modalities.append(Modality.VISION)

    audio_keywords = ["audio", "whisper", "tts", "speech"]
    if any(kw in text for kw in audio_keywords):
        modalities.append(Modality.AUDIO)

    return modalities


def _get_api_key(env_name: str) -> str:
    """Retrieve an API key from the runtime key store or environment.

    Uses ``get_next_key`` so listing calls spread load across any indexed
    key pool (``env_name`` + ``env_name_1..N``). Falls back to the base
    env var when the store has no key configured.
    """
    key = key_store.get_next_key(env_name)
    return key or os.environ.get(env_name, "")


async def discover_openrouter(router: ModelRouter) -> int:
    """Discover models from OpenRouter's public model listing.

    OpenRouter aggregates 300+ models from many providers behind a single
    OpenAI-compatible API. When an API key is present, all listed models
    become available for chat.
    """
    api_key = _get_api_key("OPENROUTER_API_KEY")
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    data = await _fetch_json("https://openrouter.ai/api/v1/models", headers)
    if not data or not isinstance(data, dict):
        return 0

    models = data.get("data", [])
    if not isinstance(models, list):
        return 0

    count = 0
    for m in models:
        model_id = m.get("id", "")
        if not model_id:
            continue
        # Skip models already in the catalog to avoid duplicates
        if router.get_model(model_id):
            continue

        # Parse context length and pricing
        context_length = m.get("context_length", 8192)
        try:
            context_length = int(context_length)
        except (TypeError, ValueError):
            context_length = 8192

        label = m.get("name", model_id)
        description = m.get("description", "") or f"{label} via OpenRouter"

        # Determine modality hints
        architecture = m.get("architecture", {})
        modality_list = _guess_modalities(model_id, [label, description])
        if architecture.get("input_modalities"):
            input_mods = architecture["input_modalities"]
            if "image" in input_mods and Modality.VISION not in modality_list:
                modality_list.append(Modality.VISION)
            if "audio" in input_mods and Modality.AUDIO not in modality_list:
                modality_list.append(Modality.AUDIO)

        entry = ModelEntry(
            id=model_id,
            label=label[:60],
            provider=ProviderType.OPENROUTER,
            base_url="https://openrouter.ai/api/v1",
            api_key_env="OPENROUTER_API_KEY",
            description=description[:200],
            modalities=modality_list,
            max_tokens=4096,
            context_window=min(context_length, 1000000),
            openai_compatible=True,
            is_open_source=False,
        )
        router.register(entry)
        count += 1

    logger.info("OpenRouter discovery: registered %d new models", count)
    return count


async def discover_ollama(router: ModelRouter) -> int:
    """Discover locally installed Ollama models.

    Queries the Ollama runtime at ``http://localhost:11434/api/tags`` and
    registers every installed model as a local chat model. Models with
    ``llava`` or ``vision`` in the name get the VISION modality.
    """
    base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
    data = await _fetch_json(f"{base_url}/api/tags", {})
    if not data or not isinstance(data, dict):
        return 0

    models = data.get("models", [])
    if not isinstance(models, list):
        return 0

    count = 0
    for m in models:
        model_id = m.get("name", "")
        if not model_id:
            continue

        # Use a provider-prefixed id to avoid collisions
        prefixed_id = f"ollama/{model_id}"
        if router.get_model(prefixed_id):
            continue

        details = m.get("details", {})
        parameter_size = details.get("parameter_size", "")
        family = details.get("family", "")
        quantization = details.get("quantization_level", "")

        label = model_id.replace("-", " ").title()
        desc_parts = [label]
        if parameter_size:
            desc_parts.append(f"({parameter_size})")
        if family:
            desc_parts.append(f"family: {family}")
        if quantization:
            desc_parts.append(quantization)
        description = " ".join(desc_parts)

        modalities = _guess_modalities(model_id)

        entry = ModelEntry(
            id=prefixed_id,
            label=label,
            provider=ProviderType.OLLAMA,
            base_url=f"{base_url}/v1",
            api_key_env="OLLAMA_API_KEY",
            description=description,
            modalities=modalities,
            max_tokens=4096,
            context_window=32768,
            openai_compatible=True,
            is_open_source=True,
            is_local=True,
        )
        router.register(entry)
        count += 1

    logger.info("Ollama discovery: registered %d local models", count)
    return count


async def discover_together(router: ModelRouter) -> int:
    """Discover models from Together AI's model listing."""
    api_key = _get_api_key("TOGETHER_API_KEY")
    if not api_key:
        return 0

    headers = {"Authorization": f"Bearer {api_key}"}
    data = await _fetch_json("https://api.together.xyz/v1/models", headers)
    if not data or not isinstance(data, list):
        return 0

    count = 0
    for m in data:
        model_id = m.get("id", "")
        if not model_id or router.get_model(model_id):
            continue

        display_name = m.get("display_name", model_id)
        entry = ModelEntry(
            id=model_id,
            label=display_name[:60],
            provider=ProviderType.TOGETHER,
            base_url="https://api.together.xyz/v1",
            api_key_env="TOGETHER_API_KEY",
            description=f"{display_name} on Together AI",
            modalities=_guess_modalities(model_id),
            max_tokens=4096,
            context_window=32768,
            openai_compatible=True,
            is_open_source=True,
        )
        router.register(entry)
        count += 1

    logger.info("Together AI discovery: registered %d new models", count)
    return count


async def discover_groq(router: ModelRouter) -> int:
    """Discover models from Groq's model listing."""
    api_key = _get_api_key("GROQ_API_KEY")
    if not api_key:
        return 0

    headers = {"Authorization": f"Bearer {api_key}"}
    data = await _fetch_json("https://api.groq.com/openai/v1/models", headers)
    if not data or not isinstance(data, dict):
        return 0

    models = data.get("data", [])
    if not isinstance(models, list):
        return 0

    count = 0
    for m in models:
        model_id = m.get("id", "")
        if not model_id or router.get_model(model_id):
            continue

        entry = ModelEntry(
            id=model_id,
            label=model_id.split("/")[-1][:60],
            provider=ProviderType.GROQ,
            base_url="https://api.groq.com/openai/v1",
            api_key_env="GROQ_API_KEY",
            description=f"{model_id} on Groq ultra-fast inference",
            modalities=_guess_modalities(model_id),
            max_tokens=32768,
            context_window=131072,
            openai_compatible=True,
            is_open_source=True,
        )
        router.register(entry)
        count += 1

    logger.info("Groq discovery: registered %d new models", count)
    return count


async def discover_mistral(router: ModelRouter) -> int:
    """Discover models from Mistral AI's model listing."""
    api_key = _get_api_key("MISTRAL_API_KEY")
    if not api_key:
        return 0

    headers = {"Authorization": f"Bearer {api_key}"}
    data = await _fetch_json("https://api.mistral.ai/v1/models", headers)
    if not data or not isinstance(data, dict):
        return 0

    models = data.get("data", [])
    if not isinstance(models, list):
        return 0

    count = 0
    for m in models:
        model_id = m.get("id", "")
        if not model_id or router.get_model(model_id):
            continue

        modalities = _guess_modalities(model_id)
        entry = ModelEntry(
            id=model_id,
            label=model_id[:60],
            provider=ProviderType.MISTRAL,
            base_url="https://api.mistral.ai/v1",
            api_key_env="MISTRAL_API_KEY",
            description=f"{model_id} on Mistral AI",
            modalities=modalities,
            max_tokens=8192,
            context_window=128000,
            openai_compatible=True,
            is_open_source=False,
        )
        router.register(entry)
        count += 1

    logger.info("Mistral AI discovery: registered %d new models", count)
    return count


# Replicate models that are clearly not chat/language models are skipped to
# keep the catalog focused. The keyword list matches model ids and labels.
_REPLICATE_LLM_KEYWORDS = (
    "llama", "mistral", "qwen", "phi", "gemma", "yi", "deepseek", "falcon",
    "chat", "instruct", "llm", "gpt", "openchat", "zephyr", "starling",
    "mixtral", "vicuna", "wizard", "solar", "internlm", "baichuan", "command",
)


async def discover_huggingface(router: ModelRouter) -> int:
    """Discover models from the Hugging Face Inference API.

    The Inference API exposes an OpenAI-compatible ``/v1/models`` endpoint
    that lists chat-capable models hosted by Hugging Face. Each model is
    registered with the ``HUGGINGFACE`` provider type so it dispatches
    through the OpenAI client against the HF base URL.
    """
    api_key = _get_api_key("HF_TOKEN")
    if not api_key:
        return 0

    headers = {"Authorization": f"Bearer {api_key}"}
    data = await _fetch_json(
        "https://api-inference.huggingface.co/v1/models", headers
    )
    # The endpoint may return either {"data": [...]} (OpenAI shape) or a bare list
    models: List[Any] = []
    if isinstance(data, dict):
        models = data.get("data", []) or []
    elif isinstance(data, list):
        models = data
    if not isinstance(models, list):
        return 0

    count = 0
    for m in models:
        if not isinstance(m, dict):
            continue
        model_id = m.get("id", "")
        if not model_id or router.get_model(model_id):
            continue
        label = m.get("id", model_id)[:60]
        entry = ModelEntry(
            id=model_id,
            label=label,
            provider=ProviderType.HUGGINGFACE,
            base_url="https://api-inference.huggingface.co/v1",
            api_key_env="HF_TOKEN",
            description=f"{model_id} via Hugging Face Inference API",
            modalities=_guess_modalities(model_id),
            max_tokens=4096,
            context_window=32768,
            openai_compatible=True,
            is_open_source=True,
        )
        router.register(entry)
        count += 1

    logger.info("Hugging Face discovery: registered %d new models", count)
    return count


async def discover_replicate(router: ModelRouter) -> int:
    """Discover language models from Replicate's model listing.

    Replicate's ``/v1/models`` endpoint returns paginated results across all
    public models. To avoid flooding the catalog with image/audio/video
    models, only entries whose id or name matches a language-model keyword
    are registered. Each is registered with the ``REPLICATE`` provider type.
    """
    api_key = _get_api_key("REPLICATE_API_TOKEN")
    if not api_key:
        return 0

    headers = {"Authorization": f"Bearer {api_key}"}
    data = await _fetch_json("https://api.replicate.com/v1/models", headers)
    if not data or not isinstance(data, dict):
        return 0

    models = data.get("results", [])
    if not isinstance(models, list):
        return 0

    count = 0
    for m in models:
        if not isinstance(m, dict):
            continue
        owner = m.get("owner", "")
        name = m.get("name", "")
        if not name:
            continue
        model_id = f"{owner}/{name}" if owner else name
        if router.get_model(model_id):
            continue
        haystack = f"{model_id} {m.get('description', '')}".lower()
        if not any(kw in haystack for kw in _REPLICATE_LLM_KEYWORDS):
            continue
        entry = ModelEntry(
            id=model_id,
            label=name[:60],
            provider=ProviderType.REPLICATE,
            base_url="https://api.replicate.com/v1",
            api_key_env="REPLICATE_API_TOKEN",
            description=m.get("description", "")[:200] or f"{model_id} on Replicate",
            modalities=_guess_modalities(model_id),
            max_tokens=4096,
            context_window=32768,
            openai_compatible=True,
            is_open_source=True,
        )
        router.register(entry)
        count += 1

    logger.info("Replicate discovery: registered %d new language models", count)
    return count


async def discover_stability(router: ModelRouter) -> int:
    """Discover image-generation engines from Stability AI.

    Stability AI exposes a ``/v1/engines/list`` endpoint that returns the
    available generation engines. Each engine is registered as an
    ``IMAGE_GEN`` model under the ``STABILITY`` provider type.
    """
    api_key = _get_api_key("STABILITY_API_KEY")
    if not api_key:
        return 0

    headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
    data = await _fetch_json("https://api.stability.ai/v1/engines/list", headers)
    if not isinstance(data, list):
        return 0

    count = 0
    for m in data:
        if not isinstance(m, dict):
            continue
        engine_id = m.get("id", "")
        if not engine_id or router.get_model(engine_id):
            continue
        name = m.get("name", engine_id)
        engine_type = m.get("type", "")
        entry = ModelEntry(
            id=engine_id,
            label=name[:60],
            provider=ProviderType.STABILITY,
            base_url="https://api.stability.ai/v1",
            api_key_env="STABILITY_API_KEY",
            description=f"Stability AI {name} ({engine_type})" if engine_type else f"Stability AI {name}",
            modalities=[Modality.IMAGE_GEN],
            max_tokens=1,
            context_window=4000,
            openai_compatible=False,
            is_open_source=True,
        )
        router.register(entry)
        count += 1

    logger.info("Stability AI discovery: registered %d engines", count)
    return count


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

async def discover_all(router: ModelRouter = None) -> Dict[str, int]:
    """Run all discovery adapters concurrently and return per-provider counts.

    Each adapter is independent: if one fails, the others still run.
    Returns a dict like ``{"openrouter": 312, "ollama": 4, "together": 0}``.
    """
    import asyncio

    r = router or default_router
    results: Dict[str, int] = {}

    tasks = [
        ("openrouter", discover_openrouter(r)),
        ("ollama", discover_ollama(r)),
        ("together", discover_together(r)),
        ("groq", discover_groq(r)),
        ("mistral", discover_mistral(r)),
        ("huggingface", discover_huggingface(r)),
        ("replicate", discover_replicate(r)),
        ("stability", discover_stability(r)),
    ]

    gathered = await asyncio.gather(
        *[t[1] for t in tasks], return_exceptions=True
    )

    for (name, _), result in zip(tasks, gathered):
        if isinstance(result, Exception):
            logger.warning("Discovery for %s failed: %s", name, str(result)[:100])
            results[name] = 0
        else:
            results[name] = result

    total = sum(results.values())
    if total > 0:
        logger.info("Model discovery complete: %d new models registered (%s)", total, results)

    return results
