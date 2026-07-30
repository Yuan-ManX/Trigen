"""Shared data types and error helpers for the LLM layer.

These dataclasses and helpers live in a dedicated module so that both
``trigen.llm.client`` (which owns the dispatch surface) and
``trigen.llm.transports`` (which produce/consume these types) can import
them without a circular dependency. Transports must not import from
``client`` at module load time; routing everything through this neutral
module keeps the import graph acyclic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ToolCall:
    """A tool call initiated by the LLM."""

    id: str
    name: str
    arguments: Dict[str, Any]


@dataclass
class LLMResponse:
    """A complete (non-streaming) LLM response."""

    content: str
    tool_calls: List[ToolCall] = field(default_factory=list)
    finish_reason: str = "stop"
    usage: Dict[str, int] = field(default_factory=dict)


@dataclass
class LLMStreamChunk:
    """A streaming response chunk emitted by a transport."""

    content: str = ""
    tool_calls: List[ToolCall] = field(default_factory=list)
    finish_reason: Optional[str] = None


@dataclass
class GenerationResult:
    """Outcome of a multimodal generation call (image / 3D / video / audio)."""

    success: bool
    modality: str
    model: str
    url: str = ""
    base64_data: str = ""
    mime_type: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)
    error: str = ""


class RetriableError(Exception):
    """Raised when a model call fails before any output is produced.

    Carries an ``error_type`` so the fallback loop can decide whether to
    skip the failing provider entirely (auth failures) or just advance to
    the next model (transient 5xx / rate-limit / timeout). Values:
    ``auth``, ``rate_limit``, ``server``, ``timeout``, ``client``,
    ``unknown``.
    """

    def __init__(self, message: str, error_type: str = "unknown"):
        super().__init__(message)
        self.error_type = error_type


def classify_error(exc: Exception) -> str:
    """Classify an exception for fallback decisions.

    Returns one of: 'auth', 'rate_limit', 'server', 'timeout', 'client',
    'unknown'. Auth and client errors (4xx other than 429) are still
    retriable across providers — only the failing provider is skipped.
    """
    # OpenAI SDK exceptions (preferred — carry structured status codes)
    try:
        from openai import (
            APIStatusError,
            APITimeoutError,
            AuthenticationError,
            RateLimitError,
        )

        if isinstance(exc, APITimeoutError):
            return "timeout"
        if isinstance(exc, AuthenticationError):
            return "auth"
        if isinstance(exc, RateLimitError):
            return "rate_limit"
        if isinstance(exc, APIStatusError):
            status = getattr(exc, "status_code", 0) or 0
            if status in (401, 403):
                return "auth"
            if status == 429:
                return "rate_limit"
            if 500 <= status < 600:
                return "server"
            if 400 <= status < 500:
                return "client"
    except ImportError:
        pass

    # httpx exceptions (used by the Anthropic adapter and direct httpx calls)
    try:
        import httpx

        if isinstance(exc, httpx.TimeoutException):
            return "timeout"
        if isinstance(exc, httpx.HTTPStatusError):
            status = exc.response.status_code
            if status in (401, 403):
                return "auth"
            if status == 429:
                return "rate_limit"
            if 500 <= status < 600:
                return "server"
            if 400 <= status < 500:
                return "client"
    except ImportError:
        pass

    # String-based fallback for unknown exception types
    msg = str(exc).lower()
    if "timeout" in msg or "timed out" in msg:
        return "timeout"
    if any(s in msg for s in ("401", "403", "unauthorized", "forbidden", "api key", "api_key")):
        return "auth"
    if "429" in msg or "rate limit" in msg or "rate_limit" in msg:
        return "rate_limit"
    if any(s in msg for s in ("500", "502", "503", "504", "internal server error", "bad gateway")):
        return "server"
    return "unknown"
