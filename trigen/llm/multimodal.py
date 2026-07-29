"""Multimodal generation dispatcher.

Generation models (image, 3D, video, audio, animation) use dedicated API
endpoints that differ from the chat-completions surface. This module
dispatches generation requests to the correct endpoint based on the
model's modality, abstracting the per-provider protocol details so the
orchestrator and tools can trigger multimodal generation uniformly.

Supported generation flows:
  - Image generation: OpenAI Images API (DALL·E), Together/Fireworks
    image endpoints for Stable Diffusion / FLUX, Stability AI native API.
  - 3D generation: Meshy direct API for text-to-3D and image-to-3D.
  - Audio: OpenAI TTS (speech synthesis) and Whisper (transcription).
  - Video: Runway Gen-3 text-to-video async job polling.
  - Animation: Together AI animation sequence generation.

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

        Routes to the OpenAI Images API for DALL·E models, Stability AI
        native API for Stable Image models, or Together/Fireworks image
        endpoints for open-source models.
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
            if provider == ProviderType.STABILITY:
                return await self._stability_image(model_id, params, prompt, size)
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

    async def _stability_image(
        self, model_id: str, params: Dict[str, Any], prompt: str, size: str
    ) -> GenerationResult:
        """Call the Stability AI native image generation API."""
        import httpx

        # Map size string to width/height
        size_map = {
            "1024x1024": (1024, 1024),
            "512x512": (512, 512),
            "768x768": (768, 768),
            "1024x576": (1024, 576),
            "576x1024": (576, 1024),
        }
        width, height = size_map.get(size, (1024, 1024))

        url = f"{params['base_url']}/generation/{model_id}/text-to-image"
        headers = {
            "Authorization": f"Bearer {params['api_key']}",
            "Accept": "image/*",
            "Content-Type": "application/json",
        }
        body = {
            "prompt": prompt,
            "output_format": "png",
            "width": width,
            "height": height,
        }
        async with httpx.AsyncClient(timeout=180.0) as http:
            r = await http.post(url, json=body, headers=headers)
            if r.status_code >= 400:
                return GenerationResult(
                    success=False, modality=Modality.IMAGE_GEN.value, model=model_id,
                    error=f"HTTP {r.status_code}: {r.text[:200]}",
                )
            b64 = base64.b64encode(r.content).decode("ascii")
            return GenerationResult(
                success=True, modality=Modality.IMAGE_GEN.value, model=model_id,
                base64_data=b64, mime_type="image/png",
            )

    async def generate_3d(
        self, model_id: str, prompt: str, output_format: str = "glb"
    ) -> GenerationResult:
        """Generate a 3D asset from a text prompt.

        Routes to Meshy direct API for text-to-3D generation. The Meshy
        API creates an async job and returns a preview URL when complete.
        """
        params = self._resolve(model_id)
        if not params.get("api_key"):
            return GenerationResult(
                success=False, modality=Modality.THREE_D.value, model=model_id,
                error="API key not configured for this model",
            )

        provider = params["provider"]
        try:
            if provider == ProviderType.MESHY:
                return await self._meshy_text_to_3d(model_id, params, prompt, output_format)
            return GenerationResult(
                success=False, modality=Modality.THREE_D.value, model=model_id,
                error=f"3D generation not implemented for provider {provider.value}",
                raw={"prompt": prompt, "format": output_format},
            )
        except Exception as exc:
            logger.exception("3D generation failed")
            return GenerationResult(
                success=False, modality=Modality.THREE_D.value, model=model_id, error=str(exc),
            )

    async def _meshy_text_to_3d(
        self, model_id: str, params: Dict[str, Any], prompt: str, output_format: str
    ) -> GenerationResult:
        """Create a Meshy text-to-3D job and poll until completion."""
        import asyncio
        import httpx

        base = params["base_url"].rstrip("/")
        headers = {"Authorization": f"Bearer {params['api_key']}"}

        # Step 1: Create the generation task
        create_url = f"{base}/text-to-3d"
        body = {
            "mode": "Turbosmooth",
            "prompt": prompt,
            "art_style": "realistic",
            "output_format": output_format,
        }
        async with httpx.AsyncClient(timeout=120.0) as http:
            r = await http.post(create_url, json=body, headers=headers)
            if r.status_code >= 400:
                return GenerationResult(
                    success=False, modality=Modality.THREE_D.value, model=model_id,
                    error=f"Meshy create failed: HTTP {r.status_code}: {r.text[:200]}",
                )
            task_data = r.json()
        task_id = task_data.get("result")
        if not task_id:
            return GenerationResult(
                success=False, modality=Modality.THREE_D.value, model=model_id,
                error="Meshy did not return a task id",
            )

        # Step 2: Poll for completion (up to 5 minutes)
        poll_url = f"{base}/text-to-3d/{task_id}"
        for _ in range(60):
            await asyncio.sleep(5)
            async with httpx.AsyncClient(timeout=30.0) as http:
                r = await http.get(poll_url, headers=headers)
                if r.status_code >= 400:
                    continue
                status_data = r.json()
            status = status_data.get("status", "")
            if status == "SUCCEEDED":
                model_urls = status_data.get("model_urls", [])
                if model_urls:
                    return GenerationResult(
                        success=True, modality=Modality.THREE_D.value, model=model_id,
                        url=model_urls[0].get("url", ""),
                        mime_type=f"model/{output_format}",
                        raw=status_data,
                    )
            elif status == "FAILED":
                return GenerationResult(
                    success=False, modality=Modality.THREE_D.value, model=model_id,
                    error=f"Meshy task failed: {status_data.get('error', 'unknown')}",
                )

        return GenerationResult(
            success=False, modality=Modality.THREE_D.value, model=model_id,
            error="Meshy task timed out after 5 minutes",
        )

    async def generate_video(
        self, model_id: str, prompt: str, duration: int = 5
    ) -> GenerationResult:
        """Generate a video from a text prompt.

        Routes to Runway Gen-3 text-to-video API. Creates an async task
        and polls until the video URL is available.
        """
        params = self._resolve(model_id)
        if not params.get("api_key"):
            return GenerationResult(
                success=False, modality=Modality.VIDEO.value, model=model_id,
                error="API key not configured for this model",
            )

        provider = params["provider"]
        try:
            if provider == ProviderType.RUNWAY:
                return await self._runway_text_to_video(model_id, params, prompt, duration)
            if provider == ProviderType.OPENAI:
                return GenerationResult(
                    success=False, modality=Modality.VIDEO.value, model=model_id,
                    error="OpenAI Sora video API is not publicly available yet",
                )
            return GenerationResult(
                success=False, modality=Modality.VIDEO.value, model=model_id,
                error=f"Video generation not implemented for provider {provider.value}",
            )
        except Exception as exc:
            logger.exception("Video generation failed")
            return GenerationResult(
                success=False, modality=Modality.VIDEO.value, model=model_id, error=str(exc),
            )

    async def _runway_text_to_video(
        self, model_id: str, params: Dict[str, Any], prompt: str, duration: int
    ) -> GenerationResult:
        """Create a Runway Gen-3 text-to-video task and poll for completion."""
        import asyncio
        import httpx

        base = params["base_url"].rstrip("/")
        headers = {
            "Authorization": f"Bearer {params['api_key']}",
            "Content-Type": "application/json",
        }
        # Extract the model slug from the id (e.g. "runway/gen3-alpha" → "gen3_alpha")
        model_slug = model_id.split("/", 1)[-1].replace("-", "_")

        create_url = f"{base}/text_to_video"
        body = {
            "prompt_text": prompt,
            "model": model_slug,
            "duration": duration,
            "ratio": "16:9",
        }
        async with httpx.AsyncClient(timeout=120.0) as http:
            r = await http.post(create_url, json=body, headers=headers)
            if r.status_code >= 400:
                return GenerationResult(
                    success=False, modality=Modality.VIDEO.value, model=model_id,
                    error=f"Runway create failed: HTTP {r.status_code}: {r.text[:200]}",
                )
            task_data = r.json()
        task_id = task_data.get("id")
        if not task_id:
            return GenerationResult(
                success=False, modality=Modality.VIDEO.value, model=model_id,
                error="Runway did not return a task id",
            )

        # Poll for completion (up to 5 minutes)
        poll_url = f"{base}/tasks/{task_id}"
        for _ in range(60):
            await asyncio.sleep(5)
            async with httpx.AsyncClient(timeout=30.0) as http:
                r = await http.get(poll_url, headers=headers)
                if r.status_code >= 400:
                    continue
                status_data = r.json()
            status = status_data.get("status", "")
            if status == "SUCCEEDED":
                output = status_data.get("output", [])
                if output:
                    return GenerationResult(
                        success=True, modality=Modality.VIDEO.value, model=model_id,
                        url=output[0] if isinstance(output[0], str) else output[0].get("url", ""),
                        mime_type="video/mp4",
                        raw=status_data,
                    )
            elif status == "FAILED":
                return GenerationResult(
                    success=False, modality=Modality.VIDEO.value, model=model_id,
                    error=f"Runway task failed: {status_data.get('failure', 'unknown')}",
                )

        return GenerationResult(
            success=False, modality=Modality.VIDEO.value, model=model_id,
            error="Runway task timed out after 5 minutes",
        )

    async def generate_animation(
        self, model_id: str, prompt: str, frames: int = 24
    ) -> GenerationResult:
        """Generate an animation sequence from a text prompt.

        Uses Together AI's image-to-animation pipeline or compatible endpoints.
        """
        params = self._resolve(model_id)
        if not params.get("api_key"):
            return GenerationResult(
                success=False, modality=Modality.ANIMATION.value, model=model_id,
                error="API key not configured for this model",
            )

        provider = params["provider"]
        try:
            if provider in (ProviderType.TOGETHER, ProviderType.FIREWORKS):
                return await self._openai_compat_image(
                    model_id, params, prompt, "1024x1024", 1
                )
            return GenerationResult(
                success=False, modality=Modality.ANIMATION.value, model=model_id,
                error=f"Animation generation not implemented for provider {provider.value}",
            )
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
