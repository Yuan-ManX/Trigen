"""Cinematic storyboard — a sequence of camera shots that plays as a
scripted camera tour.

A storyboard is a scene-level, ordered collection of shots. Each shot is a
camera pose (position + look-at target + fov) plus a duration and easing
curve. When played, the viewport camera smoothly interpolates between
consecutive shots, producing a cinematic dolly/pan sequence that narrates
the scene for the viewer.

This differs from a single camera animation (orbit / flythrough) — those
describe one camera move — whereas a storyboard is a *sequence* of discrete,
independently editable shots. It also differs from the object timeline,
which animates objects rather than the camera.

The storyboard lives on the scene as a plain dict (``Scene.storyboard``) so
it persists with the scene, round-trips through checkpoints, and flows to
the frontend through the ordinary scene-update channel. The functions in
this module are the single source of truth for the dict shape and validation.
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Dict, List, Optional

# Valid easing curves accepted on a shot.
EASINGS = ("linear", "easeIn", "easeOut", "easeInOut")

DEFAULT_EASING = "easeInOut"


def new_shot(
    name: str = "Shot",
    position: Optional[List[float]] = None,
    target: Optional[List[float]] = None,
    fov: Optional[float] = None,
    duration: Optional[float] = None,
    easing: Optional[str] = None,
    description: str = "",
) -> Dict[str, Any]:
    """Build a normalized shot dict with sensible defaults."""
    return {
        "id": f"shot_{uuid.uuid4().hex[:8]}",
        "name": name or "Shot",
        "position": _vec3(position, [5.0, 4.0, 7.0]),
        "target": _vec3(target, [0.0, 0.5, 0.0]),
        "fov": 45.0 if fov is None else float(fov),
        "duration": 3.0 if duration is None else max(0.1, float(duration)),
        "easing": easing if easing in EASINGS else DEFAULT_EASING,
        "description": description or "",
    }


def _vec3(value: Any, default: List[float]) -> List[float]:
    """Coerce a value into a length-3 float list, falling back to default."""
    if isinstance(value, (list, tuple)) and len(value) == 3:
        try:
            return [float(value[0]), float(value[1]), float(value[2])]
        except (TypeError, ValueError):
            pass
    return list(default)


def empty_storyboard(title: str = "Untitled scene") -> Dict[str, Any]:
    """A fresh storyboard with no shots yet."""
    return {
        "title": title,
        "shots": [],
        "loop": True,
        "playing": False,
        "speed": 1.0,
        "index": 0,
        "created_at": time.time(),
    }


def new_storyboard(title: str, shots: List[Dict[str, Any]], loop: bool = True) -> Dict[str, Any]:
    """Build a storyboard from raw shot dictionaries, normalizing each shot."""
    sb = empty_storyboard(title)
    sb["loop"] = bool(loop)
    sb["shots"] = [normalize_shot(s) for s in shots]
    return sb


def normalize_shot(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Coerce an arbitrary shot dict into the canonical shape."""
    return new_shot(
        name=str(raw.get("name", "Shot")),
        position=_vec3(raw.get("position"), [5.0, 4.0, 7.0]),
        target=_vec3(raw.get("target"), [0.0, 0.5, 0.0]),
        fov=_opt_float(raw.get("fov"), 45.0),
        duration=_opt_float(raw.get("duration"), 3.0),
        easing=str(raw.get("easing", DEFAULT_EASING)) if str(raw.get("easing", DEFAULT_EASING)) in EASINGS else DEFAULT_EASING,
        description=str(raw.get("description", "")),
    )


def _opt_float(value: Any, default: float) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def total_duration(storyboard: Dict[str, Any]) -> float:
    """Sum of all shot durations in a storyboard."""
    if not storyboard:
        return 0.0
    return sum(float(s.get("duration", 0.0)) for s in storyboard.get("shots", []))


def update_shot_fields(shot: Dict[str, Any], arguments: Dict[str, Any]) -> List[str]:
    """Apply allowed field updates to a shot, returning the changed field names."""
    changed: List[str] = []
    if "name" in arguments and arguments["name"]:
        shot["name"] = str(arguments["name"])
        changed.append("name")
    if "position" in arguments:
        shot["position"] = _vec3(arguments["position"], shot.get("position", [5.0, 4.0, 7.0]))
        changed.append("position")
    if "target" in arguments:
        shot["target"] = _vec3(arguments["target"], shot.get("target", [0.0, 0.5, 0.0]))
        changed.append("target")
    if "fov" in arguments:
        shot["fov"] = max(1.0, min(170.0, _opt_float(arguments["fov"], 45.0)))
        changed.append("fov")
    if "duration" in arguments:
        shot["duration"] = max(0.1, _opt_float(arguments["duration"], 3.0))
        changed.append("duration")
    if "easing" in arguments:
        easing = str(arguments["easing"])
        if easing in EASINGS:
            shot["easing"] = easing
            changed.append("easing")
    if "description" in arguments:
        shot["description"] = str(arguments["description"])
        changed.append("description")
    return changed