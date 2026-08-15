"""Scene snapshot and version management tools.

Named scene snapshots let the agent and user capture specific moments in
a creative session and jump back to them — a lightweight alternative to
persistent disk checkpoints that lives inside the session state itself.
Also exposes the diff between snapshots so the agent can audit what
changed between two revisions.
"""

from __future__ import annotations

import copy
import time
from typing import Any, Dict, List

from trigen.scene import Scene
from trigen.tools.base import SceneDelta, ToolBase, ToolResult


class SnapshotSceneTool(ToolBase):
    """Capture a named snapshot of the current scene."""

    name = "snapshot_scene"
    description = (
        "Capture a named snapshot of the entire scene state (objects, "
        "lights, cameras, groups, materials, environment, post-processing). "
        "Use restore_snapshot to jump back to a previously captured state."
    )
    category = "scene"

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Snapshot label used for restore / list / diff (auto-generated if empty)"},
                "description": {"type": "string", "default": "", "description": "Optional human-readable note on what this snapshot represents"},
            },
        }

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        name = str(arguments.get("name") or "").strip()
        description = str(arguments.get("description", ""))
        if not name:
            ts = int(time.time())
            name = f"snapshot_{ts}"

        if not hasattr(scene, "snapshots") or scene.snapshots is None:
            scene.snapshots = {}
        # Deep-copy the current scene dict so future mutations do not
        # overwrite this captured state.
        captured = copy.deepcopy(scene.to_dict())
        # Strip nested snapshot storage from the snapshot itself (avoid
        # ever-growing recursive payloads):
        captured.pop("snapshots", None)
        scene.snapshots[name] = {
            "timestamp": time.time(),
            "description": description,
            "object_count": len(scene.objects),
            "light_count": len(scene.lights),
            "camera_count": len(scene.cameras),
            "group_count": len(scene.groups),
            "scene": captured,
        }
        payload = {
            "snapshots": {k: {kk: vv for kk, vv in v.items() if kk != "scene"} for k, v in scene.snapshots.items()},
        }
        delta = SceneDelta(action="update", target_id="scene", payload=payload, snapshot={"snapshots": scene.snapshots})
        return ToolResult(
            True,
            f"Captured scene snapshot '{name}' with {len(scene.objects)} object(s).",
            deltas=[delta],
            data={"name": name, "description": description, "counts": payload["snapshots"][name]},
        )


class ListSnapshotsTool(ToolBase):
    """List named snapshots stored in the scene."""

    name = "list_snapshots"
    description = "List all named snapshots currently stored with their metadata (counts, timestamp, description)."
    category = "scene"

    def schema(self) -> Dict[str, Any]:
        return {"type": "object", "properties": {}}

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        snapshots = getattr(scene, "snapshots", {}) or {}
        summary = {}
        for name, s in snapshots.items():
            summary[name] = {
                "timestamp": s.get("timestamp"),
                "description": s.get("description", ""),
                "object_count": s.get("object_count"),
                "light_count": s.get("light_count"),
                "camera_count": s.get("camera_count"),
                "group_count": s.get("group_count"),
            }
        return ToolResult(
            True,
            f"Scene contains {len(summary)} named snapshot(s).",
            deltas=[],
            data={"snapshots": summary, "count": len(summary)},
        )


class RestoreSnapshotTool(ToolBase):
    """Restore the scene back to a previously captured snapshot state."""

    name = "restore_snapshot"
    description = (
        "Replace the current scene state with the contents of a previously "
        "captured named snapshot. Before applying, captures an implicit "
        "'before-restore' snapshot so the user can undo the jump."
    )
    category = "scene"

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "required": ["name"],
            "properties": {
                "name": {"type": "string", "description": "Snapshot label to restore"},
            },
        }

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        name = str(arguments.get("name", ""))
        snapshots = getattr(scene, "snapshots", {}) or {}
        if name not in snapshots:
            available = ", ".join(sorted(snapshots.keys())) or "(none)"
            return ToolResult(False, f"Snapshot '{name}' not found. Available: {available}")
        captured = snapshots[name].get("scene")
        if not captured:
            return ToolResult(False, f"Snapshot '{name}' contains no scene data.")

        # Implicit safety snapshot before restoring
        safety_name = f"before_restore_{name}_{int(time.time())}"
        safety_payload = copy.deepcopy(scene.to_dict())
        safety_payload.pop("snapshots", None)
        scene.snapshots[safety_name] = {
            "timestamp": time.time(),
            "description": f"Auto-captured before restoring '{name}'",
            "object_count": len(scene.objects),
            "light_count": len(scene.lights),
            "camera_count": len(scene.cameras),
            "group_count": len(scene.groups),
            "scene": safety_payload,
        }

        # Restore: rehydrate the scene from the captured dict using the
        # Scene.from_dict round-trip so all dataclass invariants hold.
        restored = Scene.from_dict(captured)
        scene.objects = restored.objects
        scene.lights = restored.lights
        scene.cameras = restored.cameras
        scene.groups = restored.groups
        scene.background = restored.background
        scene.environment = restored.environment
        scene.fog = restored.fog
        scene.ambient_intensity = restored.ambient_intensity
        scene.ambient_color = restored.ambient_color
        scene.global_gravity = restored.global_gravity
        scene.grid_visible = restored.grid_visible
        scene.grid_size = restored.grid_size
        scene.annotations = restored.annotations
        scene.storyboard = restored.storyboard
        scene.layers = restored.layers
        scene.node_graph = restored.node_graph
        scene.transitions = restored.transitions
        scene.active_transition = restored.active_transition
        scene.post_processing = restored.post_processing
        # Preserve the snapshots dict itself — don't wipe history.

        # Emit a full-scene snapshot delta so the frontend rebuilds.
        full_snapshot = scene.to_dict()
        delta = SceneDelta(
            action="update",
            target_id="scene",
            payload={"restored": name, **full_snapshot},
            snapshot=full_snapshot,
        )
        return ToolResult(
            True,
            f"Restored snapshot '{name}'. Auto-preserved previous state as '{safety_name}'.",
            deltas=[delta],
            data={"restored": name, "safety_snapshot": safety_name},
        )


class SnapshotDiffTool(ToolBase):
    """Compare two snapshots and summarize what objects were added/removed/changed."""

    name = "snapshot_diff"
    description = (
        "Compare two named snapshots. Returns a JSON-friendly summary of "
        "objects added, removed, and changed (by object id / name), plus "
        "scene-level metadata changes (environment, counts)."
    )
    category = "scene"

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "required": ["a", "b"],
            "properties": {
                "a": {"type": "string", "description": "Baseline snapshot name (earlier)"},
                "b": {"type": "string", "description": "Comparison snapshot name (later)"},
                "deep": {"type": "boolean", "default": False, "description": "If true, diff per-object materials and transforms instead of just presence"},
            },
        }

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        a_name = str(arguments.get("a", ""))
        b_name = str(arguments.get("b", ""))
        deep = bool(arguments.get("deep", False))
        snapshots = getattr(scene, "snapshots", {}) or {}
        if a_name not in snapshots:
            return ToolResult(False, f"Baseline snapshot '{a_name}' not found.")
        if b_name not in snapshots:
            return ToolResult(False, f"Comparison snapshot '{b_name}' not found.")
        a = snapshots[a_name]["scene"]
        b = snapshots[b_name]["scene"]

        def _index_by_id(d: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
            return {o["id"]: o for o in d.get("objects", [])}

        a_obj = _index_by_id(a)
        b_obj = _index_by_id(b)
        added = [b_obj[i]["name"] for i in set(b_obj) - set(a_obj)]
        removed = [a_obj[i]["name"] for i in set(a_obj) - set(b_obj)]
        common = set(a_obj) & set(b_obj)
        changed = []
        if deep:
            for i in common:
                oa = a_obj[i]
                ob = b_obj[i]
                diffs = []
                for key in ("name", "geometry", "material", "transform", "visible"):
                    if oa.get(key) != ob.get(key):
                        diffs.append(key)
                if diffs:
                    changed.append({"name": ob.get("name", i), "fields": diffs})
        else:
            changed_names = []
            for i in common:
                if a_obj[i].get("name") != b_obj[i].get("name"):
                    changed_names.append(f"{a_obj[i].get('name','?')} -> {b_obj[i].get('name','?')}")
            changed = changed_names

        meta = {
            "a": {
                "objects": len(a_obj),
                "lights": len(a.get("lights", [])),
                "background": a.get("background"),
                "timestamp": snapshots[a_name].get("timestamp"),
            },
            "b": {
                "objects": len(b_obj),
                "lights": len(b.get("lights", [])),
                "background": b.get("background"),
                "timestamp": snapshots[b_name].get("timestamp"),
            },
        }
        data = {
            "a": a_name,
            "b": b_name,
            "meta": meta,
            "added": added,
            "removed": removed,
            "changed": changed,
            "added_count": len(added),
            "removed_count": len(removed),
            "changed_count": len(changed),
        }
        return ToolResult(
            True,
            f"Diff {a_name} vs {b_name}: +{len(added)} / -{len(removed)} / ~{len(changed)}",
            deltas=[],
            data=data,
        )


class DeleteSnapshotTool(ToolBase):
    """Delete a named snapshot to save memory."""

    name = "delete_snapshot"
    description = "Delete a previously captured snapshot by name."
    category = "scene"

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "required": ["name"],
            "properties": {
                "name": {"type": "string", "description": "Snapshot label to delete"},
            },
        }

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        name = str(arguments.get("name", ""))
        snapshots = getattr(scene, "snapshots", {}) or {}
        if name not in snapshots:
            return ToolResult(False, f"Snapshot '{name}' not found.")
        del snapshots[name]
        summary = {k: {kk: vv for kk, vv in v.items() if kk != "scene"} for k, v in snapshots.items()}
        delta = SceneDelta(action="update", target_id="scene", payload={"snapshots": summary})
        return ToolResult(True, f"Deleted snapshot '{name}'.", deltas=[delta], data={"deleted": name, "remaining": list(snapshots.keys())})
