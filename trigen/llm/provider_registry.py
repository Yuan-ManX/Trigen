"""Universal provider registry.

Allows runtime registration of custom OpenAI-compatible endpoints so new
providers can be added without code changes or restarts. Each custom
provider carries its own base URL, API key, and model list, and is merged
into the live catalog on registration.

This follows the OpenConnector pattern of treating every external service
as a pluggable connector: a provider is described by a small descriptor
object, and the registry is the single source of truth that the router
consults at request time.

Custom provider metadata (name, base_url, models) is persisted to a JSON
file under the workspace so registrations survive restarts. API keys are
NOT written to that file — they are handed to the runtime ``key_store``,
which is the single secure home for secrets. The registry file only stores
a key handle (the env-name under which the key was stored) so the key can
be retrieved at request time without leaking it to disk alongside metadata.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from trigen.llm.router import Modality, ModelEntry, ProviderType, router as model_router

logger = logging.getLogger("trigen.llm.provider_registry")

# Persistence path for registered custom providers (metadata only — no keys)
_REGISTRY_FILE = os.path.join(
    os.environ.get("TRIGEN_WORKSPACE", os.path.join(os.getcwd(), ".trigen", "workspace")),
    "custom_providers.json",
)


def _key_handle(provider_name: str) -> str:
    """Build the env-name handle under which a provider's key is stored."""
    # Sanitize the provider name into a stable env-style handle. The handle
    # is only used as a lookup key in the key_store, never as a real env var.
    safe = "".join(c if c.isalnum() else "_" for c in provider_name).upper()
    return f"CUSTOM_PROVIDER_{safe}_API_KEY"


@dataclass
class CustomModel:
    """A model offered by a custom provider."""

    id: str
    label: str
    description: str = ""
    modalities: List[str] = field(default_factory=lambda: ["text"])
    max_tokens: int = 4096
    context_window: int = 8192


@dataclass
class CustomProvider:
    """Descriptor of a user-registered provider endpoint."""

    name: str
    base_url: str
    api_key: str
    openai_compatible: bool = True
    is_local: bool = False
    models: List[CustomModel] = field(default_factory=list)


class ProviderRegistry:
    """Manages custom provider registrations and router integration.

    Registered providers are converted into ModelEntry instances and
    pushed into the live ModelRouter so they immediately appear in the
    catalog and can be selected from the frontend.
    """

    def __init__(self) -> None:
        self._providers: Dict[str, CustomProvider] = {}
        self._lock = asyncio.Lock()
        self._loaded = False

    def _ensure_loaded(self) -> None:
        """Lazily load persisted providers on first access.

        API keys are rehydrated from the key_store (which has its own
        persistence), not from the registry JSON.
        """
        if self._loaded:
            return
        self._loaded = True
        try:
            if os.path.exists(_REGISTRY_FILE):
                with open(_REGISTRY_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for prov_data in data.get("providers", []):
                    models = [CustomModel(**m) for m in prov_data.get("models", [])]
                    handle = prov_data.get("key_handle", "")
                    # Rehydrate the key from the secure key_store
                    api_key = ""
                    if handle:
                        try:
                            from trigen.llm.key_store import store as _key_store

                            api_key = _key_store.get_key(handle)
                        except Exception:
                            api_key = ""
                    prov = CustomProvider(
                        name=prov_data["name"],
                        base_url=prov_data["base_url"],
                        api_key=api_key,
                        openai_compatible=prov_data.get("openai_compatible", True),
                        is_local=prov_data.get("is_local", False),
                        models=models,
                    )
                    # Stash the handle so resolve_api_key can find it
                    prov._key_handle = handle  # type: ignore[attr-defined]
                    self._providers[prov.name] = prov
                    self._sync_to_router(prov)
                logger.info("Loaded %d custom providers from %s", len(self._providers), _REGISTRY_FILE)
        except Exception as exc:
            logger.warning("Failed to load custom providers: %s", exc)

    def _sync_to_router(self, prov: CustomProvider) -> None:
        """Register all models of a custom provider with the live router."""
        for m in prov.models:
            # Modality conversion
            mods: List[Modality] = []
            for mod_str in m.modalities:
                try:
                    mods.append(Modality(mod_str))
                except ValueError:
                    mods.append(Modality.TEXT)
            if not mods:
                mods = [Modality.TEXT]

            entry = ModelEntry(
                id=f"custom/{prov.name}/{m.id}",
                label=m.label,
                provider=ProviderType.LOCAL if prov.is_local else ProviderType.OPENROUTER,
                base_url=prov.base_url,
                api_key_env="",  # Custom providers store the key in key_store
                description=m.description or f"Custom model from {prov.name}",
                modalities=mods,
                max_tokens=m.max_tokens,
                context_window=m.context_window,
                openai_compatible=prov.openai_compatible,
                is_open_source=False,
                is_local=prov.is_local,
            )
            model_router.register(entry)

    async def register_provider(self, prov: CustomProvider) -> Dict[str, Any]:
        """Register a new custom provider and persist it.

        The API key is moved into the runtime key_store under a derived
        handle; only the handle is written to the registry JSON. This keeps
        secrets out of the metadata file. If a provider with the same name
        already exists, it is overwritten.
        """
        async with self._lock:
            self._ensure_loaded()
            handle = _key_handle(prov.name)
            # Hand the key to the secure store; clear it from the in-memory
            # descriptor so it is never accidentally serialized.
            if prov.api_key:
                try:
                    from trigen.llm.key_store import store as _key_store

                    _key_store.set_key(handle, prov.api_key)
                except Exception as exc:
                    logger.warning("Failed to store key for %s: %s", prov.name, exc)
            prov._key_handle = handle  # type: ignore[attr-defined]
            prov.api_key = ""  # Never hold the raw key in the descriptor
            self._providers[prov.name] = prov
            self._sync_to_router(prov)
            await self._persist()
        logger.info("Registered custom provider '%s' with %d models", prov.name, len(prov.models))
        return {
            "provider": prov.name,
            "base_url": prov.base_url,
            "model_count": len(prov.models),
            "model_ids": [f"custom/{prov.name}/{m.id}" for m in prov.models],
        }

    async def remove_provider(self, name: str) -> bool:
        """Remove a custom provider. Returns True if it existed.

        Also clears the provider's key from the key_store.
        """
        async with self._lock:
            self._ensure_loaded()
            if name not in self._providers:
                return False
            handle = _key_handle(name)
            try:
                from trigen.llm.key_store import store as _key_store

                _key_store.delete_key(handle)
            except Exception:
                pass
            del self._providers[name]
            await self._persist()
        logger.info("Removed custom provider '%s'", name)
        return True

    def list_providers(self) -> List[Dict[str, Any]]:
        """Return all registered custom providers as serializable dicts."""
        self._ensure_loaded()
        result: List[Dict[str, Any]] = []
        for prov in self._providers.values():
            result.append(
                {
                    "name": prov.name,
                    "base_url": prov.base_url,
                    "openai_compatible": prov.openai_compatible,
                    "is_local": prov.is_local,
                    "model_count": len(prov.models),
                    "models": [asdict(m) for m in prov.models],
                }
            )
        return result

    def get_provider(self, name: str) -> Optional[CustomProvider]:
        """Look up a custom provider by name."""
        self._ensure_loaded()
        return self._providers.get(name)

    def resolve_api_key(self, model_id: str) -> Optional[str]:
        """Return the API key for a custom-model id, if registered.

        The key is retrieved from the runtime key_store using the handle
        derived from the provider name — never from the registry JSON.
        """
        self._ensure_loaded()
        if not model_id.startswith("custom/"):
            return None
        parts = model_id.split("/", 2)
        if len(parts) < 3:
            return None
        prov_name = parts[1]
        prov = self._providers.get(prov_name)
        if prov is None:
            return None
        handle = getattr(prov, "_key_handle", "") or _key_handle(prov_name)
        if not handle:
            return None
        try:
            from trigen.llm.key_store import store as _key_store

            key = _key_store.get_key(handle)
            return key or None
        except Exception:
            return None

    async def _persist(self) -> None:
        """Write provider metadata (no keys) to disk."""
        os.makedirs(os.path.dirname(_REGISTRY_FILE), exist_ok=True)
        data = {
            "providers": [
                {
                    "name": prov.name,
                    "base_url": prov.base_url,
                    # Store the handle, never the raw key
                    "key_handle": getattr(prov, "_key_handle", _key_handle(prov.name)),
                    "openai_compatible": prov.openai_compatible,
                    "is_local": prov.is_local,
                    "models": [asdict(m) for m in prov.models],
                }
                for prov in self._providers.values()
            ]
        }
        with open(_REGISTRY_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)


# Global registry instance
registry = ProviderRegistry()
