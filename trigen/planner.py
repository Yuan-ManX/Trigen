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
    """

    steps: List[TaskStep] = field(default_factory=list)
    reasoning: str = ""
    goal: str = ""
    assumptions: List[str] = field(default_factory=list)
    risks: List[str] = field(default_factory=list)
    token_budget_used: int = 0
    token_budget_limit: int = 0

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
        }


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
    # isolate_object is intentionally excluded: it mutates the visibility of
    # every object in the scene, so batching it with another visibility tweak
    # would produce non-deterministic ordering.
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
        self._enrich_plan(plan, tool_calls)
        return plan

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
