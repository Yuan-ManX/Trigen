"""Multimodal generation tools for the Trigen Agent.

Each tool wraps the central MultimodalDispatcher so the Agent can trigger
image, 3D, video, animation, speech, and transcription generation directly
from natural language. When no specific model is supplied, the tool
auto-selects the first available model matching the required modality,
making the workflow resilient even when only a subset of providers is
configured.

The tools do not mutate the 3D scene directly; instead they return the
generated asset URL or base64 payload inside ToolResult.data, which the
orchestrator forwards to the frontend for rendering or download. This
keeps generation orthogonal to scene editing while remaining accessible
from the same conversational surface.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from trigen.llm.multimodal import dispatcher as multimodal_dispatcher
from trigen.llm.router import Modality, router as model_router
from trigen.scene import Scene
from trigen.tools.base import ToolBase, ToolResult

logger = logging.getLogger("trigen.tools.multimodal")


def _pick_model_by_modality(modality: Modality, preferred: Optional[str] = None) -> Optional[str]:
    """Return the id of the first model that supports the given modality and
    has an API key configured, or None when no usable model exists."""
    if preferred:
        entry = model_router.get_model(preferred)
        if entry and modality in entry.modalities:
            resolved = model_router.resolve(preferred)
            if resolved.get("api_key"):
                return preferred
    for entry in model_router.list_by_modality(modality):
        resolved = model_router.resolve(entry.id)
        if resolved.get("api_key"):
            return entry.id
    return None


def _result_message(modality_label: str, model: str, url: str, has_b64: bool) -> str:
    """Compose a concise user-facing message describing the generation outcome."""
    if url:
        return f"{modality_label} generated with {model}. Asset URL: {url}"
    if has_b64:
        return f"{modality_label} generated with {model}. Payload returned inline."
    return f"{modality_label} generated with {model}."


class GenerateImageTool(ToolBase):
    """Generate an image from a text prompt using a diffusion or DALL·E model."""

    name = "generate_image"
    description = (
        "Generate an image from a text prompt using models like DALL·E 3, "
        "Stable Diffusion, or FLUX. Returns the image as a URL or base64 payload. "
        "Optionally specify size and count. If no model is provided, the first "
        "available image-generation model is used automatically."
    )

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Text description of the image to generate.",
                },
                "model": {
                    "type": "string",
                    "description": "Optional model id, e.g. dall-e-3 or stability/sd3.5-large.",
                },
                "size": {
                    "type": "string",
                    "description": "Image dimensions, e.g. 1024x1024, 512x512.",
                },
                "n": {
                    "type": "integer",
                    "description": "Number of images to generate.",
                },
            },
            "required": ["prompt"],
        }

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        prompt = arguments.get("prompt", "").strip()
        if not prompt:
            return ToolResult(success=False, message="Prompt is required for image generation.")
        model = arguments.get("model") or _pick_model_by_modality(Modality.IMAGE_GEN)
        if not model:
            return ToolResult(
                success=False,
                message="No image-generation model is configured. Set an API key for OpenAI, Stability, Together, or Fireworks.",
            )
        size = arguments.get("size") or "1024x1024"
        try:
            n = int(arguments.get("n") or 1)
        except (TypeError, ValueError):
            n = 1

        result = await multimodal_dispatcher.generate_image(
            model_id=model, prompt=prompt, size=size, n=n
        )
        if not result.success:
            return ToolResult(success=False, message=result.error or "Image generation failed.")

        msg = _result_message("Image", model, result.url, bool(result.base64_data))
        return ToolResult(
            success=True,
            message=msg,
            data={
                "modality": result.modality,
                "model": result.model,
                "url": result.url,
                "base64_data": result.base64_data,
                "mime_type": result.mime_type,
                "prompt": prompt,
            },
        )


class Generate3DAssetTool(ToolBase):
    """Generate a 3D asset from a text prompt using a text-to-3D model."""

    name = "generate_3d_asset"
    description = (
        "Generate a downloadable 3D asset (GLB/OBJ) from a text prompt using "
        "models like Meshy text-to-3D. Returns the asset download URL. If no "
        "model is provided, the first available 3D-generation model is used."
    )

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Text description of the 3D asset to generate.",
                },
                "model": {
                    "type": "string",
                    "description": "Optional 3D-generation model id, e.g. meshy/text-to-3d.",
                },
                "output_format": {
                    "type": "string",
                    "description": "Output format: glb, obj, fbx, or usdz.",
                },
            },
            "required": ["prompt"],
        }

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        prompt = arguments.get("prompt", "").strip()
        if not prompt:
            return ToolResult(success=False, message="Prompt is required for 3D generation.")
        model = arguments.get("model") or _pick_model_by_modality(Modality.THREE_D)
        if not model:
            return ToolResult(
                success=False,
                message="No 3D-generation model is configured. Set a Meshy API key to enable text-to-3D.",
            )
        output_format = arguments.get("output_format") or "glb"

        result = await multimodal_dispatcher.generate_3d(
            model_id=model, prompt=prompt, output_format=output_format
        )
        if not result.success:
            return ToolResult(success=False, message=result.error or "3D generation failed.")

        msg = _result_message("3D asset", model, result.url, False)
        return ToolResult(
            success=True,
            message=msg,
            data={
                "modality": result.modality,
                "model": result.model,
                "url": result.url,
                "mime_type": result.mime_type,
                "prompt": prompt,
                "output_format": output_format,
            },
        )


class GenerateVideoTool(ToolBase):
    """Generate a short video clip from a text prompt using a text-to-video model."""

    name = "generate_video"
    description = (
        "Generate a short video clip from a text prompt using models like "
        "Runway Gen-3. Returns the video URL when the async job completes. "
        "If no model is provided, the first available video-generation model is used."
    )

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Text description of the video to generate.",
                },
                "model": {
                    "type": "string",
                    "description": "Optional video-generation model id, e.g. runway/gen3-alpha.",
                },
                "duration": {
                    "type": "integer",
                    "description": "Video duration in seconds (default 5).",
                },
            },
            "required": ["prompt"],
        }

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        prompt = arguments.get("prompt", "").strip()
        if not prompt:
            return ToolResult(success=False, message="Prompt is required for video generation.")
        model = arguments.get("model") or _pick_model_by_modality(Modality.VIDEO)
        if not model:
            return ToolResult(
                success=False,
                message="No video-generation model is configured. Set a Runway API key to enable text-to-video.",
            )
        try:
            duration = int(arguments.get("duration") or 5)
        except (TypeError, ValueError):
            duration = 5

        result = await multimodal_dispatcher.generate_video(
            model_id=model, prompt=prompt, duration=duration
        )
        if not result.success:
            return ToolResult(success=False, message=result.error or "Video generation failed.")

        msg = _result_message("Video", model, result.url, False)
        return ToolResult(
            success=True,
            message=msg,
            data={
                "modality": result.modality,
                "model": result.model,
                "url": result.url,
                "mime_type": result.mime_type,
                "prompt": prompt,
                "duration": duration,
            },
        )


class GenerateAnimationTool(ToolBase):
    """Generate an animation sequence from a text prompt."""

    name = "generate_animation"
    description = (
        "Generate an animation sequence (sprite sheet or frame set) from a text "
        "prompt using open-source image diffusion models hosted on Together or "
        "Fireworks. Returns the resulting image payload. If no model is provided, "
        "the first available animation-capable model is used."
    )

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Text description of the animation to generate.",
                },
                "model": {
                    "type": "string",
                    "description": "Optional animation-capable model id.",
                },
                "frames": {
                    "type": "integer",
                    "description": "Number of frames to target (default 24).",
                },
            },
            "required": ["prompt"],
        }

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        prompt = arguments.get("prompt", "").strip()
        if not prompt:
            return ToolResult(success=False, message="Prompt is required for animation generation.")
        model = arguments.get("model") or _pick_model_by_modality(Modality.ANIMATION)
        if not model:
            return ToolResult(
                success=False,
                message="No animation-capable model is configured. Set a Together or Fireworks API key.",
            )
        try:
            frames = int(arguments.get("frames") or 24)
        except (TypeError, ValueError):
            frames = 24

        result = await multimodal_dispatcher.generate_animation(
            model_id=model, prompt=prompt, frames=frames
        )
        if not result.success:
            return ToolResult(success=False, message=result.error or "Animation generation failed.")

        msg = _result_message("Animation", model, result.url, bool(result.base64_data))
        return ToolResult(
            success=True,
            message=msg,
            data={
                "modality": result.modality,
                "model": result.model,
                "url": result.url,
                "base64_data": result.base64_data,
                "mime_type": result.mime_type,
                "prompt": prompt,
                "frames": frames,
            },
        )


class SynthesizeSpeechTool(ToolBase):
    """Convert text into spoken audio using a text-to-speech model."""

    name = "synthesize_speech"
    description = (
        "Convert text into spoken audio using OpenAI TTS or compatible providers. "
        "Returns the audio as a base64-encoded payload. Optionally specify a voice id."
    )

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "The text to synthesize into speech.",
                },
                "model": {
                    "type": "string",
                    "description": "Optional TTS model id, e.g. tts-1 or tts-1-hd.",
                },
                "voice": {
                    "type": "string",
                    "description": "Voice id: alloy, echo, fable, onyx, nova, or shimmer.",
                },
            },
            "required": ["text"],
        }

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        text = arguments.get("text", "").strip()
        if not text:
            return ToolResult(success=False, message="Text is required for speech synthesis.")
        model = arguments.get("model") or _pick_model_by_modality(Modality.VOICE)
        if not model:
            return ToolResult(
                success=False,
                message="No TTS model is configured. Set an OpenAI API key to enable speech synthesis.",
            )
        voice = arguments.get("voice") or "alloy"

        result = await multimodal_dispatcher.synthesize_speech(
            model_id=model, text=text, voice=voice
        )
        if not result.success:
            return ToolResult(success=False, message=result.error or "Speech synthesis failed.")

        return ToolResult(
            success=True,
            message=f"Speech synthesized with {model} ({voice}).",
            data={
                "modality": result.modality,
                "model": result.model,
                "base64_data": result.base64_data,
                "mime_type": result.mime_type,
                "voice": voice,
                "text": text,
            },
        )


class TranscribeAudioTool(ToolBase):
    """Transcribe audio content into text using a speech-to-text model."""

    name = "transcribe_audio"
    description = (
        "Transcribe base64-encoded audio into text using OpenAI Whisper or "
        "compatible providers. Returns the recognized text. Useful for voice-driven "
        "scene control pipelines."
    )

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "audio_base64": {
                    "type": "string",
                    "description": "Base64-encoded audio data (without data: prefix).",
                },
                "mime_type": {
                    "type": "string",
                    "description": "Audio MIME type, e.g. audio/wav or audio/mp3.",
                },
                "model": {
                    "type": "string",
                    "description": "Optional transcription model id, e.g. whisper-1.",
                },
            },
            "required": ["audio_base64"],
        }

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        audio_base64 = arguments.get("audio_base64", "").strip()
        if not audio_base64:
            return ToolResult(success=False, message="Audio payload is required for transcription.")
        model = arguments.get("model") or _pick_model_by_modality(Modality.AUDIO)
        if not model:
            return ToolResult(
                success=False,
                message="No transcription model is configured. Set an OpenAI API key to enable Whisper.",
            )
        mime_type = arguments.get("mime_type") or "audio/wav"

        result = await multimodal_dispatcher.transcribe_audio(
            model_id=model, audio_base64=audio_base64, mime_type=mime_type
        )
        if not result.success:
            return ToolResult(success=False, message=result.error or "Transcription failed.")

        transcript = result.raw.get("text", "")
        return ToolResult(
            success=True,
            message=f"Transcription complete with {model}: {transcript[:120]}",
            data={
                "modality": result.modality,
                "model": result.model,
                "text": transcript,
            },
        )


class GenerateMusicTool(ToolBase):
    """Generate a short music clip from a text prompt using a text-to-music model."""

    name = "generate_music"
    description = (
        "Generate a short music clip from a text prompt using models like Suno. "
        "Returns the audio URL when the async job completes. If no model is "
        "provided, the first available music-generation model is used."
    )

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Text description of the music to generate (style, mood, instruments).",
                },
                "model": {
                    "type": "string",
                    "description": "Optional music-generation model id, e.g. suno/v4.5.",
                },
                "duration": {
                    "type": "integer",
                    "description": "Clip duration in seconds (default 30).",
                },
            },
            "required": ["prompt"],
        }

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        prompt = arguments.get("prompt", "").strip()
        if not prompt:
            return ToolResult(success=False, message="Prompt is required for music generation.")
        model = arguments.get("model") or _pick_model_by_modality(Modality.MUSIC)
        if not model:
            return ToolResult(
                success=False,
                message="No music-generation model is configured. Set a Suno API key to enable text-to-music.",
            )
        try:
            duration = int(arguments.get("duration") or 30)
        except (TypeError, ValueError):
            duration = 30

        result = await multimodal_dispatcher.generate_music(
            model_id=model, prompt=prompt, duration=duration
        )
        if not result.success:
            return ToolResult(success=False, message=result.error or "Music generation failed.")

        msg = _result_message("Music", model, result.url, False)
        return ToolResult(
            success=True,
            message=msg,
            data={
                "modality": result.modality,
                "model": result.model,
                "url": result.url,
                "mime_type": result.mime_type,
                "prompt": prompt,
                "duration": duration,
            },
        )
