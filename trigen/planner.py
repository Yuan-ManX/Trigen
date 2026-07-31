"""Task planner.

Parses the LLM's tool-call sequence into ordered task steps, supporting
intent recognition and execution-plan generation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List

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
    """Execution plan."""

    steps: List[TaskStep] = field(default_factory=list)
    reasoning: str = ""

    @property
    def is_empty(self) -> bool:
        return not self.steps


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
}


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
        return TaskPlan(steps=steps, reasoning=reasoning)

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
