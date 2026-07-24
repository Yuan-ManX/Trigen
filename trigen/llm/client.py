"""Trigen LLM 客户端 / Trigen LLM Client.

统一封装 OpenAI 协议兼容的推理服务，支持流式输出与原生函数调用，
可对接 OpenAI、Anthropic 代理、本地推理服务（Ollama / vLLM / LM Studio）。
Unified wrapper for OpenAI-protocol compatible inference services, supporting
streaming output and native function calling. Compatible with OpenAI, Anthropic
proxies, and local inference services (Ollama / vLLM / LM Studio).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, List, Optional

from trigen.config import LLMConfig

logger = logging.getLogger("trigen.llm")


@dataclass
class ToolCall:
    """LLM 发起的工具调用。

    A tool call initiated by the LLM.
    """

    id: str
    name: str
    arguments: Dict[str, Any]


@dataclass
class LLMResponse:
    """LLM 一次完整响应。

    A complete LLM response.
    """

    content: str
    tool_calls: List[ToolCall] = field(default_factory=list)
    finish_reason: str = "stop"
    usage: Dict[str, int] = field(default_factory=dict)


@dataclass
class LLMStreamChunk:
    """流式响应片段。

    A streaming response chunk.
    """

    content: str = ""
    tool_calls: List[ToolCall] = field(default_factory=list)
    finish_reason: Optional[str] = None


class LLMClient:
    """OpenAI 协议兼容的异步 LLM 客户端。

    Asynchronous LLM client compatible with the OpenAI protocol.
    """

    def __init__(self, config: LLMConfig):
        self.config = config
        self._client = None

    def _ensure_client(self):
        if self._client is None:
            try:
                from openai import AsyncOpenAI
            except ImportError as exc:
                raise RuntimeError(
                    "未安装 openai 包，请在 agent 目录执行 pip install -e ."
                ) from exc
            kwargs: Dict[str, Any] = {
                "api_key": self.config.api_key or "missing",
                "base_url": self.config.base_url,
                "timeout": self.config.timeout,
            }
            self._client = AsyncOpenAI(**kwargs)
        return self._client

    def _build_tools_schema(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """将内部工具描述转为 OpenAI function calling schema。

        Convert internal tool descriptions into OpenAI function calling schema.
        """
        return [{"type": "function", "function": t} for t in tools]

    async def complete(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        system: Optional[str] = None,
    ) -> LLMResponse:
        """同步（非流式）补全，返回完整响应。

        Synchronous (non-streaming) completion, returning the full response.
        """
        client = self._ensure_client()
        full_messages: List[Dict[str, Any]] = []
        if system:
            full_messages.append({"role": "system", "content": system})
        full_messages.extend(messages)

        kwargs: Dict[str, Any] = {
            "model": self.config.model,
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
            logger.error("LLM 调用失败: %s", exc)
            return LLMResponse(content=f"[LLM 调用失败] {exc}", finish_reason="error")

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
    ) -> AsyncIterator[LLMStreamChunk]:
        """流式补全，逐 token 产出。

        Streaming completion, yielding token by token.
        """
        client = self._ensure_client()
        full_messages: List[Dict[str, Any]] = []
        if system:
            full_messages.append({"role": "system", "content": system})
        full_messages.extend(messages)

        kwargs: Dict[str, Any] = {
            "model": self.config.model,
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
            logger.error("LLM 流式调用失败: %s", exc)
            yield LLMStreamChunk(content=f"[LLM 调用失败] {exc}", finish_reason="error")
            return

        tool_call_accum: Dict[int, Dict[str, Any]] = {}  # 工具调用累计字典 / Tool call accumulation dict
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
