"""Provider transport layer.

Each transport encapsulates the wire protocol for a specific provider
family (OpenAI chat protocol, Anthropic Messages API, Stability image
API, Meshy 3D API, Runway video API). The ``TransportRegistry`` routes a
``ProviderType`` to the transport that implements the requested
capability (chat, image, 3D, video, voice, animation).

Importing this package wires every transport into the global ``registry``
so that ``LLMClient`` and ``MultimodalDispatcher`` can look up a
transport by provider + capability at call time.
"""

from __future__ import annotations

from trigen.llm.router import ProviderType
from trigen.llm.transports.base import (
    AnimationTransport,
    ChatTransport,
    ImageTransport,
    ProviderTransport,
    ThreeDTransport,
    TransportRegistry,
    VideoTransport,
    VoiceTransport,
    registry,
)
from trigen.llm.transports.anthropic_transport import AnthropicTransport
from trigen.llm.transports.meshy_transport import MeshyTransport
from trigen.llm.transports.openai_transport import (
    OPENAI_COMPAT_CHAT_PROVIDERS,
    OpenAITransport,
)
from trigen.llm.transports.runway_transport import RunwayTransport
from trigen.llm.transports.stability_transport import StabilityTransport


def _register_all() -> None:
    """Wire every transport into the global registry.

    One ``OpenAITransport`` instance serves all OpenAI-compatible
    providers for chat. The same instance handles image / animation /
    voice for the providers that expose those endpoints (OpenAI for
    DALL·E / TTS / Whisper; Together + Fireworks for image / animation).
    """
    openai_transport = OpenAITransport()

    # Chat: every OpenAI-compatible provider + Anthropic.
    for provider in OPENAI_COMPAT_CHAT_PROVIDERS:
        registry.register_chat(provider, openai_transport)
    registry.register_chat(ProviderType.ANTHROPIC, AnthropicTransport())

    # Image generation.
    registry.register_image(ProviderType.OPENAI, openai_transport)
    registry.register_image(ProviderType.TOGETHER, openai_transport)
    registry.register_image(ProviderType.FIREWORKS, openai_transport)
    registry.register_image(ProviderType.STABILITY, StabilityTransport())

    # 3D generation.
    registry.register_3d(ProviderType.MESHY, MeshyTransport())

    # Video generation.
    registry.register_video(ProviderType.RUNWAY, RunwayTransport())

    # Animation (Together / Fireworks image-style endpoint).
    registry.register_animation(ProviderType.TOGETHER, openai_transport)
    registry.register_animation(ProviderType.FIREWORKS, openai_transport)

    # Voice (OpenAI TTS + Whisper).
    registry.register_voice(ProviderType.OPENAI, openai_transport)


_register_all()

__all__ = [
    "AnimationTransport",
    "AnthropicTransport",
    "ChatTransport",
    "ImageTransport",
    "MeshyTransport",
    "OpenAITransport",
    "ProviderTransport",
    "RunwayTransport",
    "StabilityTransport",
    "ThreeDTransport",
    "TransportRegistry",
    "VideoTransport",
    "VoiceTransport",
    "registry",
]
