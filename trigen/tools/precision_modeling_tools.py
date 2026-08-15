"""Precision modeling tools — edge crease, bevel weight, vertex groups.

Three Agent-callable tools that expose the granular mesh-control surface a
modeler expects from a full 3D editor. They store their data on the
``SceneObject`` as structured tags so the viewport renderer can read them
at draw time without changing the parametric geometry.

  * ``set_edge_crease`` — mark edges (or all edges of an object) with a
    sharpness weight in [0, 1]. The viewport subdivision renderer uses
    crease weights to keep selected edges crisp while the rest of the
    surface smooths. Higher weight = sharper edge.
  * ``set_bevel_weight`` — tag edges with a bevel weight in [0, 1] that
    controls how wide a bevel modifier spreads along that edge. Pairs
    with the existing ``bevel_modifier`` surface op so the agent can
    bevel only the marked edges instead of the whole mesh.
  * ``manage_vertex_group`` — create / rename / delete named vertex
    groups on an object and assign a list of vertex indices to a group.
    Vertex groups are the substrate for selective deformation, weight
    painting, and rigging: a bend modifier can target only "left_arm"
    vertices, for example.

The stored payloads are plain dicts so they serialize with the scene and
survive a server restart.
"""

from __future__ import annotations

import re
import uuid
from typing import Any, Dict, List, Optional

from trigen.scene import Scene
from trigen.tools.base import SceneDelta, ToolBase, ToolResult


# Tag prefix conventions used to persist precision-modeling data on the
# SceneObject.tags list. Using tags keeps the dataclass surface small and
# lets the renderer scan a single list at draw time.
_TAG_EDGE_CREASE = "edge_crease:"
_TAG_BEVEL_WEIGHT = "bevel_weight:"
_TAG_VERTEX_GROUP = "vgroup:"


def _parse_tag_payload(tags: List[str], prefix: str) -> Dict[str, Any]:
    """Return the parsed JSON-ish payload stored under ``prefix`` or {}."""
    for tag in tags:
        if tag.startswith(prefix):
            raw = tag[len(prefix):]
            # Payloads are stored as "key=val;key=val" so they stay
            # shell-safe and human-readable in the outliner.
            out: Dict[str, Any] = {}
            for chunk in raw.split(";"):
                if "=" not in chunk:
                    continue
                k, v = chunk.split("=", 1)
                k = k.strip()
                v = v.strip()
                if not k:
                    continue
                # Try int, then float, then bool, else string.
                if re.fullmatch(r"-?\d+", v):
                    out[k] = int(v)
                elif re.fullmatch(r"-?\d+\.\d+", v):
                    out[k] = float(v)
                elif v.lower() in ("true", "false"):
                    out[k] = v.lower() == "true"
                else:
                    out[k] = v
            return out
    return {}


def _strip_prefix(tags: List[str], prefix: str) -> List[str]:
    """Return a copy of ``tags`` with every entry starting with ``prefix`` removed."""
    return [t for t in tags if not t.startswith(prefix)]


def _encode_payload(prefix: str, payload: Dict[str, Any]) -> str:
    """Encode a payload dict as a single tag string under ``prefix``."""
    chunks = []
    for k, v in payload.items():
        if isinstance(v, bool):
            chunks.append(f"{k}={'true' if v else 'false'}")
        elif isinstance(v, float):
            chunks.append(f"{k}={v:.4f}")
        else:
            chunks.append(f"{k}={v}")
    return prefix + ";".join(chunks)


# ---------------------------------------------------------------------------
# set_edge_crease
# ---------------------------------------------------------------------------

_EDGE_CREASE_PARAMS = {
    "type": "object",
    "properties": {
        "target": {
            "type": "string",
            "description": "Object id or name to mark edges on.",
        },
        "weight": {
            "type": "number",
            "minimum": 0.0,
            "maximum": 1.0,
            "description": (
                "Crease sharpness in [0, 1]. 0 = smooth (no crease), "
                "1 = infinitely sharp (edge stays fully crisp under "
                "subdivision). 0.5 is a typical architectural edge."
            ),
        },
        "edges": {
            "type": "array",
            "items": {"type": "integer"},
            "description": (
                "Optional list of edge indices to crease. When omitted, "
                "the crease weight applies to every edge of the mesh "
                "(whole-object crease)."
            ),
        },
        "clear": {
            "type": "boolean",
            "description": "If true, remove the edge-crease tag entirely.",
        },
    },
    "required": ["target"],
}


class SetEdgeCreaseTool(ToolBase):
    """Mark edges with a subdivision-surface sharpness weight."""

    name = "set_edge_crease"
    description = (
        "Set an edge-crease weight on an object so the viewport subdivision "
        "renderer keeps selected edges crisp while the rest of the surface "
        "smooths. Pass a list of edge indices to crease specific edges, or "
        "omit it to crease the whole object. Set clear=true to remove the "
        "crease tag."
    )

    def schema(self) -> Dict[str, Any]:
        return _EDGE_CREASE_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        target = str(arguments.get("target", "") or "")
        obj = scene.find_object(target)
        if obj is None:
            return ToolResult(success=False, message=f"set_edge_crease: object '{target}' not found")

        if bool(arguments.get("clear", False)):
            obj.tags = _strip_prefix(obj.tags, _TAG_EDGE_CREASE)
            return ToolResult(
                success=True,
                message=f"Cleared edge crease on '{obj.name}'.",
                deltas=[SceneDelta(action="update", target_id=obj.id, payload={"tags": list(obj.tags)})],
                data={"cleared": True},
            )

        try:
            weight = float(arguments.get("weight", 0.5))
        except (TypeError, ValueError):
            return ToolResult(success=False, message="weight must be a number in [0, 1]")
        weight = max(0.0, min(1.0, weight))

        edges_raw = arguments.get("edges")
        if edges_raw is None:
            edges_desc = "all"
            payload: Dict[str, Any] = {"weight": weight, "edges": "all"}
        else:
            if not isinstance(edges_raw, list):
                return ToolResult(success=False, message="edges must be an array of integers")
            edges = [int(e) for e in edges_raw if isinstance(e, (int, float)) and e >= 0]
            if not edges:
                return ToolResult(success=False, message="edges must contain at least one non-negative index")
            edges_desc = ",".join(str(e) for e in edges[:8])
            if len(edges) > 8:
                edges_desc += f",...(+{len(edges) - 8})"
            payload = {"weight": weight, "edges": ",".join(str(e) for e in edges), "count": len(edges)}

        obj.tags = _strip_prefix(obj.tags, _TAG_EDGE_CREASE)
        obj.tags.append(_encode_payload(_TAG_EDGE_CREASE, payload))

        sharpness = "sharp" if weight >= 0.9 else ("crisp" if weight >= 0.5 else "soft")
        return ToolResult(
            success=True,
            message=f"Set edge crease {sharpness} ({weight:.2f}) on '{obj.name}' [{edges_desc}].",
            deltas=[SceneDelta(action="update", target_id=obj.id, payload={"tags": list(obj.tags)})],
            data={"weight": weight, "edges": edges_desc, "object_id": obj.id},
        )


# ---------------------------------------------------------------------------
# set_bevel_weight
# ---------------------------------------------------------------------------

_BEVEL_WEIGHT_PARAMS = {
    "type": "object",
    "properties": {
        "target": {
            "type": "string",
            "description": "Object id or name to mark edges on.",
        },
        "weight": {
            "type": "number",
            "minimum": 0.0,
            "maximum": 1.0,
            "description": (
                "Bevel weight in [0, 1]. Controls how wide the bevel "
                "modifier spreads along the marked edges. 1 = full bevel "
                "width, 0 = no bevel on that edge."
            ),
        },
        "edges": {
            "type": "array",
            "items": {"type": "integer"},
            "description": (
                "Optional list of edge indices to weight. When omitted, "
                "applies to every edge of the mesh."
            ),
        },
        "clear": {
            "type": "boolean",
            "description": "If true, remove the bevel-weight tag entirely.",
        },
    },
    "required": ["target"],
}


class SetBevelWeightTool(ToolBase):
    """Tag edges with a bevel weight for selective bevel modifiers."""

    name = "set_bevel_weight"
    description = (
        "Set a per-edge bevel weight on an object so the bevel modifier "
        "only spreads along marked edges. Pairs with the existing "
        "bevel_modifier surface op for selective edge rounding. Set "
        "clear=true to remove the bevel-weight tag."
    )

    def schema(self) -> Dict[str, Any]:
        return _BEVEL_WEIGHT_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        target = str(arguments.get("target", "") or "")
        obj = scene.find_object(target)
        if obj is None:
            return ToolResult(success=False, message=f"set_bevel_weight: object '{target}' not found")

        if bool(arguments.get("clear", False)):
            obj.tags = _strip_prefix(obj.tags, _TAG_BEVEL_WEIGHT)
            return ToolResult(
                success=True,
                message=f"Cleared bevel weight on '{obj.name}'.",
                deltas=[SceneDelta(action="update", target_id=obj.id, payload={"tags": list(obj.tags)})],
                data={"cleared": True},
            )

        try:
            weight = float(arguments.get("weight", 1.0))
        except (TypeError, ValueError):
            return ToolResult(success=False, message="weight must be a number in [0, 1]")
        weight = max(0.0, min(1.0, weight))

        edges_raw = arguments.get("edges")
        if edges_raw is None:
            edges_desc = "all"
            payload: Dict[str, Any] = {"weight": weight, "edges": "all"}
        else:
            if not isinstance(edges_raw, list):
                return ToolResult(success=False, message="edges must be an array of integers")
            edges = [int(e) for e in edges_raw if isinstance(e, (int, float)) and e >= 0]
            if not edges:
                return ToolResult(success=False, message="edges must contain at least one non-negative index")
            edges_desc = ",".join(str(e) for e in edges[:8])
            if len(edges) > 8:
                edges_desc += f",...(+{len(edges) - 8})"
            payload = {"weight": weight, "edges": ",".join(str(e) for e in edges), "count": len(edges)}

        obj.tags = _strip_prefix(obj.tags, _TAG_BEVEL_WEIGHT)
        obj.tags.append(_encode_payload(_TAG_BEVEL_WEIGHT, payload))

        return ToolResult(
            success=True,
            message=f"Set bevel weight {weight:.2f} on '{obj.name}' [{edges_desc}].",
            deltas=[SceneDelta(action="update", target_id=obj.id, payload={"tags": list(obj.tags)})],
            data={"weight": weight, "edges": edges_desc, "object_id": obj.id},
        )


# ---------------------------------------------------------------------------
# manage_vertex_group
# ---------------------------------------------------------------------------

_VGROUP_PARAMS = {
    "type": "object",
    "properties": {
        "target": {
            "type": "string",
            "description": "Object id or name to manage vertex groups on.",
        },
        "action": {
            "type": "string",
            "enum": ["create", "rename", "delete", "assign", "remove_vertices", "list"],
            "description": (
                "create: make a new named group. "
                "rename: change a group's name (requires old_name). "
                "delete: remove a group by name. "
                "assign: add vertex indices to a group (creates the group if missing). "
                "remove_vertices: drop vertex indices from a group. "
                "list: return every group and its vertex count."
            ),
        },
        "name": {
            "type": "string",
            "description": "Group name for create / delete / assign / remove_vertices.",
        },
        "old_name": {
            "type": "string",
            "description": "Current name for the rename action.",
        },
        "new_name": {
            "type": "string",
            "description": "New name for the rename action.",
        },
        "vertices": {
            "type": "array",
            "items": {"type": "integer"},
            "description": "Vertex indices to assign or remove.",
        },
        "weight": {
            "type": "number",
            "minimum": 0.0,
            "maximum": 1.0,
            "description": "Optional per-vertex weight for the assign action (default 1.0).",
        },
    },
    "required": ["target", "action"],
}


def _parse_vgroups(tags: List[str]) -> Dict[str, Dict[str, Any]]:
    """Reconstruct the {name: {vertices, weight}} dict from vgroup tags.

    Each vgroup tag encodes "name=Foo;vertices=0,1,2;weight=1.0;count=3".
    """
    groups: Dict[str, Dict[str, Any]] = {}
    for tag in tags:
        if not tag.startswith(_TAG_VERTEX_GROUP):
            continue
        raw = tag[len(_TAG_VERTEX_GROUP):]
        fields: Dict[str, str] = {}
        for chunk in raw.split(";"):
            if "=" not in chunk:
                continue
            k, v = chunk.split("=", 1)
            fields[k.strip()] = v.strip()
        name = fields.get("name", "")
        if not name:
            continue
        verts_str = fields.get("vertices", "")
        vertices = [int(v) for v in verts_str.split(",") if v.strip().lstrip("-").isdigit()] if verts_str else []
        try:
            weight = float(fields.get("weight", "1.0"))
        except ValueError:
            weight = 1.0
        groups[name] = {"vertices": vertices, "weight": weight, "count": len(vertices)}
    return groups


def _encode_vgroup_tag(name: str, vertices: List[int], weight: float) -> str:
    verts_str = ",".join(str(v) for v in vertices) if vertices else ""
    return _encode_payload(_TAG_VERTEX_GROUP, {
        "name": name,
        "vertices": verts_str,
        "weight": weight,
        "count": len(vertices),
    })


class ManageVertexGroupTool(ToolBase):
    """Create / rename / delete / assign vertex groups on an object."""

    name = "manage_vertex_group"
    description = (
        "Manage named vertex groups on an object for selective deformation, "
        "weight painting, and rigging. Actions: create a group, rename it, "
        "delete it, assign vertex indices (optionally with a weight), "
        "remove vertices, or list every group with its vertex count. "
        "Groups persist with the scene and are read by deformation modifiers."
    )

    def schema(self) -> Dict[str, Any]:
        return _VGROUP_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        target = str(arguments.get("target", "") or "")
        obj = scene.find_object(target)
        if obj is None:
            return ToolResult(success=False, message=f"manage_vertex_group: object '{target}' not found")

        action = str(arguments.get("action", "")).lower()
        if action not in ("create", "rename", "delete", "assign", "remove_vertices", "list"):
            return ToolResult(success=False, message=f"Unknown action: {action}")

        groups = _parse_vgroups(obj.tags)

        if action == "list":
            summary = [
                {"name": n, "vertex_count": g["count"], "weight": g["weight"]}
                for n, g in sorted(groups.items())
            ]
            return ToolResult(
                success=True,
                message=f"'{obj.name}' has {len(summary)} vertex group(s).",
                data={"groups": summary, "count": len(summary)},
            )

        name = str(arguments.get("name", "") or "").strip()
        if action != "rename" and not name:
            return ToolResult(success=False, message="name is required for this action")

        if action == "create":
            if name in groups:
                return ToolResult(success=False, message=f"Vertex group '{name}' already exists on '{obj.name}'")
            obj.tags.append(_encode_vgroup_tag(name, [], 1.0))
            return ToolResult(
                success=True,
                message=f"Created vertex group '{name}' on '{obj.name}'.",
                deltas=[SceneDelta(action="update", target_id=obj.id, payload={"tags": list(obj.tags)})],
                data={"name": name, "vertices": []},
            )

        if action == "rename":
            old_name = str(arguments.get("old_name", "") or "").strip()
            new_name = str(arguments.get("new_name", "") or "").strip()
            if not old_name or not new_name:
                return ToolResult(success=False, message="rename requires old_name and new_name")
            if old_name not in groups:
                return ToolResult(success=False, message=f"Vertex group '{old_name}' not found on '{obj.name}'")
            if new_name in groups:
                return ToolResult(success=False, message=f"Vertex group '{new_name}' already exists on '{obj.name}'")
            g = groups[old_name]
            obj.tags = [t for t in obj.tags if not (t.startswith(_TAG_VERTEX_GROUP) and f"name={old_name};" in t + ";")]
            obj.tags.append(_encode_vgroup_tag(new_name, g["vertices"], g["weight"]))
            return ToolResult(
                success=True,
                message=f"Renamed vertex group '{old_name}' -> '{new_name}' on '{obj.name}'.",
                deltas=[SceneDelta(action="update", target_id=obj.id, payload={"tags": list(obj.tags)})],
                data={"old_name": old_name, "new_name": new_name},
            )

        if action == "delete":
            if name not in groups:
                return ToolResult(success=False, message=f"Vertex group '{name}' not found on '{obj.name}'")
            obj.tags = [t for t in obj.tags if not (t.startswith(_TAG_VERTEX_GROUP) and f"name={name};" in t + ";")]
            return ToolResult(
                success=True,
                message=f"Deleted vertex group '{name}' from '{obj.name}'.",
                deltas=[SceneDelta(action="update", target_id=obj.id, payload={"tags": list(obj.tags)})],
                data={"deleted": name},
            )

        # assign / remove_vertices — both need a vertices list
        verts_raw = arguments.get("vertices")
        if not isinstance(verts_raw, list) or not verts_raw:
            return ToolResult(success=False, message="vertices must be a non-empty array of integers")
        verts = [int(v) for v in verts_raw if isinstance(v, (int, float)) and v >= 0]
        if not verts:
            return ToolResult(success=False, message="vertices must contain at least one non-negative index")

        try:
            weight = float(arguments.get("weight", 1.0))
        except (TypeError, ValueError):
            weight = 1.0
        weight = max(0.0, min(1.0, weight))

        if action == "assign":
            existing = groups.get(name, {"vertices": [], "weight": weight})
            merged = sorted(set(existing["vertices"]) | set(verts))
            obj.tags = [t for t in obj.tags if not (t.startswith(_TAG_VERTEX_GROUP) and f"name={name};" in t + ";")]
            obj.tags.append(_encode_vgroup_tag(name, merged, weight))
            added = len(set(verts) - set(existing["vertices"]))
            return ToolResult(
                success=True,
                message=f"Assigned {added} vertex(es) to group '{name}' on '{obj.name}' (total {len(merged)}).",
                deltas=[SceneDelta(action="update", target_id=obj.id, payload={"tags": list(obj.tags)})],
                data={"name": name, "vertices": merged, "count": len(merged), "added": added, "weight": weight},
            )

        # remove_vertices
        if name not in groups:
            return ToolResult(success=False, message=f"Vertex group '{name}' not found on '{obj.name}'")
        existing = groups[name]
        remaining = [v for v in existing["vertices"] if v not in set(verts)]
        removed = len(existing["vertices"]) - len(remaining)
        obj.tags = [t for t in obj.tags if not (t.startswith(_TAG_VERTEX_GROUP) and f"name={name};" in t + ";")]
        if remaining:
            obj.tags.append(_encode_vgroup_tag(name, remaining, existing["weight"]))
        return ToolResult(
            success=True,
            message=f"Removed {removed} vertex(es) from group '{name}' on '{obj.name}' ({len(remaining)} remain).",
            deltas=[SceneDelta(action="update", target_id=obj.id, payload={"tags": list(obj.tags)})],
            data={"name": name, "vertices": remaining, "count": len(remaining), "removed": removed},
        )
