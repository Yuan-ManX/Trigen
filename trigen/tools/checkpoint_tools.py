"""Scene checkpoint tools — persistent, revisioned version history.

Lets the Agent capture the current scene as an immutable, semantically
labeled checkpoint, browse the revision history, and restore any earlier
revision as a lossless scene swap. Because checkpoints are ordered and
immutable (revision 1, 2, 3, …), they form a true timeline of the scene's
evolution — distinct from variants (exploration alternatives) and named
scene slots (quick save/load).

These tools read/write the process-local checkpoint store, which persists
to ``<workspace>/checkpoints.json``. ``restore_checkpoint`` replaces the
live scene in place (the same lossless swap used by load_scene_slot), so
the restored state is immediately reflected in the editor.

1. ``CheckpointSceneTool``  — checkpoint_scene: capture the current scene.
2. ``ListCheckpointsTool``  — list_checkpoints: browse the revision history.
3. ``RestoreCheckpointTool`` — restore_checkpoint: swap the scene to a revision.
4. ``CheckpointDiffTool``    — checkpoint_diff: compare two revisions.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from trigen.checkpoints import (
    SceneCheckpoint,
    build_scene_summary,
    checkpoint_store,
    diff_checkpoint_scenes,
)
from trigen.scene import Scene
from trigen.tools.base import ToolBase, ToolResult


_CHECKPOINT_PARAMS = {
    "type": "object",
    "properties": {
        "description": {
            "type": "string",
            "description": (
                "Optional human-readable label for this checkpoint, e.g. "
                "'Added forest and regrouped pillars'. When omitted, a "
                "semantic summary is auto-generated from the scene."
            ),
        },
    },
    "required": [],
}


_LIST_CHECKPOINTS_PARAMS = {
    "type": "object",
    "properties": {
        "limit": {
            "type": "integer",
            "description": "Optional cap on the number of checkpoints returned (newest-first).",
        },
    },
    "required": [],
}


_RESTORE_PARAMS = {
    "type": "object",
    "properties": {
        "revision": {
            "type": "integer",
            "description": "The checkpoint revision to restore (1-based).",
        },
    },
    "required": ["revision"],
}


_DIFF_PARAMS = {
    "type": "object",
    "properties": {
        "revision_a": {
            "type": "integer",
            "description": "The earlier checkpoint revision.",
        },
        "revision_b": {
            "type": "integer",
            "description": "The later checkpoint revision.",
        },
    },
    "required": ["revision_a", "revision_b"],
}


def _checkpoint_to_public(cp: Any) -> Dict[str, Any]:
    """Strip the heavy scene payload from a checkpoint for list/result payloads."""
    return {
        "revision": cp.revision,
        "description": cp.description,
        "created_at": cp.created_at,
        "created_by": cp.created_by,
        "summary": cp.summary,
    }


class CheckpointSceneTool(ToolBase):
    """Capture the current scene as a new revision."""

    name = "checkpoint_scene"
    description = (
        "Capture the current scene as an immutable, revisioned checkpoint "
        "(revision 1, 2, 3, …). Each checkpoint stores a semantic summary "
        "(geometry counts, material palette, light rig) so the history reads "
        "as a timeline of the scene's evolution. Use this before a risky or "
        "exploratory edit so you can restore an earlier revision later. "
        "Provide a short 'description' of what the scene represents."
    )

    def schema(self) -> Dict[str, Any]:
        return _CHECKPOINT_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        description = str(arguments.get("description", "")).strip()
        try:
            history = checkpoint_store.get()
        except Exception as exc:
            return ToolResult(
                success=False,
                message=f"Checkpoint store unavailable: {exc}",
                deltas=[],
                data={},
            )
        scene_dict = scene.to_dict()
        summary = build_scene_summary(scene_dict)
        revision = history._next_revision
        history.checkpoints.append(
            SceneCheckpoint(
                revision=revision,
                scene_dict=scene_dict,
                description=description,
                summary=summary,
            )
        )
        history._next_revision = revision + 1
        try:
            checkpoint_store.save()
        except Exception as exc:
            return ToolResult(
                success=False,
                message=f"Failed to persist checkpoint: {exc}",
                deltas=[],
                data={},
            )
        return ToolResult(
            success=True,
            message=(
                f"Checkpointed scene as revision {revision}"
                + (f" ({description})" if description else "")
                + f" — {summary['prose']}"
            ),
            deltas=[],
            data={
                "revision": revision,
                "description": description,
                "summary": summary,
                "total_checkpoints": len(checkpoint_store.get().checkpoints),
            },
        )


class ListCheckpointsTool(ToolBase):
    """Browse the checkpoint revision history."""

    name = "list_checkpoints"
    description = (
        "List the scene's checkpoint history (revision 1, 2, 3, …). Returns "
        "each revision's semantic summary, description, and timestamp, "
        "newest-first. Use this to see the scene's evolution timeline and to "
        "pick a revision to restore. Does not mutate the scene."
    )

    def schema(self) -> Dict[str, Any]:
        return _LIST_CHECKPOINTS_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        try:
            history = checkpoint_store.get()
        except Exception as exc:
            return ToolResult(
                success=False,
                message=f"Checkpoint store unavailable: {exc}",
                deltas=[],
                data={},
            )
        cps = sorted(history.checkpoints, key=lambda c: c.revision, reverse=True)
        limit_raw = arguments.get("limit")
        if limit_raw is not None:
            limit = int(limit_raw)
            if limit >= 0:
                cps = cps[:limit] if limit else []
        return ToolResult(
            success=True,
            message=f"Found {len(cps)} checkpoint(s).",
            deltas=[],
            data={
                "checkpoints": [_checkpoint_to_public(c) for c in cps],
                "next_revision": history._next_revision,
                "total": len(history.checkpoints),
            },
        )


class RestoreCheckpointTool(ToolBase):
    """Restore the scene to an earlier revision."""

    name = "restore_checkpoint"
    description = (
        "Restore the live scene to a previously captured checkpoint revision. "
        "The scene is swapped in place (lossless), so the editor immediately "
        "reflects the restored state. Use this to roll back to any earlier "
        "point in the scene's evolution timeline. Checkpoints are immutable, "
        "so restoring does not delete later revisions."
    )

    def schema(self) -> Dict[str, Any]:
        return _RESTORE_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        revision = arguments.get("revision")
        if revision is None:
            return ToolResult(
                success=False,
                message="restore_checkpoint requires a 'revision'.",
                deltas=[],
                data={},
            )
        try:
            history = checkpoint_store.get()
        except Exception as exc:
            return ToolResult(
                success=False,
                message=f"Checkpoint store unavailable: {exc}",
                deltas=[],
                data={},
            )
        target = next((c for c in history.checkpoints if c.revision == int(revision)), None)
        if target is None:
            return ToolResult(
                success=False,
                message=(
                    f"Checkpoint revision {revision} not found. "
                    f"Available: {sorted(c.revision for c in history.checkpoints)}"
                ),
                deltas=[],
                data={},
            )
        # Lossless in-place scene swap: reset then bulk-rebuild from the
        # stored scene dict (same approach as load_scene_slot).
        restored = Scene.from_dict(target.scene_dict)
        scene.__dict__.clear()
        scene.__dict__.update(restored.__dict__)
        return ToolResult(
            success=True,
            message=f"Restored scene to checkpoint revision {revision}.",
            deltas=[],
            data={
                "revision": revision,
                "description": target.description,
                "summary": target.summary,
                "scene": scene.to_dict(),
            },
        )


class CheckpointDiffTool(ToolBase):
    """Compare two checkpoint revisions."""

    name = "checkpoint_diff"
    description = (
        "Compare two checkpoint revisions and report what changed — added, "
        "removed, and modified objects with their ids and names. Use this "
        "to summarize the evolution of the scene between two points in time. "
        "Does not mutate the scene."
    )

    def schema(self) -> Dict[str, Any]:
        return _DIFF_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        rev_a = arguments.get("revision_a")
        rev_b = arguments.get("revision_b")
        if rev_a is None or rev_b is None:
            return ToolResult(
                success=False,
                message="checkpoint_diff requires 'revision_a' and 'revision_b'.",
                deltas=[],
                data={},
            )
        try:
            history = checkpoint_store.get()
        except Exception as exc:
            return ToolResult(
                success=False,
                message=f"Checkpoint store unavailable: {exc}",
                deltas=[],
                data={},
            )
        by_rev = {c.revision: c for c in history.checkpoints}
        ca = by_rev.get(int(rev_a))
        cb = by_rev.get(int(rev_b))
        if ca is None or cb is None:
            missing = [r for r in (rev_a, rev_b) if r not in by_rev]
            return ToolResult(
                success=False,
                message=f"Missing checkpoint revision(s): {missing}",
                deltas=[],
                data={},
            )
        diff = diff_checkpoint_scenes(ca.scene_dict, cb.scene_dict)
        return ToolResult(
            success=True,
            message=(
                f"Rev {rev_a} → Rev {rev_b}: "
                f"+{diff['added_count']} -{diff['removed_count']} ~{diff['changed_count']}"
            ),
            deltas=[],
            data=diff,
        )