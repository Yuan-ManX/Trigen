"""Kling text-to-video transport.

Submits a text-to-video job to the Kling direct API
(``https://api.klingai.com/v1``) and polls the task until the video URL
is available (up to five minutes). The catalog models ``kling/v2-master``
and ``kling/v1-6-pro`` are supported.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict

from trigen.llm.transports.base import VideoTransport
from trigen.llm.types import GenerationResult

logger = logging.getLogger("trigen.llm.transports.kling")


class KlingTransport(VideoTransport):
    """Text-to-video via the Kling direct REST API."""

    async def generate_video(
        self, params: Dict[str, Any], prompt: str, duration: int
    ) -> GenerationResult:
        import httpx

        base = params["base_url"].rstrip("/")
        create_url = f"{base}/videos/text2video"
        headers = {
            "Authorization": f"Bearer {params['api_key']}",
            "Content-Type": "application/json",
        }
        # Map catalog model id to the Kling model slug.
        model_slug = params["model"].split("/", 1)[-1]
        body: Dict[str, Any] = {
            "model": model_slug,
            "prompt": prompt,
            "duration": str(duration),
            "aspect_ratio": "16:9",
        }
        try:
            async with httpx.AsyncClient(timeout=120.0) as http:
                r = await http.post(create_url, json=body, headers=headers)
                if r.status_code >= 400:
                    return GenerationResult(
                        success=False, modality="video", model=params["model"],
                        error=f"Kling create failed: HTTP {r.status_code}: {r.text[:200]}",
                    )
                task_data = r.json()
        except Exception as exc:
            return GenerationResult(
                success=False, modality="video", model=params["model"],
                error=f"Kling request failed: {exc}",
            )

        # Kling returns {"code": 0, "data": {"task_id": "..."}}.
        data_obj = task_data.get("data") or {}
        task_id = data_obj.get("task_id") or task_data.get("task_id") or ""
        if not task_id:
            return GenerationResult(
                success=False, modality="video", model=params["model"],
                error="Kling did not return a task id",
            )

        # Poll for completion (up to 5 minutes).
        poll_url = f"{base}/videos/text2video/{task_id}"
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
            inner = status_data.get("data") or {}
            status = inner.get("task_status") or inner.get("status") or status_data.get("status", "")
            if status in ("succeed", "SUCCEEDED", "success", "completed"):
                videos = inner.get("videos") or []
                if videos and isinstance(videos[0], dict):
                    video_url = videos[0].get("url") or videos[0].get("video") or ""
                    if video_url:
                        return GenerationResult(
                            success=True, modality="video", model=params["model"],
                            url=video_url, mime_type="video/mp4", raw=status_data,
                        )
            elif status in ("failed", "FAILED"):
                return GenerationResult(
                    success=False, modality="video", model=params["model"],
                    error=f"Kling task failed: {status_data}",
                )

        return GenerationResult(
            success=False, modality="video", model=params["model"],
            error="Kling task timed out after 5 minutes",
        )
