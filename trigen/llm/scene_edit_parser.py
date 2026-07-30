"""Inline scene-edit parser.

Extracts ``<scene_edit>...</scene_edit>`` blocks from LLM output text and
converts the JSON payload inside each block into a list of structured
``SceneEditOp`` objects. The orchestrator dispatches each op to the
matching registered tool (create_object / transform_object / apply_material
/ delete_object / add_light / set_background / set_fog), so inline edits
reuse the exact same code path as explicit tool calls and emit the same
``SCENE_UPDATE`` deltas the frontend already renders.

Supported op shapes (each block may contain one object or a JSON array):

    {"op": "create", "geometry": "box", "name": "Cube", "color": "#e84a4a",
     "position": [0, 0, 0], "metalness": 0.2}
    {"op": "transform", "target": "Cube", "position": [2, 0, 0],
     "rotation": [0, 1.57, 0], "scale": [1, 1, 1]}
    {"op": "material", "target": "Cube", "color": "#ff0000", "metalness": 0.8}
    {"op": "material_preset", "target": "Cube", "preset": "metal"}
    {"op": "delete", "target": "Cube"}
    {"op": "add_light", "type": "point", "color": "#ffffff", "intensity": 1.0,
     "position": [3, 5, 3]}
    {"op": "background", "color": "#0a1428"}
    {"op": "fog", "color": "#0a0a0f", "near": 10, "far": 50}
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# Matches <scene_edit>...</scene_edit> (non-greedy, dotall so JSON may
# span multiple lines). Tolerates extra whitespace around the tags.
_BLOCK_RE = re.compile(r"<scene_edit>\s*(.*?)\s*</scene_edit>", re.DOTALL | re.IGNORECASE)

# Map an inline ``op`` value to the registered tool name that handles it.
# Kept in the parser module (not the orchestrator) so callers can inspect
# the mapping without importing the orchestrator.
OP_TO_TOOL: Dict[str, str] = {
    "create": "create_object",
    "transform": "transform_object",
    "material": "apply_material",
    "material_preset": "apply_material_preset",
    "delete": "delete_object",
    "add_light": "add_light",
    "background": "set_background",
    "fog": "set_fog",
}


@dataclass
class SceneEditOp:
    """A single inline scene-edit instruction parsed from LLM output."""

    op: str
    tool: str
    arguments: Dict[str, Any] = field(default_factory=dict)
    raw: Dict[str, Any] = field(default_factory=dict)


def parse_scene_edit(text: str) -> List[SceneEditOp]:
    """Extract and parse all ``<scene_edit>`` blocks from ``text``.

    Malformed JSON or unknown op values are skipped silently (the caller
    still gets any well-formed ops from the same text). Returns an empty
    list when the text contains no blocks.
    """
    ops: List[SceneEditOp] = []
    for match in _BLOCK_RE.finditer(text):
        payload = match.group(1).strip()
        if not payload:
            continue
        for raw_obj in _iter_json_objects(payload):
            op = _coerce_op(raw_obj)
            if op is not None:
                ops.append(op)
    return ops


def _iter_json_objects(payload: str) -> List[Dict[str, Any]]:
    """Parse ``payload`` as one JSON object or a JSON array of objects."""
    try:
        decoded = json.loads(payload)
    except json.JSONDecodeError:
        return []
    if isinstance(decoded, dict):
        return [decoded]
    if isinstance(decoded, list):
        return [item for item in decoded if isinstance(item, dict)]
    return []


def _coerce_op(raw: Dict[str, Any]) -> Optional[SceneEditOp]:
    """Convert a raw JSON dict into a ``SceneEditOp`` with tool arguments.

    Normalizes the field names from the inline shorthand (``geometry`` /
    ``target`` / ``preset``) into the argument shapes the registered tools
    already accept.
    """
    op_name = str(raw.get("op", "")).strip().lower()
    tool = OP_TO_TOOL.get(op_name)
    if not tool:
        return None

    args: Dict[str, Any] = {}
    if op_name == "create":
        if "geometry" in raw:
            args["geometry_type"] = raw["geometry"]
        elif "geometry_type" in raw:
            args["geometry_type"] = raw["geometry_type"]
        if "name" in raw:
            args["name"] = raw["name"]
        if "params" in raw and isinstance(raw["params"], dict):
            args["params"] = raw["params"]
        if "position" in raw:
            args["position"] = raw["position"]
        if "rotation" in raw:
            args["rotation"] = raw["rotation"]
        if "scale" in raw:
            args["scale"] = raw["scale"]
        if "color" in raw:
            args["color"] = raw["color"]
        if "metalness" in raw:
            args["metalness"] = raw["metalness"]
        if "roughness" in raw:
            args["roughness"] = raw["roughness"]
        if "opacity" in raw:
            args["opacity"] = raw["opacity"]
        if "emissive" in raw:
            args["emissive"] = raw["emissive"]
        if "emissive_intensity" in raw:
            args["emissive_intensity"] = raw["emissive_intensity"]
        if "wireframe" in raw:
            args["wireframe"] = raw["wireframe"]
    elif op_name == "transform":
        if "target" in raw:
            args["target"] = raw["target"]
        if "position" in raw:
            args["position"] = raw["position"]
        if "rotation" in raw:
            args["rotation"] = raw["rotation"]
        if "scale" in raw:
            args["scale"] = raw["scale"]
    elif op_name == "material":
        if "target" in raw:
            args["target"] = raw["target"]
        for k in ("color", "metalness", "roughness", "opacity", "emissive",
                  "emissive_intensity", "wireframe"):
            if k in raw:
                args[k] = raw[k]
    elif op_name == "material_preset":
        if "target" in raw:
            args["target"] = raw["target"]
        if "preset" in raw:
            args["preset"] = raw["preset"]
    elif op_name == "delete":
        if "target" in raw:
            args["target"] = raw["target"]
    elif op_name == "add_light":
        if "type" in raw:
            args["type"] = raw["type"]
        if "name" in raw:
            args["name"] = raw["name"]
        if "color" in raw:
            args["color"] = raw["color"]
        if "intensity" in raw:
            args["intensity"] = raw["intensity"]
        if "position" in raw:
            args["position"] = raw["position"]
    elif op_name == "background":
        if "color" in raw:
            args["color"] = raw["color"]
    elif op_name == "fog":
        if "color" in raw:
            args["color"] = raw["color"]
        if "near" in raw:
            args["near"] = raw["near"]
        if "far" in raw:
            args["far"] = raw["far"]

    return SceneEditOp(op=op_name, tool=tool, arguments=args, raw=raw)
