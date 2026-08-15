"""Scene router.

Exposes the backend Scene as a REST resource: full-scene GET/reset,
per-object CRUD, undo/redo (backend snapshot stack), selection, and
viewport camera. Mutating endpoints snapshot the scene first so the
history stack can restore prior state.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from trigen.api.services.agent_service import AgentService
from trigen.scene import (
    GEOMETRY_DEFAULTS,
    Geometry,
    LightObject,
    Material,
    SceneObject,
    Transform,
)

logger = logging.getLogger("trigen.api.scene")  # Scene router logger
router = APIRouter(tags=["scene"])  # Scene router


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class CreateObjectRequest(BaseModel):
    """Request body for creating a scene object via REST."""

    name: Optional[str] = Field(default=None, description="Object name")
    geometry_type: str = Field(default="box", description="Geometry type")
    params: Dict[str, Any] = Field(default_factory=dict, description="Geometry parameters")
    position: List[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0])
    rotation: List[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0])
    scale: List[float] = Field(default_factory=lambda: [1.0, 1.0, 1.0])
    color: str = Field(default="#cccccc")
    metalness: float = Field(default=0.0)
    roughness: float = Field(default=0.5)
    opacity: float = Field(default=1.0)


class UpdateObjectRequest(BaseModel):
    """Request body for partially updating a scene object.

    All fields are optional; only provided fields are applied.
    """

    name: Optional[str] = None
    geometry_type: Optional[str] = None
    params: Optional[Dict[str, Any]] = None
    position: Optional[List[float]] = None
    rotation: Optional[List[float]] = None
    scale: Optional[List[float]] = None
    color: Optional[str] = None
    metalness: Optional[float] = None
    roughness: Optional[float] = None
    opacity: Optional[float] = None
    visible: Optional[bool] = None
    locked: Optional[bool] = None


class CreateLightRequest(BaseModel):
    """Request body for creating a light."""

    name: Optional[str] = None
    type: str = Field(default="directional")
    color: str = Field(default="#ffffff")
    intensity: float = Field(default=1.0)
    position: List[float] = Field(default_factory=lambda: [5.0, 5.0, 5.0])
    target: Optional[List[float]] = None
    cast_shadow: bool = True


class SelectRequest(BaseModel):
    """Request body for setting the selection."""

    targets: List[str] = Field(default_factory=list, description="Object ids or names")
    clear: bool = Field(default=True, description="Clear previous selection")


class ViewportCamera(BaseModel):
    """Viewport camera state."""

    position: List[float] = Field(default_factory=lambda: [5.0, 4.0, 7.0])
    target: List[float] = Field(default_factory=lambda: [0.0, 0.5, 0.0])
    smooth: bool = True


# ---------------------------------------------------------------------------
# Full-scene endpoints
# ---------------------------------------------------------------------------


@router.get("/scene/{session_id}")
async def get_scene(session_id: str) -> JSONResponse:
    """Get the full scene of the specified session."""
    agent = AgentService.get()
    scene = agent.get_scene(session_id)
    history = agent.orchestrator.history_status(session_id)
    return JSONResponse(content={"session_id": session_id, **scene, "history": history})


@router.post("/scene/{session_id}/reset")
async def reset_scene(session_id: str) -> JSONResponse:
    """Reset the scene and conversation of the specified session."""
    agent = AgentService.get()
    agent.reset_session(session_id)
    # Re-fetch the default scene after reset
    scene = agent.get_scene(session_id)
    return JSONResponse(content={"session_id": session_id, "reset": True, **scene})


# ---------------------------------------------------------------------------
# Object CRUD
# ---------------------------------------------------------------------------


@router.get("/scene/{session_id}/objects")
async def list_objects(session_id: str) -> JSONResponse:
    """List all objects in the scene."""
    agent = AgentService.get()
    scene = agent.orchestrator.get_scene(session_id)
    return JSONResponse(
        content={
            "session_id": session_id,
            "objects": [o.to_dict() for o in scene.objects],
            "count": len(scene.objects),
        }
    )


@router.post("/scene/{session_id}/objects")
async def create_object(session_id: str, req: CreateObjectRequest) -> JSONResponse:
    """Create a new object and add it to the scene."""
    agent = AgentService.get()
    orch = agent.orchestrator
    if req.geometry_type not in GEOMETRY_DEFAULTS:
        return JSONResponse(
            status_code=400,
            content={
                "error": f"Unknown geometry_type '{req.geometry_type}'",
                "valid_types": list(GEOMETRY_DEFAULTS.keys()),
            },
        )
    # Snapshot before mutation so the user can undo via the API.
    orch.push_scene_history(session_id)
    scene = orch.get_scene(session_id)
    name = req.name or scene.next_auto_name(req.geometry_type.capitalize())
    obj = SceneObject(
        name=name,
        geometry=Geometry(type=req.geometry_type, params=dict(req.params)),
        material=Material(
            color=req.color,
            metalness=req.metalness,
            roughness=req.roughness,
            opacity=req.opacity,
        ),
        transform=Transform(
            position=list(req.position),
            rotation=list(req.rotation),
            scale=list(req.scale),
        ),
    )
    scene.objects.append(obj)
    logger.info("Scene API: created object %s (%s) in session %s", obj.id, obj.name, session_id)
    return JSONResponse(
        status_code=201,
        content={
            "session_id": session_id,
            "object": obj.to_dict(),
            "scene": scene.to_dict(),
        },
    )


@router.put("/scene/{session_id}/objects/{object_id}")
async def update_object(
    session_id: str, object_id: str, req: UpdateObjectRequest
) -> JSONResponse:
    """Partially update an existing object. Only provided fields are applied."""
    agent = AgentService.get()
    orch = agent.orchestrator
    scene = orch.get_scene(session_id)
    obj = scene.find_object(object_id)
    if obj is None:
        return JSONResponse(
            status_code=404,
            content={"error": f"Object '{object_id}' not found"},
        )
    # Validate geometry_type before snapshotting so an invalid request
    # does not pollute the undo stack.
    if req.geometry_type is not None and req.geometry_type not in GEOMETRY_DEFAULTS:
        return JSONResponse(
            status_code=400,
            content={"error": f"Unknown geometry_type '{req.geometry_type}'"},
        )
    orch.push_scene_history(session_id)
    # Apply patches.
    if req.name is not None:
        obj.name = req.name
    if req.geometry_type is not None:
        obj.geometry.type = req.geometry_type
    if req.params is not None:
        obj.geometry.params = dict(req.params)
    if req.position is not None:
        obj.transform.position = list(req.position)
    if req.rotation is not None:
        obj.transform.rotation = list(req.rotation)
    if req.scale is not None:
        obj.transform.scale = list(req.scale)
    if req.color is not None:
        obj.material.color = req.color
    if req.metalness is not None:
        obj.material.metalness = req.metalness
    if req.roughness is not None:
        obj.material.roughness = req.roughness
    if req.opacity is not None:
        obj.material.opacity = req.opacity
    if req.visible is not None:
        obj.visible = req.visible
    if req.locked is not None:
        obj.locked = req.locked
    return JSONResponse(
        content={
            "session_id": session_id,
            "object": obj.to_dict(),
            "scene": scene.to_dict(),
        }
    )


@router.delete("/scene/{session_id}/objects/{object_id}")
async def delete_object(session_id: str, object_id: str) -> JSONResponse:
    """Delete an object from the scene."""
    agent = AgentService.get()
    orch = agent.orchestrator
    scene = orch.get_scene(session_id)
    obj = scene.find_object(object_id)
    if obj is None:
        return JSONResponse(
            status_code=404,
            content={"error": f"Object '{object_id}' not found"},
        )
    orch.push_scene_history(session_id)
    scene.remove_object(object_id)
    return JSONResponse(
        content={
            "session_id": session_id,
            "deleted": True,
            "object_id": object_id,
            "scene": scene.to_dict(),
        }
    )


# ---------------------------------------------------------------------------
# Lights (subset of CRUD — create + delete suffice for the API surface)
# ---------------------------------------------------------------------------


@router.post("/scene/{session_id}/lights")
async def create_light(session_id: str, req: CreateLightRequest) -> JSONResponse:
    """Add a light to the scene."""
    agent = AgentService.get()
    orch = agent.orchestrator
    orch.push_scene_history(session_id)
    scene = orch.get_scene(session_id)
    name = req.name or scene.next_auto_name(f"{req.type}_light")
    light = LightObject(
        name=name,
        type=req.type,
        color=req.color,
        intensity=req.intensity,
        position=list(req.position),
        target=req.target,
        cast_shadow=req.cast_shadow,
    )
    scene.lights.append(light)
    return JSONResponse(
        status_code=201,
        content={
            "session_id": session_id,
            "light": light.to_dict(),
            "scene": scene.to_dict(),
        },
    )


@router.delete("/scene/{session_id}/lights/{light_id}")
async def delete_light(session_id: str, light_id: str) -> JSONResponse:
    """Delete a light from the scene."""
    agent = AgentService.get()
    orch = agent.orchestrator
    scene = orch.get_scene(session_id)
    light = scene.find_light(light_id)
    if light is None:
        return JSONResponse(
            status_code=404,
            content={"error": f"Light '{light_id}' not found"},
        )
    orch.push_scene_history(session_id)
    scene.remove_light(light_id)
    return JSONResponse(
        content={
            "session_id": session_id,
            "deleted": True,
            "light_id": light_id,
            "scene": scene.to_dict(),
        }
    )


# ---------------------------------------------------------------------------
# Undo / Redo (backend snapshot stack)
# ---------------------------------------------------------------------------


@router.post("/scene/{session_id}/undo")
async def undo_scene(session_id: str) -> JSONResponse:
    """Undo the last mutating API operation (restores the previous snapshot)."""
    agent = AgentService.get()
    result = agent.orchestrator.undo_scene(session_id)
    return JSONResponse(content={"session_id": session_id, **result})


@router.post("/scene/{session_id}/redo")
async def redo_scene(session_id: str) -> JSONResponse:
    """Redo the most recently undone API operation."""
    agent = AgentService.get()
    result = agent.orchestrator.redo_scene(session_id)
    return JSONResponse(content={"session_id": session_id, **result})


@router.get("/scene/{session_id}/history")
async def scene_history_status(session_id: str) -> JSONResponse:
    """Return the undo/redo stack depths for the session."""
    agent = AgentService.get()
    status = agent.orchestrator.history_status(session_id)
    return JSONResponse(content={"session_id": session_id, **status})


@router.get("/scene/diff")
async def scene_diff(
    session_id: str = "default",
    frm: str = "prev",
    to: str = "current",
) -> JSONResponse:
    """Compute a structural diff between two scene snapshots.

    Query params:
      - ``session_id``: target session
      - ``from`` (aliased as ``frm`` to avoid the Python keyword): snapshot
        label — one of ``prev`` (most recent undo entry), ``current``
        (live scene), or ``redo`` (most recent redo entry).
      - ``to``: snapshot label, same vocabulary as ``from``.

    Returns ``added`` / ``removed`` / ``changed`` lists for objects and
    lights, plus per-snapshot object counts and the set of changed
    scene-level fields (background/fog/grid/etc.). When either snapshot
    is unavailable (e.g. empty undo stack), ``available`` is False.
    """
    agent = AgentService.get()
    diff = agent.orchestrator.scene_diff(session_id, from_label=frm, to_label=to)
    return JSONResponse(content={"session_id": session_id, **diff})


# ---------------------------------------------------------------------------
# Selection + viewport (editor-state endpoints; return editor deltas)
# ---------------------------------------------------------------------------


@router.post("/scene/{session_id}/select")
async def set_selection(session_id: str, req: SelectRequest) -> JSONResponse:
    """Set the editor selection.

    The selection state lives on the frontend; this endpoint returns an
    ``editor_select`` delta that the frontend dispatches to its local store.
    """
    return JSONResponse(
        content={
            "session_id": session_id,
            "delta": {
                "action": "editor_select",
                "payload": {"targets": req.targets, "clear": req.clear},
            },
            "targets": req.targets,
        }
    )


@router.get("/scene/{session_id}/viewport")
async def get_viewport(session_id: str) -> JSONResponse:
    """Return the current viewport camera state.

    The viewport camera is frontend-owned; the backend has no persistent
    copy. This endpoint returns the default camera so API clients can
    bootstrap a viewport. The frontend overrides this once it has user state.
    """
    return JSONResponse(
        content={
            "session_id": session_id,
            "viewport": {"position": [5.0, 4.0, 7.0], "target": [0.0, 0.5, 0.0]},
        }
    )


@router.put("/scene/{session_id}/viewport")
async def set_viewport(session_id: str, req: ViewportCamera) -> JSONResponse:
    """Set the viewport camera.

    Returns an ``editor_viewport_camera`` delta the frontend dispatches to
    its local store (driving the R3F camera + OrbitControls target).
    """
    return JSONResponse(
        content={
            "session_id": session_id,
            "delta": {
                "action": "editor_viewport_camera",
                "payload": {
                    "position": list(req.position),
                    "target": list(req.target),
                    "smooth": req.smooth,
                },
            },
        }
    )


# ---------------------------------------------------------------------------
# Named scene snapshots — lightweight version control inside session state
# ---------------------------------------------------------------------------


class SnapshotCreateRequest(BaseModel):
    name: Optional[str] = Field(None, description="Snapshot name (auto-generated if omitted)")
    description: Optional[str] = Field("", description="Optional note describing this snapshot")


class SnapshotRestoreRequest(BaseModel):
    name: str = Field(..., description="Name of the snapshot to restore")


class SnapshotDiffRequest(BaseModel):
    a: str = Field(..., description="Baseline snapshot name")
    b: str = Field(..., description="Comparison snapshot name")
    deep: bool = Field(False, description="If true, include per-field material/transform diffs")


@router.post("/scene/{session_id}/snapshots")
async def create_snapshot(session_id: str, req: SnapshotCreateRequest) -> JSONResponse:
    """Capture a named scene snapshot via the snapshot_scene tool."""
    agent = AgentService.get()
    orch = agent.orchestrator
    scene = orch.get_scene(session_id)
    tool = orch.registry.get("snapshot_scene")
    if tool is None:
        return JSONResponse(status_code=500, content={"error": "snapshot_scene tool not registered"})
    result = await tool.execute(scene, {"name": req.name or "", "description": req.description or ""})
    if not result.success:
        return JSONResponse(status_code=400, content={"error": result.message})
    return JSONResponse(content={
        "session_id": session_id,
        "success": True,
        **result.data,
    })


@router.get("/scene/{session_id}/snapshots")
async def list_snapshots(session_id: str) -> JSONResponse:
    """List all named snapshots stored for this session."""
    agent = AgentService.get()
    orch = agent.orchestrator
    scene = orch.get_scene(session_id)
    tool = orch.registry.get("list_snapshots")
    if tool is None:
        return JSONResponse(status_code=500, content={"error": "list_snapshots tool not registered"})
    result = await tool.execute(scene, {})
    return JSONResponse(content={"session_id": session_id, **result.data})


@router.post("/scene/{session_id}/snapshots/restore")
async def restore_snapshot(session_id: str, req: SnapshotRestoreRequest) -> JSONResponse:
    """Restore the scene to a previously captured named snapshot."""
    agent = AgentService.get()
    orch = agent.orchestrator
    scene = orch.get_scene(session_id)
    tool = orch.registry.get("restore_snapshot")
    if tool is None:
        return JSONResponse(status_code=500, content={"error": "restore_snapshot tool not registered"})
    orch.push_scene_history(session_id)
    result = await tool.execute(scene, {"name": req.name})
    if not result.success:
        return JSONResponse(status_code=400, content={"error": result.message})
    return JSONResponse(content={
        "session_id": session_id,
        "success": True,
        "scene": scene.to_dict(),
        **result.data,
    })


@router.post("/scene/{session_id}/snapshots/diff")
async def diff_snapshots(session_id: str, req: SnapshotDiffRequest) -> JSONResponse:
    """Summarize the structural difference between two named snapshots."""
    agent = AgentService.get()
    orch = agent.orchestrator
    scene = orch.get_scene(session_id)
    tool = orch.registry.get("snapshot_diff")
    if tool is None:
        return JSONResponse(status_code=500, content={"error": "snapshot_diff tool not registered"})
    result = await tool.execute(scene, {"a": req.a, "b": req.b, "deep": req.deep})
    if not result.success:
        return JSONResponse(status_code=400, content={"error": result.message})
    return JSONResponse(content={"session_id": session_id, **result.data})


@router.delete("/scene/{session_id}/snapshots/{name}")
async def delete_snapshot(session_id: str, name: str) -> JSONResponse:
    """Delete a named snapshot."""
    agent = AgentService.get()
    orch = agent.orchestrator
    scene = orch.get_scene(session_id)
    tool = orch.registry.get("delete_snapshot")
    if tool is None:
        return JSONResponse(status_code=500, content={"error": "delete_snapshot tool not registered"})
    result = await tool.execute(scene, {"name": name})
    if not result.success:
        return JSONResponse(status_code=400, content={"error": result.message})
    return JSONResponse(content={"session_id": session_id, "success": True, **result.data})


# ---------------------------------------------------------------------------
# Scene export endpoints — convenience wrappers around the export tools
# ---------------------------------------------------------------------------


class SceneExportRequest(BaseModel):
    """Request body for scene export endpoints."""

    format: str = Field("json", description="Export format: json, html, python, gltf_placeholder")
    include_assets: bool = Field(True, description="Whether to include material assets")


@router.post("/scene/{session_id}/export")
async def export_scene(session_id: str, req: SceneExportRequest) -> JSONResponse:
    """Export the current scene via the export_scene tool.

    The ``export_scene`` tool writes files to the workspace exports directory
    and returns the relative paths; this endpoint wraps that call so the
    frontend can get the same paths through a dedicated REST route without
    going through ``/tools/execute``.
    """
    agent = AgentService.get()
    orch = agent.orchestrator
    scene = orch.get_scene(session_id)
    tool = orch.registry.get("export_scene")
    if tool is None:
        return JSONResponse(status_code=500, content={"error": "export_scene tool not registered"})
    fmt = req.format.lower()
    # export_scene expects {format, ...} args matching the tool schema
    result = await tool.execute(scene, {
        "format": fmt,
        "include_assets": req.include_assets,
    })
    if not result.success:
        return JSONResponse(status_code=400, content={"error": result.message})
    return JSONResponse(content={
        "session_id": session_id,
        "format": fmt,
        **result.data,
    })


@router.get("/scene/{session_id}/export/inline")
async def export_scene_inline(session_id: str, format: str = "json") -> JSONResponse:
    """Get the scene directly as inline JSON — no disk writes, just the payload.

    Useful for browser-side download buttons (construct a Blob from the
    response) or clipboard copy. ``format`` is currently limited to ``json``;
    richer formats need the disk-writing export_scene tool.
    """
    agent = AgentService.get()
    scene = agent.orchestrator.get_scene(session_id)
    fmt = format.lower()
    if fmt == "json":
        payload = scene.to_dict()
        filename = f"trigen_scene_{session_id}.json"
    else:
        return JSONResponse(
            status_code=400,
            content={"error": f"Unsupported inline format '{format}'. Use 'json' or POST /export for other formats."},
        )
    return JSONResponse(content={
        "session_id": session_id,
        "format": fmt,
        "filename": filename,
        "object_count": len(scene.objects),
        "light_count": len(scene.lights),
        "payload": payload,
    })


# ---------------------------------------------------------------------------
# Scene-wide statistics and summary endpoints (editor dashboards)
# ---------------------------------------------------------------------------


@router.get("/scene/{session_id}/summary")
async def scene_summary(session_id: str) -> JSONResponse:
    """Aggregated session summary: counts, composition, and post-processing state.

    Combines the outputs of ``scene_statistics`` and ``list_snapshots`` so the
    editor's header/dashboard widget can populate in a single round-trip.
    """
    agent = AgentService.get()
    orch = agent.orchestrator
    scene = orch.get_scene(session_id)

    def _safe_exec(tool_name: str, args: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        t = orch.registry.get(tool_name)
        if t is None:
            return None
        try:
            r = t.execute(scene, args)
            if hasattr(r, "__await__"):
                import asyncio
                r = asyncio.get_event_loop().run_until_complete(r)
            return getattr(r, "data", None) if getattr(r, "success", False) else None
        except Exception:
            logger.exception("scene_summary: %s failed", tool_name)
            return None

    stats = _safe_exec("scene_statistics", {}) or {}
    snaps = _safe_exec("list_snapshots", {}) or {}
    # Prune huge scene snapshots from the response if present.
    snap_meta = snaps.get("snapshots", snaps) if isinstance(snaps, dict) else snaps
    if isinstance(snap_meta, dict):
        snap_meta = {k: {kk: vv for kk, vv in v.items() if kk != "scene"} for k, v in snap_meta.items()}

    return JSONResponse(content={
        "session_id": session_id,
        "counts": {
            "objects": len(scene.objects),
            "lights": len(scene.lights),
            "cameras": len(scene.cameras),
            "groups": len(scene.groups),
            "layers": len(getattr(scene, "layers", {}) or {}),
            "snapshots": len(getattr(scene, "snapshots", {}) or {}),
        },
        "scene": {
            "background": scene.background,
            "fog": scene.fog,
            "ambient_intensity": getattr(scene, "ambient_intensity", 0.3),
            "grid_visible": getattr(scene, "grid_visible", True),
            "grid_size": getattr(scene, "grid_size", 40.0),
            "post_processing_keys": sorted(list((getattr(scene, "post_processing", {}) or {}).keys())),
        },
        "statistics": stats,
        "snapshots": snap_meta,
    })


# ---------------------------------------------------------------------------
# Scene context, quick-create, and proactive suggestions — REST wrappers
# around the orchestrator's scene-awareness helpers so the frontend can
# poll scene state and create objects from natural language without going
# through the streaming chat flow.
# ---------------------------------------------------------------------------


@router.get("/scene/{session_id}/context")
async def get_scene_context(session_id: str) -> JSONResponse:
    """Return the structured scene context analysis for the session.

    Calls the orchestrator's ``_build_scene_context`` helper and returns
    the compact scene-state snapshot (object/light/camera counts, dominant
    colors, geometry diversity, complexity score, missing elements, and a
    suggested next focus). Read-only — never mutates the scene.
    """
    agent = AgentService.get()
    orch = agent.orchestrator
    scene = orch.get_scene(session_id)
    try:
        context = orch._build_scene_context(scene)
    except Exception as e:
        logger.exception("scene context analysis failed for session %s", session_id)
        return JSONResponse(
            status_code=500,
            content={"error": str(e), "session_id": session_id},
        )
    return JSONResponse(content={
        "session_id": session_id,
        "context": context,
    })


class QuickCreateRequest(BaseModel):
    """Request body for the quick-create endpoint.

    Accepts a natural language description (e.g. "a red cube at [2, 0, 0]
    and a blue sphere") which is parsed by the offline intent parser into
    tool-call intents and executed immediately against the session scene.
    """

    message: str = Field(..., description="Natural language description of what to create")


@router.post("/scene/{session_id}/quick-create")
async def quick_create(session_id: str, req: QuickCreateRequest) -> JSONResponse:
    """Create objects from a natural language description without streaming.

    A REST wrapper around the offline intent parsing flow: parses the
    message into structured tool-call intents via ``parse_message``,
    executes each intent's tool against the session scene, and returns
    the per-intent results plus the updated scene snapshot. No streaming
    events are emitted — this is the synchronous counterpart to the
    chat WebSocket for callers that just want the final state.
    """
    from trigen.intent_parser import parse_message

    agent = AgentService.get()
    orch = agent.orchestrator
    scene = orch.get_scene(session_id)

    scene_dict = scene.to_dict()
    scene_objects = scene_dict.get("objects", []) or []
    scene_lights = scene_dict.get("lights", []) or []

    try:
        intents, _ = parse_message(req.message, scene_objects, scene_lights)
    except Exception as e:
        logger.exception("quick-create intent parsing failed for session %s", session_id)
        return JSONResponse(
            status_code=500,
            content={"error": str(e), "session_id": session_id, "results": []},
        )

    if not intents:
        return JSONResponse(
            status_code=200,
            content={
                "session_id": session_id,
                "message": req.message,
                "results": [],
                "executed": 0,
                "scene": scene.to_dict(),
                "note": "No intents matched the provided description.",
            },
        )

    # Snapshot before mutation so the quick-create changes are undo-able.
    orch.push_scene_history(session_id)

    results: List[Dict[str, Any]] = []
    succeeded = 0
    failed = 0
    for idx, intent in enumerate(intents):
        tool = orch.registry.get(intent.tool_name)
        if tool is None:
            failed += 1
            results.append({
                "index": idx,
                "tool": intent.tool_name,
                "description": intent.description,
                "success": False,
                "message": f"Tool '{intent.tool_name}' not found",
                "arguments": intent.arguments,
                "data": None,
            })
            continue
        try:
            result = await tool.execute(scene, intent.arguments)
        except Exception as e:
            logger.exception("quick-create step %d (%s) failed", idx, intent.tool_name)
            failed += 1
            results.append({
                "index": idx,
                "tool": intent.tool_name,
                "description": intent.description,
                "success": False,
                "message": f"Execution error: {e}",
                "arguments": intent.arguments,
                "data": None,
            })
            continue
        if result.success:
            succeeded += 1
        else:
            failed += 1
        results.append({
            "index": idx,
            "tool": intent.tool_name,
            "description": intent.description,
            "success": result.success,
            "message": result.message,
            "arguments": intent.arguments,
            "data": result.data,
        })

    # Persist the live scene (best-effort) so quick-create edits survive restarts.
    try:
        from trigen.scene_autosave import autosave_scene
        autosave_scene(session_id, scene)
    except Exception:
        logger.debug("autosave skipped during quick-create for session %s", session_id)

    return JSONResponse(
        status_code=201 if succeeded else 200,
        content={
            "session_id": session_id,
            "message": req.message,
            "results": results,
            "executed": len(results),
            "succeeded": succeeded,
            "failed": failed,
            "scene": scene.to_dict(),
        },
    )


@router.get("/scene/{session_id}/suggestions")
async def get_scene_suggestions(session_id: str) -> JSONResponse:
    """Return proactive suggestions based on the current scene state.

    Uses the orchestrator's ``_proactive_suggest`` helper, feeding the
    current scene context as both the before and after snapshot (with no
    executed intents) so the suggestions reflect what the scene still
    needs right now — e.g. add motion to a static composition, apply a
    harmonious palette, or self-evaluate a complex scene. Read-only.
    """
    agent = AgentService.get()
    orch = agent.orchestrator
    scene = orch.get_scene(session_id)
    try:
        context = orch._build_scene_context(scene)
        suggestions = orch._proactive_suggest(scene, context, context, [])
    except Exception as e:
        logger.exception("scene suggestions failed for session %s", session_id)
        return JSONResponse(
            status_code=500,
            content={"error": str(e), "session_id": session_id, "suggestions": []},
        )
    return JSONResponse(content={
        "session_id": session_id,
        "suggestions": suggestions,
        "count": len(suggestions),
        "context": context,
    })


# ---------------------------------------------------------------------------
# Scene template catalog — curated starting points the user can load via
# the command palette or the PresetsGallery sidebar. Each template ships
# with a title, tags, and a scene-dict payload so GET templates returns a
# gallery-friendly listing while POST /templates/{id}/apply clones the
# payload into the live session scene (merging or replacing).
# ---------------------------------------------------------------------------


SCENE_TEMPLATES: List[Dict[str, Any]] = [
    {
        "id": "product_showcase",
        "title": "Product Showcase",
        "description": "Studio three-point lighting + pedestal, ideal for placing a single hero object.",
        "tags": ["studio", "lighting", "product"],
        "payload": {
            "background": "#11131a",
            "objects": [
                {
                    "name": "Pedestal",
                    "geometry": {"type": "cylinder", "params": {"radiusTop": 0.9, "radiusBottom": 1.1, "height": 0.3, "radialSegments": 48}},
                    "material": {"color": "#e8e9ee", "metalness": 0.05, "roughness": 0.25},
                    "transform": {"position": [0.0, -0.15, 0.0], "rotation": [0, 0, 0], "scale": [1, 1, 1]},
                },
            ],
            "lights": [
                {"name": "Key", "type": "directional", "intensity": 1.4, "position": [4, 6, 3], "color": "#fff6e6", "cast_shadow": True},
                {"name": "Fill", "type": "directional", "intensity": 0.6, "position": [-5, 3, -2], "color": "#e8f0ff"},
                {"name": "Ambient", "type": "ambient", "intensity": 0.4, "position": [0, 0, 0]},
            ],
            "post_processing": {
                "tone_mapping": {"mode": "aces", "exposure": 1.1},
                "bloom": {"enabled": True, "intensity": 0.5, "threshold": 0.8, "radius": 0.5},
                "vignette": {"enabled": True, "intensity": 0.25, "smoothness": 0.6},
            },
        },
    },
    {
        "id": "isometric_room",
        "title": "Isometric Diorama",
        "description": "Low-angle orthographic room with a floor plane and soft shadows.",
        "tags": ["interior", "diorama", "orthographic"],
        "payload": {
            "background": "#efe8ff",
            "objects": [
                {
                    "name": "Floor",
                    "geometry": {"type": "box", "params": {"width": 10, "height": 0.1, "depth": 10}},
                    "material": {"color": "#f7d9ec", "metalness": 0.0, "roughness": 0.7},
                    "transform": {"position": [0, -0.05, 0], "rotation": [0, 0, 0], "scale": [1, 1, 1]},
                },
                {
                    "name": "BackWall",
                    "geometry": {"type": "box", "params": {"width": 10, "height": 6, "depth": 0.1}},
                    "material": {"color": "#d8ccff", "metalness": 0.0, "roughness": 0.9},
                    "transform": {"position": [0, 2.95, -5], "rotation": [0, 0, 0], "scale": [1, 1, 1]},
                },
            ],
            "lights": [
                {"name": "Sun", "type": "directional", "intensity": 1.2, "position": [5, 8, 4], "color": "#ffe8c2", "cast_shadow": True},
                {"name": "Ambient", "type": "ambient", "intensity": 0.55, "position": [0, 0, 0]},
            ],
        },
    },
    {
        "id": "galaxy_viewport",
        "title": "Galaxy Viewport",
        "description": "Deep-space backdrop + neon bloom preset for sci-fi compositions.",
        "tags": ["sci-fi", "space", "neon"],
        "payload": {
            "background": "#05060c",
            "post_processing": {
                "tone_mapping": {"mode": "aces", "exposure": 1.2},
                "bloom": {"enabled": True, "intensity": 1.5, "threshold": 0.5, "radius": 0.9},
                "chromatic_aberration": {"enabled": True, "offset": 0.004},
                "film_grain": {"enabled": True, "intensity": 0.1, "size": 1.1},
            },
            "lights": [
                {"name": "Rim", "type": "directional", "intensity": 0.9, "position": [-3, 4, -6], "color": "#88aaff"},
                {"name": "Ambient", "type": "ambient", "intensity": 0.2, "position": [0, 0, 0], "color": "#3344aa"},
            ],
        },
    },
    {
        "id": "forest_floor",
        "title": "Forest Floor",
        "description": "Earthy terrain plane, warm ambient, and soft fog for nature scenes.",
        "tags": ["nature", "outdoor", "fog"],
        "payload": {
            "background": "#eaf4dc",
            "fog": {"color": "#d8e8cc", "near": 12, "far": 45},
            "objects": [
                {
                    "name": "Ground",
                    "geometry": {"type": "plane", "params": {"width": 40, "height": 40, "widthSegments": 12, "heightSegments": 12}},
                    "material": {"color": "#96c377", "metalness": 0.0, "roughness": 0.95},
                    "transform": {"position": [0, 0, 0], "rotation": [-1.5708, 0, 0], "scale": [1, 1, 1]},
                },
            ],
            "lights": [
                {"name": "Sun", "type": "directional", "intensity": 1.1, "position": [6, 9, 4], "color": "#fff0cc", "cast_shadow": True},
                {"name": "Ambient", "type": "hemisphere", "intensity": 0.6, "position": [0, 0, 0], "color": "#aaddff"},
            ],
        },
    },
    {
        "id": "rainbow_nav",
        "title": "Rainbow Playground",
        "description": "Rounded pastel backdrop with rainbow gradient postfx.",
        "tags": ["playful", "rainbow", "pastel"],
        "payload": {
            "background": "#fff6fb",
            "post_processing": {
                "color_grading": {"saturation": 1.1, "contrast": 1.02, "temperature": 0.03, "tint": 0.0},
                "bloom": {"enabled": True, "intensity": 0.6, "threshold": 0.78, "radius": 0.6},
            },
            "theme": {"name": "rainbow"},
            "lights": [
                {"name": "Key", "type": "directional", "intensity": 1.3, "position": [3, 6, 4], "color": "#ffffff"},
                {"name": "Ambient", "type": "ambient", "intensity": 0.65, "position": [0, 0, 0]},
            ],
        },
    },
]


@router.get("/scene-templates")
async def list_scene_templates(tag: Optional[str] = None) -> JSONResponse:
    """Return the curated scene template gallery.

    When ``tag`` is provided only templates whose tag list contains the
    (case-insensitive) tag are returned. Each entry returns the template
    id, title, description, tags, and a summary preview — the full scene
    payload is intentionally omitted from the listing to keep responses
    small. Call ``GET /scene-templates/{id}`` to retrieve the payload.
    """
    items = []
    for tpl in SCENE_TEMPLATES:
        tags = list(tpl.get("tags", []))
        if tag and tag.lower() not in [tg.lower() for tg in tags]:
            continue
        payload = tpl.get("payload", {})
        items.append(
            {
                "id": tpl["id"],
                "title": tpl["title"],
                "description": tpl.get("description", ""),
                "tags": tags,
                "object_count": len(payload.get("objects", [])),
                "light_count": len(payload.get("lights", [])),
                "has_postfx": bool(payload.get("post_processing")),
                "theme_name": (payload.get("theme") or {}).get("name", "warm"),
            }
        )
    return JSONResponse(
        content={
            "templates": items,
            "count": len(items),
            "tag_filter": tag,
            "all_tags": sorted({t for tpl in SCENE_TEMPLATES for t in tpl.get("tags", [])}),
        }
    )


@router.get("/scene-templates/{template_id}")
async def get_scene_template(template_id: str) -> JSONResponse:
    """Return a single template's full payload for editor-side preview/apply."""
    tpl = next((t for t in SCENE_TEMPLATES if t["id"] == template_id), None)
    if not tpl:
        return JSONResponse(status_code=404, content={"error": f"Template '{template_id}' not found"})
    return JSONResponse(content=tpl)


class ApplyTemplateRequest(BaseModel):
    session_id: str = Field(description="Target session id")
    mode: str = Field(default="replace", description="How to merge the template: 'replace' clears the scene first, 'merge' layers the template on top.")


@router.post("/scene-templates/{template_id}/apply")
async def apply_scene_template(template_id: str, req: ApplyTemplateRequest) -> JSONResponse:
    """Apply a curated template into the target session's live scene."""
    tpl = next((t for t in SCENE_TEMPLATES if t["id"] == template_id), None)
    if not tpl:
        return JSONResponse(status_code=404, content={"error": f"Template '{template_id}' not found"})
    agent = AgentService.get()
    orch = agent.orchestrator
    session_id = req.session_id
    orch.push_scene_history(session_id)
    scene = orch.get_scene(session_id)
    payload = dict(tpl.get("payload", {}))

    if req.mode == "replace":
        scene.objects.clear()
        scene.lights.clear()
        scene.cameras.clear()
        scene.groups.clear()
    if "background" in payload:
        scene.background = str(payload["background"])
    if "fog" in payload:
        scene.fog = dict(payload["fog"]) if payload.get("fog") else None
    if "post_processing" in payload:
        scene.post_processing = dict(payload.get("post_processing") or {})
    if "theme" in payload:
        scene.theme = dict(payload.get("theme") or {})
    # Materialize payload objects/lights as real SceneObject / LightObject
    # instances so the viewport can render them directly.
    for obj_dict in payload.get("objects", []) or []:
        try:
            scene_obj = SceneObject.from_dict(obj_dict)
            scene.objects.append(scene_obj)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("skipping malformed template object: %s", exc)
    for light_dict in payload.get("lights", []) or []:
        try:
            scene.lights.append(LightObject(**light_dict))
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("skipping malformed template light: %s", exc)
    return JSONResponse(
        content={
            "ok": True,
            "template": template_id,
            "mode": req.mode,
            "object_count": len(scene.objects),
            "light_count": len(scene.lights),
            "theme": scene.theme,
        }
    )


# ---------------------------------------------------------------------------
# Workspace bootstrap — returns everything a fresh client needs on first load
# (tool count, default scene, render presets, themes, layouts, semantic
# memory digest, session restoration status). A single HTTP round-trip
# replaces the legacy cascade of individual endpoint calls.
# ---------------------------------------------------------------------------


@router.get("/workspace/bootstrap")
async def workspace_bootstrap(session_id: str = "default") -> JSONResponse:
    """Bootstrap a client session in a single round-trip.

    Returns the current scene, the live tool count + category summary,
    render presets, themes, workspace layouts, scene templates, and the
    top 5 semantic memory recalls for the current session id so the UI
    can personalize its onboarding hints immediately after load.
    """
    from trigen.tools.workspace_ux_tools import RENDER_PRESETS, THEMES, WORKSPACE_LAYOUTS
    from trigen.semantic_memory import get_store

    agent = AgentService.get()
    orch = agent.orchestrator
    scene = orch.get_scene(session_id)
    tool_list = orch.registry.categories()
    total_tools = sum(len(v) for v in tool_list.values())

    memory_items = []
    try:
        store = get_store(workspace_dir=orch.config.workspace_dir)
        memory_items = store.recall("scene preferences palette design", top_k=5, session_id=session_id)
    except Exception:
        memory_items = []

    return JSONResponse(
        content={
            "session_id": session_id,
            "scene": scene.to_dict(),
            "tool_summary": {
                "total_tools": total_tools,
                "categories": sorted(
                    [{"name": cat, "count": len(items)} for cat, items in tool_list.items()],
                    key=lambda c: c["name"],
                ),
            },
            "render_presets": [
                {"name": name, "description": spec.get("description", "")}
                for name, spec in RENDER_PRESETS.items()
            ],
            "themes": [
                {
                    "name": name,
                    "description": spec.get("description", ""),
                    "accent": (spec.get("palette") or {}).get("accent", ""),
                }
                for name, spec in THEMES.items()
            ],
            "workspace_layouts": [
                {"name": name, "description": spec.get("description", "")}
                for name, spec in WORKSPACE_LAYOUTS.items()
            ],
            "templates_preview": [
                {"id": t["id"], "title": t["title"], "tags": t.get("tags", [])}
                for t in SCENE_TEMPLATES
            ],
            "memory_digest": memory_items,
        }
    )

