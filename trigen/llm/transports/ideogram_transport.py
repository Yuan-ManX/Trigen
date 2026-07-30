"""Ideogram image generation transport.

Calls the Ideogram REST API (``/generate``) and returns the resulting
image URL. Ideogram is particularly strong at rendering legible text in
images, which makes it a useful complement to DALL·E / FLUX for posters,
logos, and diagrams.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from trigen.llm.transports.base import ImageTransport
from trigen.llm.types import GenerationResult

logger = logging.getLogger("trigen.llm.transports.ideogram")


class IdeogramTransport(ImageTransport):
    """Image generation via the Ideogram REST API."""

    async def generate_image(
        self, params: Dict[str, Any], prompt: str, size: str, n: int
    ) -> GenerationResult:
        import httpx

        url = f"{params['base_url'].rstrip('/')}/generate"
        headers = {
            "Api-Key": params["api_key"],
            "Content-Type": "application/json",
        }
        # Ideogram accepts aspect_ratio rather than explicit WxH. Map the
        # common square / landscape / portrait sizes; default to SQUARE.
        aspect = "ASPECT_RATIO_1_1"
        if size:
            try:
                w, h = size.lower().split("x")
                if w > h:
                    aspect = "ASPECT_RATIO_16_9"
                elif h > w:
                    aspect = "ASPECT_RATIO_9_16"
            except Exception:
                pass

        body = {
            "prompt": prompt,
            "model": params["model"],
            "aspect_ratio": aspect,
            "num_images": n,
            "output_type": "url",
        }
        try:
            async with httpx.AsyncClient(timeout=180.0) as http:
                r = await http.post(url, json=body, headers=headers)
                if r.status_code >= 400:
                    return GenerationResult(
                        success=False, modality="image_gen", model=params["model"],
                        error=f"Ideogram HTTP {r.status_code}: {r.text[:200]}",
                    )
                data = r.json()
        except Exception as exc:
            return GenerationResult(
                success=False, modality="image_gen", model=params["model"],
                error=f"Ideogram request failed: {exc}",
            )

        items = data.get("data", []) or []
        if not items:
            return GenerationResult(
                success=False, modality="image_gen", model=params["model"],
                error="Ideogram returned no images",
            )
        first = items[0]
        url = first.get("url", "")
        if not url:
            return GenerationResult(
                success=False, modality="image_gen", model=params["model"],
                error="Ideogram response missing url",
            )
        return GenerationResult(
            success=True, modality="image_gen", model=params["model"],
            url=url, mime_type="image/png", raw=data,
        )
