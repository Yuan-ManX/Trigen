"""Runway Gen-3 video generation transport.

Creates a Runway text-to-video async task and polls until the video URL
is available (up to five minutes).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict

from trigen.llm.transports.base import VideoTransport
from trigen.llm.types import GenerationResult

logger = logging.getLogger("trigen.llm.transports.runway")


class RunwayTransport(VideoTransport):
    """Text-to-video generation via the Runway Gen-3 API."""

    async def generate_video(
        self, params: Dict[str, Any], prompt: str, duration: int
    ) -> GenerationResult:
        import httpx

        base = params["base_url"].rstrip("/")
        headers = {
            "Authorization": f"Bearer {params['api_key']}",
            "Content-Type": "application/json",
        }
        # Extract the model slug from the id (e.g. "runway/gen3-alpha" → "gen3_alpha")
        model_slug = params["model"].split("/", 1)[-1].replace("-", "_")

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
                    success=False, modality="video", model=params["model"],
                    error=f"Runway create failed: HTTP {r.status_code}: {r.text[:200]}",
                )
            task_data = r.json()
        task_id = task_data.get("id")
        if not task_id:
            return GenerationResult(
                success=False, modality="video", model=params["model"],
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
                        success=True, modality="video", model=params["model"],
                        url=output[0] if isinstance(output[0], str) else output[0].get("url", ""),
                        mime_type="video/mp4",
                        raw=status_data,
                    )
            elif status == "FAILED":
                return GenerationResult(
                    success=False, modality="video", model=params["model"],
                    error=f"Runway task failed: {status_data.get('failure', 'unknown')}",
                )

        return GenerationResult(
            success=False, modality="video", model=params["model"],
            error="Runway task timed out after 5 minutes",
        )
