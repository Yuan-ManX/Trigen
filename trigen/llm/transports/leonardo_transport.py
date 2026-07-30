"""Leonardo image generation transport.

Submits a generation request to the Leonardo REST API
(``https://cloud.leonardo.ai/api/rest/v1``) and polls the resulting
generation object until the image URL is available (up to five minutes).
The model id selects the Leonardo model slug (e.g. ``leonardo/phoenix``
-> ``phoenix``).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict

from trigen.llm.transports.base import ImageTransport
from trigen.llm.types import GenerationResult

logger = logging.getLogger("trigen.llm.transports.leonardo")


class LeonardoTransport(ImageTransport):
    """Image generation via the Leonardo REST API."""

    async def generate_image(
        self, params: Dict[str, Any], prompt: str, size: str, n: int
    ) -> GenerationResult:
        import httpx

        base = params["base_url"].rstrip("/")
        create_url = f"{base}/generations"
        headers = {
            "Authorization": f"Bearer {params['api_key']}",
            "Content-Type": "application/json",
        }
        # Map catalog model id (e.g. leonardo/phoenix) to the Leonardo slug.
        model_slug = params["model"].split("/", 1)[-1]

        # Map size "WxH" to Leonardo's width / height fields. Default 1024.
        width, height = 1024, 1024
        if size:
            try:
                w_str, h_str = size.lower().split("x")
                width = int(w_str)
                height = int(h_str)
            except Exception:
                pass

        body: Dict[str, Any] = {
            "prompt": prompt,
            "modelId": model_slug,
            "width": width,
            "height": height,
            "num_images": max(1, min(n, 4)),
            "sd_version": "v2",
        }
        try:
            async with httpx.AsyncClient(timeout=120.0) as http:
                r = await http.post(create_url, json=body, headers=headers)
                if r.status_code >= 400:
                    return GenerationResult(
                        success=False, modality="image_gen", model=params["model"],
                        error=f"Leonardo create failed: HTTP {r.status_code}: {r.text[:200]}",
                    )
                gen_data = r.json()
        except Exception as exc:
            return GenerationResult(
                success=False, modality="image_gen", model=params["model"],
                error=f"Leonardo request failed: {exc}",
            )

        # Leonardo returns {"generations": [{"id": "...", "status": "PENDING"}]}
        # but for synchronous Phoenix generations it may return a
        # {"sdGenerationJob": {"generationId": "..."}} shape. Handle both.
        gen_id = ""
        generations = gen_data.get("generations") or []
        if generations and isinstance(generations[0], dict):
            gen_id = generations[0].get("id", "") or generations[0].get("generationId", "")
        if not gen_id:
            sd_job = gen_data.get("sdGenerationJob") or {}
            gen_id = sd_job.get("generationId", "") or ""

        if not gen_id:
            # Some Leonardo endpoints return URLs directly. Try that first.
            for item in generations:
                if isinstance(item, dict) and item.get("url"):
                    return GenerationResult(
                        success=True, modality="image_gen", model=params["model"],
                        url=item["url"], mime_type="image/png", raw=gen_data,
                    )
            return GenerationResult(
                success=False, modality="image_gen", model=params["model"],
                error="Leonardo did not return a generation id",
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
            gens = status_data.get("generations") or []
            if gens and isinstance(gens[0], dict):
                first = gens[0]
                status = first.get("status", "")
                url = first.get("url", "") or ""
                if url and status in ("COMPLETE", "COMPLETED", "complete"):
                    return GenerationResult(
                        success=True, modality="image_gen", model=params["model"],
                        url=url, mime_type="image/png", raw=status_data,
                    )
                if status in ("FAILED", "failed"):
                    return GenerationResult(
                        success=False, modality="image_gen", model=params["model"],
                        error=f"Leonardo generation failed: {status_data}",
                    )

        return GenerationResult(
            success=False, modality="image_gen", model=params["model"],
            error="Leonardo generation timed out after 5 minutes",
        )
