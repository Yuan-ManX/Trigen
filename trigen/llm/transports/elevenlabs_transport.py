"""ElevenLabs text-to-speech transport.

Calls the ElevenLabs REST TTS endpoint (``/text-to-speech/{voice}``) via
httpx and returns the resulting MP3 bytes as base64. The model id selects
the ElevenLabs model version (``eleven-multilingual-v2``, ``eleven-turbo-v2-5``,
``eleven-monolingual-v1``); the ``voice`` argument selects the speaker.
"""

from __future__ import annotations

import base64
import logging
from typing import Any, Dict

from trigen.llm.transports.base import VoiceTransport
from trigen.llm.types import GenerationResult

logger = logging.getLogger("trigen.llm.transports.elevenlabs")

# Default voice used when the caller does not specify one. ElevenLabs
# supports many voices; Rachel is a stable, broadly available default.
_DEFAULT_VOICE = "Rachel"


class ElevenLabsTransport(VoiceTransport):
    """Text-to-speech via the ElevenLabs REST API."""

    async def synthesize_speech(
        self, params: Dict[str, Any], text: str, voice: str
    ) -> GenerationResult:
        import httpx

        speaker = voice or _DEFAULT_VOICE
        url = f"{params['base_url'].rstrip('/')}/text-to-speech/{speaker}"
        headers = {
            "xi-api-key": params["api_key"],
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        }
        body = {
            "text": text,
            "model_id": params["model"],
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.5},
        }
        try:
            async with httpx.AsyncClient(timeout=120.0) as http:
                r = await http.post(url, json=body, headers=headers)
                if r.status_code >= 400:
                    return GenerationResult(
                        success=False, modality="voice", model=params["model"],
                        error=f"ElevenLabs HTTP {r.status_code}: {r.text[:200]}",
                    )
                audio_bytes = r.content
        except Exception as exc:
            return GenerationResult(
                success=False, modality="voice", model=params["model"],
                error=f"ElevenLabs request failed: {exc}",
            )
        b64 = base64.b64encode(audio_bytes).decode("ascii")
        return GenerationResult(
            success=True, modality="voice", model=params["model"],
            base64_data=b64, mime_type="audio/mpeg",
            raw={"voice": speaker, "model": params["model"]},
        )

    async def transcribe_audio(
        self, params: Dict[str, Any], audio_base64: str, mime_type: str
    ) -> GenerationResult:
        """ElevenLabs does not provide speech-to-text."""
        return GenerationResult(
            success=False, modality="audio", model=params["model"],
            error="ElevenLabs does not support audio transcription",
        )
