"""Tripo direct 3D generation transport.

Submits a text-to-3D (or image-to-3D) job to the Tripo direct API
(``https://api.tripo3d.ai/v2/openapi``) and polls the task until the
model URL is available (up to five minutes). The model id in the catalog
selects the operation type (``text-to-3d`` vs ``image-to-3d``).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict

from trigen.llm.transports.base import ThreeDTransport
from trigen.llm.types import GenerationResult

logger = logging.getLogger("trigen.llm.transports.tripo")


class TripoTransport(ThreeDTransport):
    """Text-to-3D / image-to-3D via the Tripo direct API."""

    async def generate_3d(
        self, params: Dict[str, Any], prompt: str, output_format: str
    ) -> GenerationResult:
        import httpx

        # The catalog base_url is the API root; the openapi task endpoint
        # is one path segment below it.
        base = params["base_url"].rstrip("/")
        if base.endswith("/v2"):
            base = base[:-3]
        api_root = f"{base}/v2/openapi"
        headers = {
            "Authorization": f"Bearer {params['api_key']}",
            "Content-Type": "application/json",
        }

        # Determine the operation from the model id.
        model_id = params["model"]
        if "image-to-3d" in model_id:
            create_url = f"{api_root}/image-to-3d"
            body: Dict[str, Any] = {"prompt": prompt, "output_format": output_format}
        else:
            create_url = f"{api_root}/text-to-model"
            body = {"prompt": prompt, "output_format": output_format}

        try:
            async with httpx.AsyncClient(timeout=120.0) as http:
                r = await http.post(create_url, json=body, headers=headers)
                if r.status_code >= 400:
                    return GenerationResult(
                        success=False, modality="3d", model=params["model"],
                        error=f"Tripo create failed: HTTP {r.status_code}: {r.text[:200]}",
                    )
                task_data = r.json()
        except Exception as exc:
            return GenerationResult(
                success=False, modality="3d", model=params["model"],
                error=f"Tripo request failed: {exc}",
            )

        task_id = task_data.get("data", {}).get("task_id") or task_data.get("task_id")
        if not task_id:
            return GenerationResult(
                success=False, modality="3d", model=params["model"],
                error="Tripo did not return a task id",
            )

        # Poll for completion (up to 5 minutes).
        poll_url = f"{api_root}/task/{task_id}"
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
            status = status_data.get("data", {}).get("status") or status_data.get("status", "")
            if status in ("success", "SUCCEEDED", "completed"):
                output = (status_data.get("data") or {}).get("output") or {}
                model_url = output.get("model") or output.get("url") or ""
                if model_url:
                    return GenerationResult(
                        success=True, modality="3d", model=params["model"],
                        url=model_url, mime_type=f"model/{output_format}",
                        raw=status_data,
                    )
            elif status in ("failed", "FAILED"):
                return GenerationResult(
                    success=False, modality="3d", model=params["model"],
                    error=f"Tripo task failed: {status_data}",
                )

        return GenerationResult(
            success=False, modality="3d", model=params["model"],
            error="Tripo task timed out after 5 minutes",
        )
