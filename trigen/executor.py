"""Task executor.

Executes tool calls in planned order, collecting results and scene mutations,
supporting parallel batch execution and exception isolation.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

from trigen.planner import TaskPlan, TaskStep
from trigen.scene import Scene
from trigen.tools.base import ToolRegistry, ToolResult, SceneDelta

logger = logging.getLogger("trigen.executor")


class TaskExecutor:
    """Sequentially (or batched-parallel) executes the tool calls in the task plan."""

    def __init__(self, registry: ToolRegistry, parallel: bool = True):
        self.registry = registry
        self.parallel = parallel

    async def execute_plan(self, scene: Scene, plan: TaskPlan) -> List[ToolResult]:
        if not self.parallel:
            return await self._execute_sequential(scene, plan)

        # Group steps into parallel-safe batches
        batches = self._group_batches(plan.steps)
        results: List[ToolResult] = []
        for batch in batches:
            if len(batch) == 1:
                results.append(await self._execute_step(scene, batch[0]))
            else:
                batch_results = await asyncio.gather(
                    *(self._execute_step(scene, step) for step in batch),
                    return_exceptions=False,
                )
                results.extend(batch_results)
        return results

    async def _execute_sequential(self, scene: Scene, plan: TaskPlan) -> List[ToolResult]:
        results: List[ToolResult] = []
        for step in plan.steps:
            results.append(await self._execute_step(scene, step))
        return results

    async def _execute_step(self, scene: Scene, step: TaskStep) -> ToolResult:
        tool = self.registry.get(step.tool_name)
        if tool is None:
            return ToolResult(success=False, message=f"Unknown tool: {step.tool_name}")
        try:
            result = await tool.execute(scene, step.arguments)
            logger.info(
                "Tool %s execution %s: %s",
                step.tool_name,
                "succeeded" if result.success else "failed",
                result.message,
            )
            return result
        except Exception as e:
            logger.exception("Tool %s execution exception", step.tool_name)
            return ToolResult(
                success=False,
                message=f"Tool {step.tool_name} execution exception: {e}",
            )

    def _group_batches(self, steps: List[TaskStep]) -> List[List[TaskStep]]:
        """Group consecutive parallel-safe steps into batches.

        Target key derivation:
        - Tools with a ``target`` arg batch by distinct target id.
        - create_object batches by distinct name (or geometry_type fallback).
        - add_light / add_camera batch by distinct name (or type fallback).
        - Read-only / scene-level / generation tools always batch together.
        """
        batches: List[List[TaskStep]] = []
        current: List[TaskStep] = []
        seen_targets = set()
        for step in steps:
            is_safe = step.tool_name in _PARALLEL_SAFE_TOOLS
            target = self._target_key(step)
            conflict = target is not None and target in seen_targets
            if is_safe and not conflict:
                current.append(step)
                if target is not None:
                    seen_targets.add(target)
            else:
                if current:
                    batches.append(current)
                    current = []
                    seen_targets = set()
                batches.append([step])
        if current:
            batches.append(current)
        return batches

    @staticmethod
    def _target_key(step: TaskStep) -> Optional[str]:
        """Derive a conflict key for batching. None means always batchable."""
        name = step.tool_name
        # Per-target mutation tools
        if name in {
            "transform_object", "modify_geometry", "apply_material",
            "apply_material_preset", "delete_object", "focus_object",
            "select_object", "lock_object", "set_visibility", "rename_object",
            "snap_to_grid", "array_pattern", "mirror_object",
            # Advanced material & animation — all keyed by their target object
            "gradient_material", "keyframe_animation", "orbit_animation",
            "wave_animation", "bounce_animation",
        }:
            return str(step.arguments.get("target", "")) or None
        if name in {"modify_light", "delete_light"}:
            return str(step.arguments.get("target", "")) or None
        if name in {"modify_camera"}:
            return str(step.arguments.get("target", "")) or None
        # Material blend — two-operand; serialize when either operand overlaps
        if name == "material_blend":
            a = step.arguments.get("target_a", "")
            b = step.arguments.get("target_b", "")
            return f"blend:{','.join(sorted(str(x) for x in [a, b] if x))}"
        # Voronoi shatter — single source target
        if name == "voronoi_shatter":
            return str(step.arguments.get("target", "")) or None
        # Multi-target spatial ops — conflict if two calls share any target id
        if name in {"align_objects", "distribute_objects"}:
            targets = step.arguments.get("targets", [])
            if isinstance(targets, list) and targets:
                return f"{name}:{','.join(sorted(str(t) for t in targets))}"
            return None
        if name == "frame_view":
            targets = step.arguments.get("targets", [])
            if isinstance(targets, list) and targets:
                return f"frame:{','.join(sorted(str(t) for t in targets))}"
            # Single target frame
            return f"frame:{step.arguments.get('target', '')}"
        if name == "boolean_operation":
            # Two-operand op — serialize when either operand overlaps
            a = step.arguments.get("target_a", "")
            b = step.arguments.get("target_b", "")
            return f"bool:{','.join(sorted(str(x) for x in [a, b] if x))}"
        # Editor-mode mutation — global gizmo state, two calls always conflict
        if name == "set_transform_mode":
            return "editor:transform_mode"
        # Camera-level ops — batch by explicit camera arg; two calls with no
        # camera both resolve to the first camera, so they conflict and must
        # serialize (identical empty key enforces this).
        if name == "animate_camera":
            return f"anim_cam:{step.arguments.get('camera', '')}"
        if name == "snapshot_view":
            return f"snap:{step.arguments.get('camera', '') or step.arguments.get('name', '')}"
        # Independent appends — batch by name so duplicates don't collide
        if name == "create_object":
            return f"create:{step.arguments.get('name', step.arguments.get('geometry_type', ''))}"
        if name in {"add_light", "add_camera"}:
            return f"{name}:{step.arguments.get('name', step.arguments.get('light_type', step.arguments.get('camera_type', '')))}"
        # Read-only / scene-level / generation — always batchable
        return None

    def collect_deltas(self, results: List[ToolResult]) -> List[SceneDelta]:
        deltas: List[SceneDelta] = []
        for r in results:
            deltas.extend(r.deltas)
        return deltas


# Tools that can be safely executed in parallel within a single batch.
# Must stay in sync with trigen.planner._PARALLEL_SAFE_TOOLS.
_PARALLEL_SAFE_TOOLS = {
    "apply_material",
    "apply_material_preset",
    "transform_object",
    "modify_geometry",
    "create_object",
    "add_light",
    "add_camera",
    "delete_object",
    "delete_light",
    "modify_light",
    "modify_camera",
    "set_background",
    "set_fog",
    "toggle_grid",
    "set_grid_size",
    "set_view",
    "set_environment",
    "align_objects",
    "distribute_objects",
    "animate_camera",
    "snapshot_view",
    "scene_info",
    "list_objects",
    "analyze_scene",
    "export_scene",
    "measure_distance",
    "select_object",
    "focus_object",
    "dispatch_subagent",
    "generate_image",
    "generate_3d_asset",
    "generate_video",
    "generate_animation",
    "generate_music",
    "synthesize_speech",
    "transcribe_audio",
    "array_pattern",
    "mirror_object",
    "boolean_operation",
    "snap_to_grid",
    "lock_object",
    "set_visibility",
    "rename_object",
    "set_transform_mode",
    "frame_view",
    # Advanced material tools
    "gradient_material",
    "material_blend",
    # Object animation
    "keyframe_animation",
    "orbit_animation",
    "wave_animation",
    "bounce_animation",
    # Procedural generation
    "terrain_generator",
    "l_system",
    "create_spiral_staircase",
    "voronoi_shatter",
    # Creative skills
    "invoke_skill",
    # Scene-wide palette
    "randomize_palette",
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
}
