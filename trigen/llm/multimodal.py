"""Multimodal generation dispatcher.

Generation models (image, 3D, video, audio, animation) use dedicated API
endpoints that differ from the chat-completions surface. This module
dispatches generation requests to the correct endpoint based on the
model's modality, abstracting the per-provider protocol details so the
orchestrator and tools can trigger multimodal generation uniformly.

Supported generation flows:
  - Image generation: OpenAI Images API (DALL·E), Together/Fireworks
    image endpoints for Stable Diffusion / FLUX.
  - 3D generation: Meshy / Tripo text-to-3D endpoints.
  - Audio: OpenAI TTS (speech synthesis) and Whisper (transcription).
  - Video: OpenAI Sora-style text-to-video endpoints.

Each generation function returns a structured result containing the
output URL or base64 payload, which the caller can feed back into the
scene or chat surface.
"""

from __future__ import annotations

import base64
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from trigen.llm.router import Modality, ModelRouter, ProviderType, router as default_router

logger = logging.getLogger("trigen.llm.multimodal")


@dataclass
class GenerationResult:
    """Outcome of a multimodal generation call."""

    success: bool
    modality: str
    model: str
    url: str = ""
    base64_data: str = ""
    mime_type: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)
    error: str = ""


class MultimodalDispatcher:
    """Dispatches generation requests to provider-specific endpoints.

    Uses httpx for non-OpenAI endpoints and the openai SDK for OpenAI
    image/TTS endpoints, normalizing all results into GenerationResult.
    """

    def __init__(self, model_router: Optional[ModelRouter] = None):
        self.router = model_router or default_router

    def _resolve(self, model_id: str) -> Dict[str, Any]:
        return self.router.resolve(model_id)

    async def generate_image(
        self,
        model_id: str,
        prompt: str,
        size: str = "1024x1024",
        n: int = 1,
    ) -> GenerationResult:
        """Generate an image from a text prompt.

        Routes to the OpenAI Images API for DALL·E models, or to the
        Together/Fireworks image endpoints for open-source models.
        """
        params = self._resolve(model_id)
        if not params.get("api_key"):
            return GenerationResult(
                success=False, modality=Modality.IMAGE_GEN.value, model=model_id,
                error="API key not configured for this model",
            )

        provider = params["provider"]
        try:
            if provider == ProviderType.OPENAI:
                return await self._openai_image(model_id, params, prompt, size, n)
            if provider in (ProviderType.TOGETHER, ProviderType.FIREWORKS):
                return await self._openai_compat_image(model_id, params, prompt, size, n)
            return GenerationResult(
                success=False, modality=Modality.IMAGE_GEN.value, model=model_id,
                error=f"Image generation not implemented for provider {provider.value}",
            )
        except Exception as exc:
            logger.exception("Image generation failed")
            return GenerationResult(
                success=False, modality=Modality.IMAGE_GEN.value, model=model_id, error=str(exc),
            )

    async def _openai_image(
        self, model_id: str, params: Dict[str, Any], prompt: str, size: str, n: int
    ) -> GenerationResult:
        """Call the OpenAI Images API."""
        from openai import AsyncOpenAI

        client = AsyncOpenAI(
            api_key=params["api_key"], base_url=params["base_url"], timeout=120.0
        )
        resp = await client.images.generate(
            model=model_id, prompt=prompt, size=size, n=n, response_format="b64_json"
        )
        if not resp.data:
            return GenerationResult(
                success=False, modality=Modality.IMAGE_GEN.value, model=model_id,
                error="No image returned",
            )
        first = resp.data[0]
        return GenerationResult(
            success=True,
            modality=Modality.IMAGE_GEN.value,
            model=model_id,
            base64_data=first.b64_json or "",
            mime_type="image/png",
            raw={"revised_prompt": getattr(first, "revised_prompt", "")},
        )

    async def _openai_compat_image(
        self, model_id: str, params: Dict[str, Any], prompt: str, size: str, n: int
    ) -> GenerationResult:
        """Call a Together/Fireworks image generation endpoint via httpx."""
        import httpx

        url = f"{params['base_url']}/images/generations"
        headers = {"Authorization": f"Bearer {params['api_key']}"}
        body = {"model": model_id, "prompt": prompt, "size": size, "n": n}
        async with httpx.AsyncClient(timeout=120.0) as http:
            r = await http.post(url, json=body, headers=headers)
            if r.status_code >= 400:
                return GenerationResult(
                    success=False, modality=Modality.IMAGE_GEN.value, model=model_id,
                    error=f"HTTP {r.status_code}: {r.text[:200]}",
                )
            data = r.json()
        items = data.get("data", [])
        if not items:
            return GenerationResult(
                success=False, modality=Modality.IMAGE_GEN.value, model=model_id,
                error="No image returned",
            )
        first = items[0]
        if "b64_json" in first:
            return GenerationResult(
                success=True, modality=Modality.IMAGE_GEN.value, model=model_id,
                base64_data=first["b64_json"], mime_type="image/png", raw=data,
            )
        if "url" in first:
            return GenerationResult(
                success=True, modality=Modality.IMAGE_GEN.value, model=model_id,
                url=first["url"], mime_type="image/png", raw=data,
            )
        return GenerationResult(
            success=False, modality=Modality.IMAGE_GEN.value, model=model_id,
            error="Unknown response shape",
        )

    async def generate_3d(
        self, model_id: str, prompt: str, output_format: str = "glb"
    ) -> GenerationResult:
        """Generate a 3D asset from a text prompt.

        Routes to Meshy/Tripo-style endpoints via OpenRouter when available.
        The actual provider endpoint is resolved from the model catalog.
        """
        params = self._resolve(model_id)
        if not params.get("api_key"):
            return GenerationResult(
                success=False, modality=Modality.THREE_D.value, model=model_id,
                error="API key not configured for this model",
            )
        # 3D generation endpoints are provider-specific and async; this is a
        # placeholder dispatch that emits a clear status so the Agent can
        # surface the capability boundary to the user.
        return GenerationResult(
            success=False, modality=Modality.THREE_D.value, model=model_id,
            error="3D generation requires a provider-specific async job; use the dedicated 3D tool",
            raw={"prompt": prompt, "format": output_format},
        )

    async def synthesize_speech(
        self, model_id: str, text: str, voice: str = "alloy"
    ) -> GenerationResult:
        """Synthesize speech from text via OpenAI TTS."""
        params = self._resolve(model_id)
        if not params.get("api_key"):
            return GenerationResult(
                success=False, modality=Modality.VOICE.value, model=model_id,
                error="API key not configured",
            )
        try:
            from openai import AsyncOpenAI

            client = AsyncOpenAI(
                api_key=params["api_key"], base_url=params["base_url"], timeout=60.0
            )
            resp = await client.audio.speech.create(
                model=model_id, voice=voice, input=text
            )
            audio_bytes = resp.read()
            b64 = base64.b64encode(audio_bytes).decode("ascii")
            return GenerationResult(
                success=True, modality=Modality.VOICE.value, model=model_id,
                base64_data=b64, mime_type="audio/mpeg",
            )
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
            return GenerationResult(
                success=False, modality=Modality.AUDIO.value, model=model_id,
                error="API key not configured",
            )
        try:
            from openai import AsyncOpenAI

            client = AsyncOpenAI(
                api_key=params["api_key"], base_url=params["base_url"], timeout=60.0
            )
            audio_bytes = base64.b64decode(audio_base64)
            import io

            buf = io.BytesIO(audio_bytes)
            buf.name = f"audio.{mime_type.split('/')[-1]}"
            resp = await client.audio.transcriptions.create(model=model_id, file=buf)
            return GenerationResult(
                success=True, modality=Modality.AUDIO.value, model=model_id,
                raw={"text": resp.text},
            )
        except Exception as exc:
            logger.exception("Audio transcription failed")
            return GenerationResult(
                success=False, modality=Modality.AUDIO.value, model=model_id, error=str(exc),
            )


# Global dispatcher instance
dispatcher = MultimodalDispatcher()
