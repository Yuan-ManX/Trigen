"""Live-scene autosave — disk persistence of the in-progress scene per session.

Named slots, checkpoints, and variants are explicit, user-driven saves. The
autosave layer instead captures the *live* scene so a server restart does not
silently discard work. It writes one JSON file per session under
``<workspace>/scenes/`` and restores it the next time that session's scene is
first materialized. All writes are best-effort so a persistence failure can
never break the surrounding agent turn.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Optional

logger = logging.getLogger("trigen.scene_autosave")


def _workspace_dir() -> str:
    return os.environ.get(
        "TRIGEN_WORKSPACE",
        os.path.join(os.getcwd(), ".trigen", "workspace"),
    )


def _scene_dir() -> str:
    return os.path.join(_workspace_dir(), "scenes")


def _scene_path(session_id: str) -> str:
    safe = "".join(c for c in session_id if c.isalnum() or c in ("-", "_")) or "default"
    return os.path.join(_scene_dir(), f"{safe}.json")


def autosave_scene(session_id: str, scene: Any) -> None:
    """Best-effort write of the live scene for a session. Never raises."""
    try:
        os.makedirs(_scene_dir(), exist_ok=True)
        with open(_scene_path(session_id), "w", encoding="utf-8") as f:
            json.dump(scene.to_dict(), f, ensure_ascii=False, indent=2)
    except Exception:
        logger.exception("Failed to autosave scene for session %s", session_id)


def load_autosaved_scene(session_id: str) -> Optional[dict]:
    """Return the persisted live-scene dict for a session, or None."""
    path = _scene_path(session_id)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        logger.warning("Failed to read autosaved scene for session %s", session_id)
        return None


def clear_autosave(session_id: str) -> None:
    """Remove the persisted live scene for a session. Never raises."""
    path = _scene_path(session_id)
    if os.path.exists(path):
        try:
            os.remove(path)
        except Exception:
            logger.warning("Failed to clear autosaved scene for session %s", session_id)


def has_autosave(session_id: str) -> bool:
    return os.path.exists(_scene_path(session_id))
