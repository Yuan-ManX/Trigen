"""Assets router — exported file download and listing."""

from __future__ import annotations

import logging
import os

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, JSONResponse

from trigen.api.config import config
from trigen.api.services.session_service import SessionService

logger = logging.getLogger("trigen.api.assets")  # Assets router logger
router = APIRouter(tags=["assets"])  # Assets router


@router.get("/assets/{session_id}")
async def list_assets(session_id: str) -> JSONResponse:
    """List the exported assets of the specified session."""
    session_svc = SessionService.get()
    assets = await session_svc.get_assets(session_id)
    return JSONResponse(content={"session_id": session_id, "assets": assets})


@router.get("/exports/{filename}")
async def download_export(filename: str) -> FileResponse:
    """Download an exported file."""
    # Prevent path traversal
    safe_name = os.path.basename(filename)
    filepath = os.path.join(config.exports_dir, safe_name)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail=f"File not found: {safe_name}")  # File not found error

    # Infer MIME type
    ext = safe_name.rsplit(".", 1)[-1].lower() if "." in safe_name else ""
    media_types = {
        "glb": "model/gltf-binary",
        "obj": "model/obj",
        "stl": "model/stl",
    }
    media_type = media_types.get(ext, "application/octet-stream")  # Default MIME type

    return FileResponse(filepath, media_type=media_type, filename=safe_name)
