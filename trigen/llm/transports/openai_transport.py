"""OpenAI-protocol transport.

A single transport covers every provider that speaks the OpenAI chat
completions protocol (OpenAI, DeepSeek, Qwen, Groq, Together, Fireworks,
Ollama, Mistral, Cohere, Perplexity, AI21, xAI, Moonshot, Baichuan,
MiniMax, Spark, Zhipu, Google, OpenRouter, Replicate, HuggingFace).

It also implements the generation modalities that ride on OpenAI-family
endpoints:
  - Image generation: OpenAI Images API (DALL·E) for the OPENAI provider,
    httpx POST to ``/images/generations`` for Together / Fireworks.
  - Animation: Together / Fireworks image-style endpoint.
  - Speech synthesis + transcription: OpenAI TTS / Whisper.

Internal per-provider branching is encapsulated here so the dispatch
surface (``LLMClient`` / ``MultimodalDispatcher``) never inspects
``ProviderType`` directly.
"""

from __future__ import annotations

import base64
import io
import json
import logging
from typing import Any, AsyncIterator, Dict, List, Optional

from trigen.llm.router import ProviderType
from trigen.llm.transports.base import (
    AnimationTransport,
    ChatTransport,
    ImageTransport,
    VoiceTransport,
)
from trigen.llm.types import (
    GenerationResult,
    LLMResponse,
    LLMStreamChunk,
    RetriableError,
    ToolCall,
    classify_error,
)

logger = logging.getLogger("trigen.llm.transports.openai")


# Providers that share the OpenAI chat-completions wire protocol.
OPENAI_COMPAT_CHAT_PROVIDERS = [
    ProviderType.OPENAI,
    ProviderType.DEEPSEEK,
    ProviderType.QWEN,
    ProviderType.GROQ,
    ProviderType.TOGETHER,
    ProviderType.FIREWORKS,
    ProviderType.OLLAMA,
    ProviderType.MISTRAL,
    ProviderType.COHERE,
    ProviderType.PERPLEXITY,
    ProviderType.AI21,
    ProviderType.XAI,
    ProviderType.MOONSHOT,
    ProviderType.BAICHUAN,
    ProviderType.MINIMAX,
    ProviderType.SPARK,
    ProviderType.ZHIPU,
    ProviderType.GOOGLE,
    ProviderType.OPENROUTER,
    ProviderType.REPLICATE,
    ProviderType.HUGGINGFACE,
]


def _build_tools_schema(tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Convert internal tool descriptions into OpenAI function-calling schema."""
    return [{"type": "function", "function": t} for t in tools]


class OpenAITransport(ChatTransport, ImageTransport, AnimationTransport, VoiceTransport):
    """Transport for the OpenAI chat completions protocol family.

    Caches ``AsyncOpenAI`` clients by ``(base_url, api_key)`` so repeated
    calls to the same endpoint reuse the underlying HTTP pool.
    """

    def __init__(self) -> None:
        self._clients: Dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Client cache
    # ------------------------------------------------------------------
    def _get_client(self, base_url: str, api_key: str, timeout: float):
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
                timeout=timeout,
            )
        return self._clients[cache_key]

    @staticmethod
    def _apply_extra_kwargs(kwargs: Dict[str, Any], params: Dict[str, Any]) -> None:
        """Forward optional blueprint fields (stop, reasoning_effort) onto
        the request kwargs when the model's blueprint provides them."""
        stop = params.get("stop")
        if stop:
            kwargs["stop"] = stop
        reasoning_effort = params.get("reasoning_effort")
        if reasoning_effort:
            kwargs["reasoning_effort"] = reasoning_effort

    # ------------------------------------------------------------------
    # Chat
    # ------------------------------------------------------------------
    def stream(
        self,
        params: Dict[str, Any],
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]],
        system: Optional[str],
        temperature: float,
        max_tokens: int,
    ) -> AsyncIterator[LLMStreamChunk]:
        """Stream a chat completion from an OpenAI-compatible endpoint.

        Raises ``RetriableError`` on setup/connection failure (before any
        chunk is yielded). Mid-stream failures surface as error chunks so
        the caller never sees a raw exception after partial output.
        """
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
        client = self._get_client(params["base_url"], params["api_key"], 60.0)

        full_messages: List[Dict[str, Any]] = []
        if system:
            full_messages.append({"role": "system", "content": system})
        full_messages.extend(messages)

        kwargs: Dict[str, Any] = {
            "model": params["model"],
            "messages": full_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        if tools:
            kwargs["tools"] = _build_tools_schema(tools)
            kwargs["tool_choice"] = "auto"
        self._apply_extra_kwargs(kwargs, params)

        try:
            stream = await client.chat.completions.create(**kwargs)
        except Exception as exc:
            raise RetriableError(str(exc), classify_error(exc)) from exc

        tool_call_accum: Dict[int, Dict[str, Any]] = {}
        try:
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
        except Exception as exc:
            # Mid-stream failure — caller already received partial output,
            # so surface as an error chunk rather than raising.
            logger.error("LLM stream interrupted: %s", exc)
            yield LLMStreamChunk(content=f"[Stream interrupted] {exc}", finish_reason="error")

    async def complete(
        self,
        params: Dict[str, Any],
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]],
        system: Optional[str],
        temperature: float,
        max_tokens: int,
    ) -> LLMResponse:
        """Non-streaming chat completion from an OpenAI-compatible endpoint."""
        client = self._get_client(params["base_url"], params["api_key"], 60.0)

        full_messages: List[Dict[str, Any]] = []
        if system:
            full_messages.append({"role": "system", "content": system})
        full_messages.extend(messages)

        kwargs: Dict[str, Any] = {
            "model": params["model"],
            "messages": full_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            kwargs["tools"] = _build_tools_schema(tools)
            kwargs["tool_choice"] = "auto"
        self._apply_extra_kwargs(kwargs, params)

        try:
            resp = await client.chat.completions.create(**kwargs)
        except Exception as exc:
            raise RetriableError(str(exc), classify_error(exc)) from exc

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
        """Stream a vision request using the OpenAI ``image_url`` data-URL format."""
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
        client = self._get_client(params["base_url"], params["api_key"], 60.0)

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
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        self._apply_extra_kwargs(kwargs, params)

        try:
            stream = await client.chat.completions.create(**kwargs)
        except Exception as exc:
            raise RetriableError(str(exc), classify_error(exc)) from exc

        try:
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
        except Exception as exc:
            logger.error("Vision stream interrupted: %s", exc)
            yield LLMStreamChunk(content=f"[Stream interrupted] {exc}", finish_reason="error")

    # ------------------------------------------------------------------
    # Image generation
    # ------------------------------------------------------------------
    async def generate_image(
        self, params: Dict[str, Any], prompt: str, size: str, n: int
    ) -> GenerationResult:
        """Generate an image.

        Routes to the OpenAI Images API for DALL·E models (provider
        OPENAI) or to the ``/images/generations`` httpx endpoint for
        Together / Fireworks open-source image models.
        """
        provider = params["provider"]
        if provider == ProviderType.OPENAI:
            return await self._openai_image(params, prompt, size, n)
        if provider in (ProviderType.TOGETHER, ProviderType.FIREWORKS):
            return await self._compat_image(params, prompt, size, n)
        return GenerationResult(
            success=False,
            modality="image_gen",
            model=params.get("model", ""),
            error=f"Image generation not implemented for provider {getattr(provider, 'value', provider)}",
        )

    async def _openai_image(
        self, params: Dict[str, Any], prompt: str, size: str, n: int
    ) -> GenerationResult:
        """Call the OpenAI Images API (DALL·E)."""
        from openai import AsyncOpenAI

        client = AsyncOpenAI(
            api_key=params["api_key"], base_url=params["base_url"], timeout=120.0
        )
        resp = await client.images.generate(
            model=params["model"], prompt=prompt, size=size, n=n, response_format="b64_json"
        )
        if not resp.data:
            return GenerationResult(
                success=False, modality="image_gen", model=params["model"],
                error="No image returned",
            )
        first = resp.data[0]
        return GenerationResult(
            success=True,
            modality="image_gen",
            model=params["model"],
            base64_data=first.b64_json or "",
            mime_type="image/png",
            raw={"revised_prompt": getattr(first, "revised_prompt", "")},
        )

    async def _compat_image(
        self, params: Dict[str, Any], prompt: str, size: str, n: int
    ) -> GenerationResult:
        """Call a Together / Fireworks image generation endpoint via httpx."""
        import httpx

        url = f"{params['base_url']}/images/generations"
        headers = {"Authorization": f"Bearer {params['api_key']}"}
        body = {"model": params["model"], "prompt": prompt, "size": size, "n": n}
        async with httpx.AsyncClient(timeout=120.0) as http:
            r = await http.post(url, json=body, headers=headers)
            if r.status_code >= 400:
                return GenerationResult(
                    success=False, modality="image_gen", model=params["model"],
                    error=f"HTTP {r.status_code}: {r.text[:200]}",
                )
            data = r.json()
        items = data.get("data", [])
        if not items:
            return GenerationResult(
                success=False, modality="image_gen", model=params["model"],
                error="No image returned",
            )
        first = items[0]
        if "b64_json" in first:
            return GenerationResult(
                success=True, modality="image_gen", model=params["model"],
                base64_data=first["b64_json"], mime_type="image/png", raw=data,
            )
        if "url" in first:
            return GenerationResult(
                success=True, modality="image_gen", model=params["model"],
                url=first["url"], mime_type="image/png", raw=data,
            )
        return GenerationResult(
            success=False, modality="image_gen", model=params["model"],
            error="Unknown response shape",
        )

    # ------------------------------------------------------------------
    # Animation (Together / Fireworks image-style endpoint)
    # ------------------------------------------------------------------
    async def generate_animation(
        self, params: Dict[str, Any], prompt: str, frames: int
    ) -> GenerationResult:
        """Generate an animation sequence via the Together / Fireworks image endpoint."""
        provider = params["provider"]
        if provider in (ProviderType.TOGETHER, ProviderType.FIREWORKS):
            return await self._compat_image(params, prompt, "1024x1024", 1)
        return GenerationResult(
            success=False,
            modality="animation",
            model=params.get("model", ""),
            error=f"Animation generation not implemented for provider {getattr(provider, 'value', provider)}",
        )

    # ------------------------------------------------------------------
    # Voice (OpenAI TTS + Whisper)
    # ------------------------------------------------------------------
    async def synthesize_speech(
        self, params: Dict[str, Any], text: str, voice: str
    ) -> GenerationResult:
        """Synthesize speech from text via OpenAI TTS."""
        from openai import AsyncOpenAI

        client = AsyncOpenAI(
            api_key=params["api_key"], base_url=params["base_url"], timeout=60.0
        )
        resp = await client.audio.speech.create(
            model=params["model"], voice=voice, input=text
        )
        audio_bytes = resp.read()
        b64 = base64.b64encode(audio_bytes).decode("ascii")
        return GenerationResult(
            success=True, modality="voice", model=params["model"],
            base64_data=b64, mime_type="audio/mpeg",
        )

    async def transcribe_audio(
        self, params: Dict[str, Any], audio_base64: str, mime_type: str
    ) -> GenerationResult:
        """Transcribe audio to text via OpenAI Whisper."""
        from openai import AsyncOpenAI

        client = AsyncOpenAI(
            api_key=params["api_key"], base_url=params["base_url"], timeout=60.0
        )
        audio_bytes = base64.b64decode(audio_base64)
        buf = io.BytesIO(audio_bytes)
        buf.name = f"audio.{mime_type.split('/')[-1]}"
        resp = await client.audio.transcriptions.create(model=params["model"], file=buf)
        return GenerationResult(
            success=True, modality="audio", model=params["model"],
            raw={"text": resp.text},
        )
