"""Anthropic native protocol adapter.

Anthropic's Messages API differs from the OpenAI protocol in request shape,
auth headers, and streaming event semantics. This adapter translates the
unified Trigen call surface (messages + tools + system + streaming) into the
Anthropic Messages API format so the ModelRouter can dispatch Claude-family
models without protocol mismatch.

Key translations:
  - System message is hoisted into a top-level `system` field.
  - Tool schemas are converted from OpenAI function-calling format into
    Anthropic's tool input_schema format.
  - Streaming events (message_start, content_block_delta, message_stop) are
    normalized into LLMStreamChunk instances compatible with the rest of the
    pipeline.
"""

from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator, Dict, List, Optional

from trigen.llm.client import LLMStreamChunk, ToolCall

logger = logging.getLogger("trigen.llm.anthropic")


def _convert_tools(tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Convert OpenAI function-calling tool schema to Anthropic format."""
    converted: List[Dict[str, Any]] = []
    for t in tools:
        if t.get("type") == "function" and "function" in t:
            fn = t["function"]
            converted.append(
                {
                    "name": fn.get("name", ""),
                    "description": fn.get("description", ""),
                    "input_schema": fn.get(
                        "parameters",
                        {"type": "object", "properties": {}},
                    ),
                }
            )
        else:
            # Already in {name, description, input_schema} form
            converted.append(t)
    return converted


def _split_system(messages: List[Dict[str, Any]]) -> tuple[str, List[Dict[str, Any]]]:
    """Extract system text from the message list.

    Anthropic requires a single top-level `system` field, so all system
    messages are concatenated and removed from the conversation array.
    """
    system_parts: List[str] = []
    convo: List[Dict[str, Any]] = []
    for m in messages:
        if m.get("role") == "system":
            content = m.get("content", "")
            if isinstance(content, str):
                system_parts.append(content)
            elif isinstance(content, list):
                # Concatenate text blocks
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        system_parts.append(block.get("text", ""))
        else:
            convo.append(m)
    return "\n\n".join(system_parts), convo


def _normalize_message_content(content: Any) -> Any:
    """Ensure message content matches Anthropic's expected shape.

    Anthropic accepts either a string or a list of content blocks. Tool-call
    results must be wrapped in tool_result blocks.
    """
    return content


def _build_request(
    model: str,
    messages: List[Dict[str, Any]],
    tools: Optional[List[Dict[str, Any]]],
    system: Optional[str],
    temperature: float,
    max_tokens: int,
) -> Dict[str, Any]:
    """Build the Anthropic Messages API request payload."""
    combined_system, convo = _split_system(messages)
    if system:
        combined_system = (combined_system + "\n\n" + system).strip()

    payload: Dict[str, Any] = {
        "model": model,
        "messages": convo,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if combined_system:
        payload["system"] = combined_system
    if tools:
        payload["tools"] = _convert_tools(tools)
        payload["tool_choice"] = {"type": "auto"}
    return payload


class AnthropicAdapter:
    """Streaming client for the Anthropic Messages API.

    Uses httpx directly to avoid an extra dependency and to handle the
    Server-Sent Events (SSE) streaming protocol Anthropic employs.
    """

    def __init__(self, api_key: str, base_url: str, timeout: float = 60.0):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                import httpx
            except ImportError as exc:
                raise RuntimeError("httpx is required for Anthropic protocol") from exc
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                timeout=self.timeout,
            )
        return self._client

    async def stream(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        system: Optional[str] = None,
        model: str = "",
        temperature: float = 0.6,
        max_tokens: int = 2048,
    ) -> AsyncIterator[LLMStreamChunk]:
        """Stream a completion from the Anthropic Messages API."""
        payload = _build_request(model, messages, tools, system, temperature, max_tokens)
        client = self._get_client()

        try:
            async with client.stream(
                "POST", "/messages", json=payload
            ) as response:
                if response.status_code >= 400:
                    body = await response.aread()
                    err_msg = body.decode("utf-8", errors="replace")
                    logger.error("Anthropic API error %d: %s", response.status_code, err_msg)
                    yield LLMStreamChunk(
                        content=f"[Anthropic API error {response.status_code}] {err_msg[:200]}",
                        finish_reason="error",
                    )
                    return

                tool_call_accum: Dict[int, Dict[str, Any]] = {}
                current_tool_index = -1
                finish_reason = "stop"

                async for line in response.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    data_str = line[6:]
                    try:
                        event = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue

                    event_type = event.get("type", "")

                    if event_type == "content_block_start":
                        block = event.get("content_block", {})
                        if block.get("type") == "tool_use":
                            current_tool_index += 1
                            tool_call_accum[current_tool_index] = {
                                "id": block.get("id", ""),
                                "name": block.get("name", ""),
                                "args": "",
                            }

                    elif event_type == "content_block_delta":
                        delta = event.get("delta", {})
                        delta_type = delta.get("type", "")
                        if delta_type == "text_delta":
                            text = delta.get("text", "")
                            if text:
                                yield LLMStreamChunk(content=text)
                        elif delta_type == "input_json_delta":
                            if current_tool_index in tool_call_accum:
                                tool_call_accum[current_tool_index]["args"] += delta.get(
                                    "partial_json", ""
                                )

                    elif event_type == "message_delta":
                        delta = event.get("delta", {})
                        if delta.get("stop_reason"):
                            stop = delta["stop_reason"]
                            if stop == "tool_use":
                                finish_reason = "tool_calls"
                            elif stop == "end_turn":
                                finish_reason = "stop"
                            elif stop == "max_tokens":
                                finish_reason = "length"

                    elif event_type == "message_stop":
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
                        yield LLMStreamChunk(
                            tool_calls=final_tool_calls, finish_reason=finish_reason
                        )
        except Exception as exc:
            logger.error("Anthropic streaming failed: %s", exc)
            yield LLMStreamChunk(
                content=f"[Anthropic call failed] {exc}", finish_reason="error"
            )

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
