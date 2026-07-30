"""Pika video generation transport.

Submits a text-to-video generation request to the Pika REST API and
polls the resulting generation object until the video URL is available
(up to five minutes). Pika 2.0 and Pika Scenes are the supported
catalog models.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict

from trigen.llm.transports.base import VideoTransport
from trigen.llm.types import GenerationResult

logger = logging.getLogger("trigen.llm.transports.pika")


class PikaTransport(VideoTransport):
    """Text-to-video via the Pika REST API."""

    async def generate_video(
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
            "aspect_ratio": "16:9",
        }
        try:
            async with httpx.AsyncClient(timeout=120.0) as http:
                r = await http.post(create_url, json=body, headers=headers)
                if r.status_code >= 400:
                    return GenerationResult(
                        success=False, modality="video", model=params["model"],
                        error=f"Pika create failed: HTTP {r.status_code}: {r.text[:200]}",
                    )
                gen_data = r.json()
        except Exception as exc:
            return GenerationResult(
                success=False, modality="video", model=params["model"],
                error=f"Pika request failed: {exc}",
            )

        gen_id = gen_data.get("id") or gen_data.get("generation_id") or ""
        if not gen_id:
            return GenerationResult(
                success=False, modality="video", model=params["model"],
                error="Pika did not return a generation id",
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
                video_url = (
                    status_data.get("video_url")
                    or (status_data.get("output") or {}).get("video_url")
                    or (status_data.get("assets") or {}).get("video")
                    or ""
                )
                if video_url:
                    return GenerationResult(
                        success=True, modality="video", model=params["model"],
                        url=video_url, mime_type="video/mp4", raw=status_data,
                    )
            elif status in ("failed", "FAILED"):
                return GenerationResult(
                    success=False, modality="video", model=params["model"],
                    error=f"Pika generation failed: {status_data}",
                )

        return GenerationResult(
            success=False, modality="video", model=params["model"],
            error="Pika generation timed out after 5 minutes",
        )
