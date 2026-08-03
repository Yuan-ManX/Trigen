"""Google Gemini native API transport.

Implements the ChatTransport surface against Google's
``generativelanguage.googleapis.com/v1beta`` native API format rather
than the OpenAI-compatible shim. This transport handles catalog model
ids prefixed with ``gemini-native/`` (e.g. ``gemini-native/gemini-2.5-pro``);
the OpenAI-compatible Gemini models (``gemini-2.0-flash`` etc.) continue
to dispatch through the OpenAI transport.

The native API converts the chat messages list into Gemini's
``contents`` array, supports inline image data via ``inline_data`` parts,
and forwards function-calling tools as ``functionDeclarations``.
"""

from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator, Dict, List, Optional

from trigen.llm.transports.base import ChatTransport
from trigen.llm.types import (
    LLMResponse,
    LLMStreamChunk,
    RetriableError,
    ToolCall,
    classify_error,
)

logger = logging.getLogger("trigen.llm.transports.gemini")


# Roles that Gemini accepts. Gemini does not have a separate "system"
# role — system instructions go through the ``systemInstruction`` top-level
# field, and assistant turns are labelled ``model``.
def _role_for(role: str) -> str:
    if role == "assistant":
        return "model"
    if role == "tool":
        return "user"
    return role or "user"


def _message_to_parts(msg: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Convert a single chat message into Gemini ``parts``."""
    content = msg.get("content")
    role = msg.get("role", "user")

    # String content — single text part.
    if isinstance(content, str):
        return [{"text": content}]

    # Multimodal content (list of typed parts).
    parts: List[Dict[str, Any]] = []
    if isinstance(content, list):
        for part in content:
            if not isinstance(part, dict):
                continue
            ptype = part.get("type")
            if ptype == "text":
                parts.append({"text": part.get("text", "")})
            elif ptype == "image_url":
                # OpenAI form: {"image_url": {"url": "data:mime;base64,..."}}
                url = (part.get("image_url") or {}).get("url", "")
                if url.startswith("data:"):
                    header, _, b64 = url.partition(",")
                    mime = "image/png"
                    if ":" in header and ";" in header:
                        mime = header.split(":", 1)[1].split(";", 1)[0]
                    parts.append({"inline_data": {"mime_type": mime, "data": b64}})
            elif ptype == "input_text":
                parts.append({"text": part.get("text", "")})
            elif ptype == "input_image":
                url = part.get("image_url", "")
                if url.startswith("data:"):
                    header, _, b64 = url.partition(",")
                    mime = "image/png"
                    if ":" in header and ";" in header:
                        mime = header.split(":", 1)[1].split(";", 1)[0]
                    parts.append({"inline_data": {"mime_type": mime, "data": b64}})
    # Tool call / tool result passthrough.
    if role == "assistant" and msg.get("tool_calls"):
        for tc in msg["tool_calls"]:
            fn = (tc or {}).get("function", {}) or {}
            args = fn.get("arguments")
            if isinstance(args, str):
                try:
                    args = json.loads(args) if args else {}
                except json.JSONDecodeError:
                    args = {"_raw": args}
            parts.append(
                {
                    "functionCall": {
                        "name": fn.get("name", ""),
                        "args": args or {},
                    }
                }
            )
    if role == "tool":
        # Tool result -> Gemini expects functionResponse.
        tool_call_id = msg.get("tool_call_id", "")
        content_str = content if isinstance(content, str) else json.dumps(content)
        parts.append(
            {
                "functionResponse": {
                    "name": tool_call_id or "tool",
                    "response": {"result": content_str},
                }
            }
        )
    return parts or [{"text": ""}]


def _build_tools(tools: Optional[List[Dict[str, Any]]]) -> Optional[Dict[str, Any]]:
    """Convert internal tool descriptions into a Gemini ``tools`` block."""
    if not tools:
        return None
    declarations = []
    for t in tools:
        if not isinstance(t, dict):
            continue
        declarations.append(
            {
                "name": t.get("name", ""),
                "description": t.get("description", ""),
                "parameters": t.get("parameters", {}) or {"type": "object", "properties": {}},
            }
        )
    if not declarations:
        return None
    return {"function_declarations": declarations}


def _extract_text_from_response(data: Dict[str, Any]) -> str:
    parts = (data.get("candidates") or [{}])[0].get("content", {}).get("parts", [])
    text_parts = [p.get("text", "") for p in parts if isinstance(p, dict) and p.get("text")]
    return "".join(text_parts)


def _extract_tool_calls(data: Dict[str, Any]) -> List[ToolCall]:
    parts = (data.get("candidates") or [{}])[0].get("content", {}).get("parts", [])
    calls: List[ToolCall] = []
    for idx, p in enumerate(parts):
        if not isinstance(p, dict):
            continue
        fc = p.get("functionCall")
        if not fc:
            continue
        calls.append(
            ToolCall(
                id=fc.get("id") or f"call_{idx}",
                name=fc.get("name", ""),
                arguments=fc.get("args") or {},
            )
        )
    return calls


def _finish_reason(data: Dict[str, Any]) -> str:
    cand = (data.get("candidates") or [{}])[0]
    return cand.get("finishReason", "STOP").lower() or "stop"


class GeminiTransport(ChatTransport):
    """Native Google Gemini chat transport."""

    @staticmethod
    def _strip_prefix(model_id: str) -> str:
        # Catalog ids look like "gemini-native/gemini-2.5-pro". The native
        # API expects the bare model name.
        return model_id.split("/", 1)[-1] if model_id.startswith("gemini-native/") else model_id

    @staticmethod
    def _endpoint(base_url: str, model: str, api_key: str, stream: bool) -> str:
        action = "streamGenerateContent" if stream else "generateContent"
        # alt=sse makes Gemini emit Server-Sent Events, which we parse below.
        sep = "&" if "?" in f"{base_url}/models/{model}:{action}" else "?"
        key_param = f"{sep}key={api_key}"
        if stream:
            key_param = f"{sep}alt=sse&key={api_key}"
        return f"{base_url.rstrip('/')}/models/{model}:{action}{key_param}"

    @staticmethod
    def _build_contents(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        contents: List[Dict[str, Any]] = []
        for msg in messages:
            role = msg.get("role", "user")
            # Skip system messages here — they go through systemInstruction.
            if role == "system":
                continue
            parts = _message_to_parts(msg)
            contents.append({"role": _role_for(role), "parts": parts})
        return contents

    @staticmethod
    def _system_block(system: Optional[str]) -> Optional[Dict[str, Any]]:
        if not system:
            return None
        return {"parts": [{"text": system}]}

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
        import httpx

        model_name = self._strip_prefix(params["model"])
        url = self._endpoint(params["base_url"], model_name, params["api_key"], stream=True)
        body: Dict[str, Any] = {
            "contents": self._build_contents(messages),
            "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens},
        }
        sys_block = self._system_block(system)
        if sys_block:
            body["systemInstruction"] = sys_block
        tools_block = _build_tools(tools)
        if tools_block:
            body["tools"] = [tools_block]

        try:
            async with httpx.AsyncClient(timeout=120.0) as http:
                async with http.stream("POST", url, json=body, headers={"Content-Type": "application/json"}) as r:
                    if r.status_code >= 400:
                        text = await r.aread()
                        raise RetriableError(
                            f"Gemini stream HTTP {r.status_code}: {text[:200].decode('utf-8', 'ignore')}",
                            classify_error(Exception(f"HTTP {r.status_code}")),
                        )
                    tool_calls: List[ToolCall] = []
                    finish = None
                    async for line in r.aiter_lines():
                        if not line or not line.startswith("data: "):
                            continue
                        payload = line[6:]
                        try:
                            data = json.loads(payload)
                        except json.JSONDecodeError:
                            continue
                        text_chunk = _extract_text_from_response(data)
                        if text_chunk:
                            yield LLMStreamChunk(content=text_chunk)
                        tcs = _extract_tool_calls(data)
                        if tcs:
                            tool_calls.extend(tcs)
                        fr = _finish_reason(data)
                        if fr and fr != "stop":
                            finish = fr
                        # Gemini emits a final chunk with finishReason == STOP.
                        if (data.get("candidates") or [{}])[0].get("finishReason") == "STOP":
                            finish = "stop"
            if tool_calls or finish:
                yield LLMStreamChunk(tool_calls=tool_calls, finish_reason=finish or "stop")
        except RetriableError:
            raise
        except Exception as exc:
            logger.error("Gemini stream interrupted: %s", exc)
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
        import httpx

        model_name = self._strip_prefix(params["model"])
        url = self._endpoint(params["base_url"], model_name, params["api_key"], stream=False)
        body: Dict[str, Any] = {
            "contents": self._build_contents(messages),
            "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens},
        }
        sys_block = self._system_block(system)
        if sys_block:
            body["systemInstruction"] = sys_block
        tools_block = _build_tools(tools)
        if tools_block:
            body["tools"] = [tools_block]

        try:
            async with httpx.AsyncClient(timeout=120.0) as http:
                r = await http.post(url, json=body, headers={"Content-Type": "application/json"})
                if r.status_code >= 400:
                    raise RetriableError(
                        f"Gemini HTTP {r.status_code}: {r.text[:200]}",
                        classify_error(Exception(f"HTTP {r.status_code}")),
                    )
                data = r.json()
        except RetriableError:
            raise
        except Exception as exc:
            raise RetriableError(str(exc), classify_error(exc)) from exc

        text = _extract_text_from_response(data)
        tool_calls = _extract_tool_calls(data)
        usage = {}
        md = data.get("usageMetadata") or {}
        if md:
            usage = {
                "prompt_tokens": md.get("promptTokenCount", 0),
                "completion_tokens": md.get("candidatesTokenCount", 0),
                "total_tokens": md.get("totalTokenCount", 0),
            }
        return LLMResponse(
            content=text,
            tool_calls=tool_calls,
            finish_reason=_finish_reason(data),
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
        messages: List[Dict[str, Any]] = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": text},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{image_mime};base64,{image_base64}"},
                    },
                ],
            }
        ]
        async for chunk in self._stream(params, messages, None, system, temperature, max_tokens):
            yield chunk
