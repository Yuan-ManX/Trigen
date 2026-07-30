"""AssemblyAI speech-to-text transport.

Submits an audio URL to the AssemblyAI transcription API
(``https://api.assemblyai.com/v2``) and polls the transcript until the
text is available (up to ten minutes). Only ``transcribe_audio`` is
implemented — AssemblyAI does not provide text-to-speech.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict

from trigen.llm.transports.base import VoiceTransport
from trigen.llm.types import GenerationResult

logger = logging.getLogger("trigen.llm.transports.assemblyai")


class AssemblyAITransport(VoiceTransport):
    """Speech-to-text via the AssemblyAI REST API."""

    async def synthesize_speech(
        self, params: Dict[str, Any], text: str, voice: str
    ) -> GenerationResult:
        """AssemblyAI does not provide text-to-speech."""
        return GenerationResult(
            success=False, modality="voice", model=params["model"],
            error="AssemblyAI does not support speech synthesis",
        )

    async def transcribe_audio(
        self, params: Dict[str, Any], audio_base64: str, mime_type: str
    ) -> GenerationResult:
        """Submit base64 audio to AssemblyAI and poll for the transcript.

        AssemblyAI's v2 endpoint accepts an ``audio_url`` rather than raw
        bytes, so the base64 payload is treated as a URL when it starts
        with ``http``; otherwise it is uploaded via the ``upload`` endpoint.
        To keep this implementation lightweight, callers are expected to
        pass a publicly reachable URL inside ``audio_base64``. When raw
        base64 is supplied we fall back to the upload endpoint.
        """
        import httpx

        base = params["base_url"].rstrip("/")
        headers = {
            "authorization": params["api_key"],
            "Content-Type": "application/json",
        }

        audio_payload = audio_base64.strip()
        if audio_payload.startswith(("http://", "https://")):
            audio_url = audio_payload
        else:
            # Upload raw bytes to AssemblyAI's upload endpoint.
            try:
                async with httpx.AsyncClient(timeout=120.0) as http:
                    up = await http.post(
                        f"{base}/upload",
                        headers={"authorization": params["api_key"]},
                        content=audio_payload.encode("utf-8"),
                    )
                    if up.status_code >= 400:
                        return GenerationResult(
                            success=False, modality="audio", model=params["model"],
                            error=f"AssemblyAI upload failed: HTTP {up.status_code}: {up.text[:200]}",
                        )
                    audio_url = up.json().get("upload_url", "")
            except Exception as exc:
                return GenerationResult(
                    success=False, modality="audio", model=params["model"],
                    error=f"AssemblyAI upload failed: {exc}",
                )

        if not audio_url:
            return GenerationResult(
                success=False, modality="audio", model=params["model"],
                error="AssemblyAI requires an audio URL or base64 payload",
            )

        body = {"audio_url": audio_url, "model": params["model"]}
        try:
            async with httpx.AsyncClient(timeout=120.0) as http:
                r = await http.post(f"{base}/transcript", json=body, headers=headers)
                if r.status_code >= 400:
                    return GenerationResult(
                        success=False, modality="audio", model=params["model"],
                        error=f"AssemblyAI create failed: HTTP {r.status_code}: {r.text[:200]}",
                    )
                transcript_data = r.json()
        except Exception as exc:
            return GenerationResult(
                success=False, modality="audio", model=params["model"],
                error=f"AssemblyAI request failed: {exc}",
            )

        transcript_id = transcript_data.get("id", "")
        if not transcript_id:
            return GenerationResult(
                success=False, modality="audio", model=params["model"],
                error="AssemblyAI did not return a transcript id",
            )

        # Poll for completion (up to 10 minutes).
        poll_url = f"{base}/transcript/{transcript_id}"
        for _ in range(120):
            await asyncio.sleep(5)
            try:
                async with httpx.AsyncClient(timeout=30.0) as http:
                    r = await http.get(poll_url, headers={"authorization": params["api_key"]})
                    if r.status_code >= 400:
                        continue
                    status_data = r.json()
            except Exception:
                continue
            status = status_data.get("status", "")
            if status == "completed":
                return GenerationResult(
                    success=True, modality="audio", model=params["model"],
                    raw={"text": status_data.get("text", ""), "words": status_data.get("words", [])},
                )
            if status == "error":
                return GenerationResult(
                    success=False, modality="audio", model=params["model"],
                    error=f"AssemblyAI transcription failed: {status_data.get('error', '')}",
                )

        return GenerationResult(
            success=False, modality="audio", model=params["model"],
            error="AssemblyAI transcription timed out after 10 minutes",
        )
