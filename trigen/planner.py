"""Task planner.

Parses the LLM's tool-call sequence into ordered task steps, supporting
intent recognition, execution-plan generation, tool-input pre-validation,
and per-turn token-budget tracking.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from trigen.llm.client import ToolCall

logger = logging.getLogger("trigen.planner")


@dataclass
class TaskStep:
    """A single execution step."""

    tool_name: str
    arguments: Dict[str, Any]
    tool_call_id: str = ""
    description: str = ""


@dataclass
class TaskPlan:
    """Execution plan.

    A structured artifact emitted before tool execution so the frontend
    can render the agent's reasoning (goal / assumptions / risks) and
    the planned step chain. ``token_budget_used`` / ``token_budget_limit``
    snapshot the budget state at planning time.

    ``dependencies`` maps a step's ``tool_call_id`` to the list of step ids
    it must execute after. Edges are derived from name-creation chains and
    same-target mutation conflicts, so the frontend can render a true
    dependency graph (node-graph view) instead of only a linear checklist.
    """

    steps: List[TaskStep] = field(default_factory=list)
    reasoning: str = ""
    goal: str = ""
    assumptions: List[str] = field(default_factory=list)
    risks: List[str] = field(default_factory=list)
    token_budget_used: int = 0
    token_budget_limit: int = 0
    # Explicit dependency edges: {step_id: [predecessor_step_id, ...]}.
    # Populated by ``TaskPlanner._derive_dependency_edges``.
    dependencies: Dict[str, List[str]] = field(default_factory=dict)
    # Structured sub-goal chain derived from multi-intent plans. Each entry
    # is ``{category, label, step_ids, tool_count}`` so the frontend can
    # render the high-level objective sequence (create → material → light)
    # alongside the linear step checklist. Empty for single-intent turns.
    goal_breakdown: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.steps

    def to_plan_payload(self) -> Dict[str, Any]:
        """Serialize the plan for the ``thinking`` event's ``plan`` field."""
        return {
            "goal": self.goal,
            "assumptions": list(self.assumptions),
            "risks": list(self.risks),
            "steps": [
                {
                    "tool": s.tool_name,
                    "arguments": s.arguments,
                    "description": s.description,
                }
                for s in self.steps
            ],
            "token_budget_used": self.token_budget_used,
            "token_budget_limit": self.token_budget_limit,
            "goal_breakdown": list(self.goal_breakdown),
        }

    def to_graph_payload(self) -> Dict[str, Any]:
        """Serialize the plan as a dependency graph for node-graph rendering.

        Returns ``{nodes, edges, layers}`` where ``nodes`` is the step list
        with stable ids, ``edges`` carries typed predecessor links, and
        ``layers`` groups step ids by topological depth so the frontend can
        lay out the graph left-to-right (each layer executes as a parallel
        wave when the executor batches it).

        Each node carries a ``status`` (always "pending" at plan-preview
        time — the frontend merges live ``plan_update`` transitions into
        the stored DAG) and a ``dependencies`` list (predecessor step ids)
        so a renderer can draw edges without consulting the separate edges
        list. Each edge carries a ``kind`` (advisory label such as
        "dependency") so the frontend can style edge types uniformly.
        """
        step_ids = [s.tool_call_id for s in self.steps]
        id_set = set(step_ids)
        nodes = [
            {
                "id": s.tool_call_id,
                "tool": s.tool_name,
                "label": s.description or s.tool_name,
                "arguments": s.arguments,
                "status": "pending",
                "dependencies": [
                    p for p in self.dependencies.get(s.tool_call_id, []) if p in id_set
                ],
            }
            for s in self.steps
        ]
        edges: List[Dict[str, str]] = []
        for sid, preds in self.dependencies.items():
            if sid not in id_set:
                continue
            for p in preds:
                if p in id_set:
                    edges.append({"from": p, "to": sid, "kind": "dependency"})
        # Topological layering by longest-path depth so the frontend can
        # render parallel waves. Steps with no predecessors are layer 0.
        depth: Dict[str, int] = {sid: 0 for sid in step_ids}
        # Resolve in step order (already topologically sorted by the planner)
        # so predecessor depths are computed before dependents.
        for s in self.steps:
            sid = s.tool_call_id
            preds = [p for p in self.dependencies.get(sid, []) if p in depth]
            if preds:
                depth[sid] = max(depth[p] for p in preds) + 1
        layers: List[List[str]] = []
        max_depth = max(depth.values()) if depth else 0
        for d in range(max_depth + 1):
            layers.append([sid for sid in step_ids if depth.get(sid, 0) == d])
        return {"nodes": nodes, "edges": edges, "layers": layers}


@dataclass
class TokenBudget:
    """Per-turn token budget tracker.

    The LLM client does not always return a usage block on streaming
    chunks, so we approximate tokens as ``max(1, chars // 4)``. This is
    deliberately conservative — the budget is a guard rail against
    runaway loops, not a billing instrument.
    """

    limit: int = 0  # 0 means unlimited
    used: int = 0

    @staticmethod
    def estimate(text: str) -> int:
        """Rough token estimate from text length."""
        if not text:
            return 0
        return max(1, len(text) // 4)

    def add(self, text: str) -> int:
        """Add a text chunk's estimated tokens to the budget."""
        n = self.estimate(text)
        self.used += n
        return n

    def add_tokens(self, n: int) -> None:
        """Add an explicit token count (e.g. from a usage block)."""
        if n > 0:
            self.used += n

    @property
    def exhausted(self) -> bool:
        return self.limit > 0 and self.used >= self.limit

    @property
    def remaining(self) -> int:
        if self.limit <= 0:
            return -1  # unlimited
        return max(0, self.limit - self.used)


# ---------------------------------------------------------------------------
# Tool-input pre-validation
# ---------------------------------------------------------------------------

def prevalidate_step(step: TaskStep, tool_schema: Optional[Dict[str, Any]]) -> List[str]:
    """Validate ``step.arguments`` against the tool's JSON schema.

    Returns a list of human-readable error strings. An empty list means
    the arguments pass shallow validation. Checks performed:
      - required fields are present and non-null
      - type matches (string/number/integer/boolean/array/object)
      - enum constraints
      - numeric minimum/maximum
      - array minItems/maxItems and item type
      - string minLength/maxLength

    The check is intentionally shallow (no recursive object validation)
    so unknown fields and complex nested schemas do not cause false
    positives. The tool's own ``execute`` remains the source of truth.
    """
    if not tool_schema:
        return []
    params = tool_schema.get("parameters") or tool_schema
    if not isinstance(params, dict):
        return []
    properties = params.get("properties", {}) or {}
    required = params.get("required", []) or []
    errors: List[str] = []

    for req in required:
        if not isinstance(req, str):
            continue
        if req not in step.arguments or step.arguments[req] is None:
            errors.append(f"missing required parameter '{req}'")

    for key, value in step.arguments.items():
        spec = properties.get(key)
        if spec is None:
            continue  # unknown fields are tolerated
        if value is None:
            continue
        err = _validate_value(key, value, spec)
        errors.extend(err)

    return errors


def _validate_value(key: str, value: Any, spec: Dict[str, Any]) -> List[str]:
    """Validate a single argument value against its property spec."""
    errors: List[str] = []
    expected_type = spec.get("type")

    if expected_type and not _type_matches(value, expected_type):
        errors.append(
            f"parameter '{key}' expected type '{expected_type}', got {type(value).__name__}"
        )
        return errors  # further checks assume correct type

    if expected_type == "string":
        enum = spec.get("enum")
        if enum and value not in enum:
            errors.append(
                f"parameter '{key}' value '{value}' not in enum {enum}"
            )
        min_len = spec.get("minLength")
        if isinstance(min_len, int) and isinstance(value, str) and len(value) < min_len:
            errors.append(f"parameter '{key}' shorter than minLength {min_len}")
        max_len = spec.get("maxLength")
        if isinstance(max_len, int) and isinstance(value, str) and len(value) > max_len:
            errors.append(f"parameter '{key}' longer than maxLength {max_len}")

    if expected_type in ("number", "integer"):
        minimum = spec.get("minimum")
        if isinstance(minimum, (int, float)) and isinstance(value, (int, float)) and value < minimum:
            errors.append(f"parameter '{key}' value {value} below minimum {minimum}")
        maximum = spec.get("maximum")
        if isinstance(maximum, (int, float)) and isinstance(value, (int, float)) and value > maximum:
            errors.append(f"parameter '{key}' value {value} above maximum {maximum}")

    if expected_type == "array":
        if isinstance(value, list):
            min_items = spec.get("minItems")
            if isinstance(min_items, int) and len(value) < min_items:
                errors.append(f"parameter '{key}' has fewer than minItems {min_items}")
            max_items = spec.get("maxItems")
            if isinstance(max_items, int) and len(value) > max_items:
                errors.append(f"parameter '{key}' has more than maxItems {max_items}")
            item_spec = spec.get("items")
            if isinstance(item_spec, dict):
                item_type = item_spec.get("type")
                if item_type:
                    for i, item in enumerate(value):
                        if not _type_matches(item, item_type):
                            errors.append(
                                f"parameter '{key}' item {i} expected type '{item_type}'"
                            )

    return errors


def _type_matches(value: Any, expected_type: str) -> bool:
    """Loose JSON-schema type matching (int also satisfies number)."""
    if expected_type == "string":
        return isinstance(value, str)
    if expected_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected_type == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected_type == "boolean":
        return isinstance(value, bool)
    if expected_type == "array":
        return isinstance(value, list)
    if expected_type == "object":
        return isinstance(value, dict)
    return True  # unknown type — accept


# Tools that can be safely executed in parallel within a single batch.
# Conservative policy: read-only tools and tools that mutate independent
# targets are eligible. The executor further filters by distinct target id
# so two transforms on the same object are never batched together.
_PARALLEL_SAFE_TOOLS = {
    # Material / geometry on distinct targets
    "apply_material",
    "apply_material_preset",
    "transform_object",
    "modify_geometry",
    # Independent appends (auto-naming handles uniqueness)
    "create_object",
    "add_light",
    "add_camera",
    # Per-target deletion / modification
    "delete_object",
    "delete_light",
    "modify_light",
    "modify_camera",
    # Scene-level attributes (different fields, no cross-interference)
    "set_background",
    "set_fog",
    "toggle_grid",
    "set_grid_size",
    "set_view",
    "set_environment",
    # Multi-target spatial operations (each call independently mutates its target set)
    "align_objects",
    "distribute_objects",
    # Camera-level operations (independent camera objects)
    "animate_camera",
    "snapshot_view",
    # Read-only inspection
    "scene_info",
    "list_objects",
    "analyze_scene",
    "export_scene",
    "export_code",
    "measure_distance",
    # Editor control (no scene mutation)
    "select_object",
    "focus_object",
    # Isolated LLM call
    "dispatch_subagent",
    "ensemble_brainstorm",
    # Independent multimodal generation (external API calls)
    "generate_image",
    "generate_3d_asset",
    "generate_video",
    "generate_animation",
    "generate_music",
    "synthesize_speech",
    "transcribe_audio",
    # Composite & editor state tools (per-target mutations handled by _target_key)
    "array_pattern",
    "mirror_object",
    "boolean_operation",
    "snap_to_grid",
    "lock_object",
    "set_visibility",
    "rename_object",
    "set_transform_mode",
    "frame_view",
    # Advanced material tools (per-target)
    "gradient_material",
    "material_blend",
    # Object animation (per-target descriptor attachment)
    "keyframe_animation",
    "orbit_animation",
    "wave_animation",
    "bounce_animation",
    "pulse_animation",
    "sway_animation",
    "spin_animation",
    # Procedural generation (independent appends; per-call target key handles conflicts)
    "terrain_generator",
    "l_system",
    "create_spiral_staircase",
    "voronoi_shatter",
    # Creative skills — each invocation is independent
    "invoke_skill",
    # Suggestions / palette are scene-wide but read-mostly
    "randomize_palette",
    # Scene-structure management (per-target mutations handled by _target_key;
    # reorder_layer is intentionally excluded as it reorders the whole list)
    "rename_group",
    "delete_camera",
    "select_all",
    # Viewport / playback / session editor control (delta-only, no scene mutation)
    "set_viewport_camera",
    "play_animation",
    "pause_animation",
    "seek_animation",
    "set_selection",
    "capture_viewport",
    "set_playback_speed",
    "toggle_grid_snapping",
    "focus_panel",
    "undo_scene",
    "redo_scene",
    "set_render_quality",
    # Advanced editor control — per-target mutations handled by _target_key
    "reset_transform",
    "set_object_pivot",
    "set_object_layer",
    "set_clipping_plane",
    "apply_material_batch",
    # Viewport & editor-state control — emit editor deltas only, no scene
    # mutation, so they can run alongside other tools safely.
    "set_minimap",
    "set_shadows",
    "set_viewport_projection",
    "set_editor_mode",
    "save_scene_slot",
    # isolate_object is intentionally excluded: it mutates the visibility of
    # every object in the scene, so batching it with another visibility tweak
    # would produce non-deterministic ordering.
    # load_scene_slot is intentionally excluded: it can replace the entire
    # scene (clear_scene=true), so running it in parallel with anything else
    # would race on scene.objects / lights / cameras.
    # Editor gap tools — delta-only (no scene mutation), safe to parallelize.
    "control_radial_menu",
    "clear_measurement",
    "stop_camera_flythrough",
    # Read-only macro / variant listing — no side effects.
    "list_macros",
    "list_variants",
    # invoke_macro / define_macro / delete_macro / save_variant / load_variant
    # / randomize_variant are intentionally excluded: invoke_macro replays a
    # multi-step plan (semantics parallel to invoke_skill), define/delete
    # mutate the macro store, and save/load/randomize_variant can replace the
    # entire scene — all of which would race under parallel execution.
}


# Tools that introduce a new named entity into the scene. The planner uses
# these to derive name-based dependencies: any subsequent step referencing
# the produced name must execute after the producing step.
_CREATION_TOOLS = {"create_object", "add_light", "add_camera"}


class TaskPlanner:
    """Parses LLM responses into an executable plan."""

    def from_tool_calls(self, tool_calls: List[ToolCall], reasoning: str = "") -> TaskPlan:
        steps: List[TaskStep] = []
        for tc in tool_calls:
            steps.append(
                TaskStep(
                    tool_name=tc.name,
                    arguments=tc.arguments,
                    tool_call_id=tc.id,
                    description=f"Call {tc.name}",
                )
            )
        steps = self._order_by_dependencies(steps)
        plan = TaskPlan(steps=steps, reasoning=reasoning)
        plan.dependencies = self._derive_dependency_edges(steps)
        self._enrich_plan(plan, tool_calls)
        return plan

    def _derive_dependency_edges(self, steps: List[TaskStep]) -> Dict[str, List[str]]:
        """Compute explicit predecessor edges for each step.

        Two edge sources, both conservative (only add an edge when a real
        ordering constraint exists, so unrelated steps stay parallel):
          1. Name-creation chains — a step referencing a name produced by an
             earlier creation step depends on that creator.
          2. Same-target mutation — two steps mutating the same target name
             depend on each other in declared order so the executor never
             batches conflicting mutations.

        Edges point from predecessor -> successor (successor id maps to its
        predecessor ids). Self-edges and transitive duplicates are skipped.
        """
        edges: Dict[str, List[str]] = {s.tool_call_id: [] for s in steps}
        if not steps:
            return edges
        # 1. Name-creation chains.
        creator_of: Dict[str, str] = {}  # name -> creator step id
        for s in steps:
            if s.tool_name in _CREATION_TOOLS:
                nm = s.arguments.get("name")
                if isinstance(nm, str) and nm and nm not in creator_of:
                    creator_of[nm] = s.tool_call_id
        for s in steps:
            if s.tool_name in _CREATION_TOOLS:
                continue
            preds = set(edges[s.tool_call_id])
            for t in self._step_target_names(s):
                creator_id = creator_of.get(t)
                if creator_id and creator_id != s.tool_call_id:
                    preds.add(creator_id)
            edges[s.tool_call_id] = sorted(preds)

        # 2. Same-target mutation ordering (declared order only).
        # Track the most recent step that mutated each target name; a later
        # step on the same target depends on it.
        last_mutator: Dict[str, str] = {}
        for s in steps:
            preds = set(edges[s.tool_call_id])
            for t in self._step_target_names(s):
                prev = last_mutator.get(t)
                if prev and prev != s.tool_call_id:
                    preds.add(prev)
            # Record this step as the latest mutator for its targets.
            for t in self._step_target_names(s):
                last_mutator[t] = s.tool_call_id
            edges[s.tool_call_id] = sorted(preds)
        return edges

    def _enrich_plan(self, plan: TaskPlan, tool_calls: List[ToolCall]) -> None:
        """Derive goal / assumptions / risks from reasoning text and tool calls.

        Heuristic, not LLM-driven — keeps the planning step cheap and
        deterministic. The goal is the first non-trivial sentence of the
        reasoning text (or a fallback describing the tool chain).
        Assumptions are inferred from common patterns (creation followed
        by transform implies "object will exist before transform"). Risks
        flag potential issues (delete before create, missing target).
        """
        reasoning = (plan.reasoning or "").strip()
        goal = ""
        if reasoning:
            # Take the first sentence-like fragment up to ~120 chars.
            for sep in (". ", "。", "\n"):
                idx = reasoning.find(sep)
                if 0 < idx <= 140:
                    goal = reasoning[: idx + 1].strip()
                    break
            if not goal:
                goal = reasoning[:120].strip()
        if not goal and tool_calls:
            names = [tc.name for tc in tool_calls]
            goal = f"Execute {len(names)} tool(s): {', '.join(names)}"
        # Multi-intent goal decomposition: when the plan spans multiple
        # distinct intent categories (e.g. creation + material + lighting),
        # append a structured breakdown so the frontend can render the
        # sub-goal chain alongside the linear step checklist. Cheap and
        # deterministic — derived from the tool categories already
        # registered on the orchestrator side.
        breakdown = self._decompose_goal(plan.steps)
        if breakdown:
            plan.goal_breakdown = breakdown
            if not goal:
                goal = breakdown[0].get("label", "")
        plan.goal = goal

        # Assumption: when a creation tool precedes a mutation tool, the
        # planner's dependency ordering assumes the created name exists.
        created_names: set = set()
        for step in plan.steps:
            if step.tool_name in _CREATION_TOOLS:
                nm = step.arguments.get("name")
                if isinstance(nm, str) and nm:
                    created_names.add(nm)
        reported_assumptions: set = set()
        for step in plan.steps:
            if step.tool_name in _CREATION_TOOLS:
                continue
            for t in self._step_target_names(step):
                if t in created_names and t not in reported_assumptions:
                    plan.assumptions.append(
                        f"'{t}' will exist before {step.tool_name} (created earlier in plan)"
                    )
                    reported_assumptions.add(t)

        # Risk: transform on a name not created here (may not exist —
        # surfaced as a risk, not a hard error). Only meaningful when the
        # plan contains at least one creation tool, otherwise every target
        # would be flagged which is just normal scene interaction.
        all_targets: set = set()
        for step in plan.steps:
            all_targets.update(self._step_target_names(step))
        undeclared = all_targets - created_names
        if undeclared and any(s.tool_name in _CREATION_TOOLS for s in plan.steps):
            for name in list(undeclared)[:3]:
                plan.risks.append(
                    f"'{name}' is referenced but not created in this plan — depends on prior scene state"
                )
        for step in plan.steps:
            if step.tool_name == "delete_object":
                plan.risks.append(
                    f"delete_object on '{step.arguments.get('target', '?')}' is irreversible"
                )

    # Tool-name → coarse intent category mirror of the orchestrator's
    # _TOOL_CATEGORIES. Kept local to the planner so goal decomposition
    # stays self-contained and does not import the orchestrator (which
    # would create a circular dependency). Updated in lockstep with the
    # orchestrator's taxonomy — covers the same 16 categories.
    _TOOL_CATEGORY_MAP: Dict[str, str] = {
        "create_object": "creation", "modify_geometry": "creation",
        "duplicate_object": "creation", "delete_object": "creation",
        "array_pattern": "creation", "boolean_operation": "creation",
        "set_geometry_params": "creation", "place_asset": "creation",
        "scatter_paint": "creation", "snap_to_surface": "creation",
        "transform_object": "transform", "mirror_object": "transform",
        "align_objects": "transform", "distribute_objects": "transform",
        "snap_to_grid": "transform", "reset_transform": "transform",
        "apply_material": "material", "apply_material_preset": "material",
        "gradient_material": "material", "material_blend": "material",
        "randomize_palette": "material", "apply_material_batch": "material",
        "set_material_property": "material",
        "add_light": "lighting", "modify_light": "lighting", "delete_light": "lighting",
        "add_camera": "camera", "modify_camera": "camera", "delete_camera": "camera",
        "set_view": "camera", "snapshot_view": "camera", "capture_viewport": "camera",
        "animate_camera": "camera", "frame_view": "camera",
        "group_objects": "scene", "ungroup_objects": "scene", "assign_to_group": "scene",
        "rename_group": "scene", "reorder_layer": "scene", "arrange_layout": "scene",
        "set_background": "scene", "set_fog": "scene", "set_environment": "scene",
        "toggle_grid": "scene", "set_grid_size": "scene", "smart_compose": "scene",
        "select_object": "editor", "select_all": "editor", "set_selection": "editor",
        "focus_object": "editor", "focus_panel": "editor",
        "keyframe_animation": "animation", "orbit_animation": "animation",
        "wave_animation": "animation", "bounce_animation": "animation",
        "pulse_animation": "animation", "sway_animation": "animation",
        "spin_animation": "animation",
        "play_animation": "animation", "pause_animation": "animation",
        "seek_animation": "animation", "set_playback_speed": "animation",
        "terrain_generator": "procedural", "l_system": "procedural",
        "create_spiral_staircase": "procedural", "voronoi_shatter": "procedural",
        "radial_symmetry": "procedural", "clone_with_jitter": "procedural",
        "generate_image": "multimodal", "generate_3d_asset": "multimodal",
        "generate_video": "multimodal", "generate_animation": "multimodal",
        "generate_music": "multimodal", "synthesize_speech": "multimodal",
        "transcribe_audio": "multimodal", "image_to_3d": "multimodal",
        "export_scene": "export", "export_code": "export",
        "scene_info": "inspection", "list_objects": "inspection",
        "analyze_scene": "inspection", "measure_distance": "inspection",
        "describe_scene": "inspection", "suggest_next_actions": "inspection",
        "query_scene": "inspection", "scene_statistics": "inspection",
        "list_annotations": "inspection",
        "invoke_skill": "skills",
    }

    # Friendly per-category labels for the goal-breakdown chain.
    _CATEGORY_LABELS: Dict[str, str] = {
        "creation": "Create geometry",
        "transform": "Position and shape",
        "material": "Apply materials",
        "lighting": "Set up lighting",
        "camera": "Frame the view",
        "scene": "Organize the scene",
        "editor": "Editor control",
        "animation": "Animate",
        "procedural": "Procedural generation",
        "multimodal": "Generate media",
        "export": "Export the result",
        "inspection": "Inspect the scene",
        "skills": "Run a creative skill",
    }

    def _decompose_goal(self, steps: List[TaskStep]) -> List[Dict[str, Any]]:
        """Group plan steps into an ordered sub-goal chain by category.

        Returns a list of ``{category, label, step_ids, tool_count}`` entries
        in first-occurrence order. Single-category plans return an empty list
        (no decomposition needed — the linear checklist already captures the
        intent). Multi-category plans return one entry per distinct category
        in the order they first appear, so the frontend can render a compact
        "create → material → light" sequence above the step checklist.
        """
        if not steps:
            return []
        order: List[str] = []
        bucket: Dict[str, List[str]] = {}
        for s in steps:
            cat = self._TOOL_CATEGORY_MAP.get(s.tool_name, "editor")
            if cat not in bucket:
                bucket[cat] = []
                order.append(cat)
            bucket[cat].append(s.tool_call_id)
        if len(order) <= 1:
            return []
        return [
            {
                "category": cat,
                "label": self._CATEGORY_LABELS.get(cat, cat),
                "step_ids": list(bucket[cat]),
                "tool_count": len(bucket[cat]),
            }
            for cat in order
        ]

    @staticmethod
    def _step_target_names(step: TaskStep) -> List[str]:
        """Extract target name references from a step's arguments.

        Returns a de-duplicated list of string names. Handles both single
        ``target`` args and multi-target ``targets`` args. Used only for
        dependency ordering — resolution to real objects happens at execution.
        """
        names: List[str] = []
        for key in ("target", "target_a", "target_b"):
            val = step.arguments.get(key)
            if isinstance(val, str) and val:
                names.append(val)
        targets = step.arguments.get("targets")
        if isinstance(targets, list):
            for t in targets:
                if isinstance(t, str) and t:
                    names.append(t)
        # De-duplicate preserving order
        seen: set = set()
        unique: List[str] = []
        for n in names:
            if n not in seen:
                seen.add(n)
                unique.append(n)
        return unique

    def _order_by_dependencies(self, steps: List[TaskStep]) -> List[TaskStep]:
        """Stable topological sort enforcing name dependencies.

        Ensures any creation step (create_object/add_light/add_camera) that
        produces a referenced name executes before any later step that targets
        that same name. Only adds constraints when a real name dependency
        exists; unrelated steps retain their original relative order. This
        keeps the common LLM pattern (create then transform then material)
        correct even when the model emits steps out of order.
        """
        ordered = list(steps)
        max_iter = len(ordered) * len(ordered) + 1
        changed = True
        iterations = 0
        while changed and iterations < max_iter:
            changed = False
            iterations += 1
            creator_idx: Dict[str, int] = {}
            for i, s in enumerate(ordered):
                if s.tool_name in _CREATION_TOOLS:
                    name = s.arguments.get("name")
                    if isinstance(name, str) and name and name not in creator_idx:
                        creator_idx[name] = i
            if not creator_idx:
                break
            for j, s in enumerate(ordered):
                targets = self._step_target_names(s)
                moved = False
                for t in targets:
                    ci = creator_idx.get(t)
                    if ci is not None and ci > j:
                        creator = ordered.pop(ci)
                        ordered.insert(j, creator)
                        changed = True
                        moved = True
                        break
                if moved:
                    break
        return ordered

    def build_context_message(self, scene_snapshot: Dict[str, Any]) -> str:
        """Build the current scene context message so the LLM can perceive
        the scene state."""
        objs = scene_snapshot.get("objects", [])
        lights = scene_snapshot.get("lights", [])
        groups = scene_snapshot.get("groups", [])
        bg = scene_snapshot.get("background", "#0a0a0f")
        lines = [
            f"Current scene state: {len(objs)} objects, {len(lights)} lights, "
            f"background color {bg}."
        ]
        for o in objs:
            geo = o.get("geometry", {})
            tf = o.get("transform", {})
            mat = o.get("material", {})
            pos = tf.get("position", [0, 0, 0])
            scale = tf.get("scale", [1, 1, 1])
            color = mat.get("color", "#cccccc")
            metal = mat.get("metalness", 0)
            rough = mat.get("roughness", 0.5)
            lines.append(
                f"  - {o.get('name')} (id={o.get('id')}, {geo.get('type')})"
                f" position=({pos[0]:.2f},{pos[1]:.2f},{pos[2]:.2f})"
                f" scale=({scale[0]:.2f},{scale[1]:.2f},{scale[2]:.2f})"
                f" material={color} metalness={metal:.2f} roughness={rough:.2f}"
            )
        for l in lights:
            lines.append(
                f"  - {l.get('name')} ({l.get('type')}, intensity={l.get('intensity')}, "
                f"color={l.get('color')})"
            )
        for g in groups:
            lines.append(
                f"  - Group {g.get('name')} (id={g.get('id')}, "
                f"{len(g.get('child_ids', []))} members)"
            )
        return "\n".join(lines)
