"""Provider transport layer.

Each transport encapsulates the wire protocol for a specific provider
family (OpenAI chat protocol, Anthropic Messages API, Stability image
API, Meshy 3D API, Runway video API, fal.ai multimodal API, ElevenLabs
TTS API, etc.). The ``TransportRegistry`` routes a ``ProviderType`` to
the transport that implements the requested capability (chat, image,
3D, video, voice, animation, music).

Importing this package wires every transport into the global ``registry``
so that ``LLMClient`` and ``MultimodalDispatcher`` can look up a
transport by provider + capability at call time.

The Google Gemini provider keeps an OpenAI-compatible registration for
``gemini-2.0-*`` / ``gemini-1.5-*`` models. Catalog ids prefixed with
``gemini-native/`` are routed to the ``GeminiTransport`` by the client's
``_get_chat_transport`` helper (model id prefix check), so they bypass
the OpenAI-compatible chat lookup entirely.
"""

from __future__ import annotations

from trigen.llm.router import ProviderType
from trigen.llm.transports.anthropic_transport import AnthropicTransport
from trigen.llm.transports.assemblyai_transport import AssemblyAITransport
from trigen.llm.transports.base import (
    AnimationTransport,
    ChatTransport,
    ImageTransport,
    MusicTransport,
    ProviderTransport,
    ThreeDTransport,
    TransportRegistry,
    VideoTransport,
    VoiceTransport,
    registry,
)
from trigen.llm.transports.elevenlabs_transport import ElevenLabsTransport
from trigen.llm.transports.fal_transport import FalTransport
from trigen.llm.transports.gemini_transport import GeminiTransport
from trigen.llm.transports.ideogram_transport import IdeogramTransport
from trigen.llm.transports.kling_transport import KlingTransport
from trigen.llm.transports.leonardo_transport import LeonardoTransport
from trigen.llm.transports.meshy_transport import MeshyTransport
from trigen.llm.transports.luma_transport import LumaTransport
from trigen.llm.transports.openai_transport import (
    OPENAI_COMPAT_CHAT_PROVIDERS,
    OpenAITransport,
)
from trigen.llm.transports.pika_transport import PikaTransport
from trigen.llm.transports.recraft_transport import RecraftTransport
from trigen.llm.transports.runway_transport import RunwayTransport
from trigen.llm.transports.stability_transport import StabilityTransport
from trigen.llm.transports.suno_transport import SunoTransport
from trigen.llm.transports.tripo_transport import TripoTransport


def _register_all() -> None:
    """Wire every transport into the global registry.

    One ``OpenAITransport`` instance serves all OpenAI-compatible
    providers for chat. The same instance handles image / animation /
    voice for the providers that expose those endpoints (OpenAI for
    DALL·E / TTS / Whisper; Together + Fireworks for image / animation).

    Generation-only providers (fal, ElevenLabs, Tripo, Luma, Ideogram,
    Leonardo, Recraft, Pika, Kling, AssemblyAI, Suno) each register a
    dedicated transport for the capabilities they expose. Gemini native
    API models register a dedicated chat transport for the ``GOOGLE``
    provider; ``gemini-native/`` ids are routed to it via client-side
    prefix detection.
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
    registry.register_image(ProviderType.FAL, FalTransport())
    registry.register_image(ProviderType.IDEOGRAM, IdeogramTransport())
    registry.register_image(ProviderType.LEONARDO, LeonardoTransport())
    registry.register_image(ProviderType.RECRAFT, RecraftTransport())

    # 3D generation.
    registry.register_3d(ProviderType.MESHY, MeshyTransport())
    registry.register_3d(ProviderType.FAL, FalTransport())
    registry.register_3d(ProviderType.TRIPO, TripoTransport())

    # Video generation.
    registry.register_video(ProviderType.RUNWAY, RunwayTransport())
    registry.register_video(ProviderType.FAL, FalTransport())
    registry.register_video(ProviderType.LUMA, LumaTransport())
    registry.register_video(ProviderType.PIKA, PikaTransport())
    registry.register_video(ProviderType.KLING, KlingTransport())

    # Animation (Together / Fireworks image endpoint).
    registry.register_animation(ProviderType.TOGETHER, openai_transport)
    registry.register_animation(ProviderType.FIREWORKS, openai_transport)

    # Voice (OpenAI TTS + Whisper; ElevenLabs TTS; AssemblyAI STT).
    registry.register_voice(ProviderType.OPENAI, openai_transport)
    registry.register_voice(ProviderType.ELEVENLABS, ElevenLabsTransport())
    registry.register_voice(ProviderType.ASSEMBLYAI, AssemblyAITransport())

    # Music (Suno).
    registry.register_music(ProviderType.SUNO, SunoTransport())

    # Google Gemini native API. Used when the catalog model id starts
    # with "gemini-native/" — the client's _get_chat_transport detects
    # the prefix and falls through to this transport. Other GOOGLE
    # models (gemini-2.0-flash etc.) keep their OpenAI-compatible
    # registration, so we do NOT overwrite the GOOGLE chat slot here.
    GeminiTransport._native_instance = GeminiTransport()  # type: ignore[attr-defined]


_register_all()

__all__ = [
    "AnimationTransport",
    "AnthropicTransport",
    "AssemblyAITransport",
    "ChatTransport",
    "ElevenLabsTransport",
    "FalTransport",
    "GeminiTransport",
    "IdeogramTransport",
    "ImageTransport",
    "KlingTransport",
    "LeonardoTransport",
    "LumaTransport",
    "MeshyTransport",
    "MusicTransport",
    "OpenAITransport",
    "PikaTransport",
    "ProviderTransport",
    "RecraftTransport",
    "RunwayTransport",
    "StabilityTransport",
    "SunoTransport",
    "ThreeDTransport",
    "TransportRegistry",
    "TripoTransport",
    "VideoTransport",
    "VoiceTransport",
    "registry",
]
