"""Trigen LLM Client.

Unified wrapper that dispatches to diverse LLM providers via the
``ModelRouter`` and the transport registry. Chat / vision calls are
routed to the ``ChatTransport`` registered for the resolved provider
(OpenAI-compatible providers share the ``OpenAITransport``; Anthropic
uses the ``AnthropicTransport``). The transport owns the wire protocol;
this client owns fallback-chain iteration and multi-key rotation.
"""

from __future__ import annotations

import logging
from typing import Any, AsyncIterator, Dict, List, Optional

from trigen.config import LLMConfig
from trigen.llm.router import ModelRouter, Modality, ProviderType, router as default_router
from trigen.llm.types import (
    LLMResponse,
    LLMStreamChunk,
    RetriableError as _RetriableError,
    ToolCall,
)

logger = logging.getLogger("trigen.llm")

# Re-export shared types so existing imports (`from trigen.llm.client import ...`)
# keep working without depending on the transports package.
__all__ = [
    "LLMClient",
    "LLMResponse",
    "LLMStreamChunk",
    "ModelRouter",
    "ModelEntry",
    "Modality",
    "ProviderType",
    "ToolCall",
    "router",
]


class LLMClient:
    """Asynchronous LLM client with multi-provider routing.

    When a model id is passed to stream()/complete(), the router resolves
    the correct provider, base_url, and api_key. The transport registry
    then selects the transport that speaks the provider's wire protocol.
    If the model is unknown, the router falls back to the default
    ``LLMConfig`` values.

    Both stream() and complete() build a fallback chain via the router so
    that a retriable failure (5xx, timeout, rate-limit, auth) on the
    primary model automatically advances to the next candidate model.
    When a key rotation pool exists for the failing provider, the same
    model is retried with a different key before advancing the chain.
    """

    # Maximum number of models tried per call before giving up.
    MAX_FALLBACK_ATTEMPTS = 3

    def __init__(self, config: LLMConfig, model_router: Optional[ModelRouter] = None):
        self.config = config
        self.router = model_router or default_router

    # ------------------------------------------------------------------
    # Param resolution + key rotation
    # ------------------------------------------------------------------
    def _resolve_params(self, model: Optional[str], api_key_override: str = "") -> Dict[str, Any]:
        """Resolve connection parameters for a model id.

        ``api_key_override`` (when non-empty) replaces the resolved api_key.
        Used by the multi-key rotation path to retry the same model with a
        different key after a rate-limit/auth failure.

        A per-model ``ModelBlueprint`` (shipped on the ``ModelEntry`` and/or
        set at runtime via ``blueprint.store``) is merged over the
        ``LLMConfig`` defaults. The effective temperature / max_tokens are
        placed on the returned params, and ``stop`` / ``reasoning_effort``
        are forwarded so transports can honor them. ``system_override`` and
        ``template`` are consumed by ``_apply_blueprint_system``.
        """
        if model and model != "trigen-default":
            params = self.router.resolve(model)
            if api_key_override:
                params = dict(params)
                params["api_key"] = api_key_override
            self._merge_blueprint(params, model)
            return params
        # Fallback to default config
        params = {
            "model": model or self.config.model,
            "base_url": self.config.base_url,
            "api_key": api_key_override or self.config.api_key,
            "api_key_env": "TRIGEN_LLM_API_KEY",
            "openai_compatible": True,
            "provider": ProviderType.OPENAI,
            "modalities": [Modality.TEXT],
        }
        self._merge_blueprint(params, params["model"])
        return params

    def _merge_blueprint(self, params: Dict[str, Any], model_id: str) -> None:
        """Apply the effective blueprint for ``model_id`` onto ``params``.

        Resolution: ``LLMConfig`` defaults → ``ModelEntry.blueprint`` →
        runtime ``BlueprintStore``. Later sources win field-by-field.
        """
        from trigen.llm.blueprint import ModelBlueprint, store as _bp_store

        entry = self.router._models.get(model_id)
        bp = entry.blueprint if entry is not None and entry.blueprint is not None else ModelBlueprint()
        runtime_bp = _bp_store.get(model_id)
        if runtime_bp is not None:
            bp = runtime_bp.merge_over(bp)

        params["temperature"] = (
            bp.temperature if bp.temperature is not None else self.config.temperature
        )
        params["max_tokens"] = (
            bp.max_tokens if bp.max_tokens is not None else self.config.max_tokens
        )
        if bp.stop is not None:
            params["stop"] = bp.stop
        if bp.reasoning_effort is not None:
            params["reasoning_effort"] = bp.reasoning_effort
        # Stash template / system_override for _apply_blueprint_system.
        if bp.template is not None:
            params["_blueprint_template"] = bp.template
        if bp.system_override is not None:
            params["_blueprint_system_override"] = bp.system_override

    @staticmethod
    def _apply_blueprint_system(
        system: Optional[str], params: Dict[str, Any]
    ) -> Optional[str]:
        """Return the system prompt after applying blueprint overrides.

        ``system_override`` fully replaces the caller's system prompt;
        otherwise ``template`` is prepended to it. When neither is set the
        caller's system is returned unchanged.
        """
        override = params.get("_blueprint_system_override")
        if override is not None:
            return override
        template = params.get("_blueprint_template")
        if template:
            return f"{template}\n{system}" if system else template
        return system

    @staticmethod
    def _key_store():
        """Lazy accessor for the runtime key store (avoids import cycle)."""
        from trigen.llm.key_store import store as _store

        return _store

    def _rotate_key(self, params: Dict[str, Any], failed_key: str) -> str:
        """Return a different healthy key for the same provider, or "".

        Marks the failed key as failed and asks the key store for the next
        healthy key. Returns an empty string when no alternative key is
        available (caller should then advance to the next model in the
        fallback chain).
        """
        env_name = params.get("api_key_env", "") or ""
        if not env_name or not failed_key:
            return ""
        try:
            ks = self._key_store()
            next_key = ks.get_next_key(env_name)
            if next_key and next_key != failed_key:
                return next_key
        except Exception as exc:  # pragma: no cover — defensive
            logger.debug("Key rotation skipped: %s", exc)
        return ""

    def _mark_key_failed(self, params: Dict[str, Any], error_type: str, key: str = "") -> None:
        """Record a key failure in the rotation pool (best-effort)."""
        env_name = params.get("api_key_env", "") or ""
        failed_key = key or params.get("api_key", "") or ""
        if not env_name or not failed_key:
            return
        try:
            self._key_store().mark_failed(env_name, failed_key, error_type)
        except Exception:
            pass

    def _mark_key_success(self, params: Dict[str, Any], key: str = "") -> None:
        """Reset the key health slot after a successful call (best-effort)."""
        env_name = params.get("api_key_env", "") or ""
        ok_key = key or params.get("api_key", "") or ""
        if not env_name or not ok_key:
            return
        try:
            self._key_store().mark_success(env_name, ok_key)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Transport lookup
    # ------------------------------------------------------------------
    @staticmethod
    def _get_chat_transport(params: Dict[str, Any]):
        """Look up the chat transport for the resolved provider.

        Catalog ids prefixed with ``gemini-native/`` route to the native
        Gemini transport (REST + SSE format) regardless of provider, so
        Gemini 2.5 native models bypass the OpenAI-compatible shim.

        Falls back to the OpenAI transport when the provider has no
        dedicated transport registered (preserves the prior behaviour of
        routing unknown non-OpenAI providers through the OpenAI client).
        """
        from trigen.llm.transports import registry
        from trigen.llm.transports.gemini_transport import GeminiTransport

        model_id = params.get("model", "") or ""
        if model_id.startswith("gemini-native/"):
            native = getattr(GeminiTransport, "_native_instance", None)
            if native is None:
                native = GeminiTransport()
            return native

        provider = params.get("provider")
        transport = registry.get_chat(provider) if provider is not None else None
        if transport is None:
            transport = registry.get_chat(ProviderType.OPENAI)
        return transport

    @staticmethod
    def _provider_label(params: Dict[str, Any]) -> str:
        """Extract a comparable provider label from resolved params."""
        provider = params.get("provider", "")
        if hasattr(provider, "value"):
            return provider.value
        return str(provider)

    @staticmethod
    def _supports_vision(modalities: List[Modality]) -> bool:
        """Check if the model supports vision input."""
        return Modality.VISION in modalities

    def _is_offline(self, params: Dict[str, Any]) -> bool:
        """True when the resolved model is the offline default or has no key."""
        return params["model"] == "trigen-default" or not params["api_key"]

    # ------------------------------------------------------------------
    # Non-streaming completion
    # ------------------------------------------------------------------
    async def complete(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        system: Optional[str] = None,
        model: Optional[str] = None,
    ) -> LLMResponse:
        """Non-streaming completion, returning the full response.

        Builds a fallback chain from the router and tries each model in
        turn. Auth failures skip the rest of the failing provider; other
        retriable errors (5xx, timeout, rate-limit) advance to the next
        model in the chain. When a key rotation pool exists for the
        failing provider, the same model is retried with a different key
        before falling back to the next model.
        """
        chain = self.router.build_fallback_chain(primary=model)
        failed_providers: set[str] = set()
        last_error = ""
        attempts = 0

        for current_model in chain:
            if attempts >= self.MAX_FALLBACK_ATTEMPTS:
                break
            params = self._resolve_params(current_model)
            provider_label = self._provider_label(params)
            if provider_label in failed_providers:
                continue
            attempts += 1
            try:
                response = await self._complete_single(messages, tools, system, current_model)
                self._mark_key_success(params)
                return response
            except _RetriableError as exc:
                last_error = str(exc)
                self._mark_key_failed(params, exc.error_type)
                # Try rotating the API key before giving up on this model
                if exc.error_type in ("auth", "rate_limit"):
                    next_key = self._rotate_key(params, params.get("api_key", ""))
                    if next_key and attempts < self.MAX_FALLBACK_ATTEMPTS:
                        attempts += 1
                        try:
                            response = await self._complete_single(
                                messages, tools, system, current_model, api_key_override=next_key,
                            )
                            self._mark_key_success(params, key=next_key)
                            return response
                        except _RetriableError as exc2:
                            last_error = str(exc2)
                            self._mark_key_failed(params, exc2.error_type, key=next_key)
                if exc.error_type == "auth":
                    failed_providers.add(provider_label)
                logger.warning(
                    "complete() model %s failed (attempt %d): %s",
                    current_model,
                    attempts,
                    exc,
                )
                continue

        return LLMResponse(
            content=f"[LLM call failed after {attempts} attempt(s)] {last_error}",
            finish_reason="error",
        )

    async def _complete_single(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]],
        system: Optional[str],
        model: str,
        api_key_override: str = "",
    ) -> LLMResponse:
        """Run a non-streaming completion against one model.

        Raises ``_RetriableError`` on any setup/connection failure so the
        fallback loop in complete() can advance to the next model.
        """
        params = self._resolve_params(model, api_key_override=api_key_override)

        if self._is_offline(params):
            return LLMResponse(
                content="(Offline mode) LLM not configured. Using rule-based engine.",
                finish_reason="stop",
            )

        transport = self._get_chat_transport(params)
        return await transport.complete(
            params,
            messages,
            tools,
            self._apply_blueprint_system(system, params),
            params["temperature"],
            params["max_tokens"],
        )

    # ------------------------------------------------------------------
    # Streaming completion
    # ------------------------------------------------------------------
    async def stream(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        system: Optional[str] = None,
        model: Optional[str] = None,
    ) -> AsyncIterator[LLMStreamChunk]:
        """Streaming completion, yielding token by token.

        Builds a fallback chain from the router. The primary model is
        tried first; if it fails before producing any output (auth, 5xx,
        timeout, rate-limit), the next model in the chain is tried. Once a
        model starts streaming, the attempt is committed and mid-stream
        failures surface as error chunks without further retry. When a
        key rotation pool exists for the failing provider, the same model
        is retried with a different key before falling back.
        """
        chain = self.router.build_fallback_chain(primary=model)
        failed_providers: set[str] = set()
        last_error = ""
        attempts = 0

        for current_model in chain:
            if attempts >= self.MAX_FALLBACK_ATTEMPTS:
                break
            params = self._resolve_params(current_model)
            provider_label = self._provider_label(params)
            if provider_label in failed_providers:
                continue
            attempts += 1
            try:
                async for chunk in self._stream_single(messages, tools, system, current_model):
                    yield chunk
                self._mark_key_success(params)
                return  # Success — whole stream consumed
            except _RetriableError as exc:
                last_error = str(exc)
                self._mark_key_failed(params, exc.error_type)
                # Try rotating the API key before giving up on this model
                if exc.error_type in ("auth", "rate_limit"):
                    next_key = self._rotate_key(params, params.get("api_key", ""))
                    if next_key and attempts < self.MAX_FALLBACK_ATTEMPTS:
                        attempts += 1
                        try:
                            async for chunk in self._stream_single(
                                messages, tools, system, current_model, api_key_override=next_key,
                            ):
                                yield chunk
                            self._mark_key_success(params, key=next_key)
                            return
                        except _RetriableError as exc2:
                            last_error = str(exc2)
                            self._mark_key_failed(params, exc2.error_type, key=next_key)
                if exc.error_type == "auth":
                    failed_providers.add(provider_label)
                logger.warning(
                    "stream() model %s failed (attempt %d): %s",
                    current_model,
                    attempts,
                    exc,
                )
                continue

        yield LLMStreamChunk(
            content=f"[LLM call failed after {attempts} attempt(s)] {last_error}",
            finish_reason="error",
        )

    async def _stream_single(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]],
        system: Optional[str],
        model: str,
        api_key_override: str = "",
    ) -> AsyncIterator[LLMStreamChunk]:
        """Stream from a single model.

        Raises ``_RetriableError`` on setup/connection failure (before any
        chunk is yielded). Mid-stream failures are converted to error
        chunks by the transport so the caller never sees a raw exception
        after partial output.
        """
        params = self._resolve_params(model, api_key_override=api_key_override)

        if self._is_offline(params):
            yield LLMStreamChunk(
                content="(Offline mode) LLM not configured. Using rule-based engine.",
                finish_reason="stop",
            )
            return

        transport = self._get_chat_transport(params)
        async for chunk in transport.stream(
            params,
            messages,
            tools,
            self._apply_blueprint_system(system, params),
            params["temperature"],
            params["max_tokens"],
        ):
            yield chunk

    # ------------------------------------------------------------------
    # Vision streaming
    # ------------------------------------------------------------------
    async def stream_vision(
        self,
        text: str,
        image_base64: str,
        image_mime: str = "image/png",
        system: Optional[str] = None,
        model: Optional[str] = None,
    ) -> AsyncIterator[LLMStreamChunk]:
        """Stream a vision-language request with an image attachment.

        Routes to the provider's native vision format via the transport
        registry. Falls back across the chain on retriable setup failures,
        same as stream().
        """
        chain = self.router.build_fallback_chain(primary=model)
        failed_providers: set[str] = set()
        last_error = ""
        attempts = 0

        for current_model in chain:
            if attempts >= self.MAX_FALLBACK_ATTEMPTS:
                break
            params = self._resolve_params(current_model)
            provider_label = self._provider_label(params)
            if provider_label in failed_providers:
                continue
            attempts += 1
            try:
                async for chunk in self._stream_vision_single(
                    text, image_base64, image_mime, system, current_model
                ):
                    yield chunk
                self._mark_key_success(params)
                return
            except _RetriableError as exc:
                last_error = str(exc)
                self._mark_key_failed(params, exc.error_type)
                if exc.error_type in ("auth", "rate_limit"):
                    next_key = self._rotate_key(params, params.get("api_key", ""))
                    if next_key and attempts < self.MAX_FALLBACK_ATTEMPTS:
                        attempts += 1
                        try:
                            async for chunk in self._stream_vision_single(
                                text, image_base64, image_mime, system, current_model,
                                api_key_override=next_key,
                            ):
                                yield chunk
                            self._mark_key_success(params, key=next_key)
                            return
                        except _RetriableError as exc2:
                            last_error = str(exc2)
                            self._mark_key_failed(params, exc2.error_type, key=next_key)
                if exc.error_type == "auth":
                    failed_providers.add(provider_label)
                logger.warning(
                    "stream_vision() model %s failed (attempt %d): %s",
                    current_model,
                    attempts,
                    exc,
                )
                continue

        yield LLMStreamChunk(
            content=f"[Vision call failed after {attempts} attempt(s)] {last_error}",
            finish_reason="error",
        )

    async def _stream_vision_single(
        self,
        text: str,
        image_base64: str,
        image_mime: str,
        system: Optional[str],
        model: str,
        api_key_override: str = "",
    ) -> AsyncIterator[LLMStreamChunk]:
        """Stream a vision request against one model.

        Raises ``_RetriableError`` on setup failure; mid-stream failures
        surface as error chunks (handled inside the transport).
        """
        params = self._resolve_params(model, api_key_override=api_key_override)

        if self._is_offline(params):
            yield LLMStreamChunk(
                content="(Offline mode) Vision LLM not configured.",
                finish_reason="stop",
            )
            return

        transport = self._get_chat_transport(params)
        async for chunk in transport.stream_vision(
            params,
            text,
            image_base64,
            image_mime,
            self._apply_blueprint_system(system, params),
            params["temperature"],
            params["max_tokens"],
        ):
            yield chunk
