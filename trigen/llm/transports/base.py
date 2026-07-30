"""Transport base classes and registry.

A ``ProviderTransport`` encapsulates the wire protocol for a specific
provider family (OpenAI chat protocol, Anthropic Messages API, Stability
image API, etc.). Capability mixins (``ChatTransport``, ``ImageTransport``,
``ThreeDTransport``, ``VideoTransport``, ``AnimationTransport``,
``VoiceTransport``) declare the methods a transport implements for each
modality.

The ``TransportRegistry`` maps a ``ProviderType`` to the transport that
implements a given capability. Callers (``LLMClient`` and
``MultimodalDispatcher``) look up a transport by provider + capability
and delegate to it, removing the inline ``if provider == ...`` chains
that previously lived in the dispatch surface.

Transports must not import from ``trigen.llm.client`` at module load —
all shared dataclasses and error helpers come from ``trigen.llm.types``.
``client`` imports the registry at call time, which keeps the import
graph acyclic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, Dict, List, Optional

from trigen.llm.router import ProviderType
from trigen.llm.types import (
    GenerationResult,
    LLMResponse,
    LLMStreamChunk,
)


class ProviderTransport(ABC):
    """Base for all provider transports.

    Subclasses declare which ``ProviderType`` values they handle via the
    ``provider_types`` class attribute and implement the capability
    mixins they support.
    """

    provider_types: List[ProviderType] = []


class ChatTransport(ProviderTransport):
    """Streaming chat + vision transport."""

    @abstractmethod
    def stream(
        self,
        params: Dict[str, Any],
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]],
        system: Optional[str],
        temperature: float,
        max_tokens: int,
    ) -> AsyncIterator[LLMStreamChunk]:
        """Stream a chat completion. Raises RetriableError on setup failure."""
        ...

    @abstractmethod
    async def complete(
        self,
        params: Dict[str, Any],
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]],
        system: Optional[str],
        temperature: float,
        max_tokens: int,
    ) -> LLMResponse:
        """Non-streaming chat completion. Raises RetriableError on failure."""
        ...

    @abstractmethod
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
        """Stream a vision request. Raises RetriableError on setup failure."""
        ...


class ImageTransport(ProviderTransport):
    @abstractmethod
    async def generate_image(
        self, params: Dict[str, Any], prompt: str, size: str, n: int
    ) -> GenerationResult:
        ...


class ThreeDTransport(ProviderTransport):
    @abstractmethod
    async def generate_3d(
        self, params: Dict[str, Any], prompt: str, output_format: str
    ) -> GenerationResult:
        ...


class VideoTransport(ProviderTransport):
    @abstractmethod
    async def generate_video(
        self, params: Dict[str, Any], prompt: str, duration: int
    ) -> GenerationResult:
        ...


class AnimationTransport(ProviderTransport):
    @abstractmethod
    async def generate_animation(
        self, params: Dict[str, Any], prompt: str, frames: int
    ) -> GenerationResult:
        ...


class VoiceTransport(ProviderTransport):
    @abstractmethod
    async def synthesize_speech(
        self, params: Dict[str, Any], text: str, voice: str
    ) -> GenerationResult:
        ...

    @abstractmethod
    async def transcribe_audio(
        self, params: Dict[str, Any], audio_base64: str, mime_type: str
    ) -> GenerationResult:
        ...


class MusicTransport(ProviderTransport):
    """Text-to-music generation transport."""

    @abstractmethod
    async def generate_music(
        self,
        params: Dict[str, Any],
        prompt: str,
        duration: int,
    ) -> GenerationResult:
        ...


class TransportRegistry:
    """Maps ``ProviderType`` to the transport for each capability.

    A single transport instance may be registered for many providers
    (e.g. ``OpenAITransport`` serves every OpenAI-compatible provider
    for chat). Lookup returns ``None`` when no transport is registered
    for the requested capability — callers fall back gracefully.
    """

    def __init__(self) -> None:
        self._chat: Dict[ProviderType, ChatTransport] = {}
        self._image: Dict[ProviderType, ImageTransport] = {}
        self._three_d: Dict[ProviderType, ThreeDTransport] = {}
        self._video: Dict[ProviderType, VideoTransport] = {}
        self._animation: Dict[ProviderType, AnimationTransport] = {}
        self._voice: Dict[ProviderType, VoiceTransport] = {}
        self._music: Dict[ProviderType, MusicTransport] = {}

    def register_chat(self, provider: ProviderType, transport: ChatTransport) -> None:
        self._chat[provider] = transport

    def register_image(self, provider: ProviderType, transport: ImageTransport) -> None:
        self._image[provider] = transport

    def register_3d(self, provider: ProviderType, transport: ThreeDTransport) -> None:
        self._three_d[provider] = transport

    def register_video(self, provider: ProviderType, transport: VideoTransport) -> None:
        self._video[provider] = transport

    def register_animation(
        self, provider: ProviderType, transport: AnimationTransport
    ) -> None:
        self._animation[provider] = transport

    def register_voice(self, provider: ProviderType, transport: VoiceTransport) -> None:
        self._voice[provider] = transport

    def register_music(self, provider: ProviderType, transport: MusicTransport) -> None:
        self._music[provider] = transport

    def get_chat(self, provider: ProviderType) -> Optional[ChatTransport]:
        return self._chat.get(provider)

    def get_image(self, provider: ProviderType) -> Optional[ImageTransport]:
        return self._image.get(provider)

    def get_3d(self, provider: ProviderType) -> Optional[ThreeDTransport]:
        return self._three_d.get(provider)

    def get_video(self, provider: ProviderType) -> Optional[VideoTransport]:
        return self._video.get(provider)

    def get_animation(self, provider: ProviderType) -> Optional[AnimationTransport]:
        return self._animation.get(provider)

    def get_voice(self, provider: ProviderType) -> Optional[VoiceTransport]:
        return self._voice.get(provider)

    def get_music(self, provider: ProviderType) -> Optional[MusicTransport]:
        return self._music.get(provider)


# Global registry instance. Transport modules register themselves
# against this object at import time (see transports/__init__.py).
registry = TransportRegistry()
