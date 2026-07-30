"""Anthropic Messages API transport.

Wraps the existing ``AnthropicAdapter`` (which speaks Anthropic's native
SSE protocol via httpx) behind the ``ChatTransport`` interface so the
``LLMClient`` can dispatch Claude-family models through the transport
registry without provider-specific branching.

The adapter streams ``LLMStreamChunk`` instances directly; this transport
adds the "peek first chunk" protocol the fallback loop expects: if the
adapter fails before producing any output, a ``RetriableError`` is raised
so the caller can advance to the next model in the chain. Once a real
chunk arrives, the attempt is committed and mid-stream failures surface
as error chunks.
"""

from __future__ import annotations

import logging
from typing import Any, AsyncIterator, Dict, List, Optional

from trigen.llm.transports.base import ChatTransport
from trigen.llm.types import (
    LLMResponse,
    LLMStreamChunk,
    RetriableError,
    classify_error,
)

logger = logging.getLogger("trigen.llm.transports.anthropic")


class AnthropicTransport(ChatTransport):
    """Chat + vision transport for the Anthropic Messages API."""

    def __init__(self) -> None:
        self._adapters: Dict[str, Any] = {}

    def _get_adapter(self, base_url: str, api_key: str, timeout: float):
        cache_key = f"anthropic|{base_url}|{api_key[:8]}"
        if cache_key not in self._adapters:
            from trigen.llm.anthropic_adapter import AnthropicAdapter

            self._adapters[cache_key] = AnthropicAdapter(
                api_key=api_key,
                base_url=base_url,
                timeout=timeout,
            )
        return self._adapters[cache_key]

    def stream(
        self,
        params: Dict[str, Any],
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]],
        system: Optional[str],
        temperature: float,
        max_tokens: int,
    ) -> AsyncIterator[LLMStreamChunk]:
        return self._stream(params, messages, tools, system, temperature, max_tokens)

    async def _stream(
        self,
        params: Dict[str, Any],
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]],
        system: Optional[str],
        temperature: float,
        max_tokens: int,
    ) -> AsyncIterator[LLMStreamChunk]:
        adapter = self._get_adapter(
            params["base_url"], params["api_key"], 60.0
        )
        iterator = adapter.stream(
            messages=messages,
            tools=tools,
            system=system,
            model=params["model"],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        # Peek the first chunk: if it is an error, raise so the fallback
        # loop can advance to the next model. Once a real chunk arrives,
        # the attempt is committed.
        try:
            first_chunk = await iterator.__anext__()
        except StopAsyncIteration:
            return
        except Exception as exc:
            raise RetriableError(str(exc), classify_error(exc)) from exc
        if first_chunk.finish_reason == "error":
            raise RetriableError(
                first_chunk.content, classify_error(RuntimeError(first_chunk.content))
            )
        yield first_chunk
        async for chunk in iterator:
            yield chunk

    async def complete(
        self,
        params: Dict[str, Any],
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]],
        system: Optional[str],
        temperature: float,
        max_tokens: int,
    ) -> LLMResponse:
        adapter = self._get_adapter(params["base_url"], params["api_key"], 60.0)
        try:
            response = await adapter.complete(
                messages=messages,
                tools=tools,
                system=system,
                model=params["model"],
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except Exception as exc:
            raise RetriableError(str(exc), classify_error(exc)) from exc
        if response.finish_reason == "error":
            raise RetriableError(
                response.content, classify_error(RuntimeError(response.content))
            )
        return response

    def stream_vision(
        self,
        params: Dict[str, Any],
        text: str,
        image_base64: str,
        image_mime: str,
        system: Optional[str],
        temperature: float,
        max_tokens: int,
    ) -> AsyncIterator[LLMStreamChunk]:
        return self._stream_vision(
            params, text, image_base64, image_mime, system, temperature, max_tokens
        )

    async def _stream_vision(
        self,
        params: Dict[str, Any],
        text: str,
        image_base64: str,
        image_mime: str,
        system: Optional[str],
        temperature: float,
        max_tokens: int,
    ) -> AsyncIterator[LLMStreamChunk]:
        adapter = self._get_adapter(params["base_url"], params["api_key"], 60.0)
        iterator = adapter.stream_vision(
            text=text,
            image_base64=image_base64,
            image_mime=image_mime,
            system=system,
            model=params["model"],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        try:
            first_chunk = await iterator.__anext__()
        except StopAsyncIteration:
            return
        except Exception as exc:
            raise RetriableError(str(exc), classify_error(exc)) from exc
        if first_chunk.finish_reason == "error":
            raise RetriableError(
                first_chunk.content, classify_error(RuntimeError(first_chunk.content))
            )
        yield first_chunk
        async for chunk in iterator:
            yield chunk
