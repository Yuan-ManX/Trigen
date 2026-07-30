"""Multimodal generation dispatcher.

Generation models (image, 3D, video, audio, animation) use dedicated API
endpoints that differ from the chat-completions surface. This module
dispatches generation requests to the correct transport via the
``TransportRegistry``, abstracting the per-provider protocol details so
the orchestrator and tools can trigger multimodal generation uniformly.

Each generation function resolves the model's connection params, looks up
the transport registered for the provider + capability, and delegates to
it. When no transport is registered, a structured ``GenerationResult``
error is returned.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from trigen.llm.router import ModelRouter, Modality, ProviderType, router as default_router
from trigen.llm.types import GenerationResult

logger = logging.getLogger("trigen.llm.multimodal")


class MultimodalDispatcher:
    """Dispatches generation requests to provider transports.

    The transport registry holds one transport per (provider, capability)
    pair. This dispatcher is a thin lookup + delegate layer: it resolves
    the model params, finds the transport, and forwards the call. All
    wire-protocol details live inside the transport.
    """

    def __init__(self, model_router: Optional[ModelRouter] = None):
        self.router = model_router or default_router

    def _resolve(self, model_id: str) -> Dict[str, Any]:
        return self.router.resolve(model_id)

    @staticmethod
    def _registry():
        """Lazy accessor for the transport registry (avoids import cycle)."""
        from trigen.llm.transports import registry

        return registry

    @staticmethod
    def _no_key(model_id: str, modality: Modality) -> GenerationResult:
        return GenerationResult(
            success=False, modality=modality.value, model=model_id,
            error="API key not configured for this model",
        )

    @staticmethod
    def _no_transport(model_id: str, modality: Modality, provider: ProviderType) -> GenerationResult:
        return GenerationResult(
            success=False, modality=modality.value, model=model_id,
            error=f"{modality.value} generation not implemented for provider {provider.value}",
        )

    async def generate_image(
        self,
        model_id: str,
        prompt: str,
        size: str = "1024x1024",
        n: int = 1,
    ) -> GenerationResult:
        """Generate an image from a text prompt."""
        params = self._resolve(model_id)
        if not params.get("api_key"):
            return self._no_key(model_id, Modality.IMAGE_GEN)

        provider = params["provider"]
        transport = self._registry().get_image(provider)
        if transport is None:
            return self._no_transport(model_id, Modality.IMAGE_GEN, provider)
        try:
            return await transport.generate_image(params, prompt, size, n)
        except Exception as exc:
            logger.exception("Image generation failed")
            return GenerationResult(
                success=False, modality=Modality.IMAGE_GEN.value, model=model_id, error=str(exc),
            )

    async def generate_3d(
        self, model_id: str, prompt: str, output_format: str = "glb"
    ) -> GenerationResult:
        """Generate a 3D asset from a text prompt."""
        params = self._resolve(model_id)
        if not params.get("api_key"):
            return self._no_key(model_id, Modality.THREE_D)

        provider = params["provider"]
        transport = self._registry().get_3d(provider)
        if transport is None:
            return self._no_transport(model_id, Modality.THREE_D, provider)
        try:
            return await transport.generate_3d(params, prompt, output_format)
        except Exception as exc:
            logger.exception("3D generation failed")
            return GenerationResult(
                success=False, modality=Modality.THREE_D.value, model=model_id, error=str(exc),
            )

    async def generate_video(
        self, model_id: str, prompt: str, duration: int = 5
    ) -> GenerationResult:
        """Generate a video from a text prompt."""
        params = self._resolve(model_id)
        if not params.get("api_key"):
            return self._no_key(model_id, Modality.VIDEO)

        provider = params["provider"]
        transport = self._registry().get_video(provider)
        if transport is None:
            # Preserve the prior explicit message for OpenAI Sora.
            if provider == ProviderType.OPENAI:
                return GenerationResult(
                    success=False, modality=Modality.VIDEO.value, model=model_id,
                    error="OpenAI Sora video API is not publicly available yet",
                )
            return self._no_transport(model_id, Modality.VIDEO, provider)
        try:
            return await transport.generate_video(params, prompt, duration)
        except Exception as exc:
            logger.exception("Video generation failed")
            return GenerationResult(
                success=False, modality=Modality.VIDEO.value, model=model_id, error=str(exc),
            )

    async def generate_animation(
        self, model_id: str, prompt: str, frames: int = 24
    ) -> GenerationResult:
        """Generate an animation sequence from a text prompt."""
        params = self._resolve(model_id)
        if not params.get("api_key"):
            return self._no_key(model_id, Modality.ANIMATION)

        provider = params["provider"]
        transport = self._registry().get_animation(provider)
        if transport is None:
            return self._no_transport(model_id, Modality.ANIMATION, provider)
        try:
            return await transport.generate_animation(params, prompt, frames)
        except Exception as exc:
            logger.exception("Animation generation failed")
            return GenerationResult(
                success=False, modality=Modality.ANIMATION.value, model=model_id, error=str(exc),
            )

    async def synthesize_speech(
        self, model_id: str, text: str, voice: str = "alloy"
    ) -> GenerationResult:
        """Synthesize speech from text via OpenAI TTS."""
        params = self._resolve(model_id)
        if not params.get("api_key"):
            return self._no_key(model_id, Modality.VOICE)

        provider = params["provider"]
        transport = self._registry().get_voice(provider)
        if transport is None:
            return self._no_transport(model_id, Modality.VOICE, provider)
        try:
            return await transport.synthesize_speech(params, text, voice)
        except Exception as exc:
            logger.exception("Speech synthesis failed")
            return GenerationResult(
                success=False, modality=Modality.VOICE.value, model=model_id, error=str(exc),
            )

    async def transcribe_audio(
        self, model_id: str, audio_base64: str, mime_type: str = "audio/wav"
    ) -> GenerationResult:
        """Transcribe audio to text via OpenAI Whisper."""
        params = self._resolve(model_id)
        if not params.get("api_key"):
            return self._no_key(model_id, Modality.AUDIO)

        provider = params["provider"]
        transport = self._registry().get_voice(provider)
        if transport is None:
            return self._no_transport(model_id, Modality.AUDIO, provider)
        try:
            return await transport.transcribe_audio(params, audio_base64, mime_type)
        except Exception as exc:
            logger.exception("Audio transcription failed")
            return GenerationResult(
                success=False, modality=Modality.AUDIO.value, model=model_id, error=str(exc),
            )


# Global dispatcher instance
dispatcher = MultimodalDispatcher()
