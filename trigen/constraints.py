"""Constraint model + greedy iterative solver.

Lets the Agent author explicit spatial constraints between objects in a
scene (e.g. "object A must sit above object B", "the chair must face the
desk", "the lamp must be centered on the table") and then solve them in
one call. Distinct from the prescriptive ``critique_scene`` engine:
critique finds generic design problems post-hoc, while constraints let
the user declaratively pin down relationships they want enforced. The
solver is a simple greedy iterative position-adjustment pass — not a
full SMT solver — but it covers the common relational cases (above /
below / above_floor / faces / centered / min_distance / aligned).

The constraint store is keyed by ``id(scene)`` so the same Scene object
instance (reused per session by the orchestrator) keeps its constraint
set across calls. The model is dataclass-based so it serializes cleanly
to JSON for the frontend panel.
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Tuple

from trigen.scene import Scene, SceneObject


# ---------------------------------------------------------------------------
# Geometry extent estimation (mirrors scene_critique._estimate_extent but
# kept self-contained so this module has no cross-tool dependency)
# ---------------------------------------------------------------------------

def _sphere_r(params: Dict[str, Any]) -> float:
    return float(params.get("radius", 0.5))


def _box_extent(params: Dict[str, Any]) -> List[float]:
    return [
        float(params.get("width", 1.0)) / 2.0,
        float(params.get("height", 1.0)) / 2.0,
        float(params.get("depth", 1.0)) / 2.0,
    ]


def _cylinder_extent(params: Dict[str, Any]) -> List[float]:
    r = max(float(params.get("radiusTop", 0.5)), float(params.get("radiusBottom", 0.5)))
    return [r, float(params.get("height", 1.0)) / 2.0, r]


def _cone_extent(params: Dict[str, Any]) -> List[float]:
    r = float(params.get("radius", 0.5))
    return [r, float(params.get("height", 1.0)) / 2.0, r]


def _torus_extent(params: Dict[str, Any]) -> List[float]:
    r = float(params.get("radius", 0.5))
    tube = float(params.get("tube", 0.2))
    return [r + tube, tube, r + tube]


def _plane_extent(params: Dict[str, Any]) -> List[float]:
    return [
        float(params.get("width", 1.0)) / 2.0,
        0.0,
        float(params.get("height", 1.0)) / 2.0,
    ]


def _poly_extent(params: Dict[str, Any]) -> List[float]:
    r = _sphere_r(params)
    return [r, r, r]


def _ring_extent(params: Dict[str, Any]) -> List[float]:
    outer = float(params.get("outerRadius", 0.5))
    return [outer, 0.0, outer]


def _capsule_extent(params: Dict[str, Any]) -> List[float]:
    r = float(params.get("radius", 0.25))
    length = float(params.get("length", 1.0))
    return [r, length / 2.0 + r, r]


def _tube_extent(params: Dict[str, Any]) -> List[float]:
    r = float(params.get("radius", 0.25))
    return [r, r, r]


_EXTENT_FN = {
    "box": _box_extent,
    "sphere": lambda p: [_sphere_r(p)] * 3,
    "cylinder": _cylinder_extent,
    "cone": _cone_extent,
    "torus": _torus_extent,
    "torusKnot": _torus_extent,
    "plane": _plane_extent,
    "dodecahedron": _poly_extent,
    "icosahedron": _poly_extent,
    "octahedron": _poly_extent,
    "tetrahedron": _poly_extent,
    "ring": _ring_extent,
    "capsule": _capsule_extent,
    "tube": _tube_extent,
    "lathe": _poly_extent,
    "extrude": _poly_extent,
    "text": lambda p: [1.0, 0.5, 0.1],
    "spline": _tube_extent,
}

_DEFAULT_EXTENT = [0.5, 0.5, 0.5]


def _estimate_extent(geo_type: str, params: Dict[str, Any]) -> List[float]:
    """Return approximate half-extents [x, y, z] for a geometry type."""
    fn = _EXTENT_FN.get(geo_type)
    if fn is None:
        return list(_DEFAULT_EXTENT)
    try:
        return [abs(float(v)) for v in fn(params or {})]
    except (TypeError, ValueError):
        return list(_DEFAULT_EXTENT)


def _bbox(obj: SceneObject) -> Tuple[List[float], List[float]]:
    """Compute the world-space AABB of an object as ``(min, max)`` 3-vectors.

    Uses the geometry half-extents scaled by the object transform, centered
    on its position. Falls back to a unit cube (1x1x1) for unknown types.
    """
    half = _estimate_extent(obj.geometry.type, obj.geometry.params or {})
    scale = list(obj.transform.scale or [1.0, 1.0, 1.0])
    pos = list(obj.transform.position or [0.0, 0.0, 0.0])
    hx = half[0] * abs(scale[0])
    hy = half[1] * abs(scale[1])
    hz = half[2] * abs(scale[2])
    return (
        [pos[0] - hx, pos[1] - hy, pos[2] - hz],
        [pos[0] + hx, pos[1] + hy, pos[2] + hz],
    )


def _bbox_center(obj: SceneObject) -> List[float]:
    """World-space center of an object's AABB."""
    lo, hi = _bbox(obj)
    return [(lo[i] + hi[i]) / 2.0 for i in range(3)]


# ---------------------------------------------------------------------------
# Constraint data model
# ---------------------------------------------------------------------------

# Supported constraint kinds. Each one is checked by ``evaluate`` and
# adjusted by ``solve``.
#
#   above        — subject's base sits above anchor's top (offset above)
#   below        — subject's top sits below anchor's base
#   above_floor  — subject's base sits at/above y=0 (or target_point.y)
#   faces        — subject's +Z axis points at anchor / target_point
#   centered     — subject's center matches anchor's center on the
#                  given axis (or all axes if no axis set)
#   min_distance — subject's center is at least ``distance`` from anchor
#   aligned      — subject's center aligns to anchor's center on the
#                  given axis within tolerance (advisory check; solver
#                  nudges into alignment when violated)
CONSTRAINT_KINDS = (
    "above",
    "below",
    "above_floor",
    "faces",
    "centered",
    "min_distance",
    "aligned",
)


@dataclass
class Constraint:
    """A single spatial constraint between scene objects.

    ``subject`` is the object being constrained (id or name). ``anchor``
    is the reference object (id or name) for relational kinds. Some
    kinds use an absolute ``target_point`` instead of (or in addition
    to) an anchor.

    ``axis`` is one of ``"x" | "y" | "z"`` for ``centered`` / ``aligned``
    (None means "all axes"). ``distance`` is a length used by
    ``min_distance`` and as the gap for ``above``/``below`` when no
    explicit ``offset`` is set. ``offset`` is an explicit gap along the
    Y axis for above/below. ``tolerance`` is the slack used by
    ``centered``/``aligned``/``above_floor``.
    """

    kind: str
    subject: str
    anchor: Optional[str] = None
    target_point: Optional[List[float]] = None
    axis: Optional[str] = None
    distance: Optional[float] = None
    offset: Optional[float] = None
    tolerance: float = 0.05
    description: str = ""
    id: str = field(default_factory=lambda: f"c_{uuid.uuid4().hex[:8]}")

    def __post_init__(self) -> None:
        if self.kind not in CONSTRAINT_KINDS:
            raise ValueError(
                f"Unknown constraint kind '{self.kind}'. "
                f"Expected one of {CONSTRAINT_KINDS}"
            )
        if self.axis is not None and self.axis not in ("x", "y", "z"):
            raise ValueError(f"axis must be one of x/y/z, got '{self.axis}'")
        if self.target_point is not None and len(self.target_point) != 3:
            raise ValueError("target_point must be a 3-vector [x, y, z]")

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Per-scene constraint store (keyed by id(scene) — the orchestrator
# reuses the same Scene instance per session, so this is session-scoped)
# ---------------------------------------------------------------------------

_STORE: Dict[int, List[Constraint]] = {}


def get_constraints(scene: Scene) -> List[Constraint]:
    """Return the constraint list attached to a scene (empty if none)."""
    return _STORE.get(id(scene), [])


def set_constraints(scene: Scene, constraints: List[Constraint]) -> None:
    """Replace the constraint list attached to a scene."""
    _STORE[id(scene)] = list(constraints)


def add_constraint(scene: Scene, constraint: Constraint) -> None:
    """Append a constraint to the scene's store."""
    _STORE.setdefault(id(scene), []).append(constraint)


def clear_constraints(scene: Scene) -> int:
    """Remove every constraint attached to a scene. Returns the count cleared."""
    n = len(_STORE.get(id(scene), []))
    _STORE[id(scene)] = []
    return n


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------

def _resolve(scene: Scene, identifier: str) -> Optional[SceneObject]:
    """Resolve a subject/anchor identifier to a SceneObject."""
    return scene.find_object(identifier)


def evaluate(constraint: Constraint, scene: Scene) -> Tuple[bool, str]:
    """Check whether a constraint is currently satisfied.

    Returns ``(passed, message)``. ``passed`` is True when the constraint
    holds within its tolerance; ``message`` explains the current state.
    """
    sub = _resolve(scene, constraint.subject)
    if sub is None:
        return False, f"Subject '{constraint.subject}' not found in scene"
    anc = _resolve(scene, constraint.anchor) if constraint.anchor else None
    if constraint.anchor and anc is None:
        return False, f"Anchor '{constraint.anchor}' not found in scene"

    tol = float(constraint.tolerance or 0.0)

    if constraint.kind == "above_floor":
        floor_y = 0.0
        if constraint.target_point and len(constraint.target_point) >= 2:
            floor_y = float(constraint.target_point[1])
        elif constraint.offset is not None:
            floor_y = float(constraint.offset)
        lo, _ = _bbox(sub)
        gap = lo[1] - floor_y
        ok = gap >= -tol
        msg = (
            f"'{sub.name}' base y={lo[1]:.2f}, floor y={floor_y:.2f}, "
            f"gap {gap:.2f} (>= -{tol:.2f})"
        )
        return ok, msg

    if constraint.kind == "above":
        if anc is None:
            return False, "'above' requires an anchor object"
        gap = float(constraint.offset) if constraint.offset is not None else float(constraint.distance or 0.0)
        _, sub_hi_unused = _bbox(sub)
        _, anc_hi = _bbox(anc)
        lo, _ = _bbox(sub)
        delta = lo[1] - (anc_hi[1] + gap)
        ok = delta >= -tol
        msg = (
            f"'{sub.name}' base y={lo[1]:.2f}, '{anc.name}' top y={anc_hi[1]:.2f}, "
            f"target gap {gap:.2f}, actual {delta:.2f} (>= -{tol:.2f})"
        )
        return ok, msg

    if constraint.kind == "below":
        if anc is None:
            return False, "'below' requires an anchor object"
        gap = float(constraint.offset) if constraint.offset is not None else float(constraint.distance or 0.0)
        _, sub_hi = _bbox(sub)
        anc_lo, _ = _bbox(anc)
        delta = (anc_lo[1] - gap) - sub_hi[1]
        ok = delta >= -tol
        msg = (
            f"'{sub.name}' top y={sub_hi[1]:.2f}, '{anc.name}' base y={anc_lo[1]:.2f}, "
            f"target gap {gap:.2f}, actual {delta:.2f} (>= -{tol:.2f})"
        )
        return ok, msg

    if constraint.kind == "min_distance":
        if anc is None:
            return False, "'min_distance' requires an anchor object"
        dist = float(constraint.distance or 0.0)
        cs = _bbox_center(sub)
        ca = _bbox_center(anc)
        d = math.sqrt(sum((cs[i] - ca[i]) ** 2 for i in range(3)))
        ok = d >= dist - tol
        msg = (
            f"'{sub.name}' <-> '{anc.name}' distance {d:.2f}, "
            f"required >= {dist:.2f}"
        )
        return ok, msg

    if constraint.kind in ("centered", "aligned"):
        # Aligned is the same check as centered (axis match within tol);
        # the solver differs (aligned nudges, centered snaps).
        if anc is None and constraint.target_point is None:
            return False, f"'{constraint.kind}' requires an anchor or target_point"
        cs = _bbox_center(sub)
        if anc is not None:
            ref = _bbox_center(anc)
            ref_name = anc.name
        else:
            ref = list(constraint.target_point)  # type: ignore[assignment]
            ref_name = f"point {ref}"
        axes = [constraint.axis] if constraint.axis else [0, 1, 2]
        bad: List[str] = []
        for ax in axes:
            idx = {"x": 0, "y": 1, "z": 2}.get(ax, ax)  # type: ignore[arg-type]
            if abs(cs[idx] - ref[idx]) > tol:
                bad.append(f"{('x','y','z')[idx]}={cs[idx]:.2f} vs {ref[idx]:.2f}")
        ok = not bad
        msg = (
            f"'{sub.name}' center vs {ref_name} on "
            f"{('all' if not constraint.axis else constraint.axis)}: "
            + ("match" if ok else "; ".join(bad))
        )
        return ok, msg

    if constraint.kind == "faces":
        # Subject's +Z axis (rotation.y rotates around Y) should point at
        # the anchor / target_point. Compute the bearing from subject
        # position to the reference and compare to the subject's yaw.
        cs = list(sub.transform.position or [0, 0, 0])
        if anc is not None:
            ca = list(anc.transform.position or [0, 0, 0])
        elif constraint.target_point is not None:
            ca = list(constraint.target_point)
        else:
            return False, "'faces' requires an anchor or target_point"
        desired = math.atan2(ca[0] - cs[0], ca[2] - cs[2])
        yaw = float((sub.transform.rotation or [0, 0, 0])[1])
        diff = (desired - yaw + math.pi) % (2 * math.pi) - math.pi
        ok = abs(diff) <= max(tol, 0.1)
        msg = (
            f"'{sub.name}' yaw={yaw:.2f}, desired={desired:.2f}, "
            f"delta {diff:.2f} rad (within {max(tol, 0.1):.2f})"
        )
        return ok, msg

    return False, f"Unknown constraint kind '{constraint.kind}'"


# ---------------------------------------------------------------------------
# Solver — greedy iterative position (and rotation.y for `faces`) adjustment
# ---------------------------------------------------------------------------

def _apply_above_floor(c: Constraint, sub: SceneObject, anc: Optional[SceneObject]) -> bool:
    floor_y = 0.0
    if c.target_point and len(c.target_point) >= 2:
        floor_y = float(c.target_point[1])
    elif c.offset is not None:
        floor_y = float(c.offset)
    lo, _ = _bbox(sub)
    if abs(lo[1] - floor_y) <= (c.tolerance or 0.0):
        return False
    sub.transform.position[1] += floor_y - lo[1]
    return True


def _apply_above(c: Constraint, sub: SceneObject, anc: SceneObject) -> bool:
    gap = float(c.offset) if c.offset is not None else float(c.distance or 0.0)
    _, anc_hi = _bbox(anc)
    lo, _ = _bbox(sub)
    target_base = anc_hi[1] + gap
    if abs(lo[1] - target_base) <= (c.tolerance or 0.0):
        return False
    sub.transform.position[1] += target_base - lo[1]
    return True


def _apply_below(c: Constraint, sub: SceneObject, anc: SceneObject) -> bool:
    gap = float(c.offset) if c.offset is not None else float(c.distance or 0.0)
    anc_lo, _ = _bbox(anc)
    _, sub_hi = _bbox(sub)
    target_top = anc_lo[1] - gap
    if abs(sub_hi[1] - target_top) <= (c.tolerance or 0.0):
        return False
    sub.transform.position[1] += target_top - sub_hi[1]
    return True


def _apply_min_distance(c: Constraint, sub: SceneObject, anc: SceneObject) -> bool:
    dist = float(c.distance or 0.0)
    cs = _bbox_center(sub)
    ca = _bbox_center(anc)
    d = math.sqrt(sum((cs[i] - ca[i]) ** 2 for i in range(3)))
    if d >= dist - (c.tolerance or 0.0):
        return False
    if d < 1e-6:
        # Coincident — push along +X by the required distance.
        sub.transform.position[0] += dist
        return True
    # Push subject outward along the line from anchor to subject.
    push = (dist - d) + 1e-3
    ux = (cs[0] - ca[0]) / d
    uy = (cs[1] - ca[1]) / d
    uz = (cs[2] - ca[2]) / d
    sub.transform.position[0] += ux * push
    sub.transform.position[1] += uy * push
    sub.transform.position[2] += uz * push
    return True


def _apply_centered(c: Constraint, sub: SceneObject, ref: List[float]) -> bool:
    axes = [c.axis] if c.axis else ["x", "y", "z"]
    moved = False
    cs = _bbox_center(sub)
    pos = list(sub.transform.position or [0, 0, 0])
    # Estimate the offset between bbox center and transform position so we
    # can shift the transform by the right delta (bbox center is what we
    # align, transform position is what we mutate).
    pos_offset = [cs[i] - pos[i] for i in range(3)]
    idx_map = {"x": 0, "y": 1, "z": 2}
    for ax in axes:
        idx = idx_map[ax]
        if abs(cs[idx] - ref[idx]) <= (c.tolerance or 0.0):
            continue
        sub.transform.position[idx] = ref[idx] - pos_offset[idx]
        moved = True
    return moved


def _apply_aligned(c: Constraint, sub: SceneObject, ref: List[float]) -> bool:
    # For aligned we only nudge halfway toward the reference (advisory),
    # so multiple aligned constraints don't fight each other to a stalemate.
    axes = [c.axis] if c.axis else ["x", "y", "z"]
    moved = False
    cs = _bbox_center(sub)
    pos = list(sub.transform.position or [0, 0, 0])
    pos_offset = [cs[i] - pos[i] for i in range(3)]
    idx_map = {"x": 0, "y": 1, "z": 2}
    for ax in axes:
        idx = idx_map[ax]
        if abs(cs[idx] - ref[idx]) <= (c.tolerance or 0.0):
            continue
        target = ref[idx] - pos_offset[idx]
        sub.transform.position[idx] += (target - sub.transform.position[idx]) * 0.5
        moved = True
    return moved


def _apply_faces(c: Constraint, sub: SceneObject, ref: List[float]) -> bool:
    cs = list(sub.transform.position or [0, 0, 0])
    desired = math.atan2(ref[0] - cs[0], ref[2] - cs[2])
    yaw = float((sub.transform.rotation or [0, 0, 0])[1])
    diff = (desired - yaw + math.pi) % (2 * math.pi) - math.pi
    if abs(diff) <= max(c.tolerance or 0.0, 0.1):
        return False
    # Nudge halfway toward the desired yaw to avoid overshoot when several
    # faces constraints interact.
    sub.transform.rotation[1] = yaw + diff * 0.75
    return True


def solve(
    scene: Scene,
    constraints: Optional[List[Constraint]] = None,
    max_passes: int = 5,
) -> Dict[str, Any]:
    """Greedy iterative solver: adjust subject positions to satisfy constraints.

    For each pass, walks the constraint list in order and mutates the
    subject's ``transform.position`` (and ``rotation.y`` for ``faces``)
    toward satisfaction. Multiple passes let relational constraints
    settle (e.g. A-above-B and B-above-C). Returns a structured report
    of what moved, what is still violated, and per-pass deltas.

    Only the subject is moved; anchors stay put. The solver is
    deliberately conservative — it never moves an object more than
    necessary to satisfy the immediate constraint, and an unsatisfiable
    constraint (e.g. circular dependency) leaves the subject at its
    last-computed position.
    """
    if constraints is None:
        constraints = get_constraints(scene)
    if not constraints:
        return {
            "solved": 0,
            "still_violated": [],
            "moved": [],
            "passes": 0,
        }

    # Snapshot initial positions so we can report deltas.
    initial: Dict[str, List[float]] = {}
    for c in constraints:
        sub = _resolve(scene, c.subject)
        if sub is not None and sub.id not in initial:
            initial[sub.id] = list(sub.transform.position or [0, 0, 0])

    passes_done = 0
    for _ in range(max(1, max_passes)):
        passes_done += 1
        moved_this_pass = False
        for c in constraints:
            sub = _resolve(scene, c.subject)
            if sub is None:
                continue
            anc = _resolve(scene, c.anchor) if c.anchor else None
            if c.anchor and anc is None:
                continue
            moved = False
            if c.kind == "above_floor":
                moved = _apply_above_floor(c, sub, anc)
            elif c.kind == "above":
                if anc is not None:
                    moved = _apply_above(c, sub, anc)
            elif c.kind == "below":
                if anc is not None:
                    moved = _apply_below(c, sub, anc)
            elif c.kind == "min_distance":
                if anc is not None:
                    moved = _apply_min_distance(c, sub, anc)
            elif c.kind == "centered":
                ref = _bbox_center(anc) if anc is not None else (c.target_point or [0, 0, 0])
                moved = _apply_centered(c, sub, list(ref))
            elif c.kind == "aligned":
                ref = _bbox_center(anc) if anc is not None else (c.target_point or [0, 0, 0])
                moved = _apply_aligned(c, sub, list(ref))
            elif c.kind == "faces":
                if anc is not None:
                    ref = list(anc.transform.position or [0, 0, 0])
                elif c.target_point is not None:
                    ref = list(c.target_point)
                else:
                    continue
                moved = _apply_faces(c, sub, ref)
            if moved:
                moved_this_pass = True
        if not moved_this_pass:
            break

    # Final evaluation to figure out what is still violated.
    still_violated: List[Dict[str, Any]] = []
    solved = 0
    for c in constraints:
        ok, msg = evaluate(c, scene)
        if ok:
            solved += 1
        else:
            still_violated.append({
                "id": c.id,
                "kind": c.kind,
                "subject": c.subject,
                "anchor": c.anchor,
                "message": msg,
            })

    moved: List[Dict[str, Any]] = []
    for c in constraints:
        sub = _resolve(scene, c.subject)
        if sub is None or sub.id not in initial:
            continue
        now = list(sub.transform.position or [0, 0, 0])
        before = initial[sub.id]
        if now != before:
            moved.append({
                "id": sub.id,
                "name": sub.name,
                "from": before,
                "to": now,
            })

    return {
        "solved": solved,
        "still_violated": still_violated,
        "moved": moved,
        "passes": passes_done,
    }
