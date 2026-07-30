"""Suno music generation transport.

Submits a text-to-music generation request to the Suno REST API and
polls the resulting generation object until the audio URL is available
(up to five minutes). The catalog models ``suno/v4.5`` and ``suno/v3.5``
are supported.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict

from trigen.llm.transports.base import MusicTransport
from trigen.llm.types import GenerationResult

logger = logging.getLogger("trigen.llm.transports.suno")


class SunoTransport(MusicTransport):
    """Text-to-music via the Suno REST API."""

    async def generate_music(
        self, params: Dict[str, Any], prompt: str, duration: int
    ) -> GenerationResult:
        import httpx

        base = params["base_url"].rstrip("/")
        create_url = f"{base}/generations"
        headers = {
            "Authorization": f"Bearer {params['api_key']}",
            "Content-Type": "application/json",
        }
        body: Dict[str, Any] = {
            "prompt": prompt,
            "model": params["model"],
            "duration": str(duration),
            "format": "mp3",
        }
        try:
            async with httpx.AsyncClient(timeout=120.0) as http:
                r = await http.post(create_url, json=body, headers=headers)
                if r.status_code >= 400:
                    return GenerationResult(
                        success=False, modality="music", model=params["model"],
                        error=f"Suno create failed: HTTP {r.status_code}: {r.text[:200]}",
                    )
                gen_data = r.json()
        except Exception as exc:
            return GenerationResult(
                success=False, modality="music", model=params["model"],
                error=f"Suno request failed: {exc}",
            )

        gen_id = gen_data.get("id") or gen_data.get("generation_id") or ""
        if not gen_id:
            # Some Suno endpoints return the audio URL immediately.
            audio_url = gen_data.get("audio_url") or gen_data.get("url") or ""
            if audio_url:
                return GenerationResult(
                    success=True, modality="music", model=params["model"],
                    url=audio_url, mime_type="audio/mpeg", raw=gen_data,
                )
            return GenerationResult(
                success=False, modality="music", model=params["model"],
                error="Suno did not return a generation id",
            )

        # Poll for completion (up to 5 minutes).
        poll_url = f"{base}/generations/{gen_id}"
        for _ in range(60):
            await asyncio.sleep(5)
            try:
                async with httpx.AsyncClient(timeout=30.0) as http:
                    r = await http.get(poll_url, headers=headers)
                    if r.status_code >= 400:
                        continue
                    status_data = r.json()
            except Exception:
                continue
            status = status_data.get("status", "")
            if status in ("completed", "COMPLETED", "complete"):
                audio_url = (
                    status_data.get("audio_url")
                    or (status_data.get("output") or {}).get("audio_url")
                    or (status_data.get("assets") or {}).get("audio")
                    or ""
                )
                if audio_url:
                    return GenerationResult(
                        success=True, modality="music", model=params["model"],
                        url=audio_url, mime_type="audio/mpeg", raw=status_data,
                    )
            elif status in ("failed", "FAILED"):
                return GenerationResult(
                    success=False, modality="music", model=params["model"],
                    error=f"Suno generation failed: {status_data}",
                )

        return GenerationResult(
            success=False, modality="music", model=params["model"],
            error="Suno generation timed out after 5 minutes",
        )
