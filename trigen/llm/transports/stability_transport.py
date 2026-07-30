"""Stability AI image generation transport.

Calls the Stability AI native image generation API (``/generation/{model}/
text-to-image``) via httpx. Returns raw PNG bytes encoded as base64 inside
a ``GenerationResult``.
"""

from __future__ import annotations

import base64
import logging
from typing import Any, Dict

from trigen.llm.transports.base import ImageTransport
from trigen.llm.types import GenerationResult

logger = logging.getLogger("trigen.llm.transports.stability")


# Map common size strings to (width, height) pairs accepted by Stability.
_SIZE_MAP = {
    "1024x1024": (1024, 1024),
    "512x512": (512, 512),
    "768x768": (768, 768),
    "1024x576": (1024, 576),
    "576x1024": (576, 1024),
}


class StabilityTransport(ImageTransport):
    """Image generation via the Stability AI native API."""

    async def generate_image(
        self, params: Dict[str, Any], prompt: str, size: str, n: int
    ) -> GenerationResult:
        import httpx

        width, height = _SIZE_MAP.get(size, (1024, 1024))

        url = f"{params['base_url']}/generation/{params['model']}/text-to-image"
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
                    success=False, modality="image_gen", model=params["model"],
                    error=f"HTTP {r.status_code}: {r.text[:200]}",
                )
            b64 = base64.b64encode(r.content).decode("ascii")
            return GenerationResult(
                success=True, modality="image_gen", model=params["model"],
                base64_data=b64, mime_type="image/png",
            )
