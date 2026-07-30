"""Luma Dream Machine / Ray 2 video generation transport.

Submits a text-to-video generation request to the Luma API and polls
the resulting generation object until the video URL is available (up to
five minutes).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict

from trigen.llm.transports.base import VideoTransport
from trigen.llm.types import GenerationResult

logger = logging.getLogger("trigen.llm.transports.luma")


class LumaTransport(VideoTransport):
    """Text-to-video via the Luma Labs API."""

    async def generate_video(
        self, params: Dict[str, Any], prompt: str, duration: int
    ) -> GenerationResult:
        import httpx

        url = f"{params['base_url'].rstrip('/')}/generations"
        headers = {
            "Authorization": f"Bearer {params['api_key']}",
            "Content-Type": "application/json",
        }
        # Map the catalog model id to the Luma model slug.
        model_slug = params["model"].split("/", 1)[-1]
        body = {
            "prompt": prompt,
            "model": model_slug,
            "duration": str(duration),
            "aspect_ratio": "16:9",
        }
        try:
            async with httpx.AsyncClient(timeout=120.0) as http:
                r = await http.post(url, json=body, headers=headers)
                if r.status_code >= 400:
                    return GenerationResult(
                        success=False, modality="video", model=params["model"],
                        error=f"Luma create failed: HTTP {r.status_code}: {r.text[:200]}",
                    )
                gen_data = r.json()
        except Exception as exc:
            return GenerationResult(
                success=False, modality="video", model=params["model"],
                error=f"Luma request failed: {exc}",
            )

        gen_id = gen_data.get("id")
        if not gen_id:
            return GenerationResult(
                success=False, modality="video", model=params["model"],
                error="Luma did not return a generation id",
            )

        # Poll for completion (up to 5 minutes).
        poll_url = f"{params['base_url'].rstrip('/')}/generations/{gen_id}"
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
            state = status_data.get("state", "")
            if state == "completed":
                assets = status_data.get("assets", {}) or {}
                video_url = assets.get("video") or assets.get("video_url") or ""
                if video_url:
                    return GenerationResult(
                        success=True, modality="video", model=params["model"],
                        url=video_url, mime_type="video/mp4", raw=status_data,
                    )
            elif state == "failed":
                return GenerationResult(
                    success=False, modality="video", model=params["model"],
                    error=f"Luma generation failed: {status_data.get('failure_reason', '')}",
                )

        return GenerationResult(
            success=False, modality="video", model=params["model"],
            error="Luma generation timed out after 5 minutes",
        )
