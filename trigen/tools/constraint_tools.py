"""Constraint-authoring tools — let the Agent declare and solve spatial
relationships between scene objects.

Four tools exposed to the Agent:
  * ``add_constraint``     — register a new constraint
  * ``list_constraints``   — read all constraints with current pass/fail
  * ``clear_constraints``  — drop every constraint
  * ``solve_constraints``  — run the greedy solver, mutate transforms,
                              emit ``update`` deltas for the frontend

The constraint model and store live in ``trigen.constraints``; these
tool wrappers just adapt it to the ToolBase contract. Distinct from
``critique_scene`` (post-hoc problem finder) and ``auto_fix_scene``
(heal known problems) — constraints let the user declaratively pin
relationships they want enforced and then re-derive transforms from
them in one call.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from trigen.scene import Scene
from trigen.tools.base import SceneDelta, ToolBase, ToolResult
from trigen.constraints import (
    CONSTRAINT_KINDS,
    Constraint,
    add_constraint as _store_add,
    clear_constraints as _store_clear,
    evaluate,
    get_constraints,
    solve as _solve,
)


class AddConstraintTool(ToolBase):
    """Register a single spatial constraint on the current scene."""

    name = "add_constraint"
    description = (
        "Add an explicit spatial constraint between two scene objects (or "
        "between an object and a world point). Kinds: 'above' (subject's base "
        "sits above anchor's top, with optional offset gap), 'below' (subject's "
        "top below anchor's base), 'above_floor' (subject rests on y=0 or a "
        "given target_point.y), 'faces' (subject's +Z axis points at the "
        "anchor), 'centered' (subject's center matches anchor's center on the "
        "given axis, or all axes), 'min_distance' (centers kept >= distance "
        "apart), 'aligned' (centers aligned on the given axis within "
        "tolerance). Use this to pin down relationships like 'lamp above "
        "table', 'chair faces desk', 'sphere centered on pedestal'. Does not "
        "move objects — call solve_constraints to enforce."
    )
    category = "constraints"

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "kind": {
                    "type": "string",
                    "enum": list(CONSTRAINT_KINDS),
                    "description": "Constraint kind.",
                },
                "subject": {
                    "type": "string",
                    "description": "The object being constrained (id or name).",
                },
                "anchor": {
                    "type": "string",
                    "description": "Reference object (id or name) for relational kinds.",
                },
                "target_point": {
                    "type": "array",
                    "items": {"type": "number"},
                    "description": "Optional absolute world-space reference [x, y, z].",
                },
                "axis": {
                    "type": "string",
                    "enum": ["x", "y", "z"],
                    "description": "Axis for 'centered' / 'aligned' (omit = all axes).",
                },
                "distance": {
                    "type": "number",
                    "description": "Required separation for 'min_distance', or gap for above/below when no offset.",
                },
                "offset": {
                    "type": "number",
                    "description": "Explicit gap for above/below/above_floor.",
                },
                "tolerance": {
                    "type": "number",
                    "description": "Slack for centered/aligned/above_floor (default 0.05).",
                },
                "description": {
                    "type": "string",
                    "description": "Optional human-readable note.",
                },
            },
            "required": ["kind", "subject"],
        }

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        kind = str(arguments.get("kind", "")).strip()
        if kind not in CONSTRAINT_KINDS:
            return ToolResult(
                success=False,
                message=f"Unknown constraint kind '{kind}'. Expected one of {list(CONSTRAINT_KINDS)}.",
            )
        subject = str(arguments.get("subject", "")).strip()
        if not subject:
            return ToolResult(success=False, message="'subject' is required")
        anchor = arguments.get("anchor")
        anchor = str(anchor).strip() if anchor else None
        target_point = arguments.get("target_point")
        if target_point is not None:
            if not isinstance(target_point, list) or len(target_point) != 3:
                return ToolResult(
                    success=False,
                    message="target_point must be a 3-vector [x, y, z]",
                )
        axis = arguments.get("axis")
        if axis is not None:
            axis = str(axis).strip().lower()
        distance = arguments.get("distance")
        if distance is not None:
            try:
                distance = float(distance)
            except (TypeError, ValueError):
                distance = None
        offset = arguments.get("offset")
        if offset is not None:
            try:
                offset = float(offset)
            except (TypeError, ValueError):
                offset = None
        try:
            tol = float(arguments.get("tolerance", 0.05))
        except (TypeError, ValueError):
            tol = 0.05
        description = str(arguments.get("description", "") or "")

        try:
            c = Constraint(
                kind=kind,
                subject=subject,
                anchor=anchor,
                target_point=list(target_point) if target_point else None,
                axis=axis,
                distance=distance,
                offset=offset,
                tolerance=tol,
                description=description,
            )
        except ValueError as exc:
            return ToolResult(success=False, message=f"Invalid constraint: {exc}")

        # Validate that subject/anchor resolve against the current scene so
        # the user gets immediate feedback for a typo. The constraint is
        # still stored even if resolution fails (the object might be added
        # later), but we surface a warning.
        sub_obj = scene.find_object(subject)
        anchor_missing: Optional[str] = None
        if anchor and scene.find_object(anchor) is None:
            anchor_missing = anchor
        _store_add(scene, c)

        msg = (
            f"Constraint '{c.id}' added: {kind}('{subject}'"
            + (f", '{anchor}'" if anchor else "")
            + (f", axis={axis}" if axis else "")
            + (f", distance={distance}" if distance is not None else "")
            + (f", offset={offset}" if offset is not None else "")
            + ")"
        )
        if sub_obj is None:
            msg += f" — WARNING: subject '{subject}' not in scene yet"
        if anchor_missing:
            msg += f" — WARNING: anchor '{anchor_missing}' not in scene yet"
        return ToolResult(
            success=True,
            message=msg,
            data={"constraint": c.to_dict()},
        )


class ListConstraintsTool(ToolBase):
    """List every constraint attached to the scene with current pass/fail."""

    name = "list_constraints"
    description = (
        "List all spatial constraints currently registered on the scene, each "
        "with its current pass/fail evaluation against the live scene state. "
        "Use this to review the constraint set before solving, or to verify "
        "what constraints are in force. Read-only; never mutates the scene."
    )
    category = "constraints"

    def schema(self) -> Dict[str, Any]:
        return {"type": "object", "properties": {}, "required": []}

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        cs = get_constraints(scene)
        if not cs:
            return ToolResult(
                success=True,
                message="No constraints registered on this scene.",
                data={"constraints": [], "count": 0, "passed": 0, "failed": 0},
            )
        rows: List[Dict[str, Any]] = []
        passed = 0
        for c in cs:
            ok, msg = evaluate(c, scene)
            if ok:
                passed += 1
            rows.append({
                **c.to_dict(),
                "passed": ok,
                "message": msg,
            })
        summary = (
            f"{len(cs)} constraint(s) registered; {passed} passing, "
            f"{len(cs) - passed} failing."
        )
        return ToolResult(
            success=True,
            message=summary,
            data={
                "constraints": rows,
                "count": len(cs),
                "passed": passed,
                "failed": len(cs) - passed,
            },
        )


class ClearConstraintsTool(ToolBase):
    """Remove every constraint from the scene."""

    name = "clear_constraints"
    description = (
        "Remove every spatial constraint currently registered on the scene. "
        "Use this to start a fresh constraint set after solving. Does not "
        "revert any transforms applied by a previous solve — pair with undo "
        "if you want both."
    )
    category = "constraints"

    def schema(self) -> Dict[str, Any]:
        return {"type": "object", "properties": {}, "required": []}

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        n = _store_clear(scene)
        return ToolResult(
            success=True,
            message=f"Cleared {n} constraint(s) from the scene.",
            data={"cleared": n},
        )


class SolveConstraintsTool(ToolBase):
    """Run the greedy constraint solver and mutate object transforms."""

    name = "solve_constraints"
    description = (
        "Run the iterative constraint solver: for each violated constraint, "
        "adjust the subject's transform.position (and rotation.y for 'faces') "
        "until all constraints pass or a max-pass cap is reached. Emits an "
        "'update' delta for every moved object so the frontend reflects the "
        "new transforms in one shot. Use this after add_constraint to enforce "
        "the declared relationships. Multiple passes let relational chains "
        "(A above B above C) settle."
    )
    category = "constraints"

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "max_passes": {
                    "type": "integer",
                    "description": "Maximum solver iterations (default 5, capped at 20).",
                },
            },
            "required": [],
        }

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        try:
            max_passes = int(arguments.get("max_passes", 5))
        except (TypeError, ValueError):
            max_passes = 5
        max_passes = max(1, min(max_passes, 20))

        cs = get_constraints(scene)
        if not cs:
            return ToolResult(
                success=True,
                message="No constraints to solve.",
                data={"solved": 0, "still_violated": [], "moved": [], "passes": 0},
            )

        report = _solve(scene, cs, max_passes=max_passes)

        # Emit an update delta for each moved object so the frontend can
        # refresh the transform without waiting for the next snapshot. The
        # orchestrator will still send the full scene snapshot afterwards.
        deltas: List[SceneDelta] = []
        for m in report.get("moved", []):
            obj = scene.find_object(m["id"]) or scene.find_object(m.get("name", ""))
            if obj is not None:
                deltas.append(SceneDelta(
                    action="update",
                    target_id=obj.id,
                    payload={"transform": obj.transform.to_dict()},
                ))

        solved = int(report.get("solved", 0))
        total = len(cs)
        still = report.get("still_violated", [])
        moved = report.get("moved", [])
        passes = report.get("passes", 0)
        msg = (
            f"Solved {solved}/{total} constraint(s) in {passes} pass(es); "
            f"{len(moved)} object(s) moved, {len(still)} still violated."
        )
        return ToolResult(
            success=True,
            message=msg,
            deltas=deltas,
            data={
                "solved": solved,
                "total": total,
                "still_violated": still,
                "moved": moved,
                "passes": passes,
            },
        )
