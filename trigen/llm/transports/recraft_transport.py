"""Recraft image generation transport.

Calls the Recraft REST API (``/images/generations``) and returns the
resulting image URL. Recraft supports vector and raster output with
strong brand / icon styling.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from trigen.llm.transports.base import ImageTransport
from trigen.llm.types import GenerationResult

logger = logging.getLogger("trigen.llm.transports.recraft")


class RecraftTransport(ImageTransport):
    """Image generation via the Recraft REST API."""

    async def generate_image(
        self, params: Dict[str, Any], prompt: str, size: str, n: int
    ) -> GenerationResult:
        import httpx

        url = f"{params['base_url'].rstrip('/')}/images/generations"
        headers = {
            "Authorization": f"Bearer {params['api_key']}",
            "Content-Type": "application/json",
        }
        body = {
            "prompt": prompt,
            "model": params["model"],
            "size": size or "1024x1024",
            "response_format": "url",
            "n": max(1, min(n, 4)),
        }
        try:
            async with httpx.AsyncClient(timeout=180.0) as http:
                r = await http.post(url, json=body, headers=headers)
                if r.status_code >= 400:
                    return GenerationResult(
                        success=False, modality="image_gen", model=params["model"],
                        error=f"Recraft HTTP {r.status_code}: {r.text[:200]}",
                    )
                data = r.json()
        except Exception as exc:
            return GenerationResult(
                success=False, modality="image_gen", model=params["model"],
                error=f"Recraft request failed: {exc}",
            )

        items = data.get("data", []) or []
        if not items:
            return GenerationResult(
                success=False, modality="image_gen", model=params["model"],
                error="Recraft returned no images",
            )
        first = items[0]
        image_url = first.get("url", "") or ""
        if not image_url:
            return GenerationResult(
                success=False, modality="image_gen", model=params["model"],
                error="Recraft response missing url",
            )
        return GenerationResult(
            success=True, modality="image_gen", model=params["model"],
            url=image_url, mime_type="image/png", raw=data,
        )
