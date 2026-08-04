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
