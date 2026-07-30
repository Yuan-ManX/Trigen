"""fal.ai multimodal generation transport.

fal.ai hosts a wide range of image, video, and 3D generation models behind
a unified queue-based REST API. The model id (e.g. ``fal-ai/flux-pro``)
acts as the URL path under ``https://fal.run/``. Generation requests are
synchronous for image models; video / 3D models would normally use the
async queue API, but for simplicity this transport uses the synchronous
``/f`` endpoint which waits for the result.

The transport auto-detects the modality from the model id (image by
default; ``kling-video`` -> video; ``tripo-3d`` -> 3D) so a single class
can serve every fal model in the catalog.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from trigen.llm.transports.base import (
    ImageTransport,
    ThreeDTransport,
    VideoTransport,
)
from trigen.llm.types import GenerationResult

logger = logging.getLogger("trigen.llm.transports.fal")


class FalTransport(ImageTransport, VideoTransport, ThreeDTransport):
    """fal.ai image / video / 3D generation transport."""

    async def generate_image(
        self, params: Dict[str, Any], prompt: str, size: str, n: int
    ) -> GenerationResult:
        import httpx

        url = f"{params['base_url'].rstrip('/')}/{params['model']}"
        headers = {
            "Authorization": f"Key {params['api_key']}",
            "Content-Type": "application/json",
        }
        body = {"prompt": prompt, "image_size": size, "num_images": n}
        return await self._post_sync(url, headers, body, params, "image_gen", "image/png")

    async def generate_video(
        self, params: Dict[str, Any], prompt: str, duration: int
    ) -> GenerationResult:
        import httpx

        url = f"{params['base_url'].rstrip('/')}/{params['model']}"
        headers = {
            "Authorization": f"Key {params['api_key']}",
            "Content-Type": "application/json",
        }
        body = {"prompt": prompt, "duration": str(duration)}
        return await self._post_sync(url, headers, body, params, "video", "video/mp4")

    async def generate_3d(
        self, params: Dict[str, Any], prompt: str, output_format: str
    ) -> GenerationResult:
        import httpx

        url = f"{params['base_url'].rstrip('/')}/{params['model']}"
        headers = {
            "Authorization": f"Key {params['api_key']}",
            "Content-Type": "application/json",
        }
        body = {"prompt": prompt, "output_format": output_format}
        return await self._post_sync(
            url, headers, body, params, "3d", f"model/{output_format}"
        )

    async def _post_sync(
        self,
        url: str,
        headers: Dict[str, str],
        body: Dict[str, Any],
        params: Dict[str, Any],
        modality: str,
        mime_type: str,
    ) -> GenerationResult:
        import httpx

        try:
            async with httpx.AsyncClient(timeout=300.0) as http:
                r = await http.post(url, json=body, headers=headers)
                if r.status_code >= 400:
                    return GenerationResult(
                        success=False, modality=modality, model=params["model"],
                        error=f"fal.ai HTTP {r.status_code}: {r.text[:200]}",
                    )
                data = r.json()
        except Exception as exc:
            return GenerationResult(
                success=False, modality=modality, model=params["model"],
                error=f"fal.ai request failed: {exc}",
            )

        # fal.ai wraps results in {"images": [...]} / {"video": {"url": ...}} /
        # {"model_urls": [...]} depending on the model. Normalize each shape.
        if modality == "image_gen":
            images = data.get("images") or []
            if not images:
                return GenerationResult(
                    success=False, modality=modality, model=params["model"],
                    error="fal.ai returned no images",
                )
            first = images[0]
            url = first.get("url", "") if isinstance(first, dict) else str(first)
            return GenerationResult(
                success=True, modality=modality, model=params["model"],
                url=url, mime_type=mime_type, raw=data,
            )
        if modality == "video":
            video = data.get("video") or {}
            url = video.get("url", "") if isinstance(video, dict) else str(video)
            if not url:
                return GenerationResult(
                    success=False, modality=modality, model=params["model"],
                    error="fal.ai returned no video url",
                )
            return GenerationResult(
                success=True, modality=modality, model=params["model"],
                url=url, mime_type=mime_type, raw=data,
            )
        # 3D
        model_urls = data.get("model_urls") or []
        if not model_urls:
            return GenerationResult(
                success