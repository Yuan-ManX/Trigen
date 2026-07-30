"""Meshy 3D generation transport.

Creates a Meshy text-to-3D async job and polls until completion (up to
five minutes). Returns the first model URL from the completed task.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict

from trigen.llm.transports.base import ThreeDTransport
from trigen.llm.types import GenerationResult

logger = logging.getLogger("trigen.llm.transports.meshy")


class MeshyTransport(ThreeDTransport):
    """Text-to-3D generation via the Meshy direct API."""

    async def generate_3d(
        self, params: Dict[str, Any], prompt: str, output_format: str
    ) -> GenerationResult:
        import httpx

        base = params["base_url"].rstrip("/")
        headers = {"Authorization": f"Bearer {params['api_key']}"}

        # Step 1: create the generation task
        create_url = f"{base}/text-to-3d"
        body = {
            "mode": "Turbosmooth",
            "prompt": prompt,
            "art_style": "realistic",
            "output_format": output_format,
        }
        async with httpx.AsyncClient(timeout=120.0) as http:
            r = await http.post(create_url, json=body, headers=headers)
            if r.status_code >= 400:
                return GenerationResult(
                    success=False, modality="3d", model=params["model"],
                    error=f"Meshy create failed: HTTP {r.status_code}: {r.text[:200]}",
                )
            task_data = r.json()
        task_id = task_data.get("result")
        if not task_id:
            return GenerationResult(
                success=False, modality="3d", model=params["model"],
                error="Meshy did not return a task id",
            )

        # Step 2: poll for completion (up to 5 minutes)
        poll_url = f"{base}/text-to-3d/{task_id}"
        for _ in range(60):
            await asyncio.sleep(5)
            async with httpx.AsyncClient(timeout=30.0) as http:
                r = await http.get(poll_url, headers=headers)
                if r.status_code >= 400:
                    continue
                status_data = r.json()
            status = status_data.get("status", "")
            if status == "SUCCEEDED":
                model_urls = status_data.get("model_urls", [])
                if model_urls:
                    return GenerationResult(
                        success=True, modality="3d", model=params["model"],
                        url=model_urls[0].get("url", ""),
                        mime_type=f"model/{output_format}",
                        raw=status_data,
                    )
            elif status == "FAILED":
                return GenerationResult(
                    success=False, modality="3d", model=params["model"],
                    error=f"Meshy task failed: {status_data.get('error', 'unknown')}",
                )

        return GenerationResult(
            success=False, modality="3d", model=params["model"],
            error="Meshy task timed out after 5 minutes",
        )
