"""Trigen LLM Client.

Unified wrapper that dispatches to diverse LLM providers via the ModelRouter.
Supports OpenAI-protocol compatible services (OpenAI, DeepSeek, Qwen, Groq,
Together, Fireworks, Ollama), Anthropic native protocol via the
AnthropicAdapter, and OpenRouter. Handles streaming output and native
function calling across all supported protocols.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, List, Optional

from trigen.config import LLMConfig
from trigen.llm.router import ModelRouter, Modality, ProviderType, router as default_router

logger = logging.getLogger("trigen.llm")


@dataclass
class ToolCall:
    """A tool call initiated by the LLM."""

    id: str
    name: str
    arguments: Dict[str, Any]


@dataclass
class LLMResponse:
    """A complete LLM response."""

    content: str
    tool_calls: List[ToolCall] = field(default_factory=list)
    finish_reason: str = "stop"
    usage: Dict[str, int] = field(default_factory=dict)


@dataclass
class LLMStreamChunk:
    """A streaming response chunk."""

    content: str = ""
    tool_calls: List[ToolCall] = field(default_factory=list)
    finish_reason: Optional[str] = None


class LLMClient:
    """Asynchronous LLM client with multi-provider routing.

    When a model id is passed to stream()/complete(), the router resolves
    the correct provider, base_url, and api_key. If the model is unknown,
    it falls back to the default LLMConfig values. Providers that do not
    follow the OpenAI protocol (e.g. Anthropic) are dispatched to a
    dedicated adapter that translates the request and stream.
    """

    def __init__(self, config: LLMConfig, model_router: Optional[ModelRouter] = None):
        self.config = config
        self.router = model_router or default_router
        self._clients: Dict[str, Any] = {}  # Cache OpenAI-protocol clients by base_url
        self._adapters: Dict[str, Any] = {}  # Cache non-OpenAI adapters by base_url

    def _get_client(self, base_url: str, api_key: str):
        """Get or create a cached AsyncOpenAI client for the given base_url."""
        cache_key = f"{base_url}|{api_key[:8]}" if api_key else base_url
        if cache_key not in self._clients:
            try:
                from openai import AsyncOpenAI
            except ImportError as exc:
                raise RuntimeError(
                    "openai package not installed. Run pip install -e . in the agent directory."
                ) from exc
            self._clients[cache_key] = AsyncOpenAI(
                api_key=api_key or "missing",
                base_url=base_url,
                timeout=self.config.timeout,
            )
        return self._clients[cache_key]

    def _get_anthropic_adapter(self, base_url: str, api_key: str):
        """Get or create a cached AnthropicAdapter for the given base_url."""
        cache_key = f"anthropic|{base_url}|{api_key[:8]}"
        if cache_key not in self._adapters:
            from trigen.llm.anthropic_adapter import AnthropicAdapter

            self._adapters[cache_key] = AnthropicAdapter(
                api_key=api_key,
                base_url=base_url,
                timeout=self.config.timeout,
            )
        return self._adapters[cache_key]

    def _resolve_params(self, model: Optional[str]) -> Dict[str, Any]:
        """Resolve connection parameters for a model id."""
        if model and model != "trigen-default":
            params = self.router.resolve(model)
            return params
        # Fallback to default config
        return {
            "model": model or self.config.model,
            "base_url": self.config.base_url,
            "api_key": self.config.api_key,
            "openai_compatible": True,
            "provider": ProviderType.OPENAI,
            "modalities": [Modality.TEXT],
        }

    def _build_tools_schema(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Convert internal tool descriptions into OpenAI function calling schema."""
        return [{"type": "function", "function": t} for t in tools]

    def _supports_vision(self, modalities: List[Modality]) -> bool:
        """Check if the model supports vision input."""
        return Modality.VISION in modalities

    async def complete(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        system: Optional[str] = None,
        model: Optional[str] = None,
    ) -> LLMResponse:
        """Synchronous (non-streaming) completion, returning the full response."""
        params = self._resolve_params(model)
        client = self._get_client(params["base_url"], params["api_key"])

        full_messages: List[Dict[str, Any]] = []
        if system:
            full_messages.append({"role": "system", "content": system})
        full_messages.extend(messages)

        kwargs: Dict[str, Any] = {
            "model": params["model"],
            "messages": full_messages,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
        }
        if tools:
            kwargs["tools"] = self._build_tools_schema(tools)
            kwargs["tool_choice"] = "auto"

        try:
            resp = await client.chat.completions.create(**kwargs)
        except Exception as exc:
            logger.error("LLM call failed: %s", exc)
            return LLMResponse(content=f"[LLM call failed] {exc}", finish_reason="error")

        choice = resp.choices[0]
        msg = choice.message
        tool_calls: List[ToolCall] = []
        if msg.tool_calls:
            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments) if tc.function.arguments else {}
                except json.JSONDecodeError:
                    args = {"_raw": tc.function.arguments}
                tool_calls.append(ToolCall(id=tc.id, name=tc.function.name, arguments=args))
        usage = {}
        if resp.usage:
            usage = {
                "prompt_tokens": resp.usage.prompt_tokens,
                "completion_tokens": resp.usage.completion_tokens,
                "total_tokens": resp.usage.total_tokens,
            }
        return LLMResponse(
            content=msg.content or "",
            tool_calls=tool_calls,
            finish_reason=choice.finish_reason or "stop",
            usage=usage,
        )

    async def stream(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        system: Optional[str] = None,
        model: Optional[str] = None,
    ) -> AsyncIterator[LLMStreamChunk]:
        """Streaming completion, yielding token by token. Routes to the
        correct provider based on the model id. Providers that do not
        implement the OpenAI protocol are dispatched to their native adapter.
        """
        params = self._resolve_params(model)

        # Offline mode — should not reach here, but guard anyway
        if params["model"] == "trigen-default" or not params["api_key"]:
            yield LLMStreamChunk(
                content="(Offline mode) LLM not configured. Using rule-based engine.",
                finish_reason="stop",
            )
            return

        # Dispatch to Anthropic native protocol when not OpenAI-compatible
        if not params.get("openai_compatible", True):
            if params["provider"] == ProviderType.ANTHROPIC:
                adapter = self._get_anthropic_adapter(params["base_url"], params["api_key"])
                async for chunk in adapter.stream(
                    messages=messages,
                    tools=tools,
                    system=system,
                    model=params["model"],
                    temperature=self.config.temperature,
                    max_tokens=self.config.max_tokens,
                ):
                    yield chunk
                return
            logger.warning(
                "Model %s is marked non-OpenAI but no adapter is available; falling back to OpenAI client",
                params["model"],
            )

        client = self._get_client(params["base_url"], params["api_key"])

        full_messages: List[Dict[str, Any]] = []
        if system:
            full_messages.append({"role": "system", "content": system})
        full_messages.extend(messages)

        kwargs: Dict[str, Any] = {
            "model": params["model"],
            "messages": full_messages,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
            "stream": True,
        }
        if tools:
            kwargs["tools"] = self._build_tools_schema(tools)
            kwargs["tool_choice"] = "auto"

        try:
            stream = await client.chat.completions.create(**kwargs)
        except Exception as exc:
            logger.error("LLM streaming call failed: %s", exc)
            yield LLMStreamChunk(content=f"[LLM call failed] {exc}", finish_reason="error")
            return

        tool_call_accum: Dict[int, Dict[str, Any]] = {}
        async for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            finish = chunk.choices[0].finish_reason

            content = delta.content or ""
            if delta.tool_calls:
                for tc in delta.tool_calls:
                    idx = tc.index
                    if idx not in tool_call_accum:
                        tool_call_accum[idx] = {
                            "id": tc.id or "",
                            "name": tc.function.name if tc.function else "",
                            "args": "",
                        }
                    if tc.id:
                        tool_call_accum[idx]["id"] = tc.id
                    if tc.function and tc.function.name:
                        tool_call_accum[idx]["name"] = tc.function.name
                    if tc.function and tc.function.arguments:
                        tool_call_accum[idx]["args"] += tc.function.arguments

            if content:
                yield LLMStreamChunk(content=content)

            if finish:
                final_tool_calls: List[ToolCall] = []
                for idx in sorted(tool_call_accum.keys()):
                    acc = tool_call_accum[idx]
                    try:
                        args = json.loads(acc["args"]) if acc["args"] else {}
                    except json.JSONDecodeError:
                        args = {"_raw": acc["args"]}
                    if acc["name"]:
                        final_tool_calls.append(
                            ToolCall(id=acc["id"], name=acc["name"], arguments=args)
                        )
                yield LLMStreamChunk(tool_calls=final_tool_calls, finish_reason=finish)

    async def stream_vision(
        self,
        text: str,
        image_base64: str,
        image_mime: str = "image/png",
        system: Optional[str] = None,
        model: Optional[str] = None,
    ) -> AsyncIterator[LLMStreamChunk]:
        """Stream a vision-language request with an image attachment.

        The image is encoded as a data URL in the user message content array,
        following the OpenAI vision protocol. Only models with VISION modality
        should be used.
        """
        params = self._resolve_params(model)
        client = self._get_client(params["base_url"], params["api_key"])

        messages: List[Dict[str, Any]] = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": text},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{image_mime};base64,{image_base64}",
                        },
                    },
                ],
            }
        ]

        full_messages: List[Dict[str, Any]] = []
        if system:
            full_messages.append({"role": "system", "content": system})
        full_messages.extend(messages)

        kwargs: Dict[str, Any] = {
            "model": params["model"],
            "messages": full_messages,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
            "stream": True,
        }

        try:
            stream = await client.chat.completions.create(**kwargs)
        except Exception as exc:
            logger.error("Vision LLM call failed: %s", exc)
            yield LLMStreamChunk(content=f"[Vision call failed] {exc}", finish_reason="error")
            return

        async for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            finish = chunk.choices[0].finish_reason
            content = delta.content or ""
            if content:
                yield LLMStreamChunk(content=content)
            if finish:
                yield LLMStreamChunk(finish_reason=finish)
