"""Sub-agent dispatch tool.

Spawns an isolated LLM conversation that receives a compact scene summary
and a task prompt from the caller. Two modes:

* **Read-only** (default): a single non-streaming ``complete()`` call. The
  sub-agent replies with text only — it cannot touch the scene. Use for
  analysis, suggestions, palette proposals, or sanity checks.

* **Mutating**: when the caller supplies a ``tools`` whitelist and sets
  ``mutate_scene`` to true, the sub-agent runs a bounded tool-call loop
  against the parent scene. Each tool call executes through the shared
  registry, and the accumulated scene deltas are returned to the parent
  agent as ``ToolResult.deltas``. Use to delegate a focused multi-step
  sub-task (e.g. "build a small forest of varied trees") while the parent
  agent continues with independent work.

The mutating loop is bounded by ``max_steps`` (hard-capped at 6) and
recursion-safe: ``dispatch_subagent`` is always filtered out of the
whitelist so a sub-agent cannot spawn further sub-agents.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from trigen.config import LLMConfig
from trigen.llm.client import LLMClient
from trigen.scene import Scene
from trigen.tools.base import SceneDelta, ToolBase, ToolRegistry, ToolResult

logger = logging.getLogger("trigen.tools.subagent")

# Hard ceiling on the mutating sub-agent's tool-call loop. The caller's
# ``max_steps`` is clamped to this value so a runaway request cannot
# inflate the loop indefinitely.
_MAX_STEPS_CAP = 6

# Tools a mutating sub-agent is never allowed to call, even if the caller
# whitelists them. ``dispatch_subagent`` is blocked to prevent unbounded
# recursion; ``invoke_skill`` is blocked because skills may themselves
# dispatch sub-agents or run open-ended recipes.
_FORBIDDEN_SUBAGENT_TOOLS = {"dispatch_subagent", "invoke_skill"}


_SUBAGENT_SYSTEM_READONLY = (
    "You are a focused Trigen sub-agent. You receive a read-only snapshot of "
    "the current 3D scene and a specific task from the orchestrating agent. "
    "Analyze, suggest, or reason about the scene as requested. You cannot "
    "modify the scene directly — return a concise, actionable text answer. "
    "Stay on-topic and do not ask follow-up questions."
)

_SUBAGENT_SYSTEM_MUTATING = (
    "You are a focused Trigen sub-agent with bounded tool access. You receive "
    "the current 3D scene summary and a single task from the orchestrating "
    "agent. Call the whitelisted tools to accomplish the task, then stop. You "
    "may call at most {max_steps} tool(s) in total. Each tool call must target "
    "an independent aspect of the scene — do not repeatedly mutate the same "
    "object. After your last tool call, reply with a one-line summary of what "
    "you produced. Do not ask follow-up questions and do not spawn further "
    "sub-agents."
)


# Specialized sub-agent profiles. Each profile bundles a curated tool
# whitelist, a tailored system prompt, and a default max_steps so the
# orchestrator can delegate a focused task without hand-picking tools.
# When the caller supplies ``profile``, the profile's whitelist is
# intersected with the caller's ``tools`` (so the caller can only narrow
# the profile, never broaden it) and the profile's system prompt is used
# in place of the generic mutating/readonly templates.
SUBAGENT_PROFILES: Dict[str, Dict[str, Any]] = {
    "lighting_specialist": {
        "description": (
            "Sub-agent focused on scene lighting: balancing intensities, "
            "choosing light types, placing rim/fill/key lights, and tuning "
            "shadows for mood."
        ),
        "tools": [
            "add_light", "modify_light", "delete_light",
            "scene_info", "list_objects", "describe_scene",
            "set_environment", "set_shadows",
        ],
        "default_max_steps": 4,
        "system_prompt": (
            "You are Trigen's lighting specialist sub-agent. You tune the "
            "scene's light rig for mood, balance, and physical plausibility. "
            "Prefer additive lighting (key + fill + rim) before removing "
            "lights. Adjust intensity in small increments (≤0.4) and watch "
            "shadow-casting lights for over-darkening. After your last tool "
            "call, reply with a one-line summary of the lighting changes."
        ),
    },
    "material_specialist": {
        "description": (
            "Sub-agent focused on surface appearance: PBR presets, color "
            "palettes, gradients, and per-property fine tuning."
        ),
        "tools": [
            "apply_material", "apply_material_preset", "set_material_property",
            "gradient_material", "material_blend", "randomize_palette",
            "apply_material_batch", "scene_info", "list_objects",
        ],
        "default_max_steps": 4,
        "system_prompt": (
            "You are Trigen's material specialist sub-agent. You craft "
            "coherent surface appearance: pick presets that match the "
            "project's aesthetic, blend gradients where appropriate, and "
            "keep the palette within 5 distinct hues. Avoid pure-black or "
            "pure-white albedo unless explicitly requested. After your last "
            "tool call, reply with a one-line summary of the material changes."
        ),
    },
    "composition_specialist": {
        "description": (
            "Sub-agent focused on spatial composition: framing, alignment, "
            "distribution, rule-of-thirds, and crowd/cluster layouts."
        ),
        "tools": [
            "transform_object", "align_objects", "distribute_objects",
            "arrange_layout", "smart_compose", "snap_to_grid", "frame_view",
            "set_view", "scene_info", "describe_scene", "list_objects",
        ],
        "default_max_steps": 5,
        "system_prompt": (
            "You are Trigen's composition specialist sub-agent. You improve "
            "spatial composition: rule-of-thirds framing, balanced clusters, "
            "rhythmic spacing, and clear silhouettes. Avoid perfectly aligned "
            "grids unless explicitly requested; prefer jittered but readable "
            "arrangements. After your last tool call, reply with a one-line "
            "summary of the composition changes."
        ),
    },
    "animation_specialist": {
        "description": (
            "Sub-agent focused on motion: keyframes, orbit/wave/bounce "
            "patterns, and playback pacing."
        ),
        "tools": [
            "keyframe_animation", "orbit_animation", "wave_animation",
            "bounce_animation", "animate_camera", "play_animation",
            "pause_animation", "seek_animation", "set_playback_speed",
            "scene_info", "list_objects",
        ],
        "default_max_steps": 4,
        "system_prompt": (
            "You are Trigen's animation specialist sub-agent. You design "
            "lightweight, legible motion: one focal animation per turn, "
            "amplitudes kept modest (≤2 units), periods ≥1s to avoid strobing. "
            "After your last tool call, reply with a one-line summary of the "
            "animation you created."
        ),
    },
    "geometry_specialist": {
        "description": (
            "Sub-agent focused on geometry editing: creation, boolean ops, "
            "mirroring, arrays, and primitive parameter tuning."
        ),
        "tools": [
            "create_object", "modify_geometry", "duplicate_object",
            "delete_object", "mirror_object", "array_pattern",
            "boolean_operation", "set_geometry_params", "snap_to_grid",
            "scene_info", "list_objects",
        ],
        "default_max_steps": 5,
        "system_prompt": (
            "You are Trigen's geometry specialist sub-agent. You build and "
            "edit meshes: prefer non-destructive ops (duplicate, mirror, "
            "array) over boolean unions; keep poly counts low; name new "
            "objects by their role (e.g. 'Pillar', 'RoofBeam') not their "
            "shape. After your last tool call, reply with a one-line summary "
            "of the geometry you produced."
        ),
    },
    "critique_specialist": {
        "description": (
            "Sub-agent focused on editorial review: running the scene "
            "critique, prioritizing findings by severity, and applying "
            "concrete fixes for the highest-impact problems."
        ),
        "tools": [
            "critique_scene", "analyze_scene", "describe_scene",
            "scene_statistics", "scene_info", "list_objects",
            "add_light", "modify_light", "transform_object",
            "apply_material", "arrange_layout", "set_background",
        ],
        "default_max_steps": 4,
        "system_prompt": (
            "You are Trigen's critique specialist sub-agent. You act as a "
            "fresh pair of editorial eyes. First call critique_scene to get "
            "the ranked findings, then address only the highest-severity "
            "issues (high before medium before low) using their proposed "
            "fixes. Never introduce new problems while fixing — keep changes "
            "minimal and legible. After your last tool call, reply with a "
            "one-line summary of the problems you found and fixed."
        ),
    },
}


_SUBAGENT_PARAMS = {
    "type": "object",
    "properties": {
        "task": {
            "type": "string",
            "description": "The instruction for the sub-agent (e.g. 'evaluate the lighting balance' "
            "or 'build a small forest of 3 varied trees').",
        },
        "tools": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Optional whitelist of tool names the sub-agent may call. When omitted "
            "or empty, the sub-agent runs in read-only mode and returns a text answer. When "
            "non-empty AND mutate_scene is true, the sub-agent runs a bounded tool-call loop "
            "against the parent scene.",
        },
        "mutate_scene": {
            "type": "boolean",
            "description": "When true (and 'tools' is non-empty), the sub-agent's tool calls "
            "execute against the parent scene and the resulting deltas are returned to the "
            "caller. When false (default), the sub-agent is read-only.",
        },
        "max_steps": {
            "type": "integer",
            "description": "Maximum number of tool calls the mutating sub-agent may issue. "
            "Clamped to a hard cap of 6. Ignored in read-only mode.",
            "minimum": 1,
            "maximum": _MAX_STEPS_CAP,
        },
        "model": {
            "type": "string",
            "description": "Optional model id to use for the sub-agent. If omitted, the default "
            "configured model is used.",
        },
        "profile": {
            "type": "string",
            "enum": list(SUBAGENT_PROFILES.keys()),
            "description": (
                "Optional specialist profile. When supplied, the sub-agent "
                "uses the profile's curated tool whitelist (intersected with "
                "any caller-supplied 'tools') and the profile's tailored "
                "system prompt. Profiles: lighting_specialist, "
                "material_specialist, composition_specialist, "
                "animation_specialist, geometry_specialist, "
                "critique_specialist. When a profile "
                "is supplied without an explicit 'tools' list, the profile's "
                "default whitelist is used and mutate_scene is treated as "
                "true unless explicitly set to false."
            ),
        },
    },
    "required": ["task"],
}


class DispatchSubagentTool(ToolBase):
    """Dispatch a sub-agent conversation.

    Read-only by default: a single non-streaming ``complete()`` call with a
    compact scene summary injected as context. When the caller supplies a
    ``tools`` whitelist and sets ``mutate_scene`` to true, the sub-agent
    runs a bounded tool-call loop whose deltas are returned to the parent
    agent for merging.
    """

    name = "dispatch_subagent"
    description = (
        "Dispatch a sub-agent to analyze the scene or execute a bounded "
        "sub-task. Read-only by default (returns a text answer). Pass a "
        "tool whitelist plus mutate_scene=true to let the sub-agent run a "
        "short tool loop that mutates the scene; the resulting deltas are "
        "merged back into the parent scene."
    )

    def __init__(
        self,
        config: Optional[LLMConfig] = None,
        registry: Optional[ToolRegistry] = None,
    ) -> None:
        self.llm_config = config or LLMConfig()
        self.registry = registry

    def schema(self) -> Dict[str, Any]:
        return _SUBAGENT_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        task = arguments.get("task", "").strip()
        if not task:
            return ToolResult(success=False, message="Missing 'task' argument for sub-agent.")

        model = arguments.get("model") or None
        tools_whitelist = self._normalize_whitelist(arguments.get("tools"))
        mutate_scene = bool(arguments.get("mutate_scene", False))
        profile_name = arguments.get("profile")
        profile = None
        if profile_name:
            profile = SUBAGENT_PROFILES.get(profile_name)
            if profile is None:
                return ToolResult(
                    success=False,
                    message=(
                        f"Unknown sub-agent profile: {profile_name}. "
                        f"Available: {', '.join(SUBAGENT_PROFILES.keys())}"
                    ),
                )
            # When a profile is supplied without an explicit tools list,
            # inherit the profile's whitelist. When the caller also supplied
            # a tools list, intersect it with the profile's whitelist so the
            # caller can only narrow the profile, never broaden it.
            profile_tools = list(profile.get("tools", []))
            if not tools_whitelist:
                tools_whitelist = profile_tools
            else:
                allowed = set(profile_tools)
                tools_whitelist = [t for t in tools_whitelist if t in allowed]
            # A profile implies mutating mode unless the caller explicitly
            # opted out via mutate_scene=false.
            if "mutate_scene" not in arguments:
                mutate_scene = True
            # Apply the profile's default max_steps when the caller did not.
            if arguments.get("max_steps") is None:
                arguments = dict(arguments)
                arguments["max_steps"] = int(profile.get("default_max_steps", 3))

        # Mutating mode requires both a non-empty whitelist and a registry.
        if mutate_scene and tools_whitelist:
            if self.registry is None:
                return ToolResult(
                    success=False,
                    message="Sub-agent mutating mode requires a tool registry, none configured.",
                )
            return await self._run_mutating(scene, task, tools_whitelist, arguments, model, profile=profile)

        # Default: read-only single-shot analysis.
        return await self._run_readonly(scene, task, model, profile=profile)

    # ------------------------------------------------------------------
    # Read-only path
    # ------------------------------------------------------------------

    async def _run_readonly(
        self,
        scene: Scene,
        task: str,
        model: Optional[str],
        profile: Optional[Dict[str, Any]] = None,
    ) -> ToolResult:
        client = LLMClient(self.llm_config)
        summary = self._scene_summary(scene)
        system_prompt = _SUBAGENT_SYSTEM_READONLY
        if profile is not None:
            system_prompt = str(profile.get("system_prompt", system_prompt))
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"{summary}\n\nTask: {task}"},
        ]
        try:
            response = await client.complete(messages=messages, system=system_prompt, model=model)
        except Exception as exc:
            logger.exception("Sub-agent complete() failed")
            return ToolResult(success=False, message=f"Sub-agent call failed: {exc}")

        content = response.content or ""
        if response.finish_reason == "error":
            return ToolResult(success=False, message=f"Sub-agent error: {content}")

        data = {
            "task": task,
            "model": model or self.llm_config.model,
            "finish_reason": response.finish_reason,
            "mode": "readonly",
        }
        if profile is not None:
            data["profile"] = profile.get("name") if isinstance(profile, dict) and "name" in profile else None
        return ToolResult(
            success=True,
            message=content,
            data=data,
        )

    # ------------------------------------------------------------------
    # Mutating path — bounded tool-call loop
    # ------------------------------------------------------------------

    async def _run_mutating(
        self,
        scene: Scene,
        task: str,
        whitelist: List[str],
        arguments: Dict[str, Any],
        model: Optional[str],
        profile: Optional[Dict[str, Any]] = None,
    ) -> ToolResult:
        # Resolve the effective whitelist: drop forbidden names and any
        # name not present in the registry.
        available_schemas: List[Dict[str, Any]] = []
        for name in whitelist:
            if name in _FORBIDDEN_SUBAGENT_TOOLS:
                continue
            tool = self.registry.get(name) if self.registry else None
            if tool is None:
                continue
            available_schemas.append(
                {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.schema(),
                }
            )
        if not available_schemas:
            return ToolResult(
                success=False,
                message="Sub-agent mutating mode requested but no whitelisted tools resolved.",
            )

        requested_steps = arguments.get("max_steps")
        try:
            max_steps = int(requested_steps) if requested_steps is not None else 3
        except (TypeError, ValueError):
            max_steps = 3
        max_steps = max(1, min(max_steps, _MAX_STEPS_CAP))

        # When a profile is supplied, use its tailored system prompt but
        # append the bounded-loop directive so the model still knows the
        # step budget. Otherwise fall back to the generic mutating template.
        if profile is not None:
            base_prompt = str(profile.get("system_prompt", ""))
            system_prompt = (
                base_prompt
                + f" You may call at most {max_steps} tool(s) in total. "
                "Do not ask follow-up questions and do not spawn further sub-agents."
            )
        else:
            system_prompt = _SUBAGENT_SYSTEM_MUTATING.format(max_steps=max_steps)
        summary = self._scene_summary(scene)

        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": (
                    f"{summary}\n\nTask: {task}\n\n"
                    f"You may call at most {max_steps} tool(s). "
                    f"Available tools: {', '.join(s['name'] for s in available_schemas)}."
                ),
            },
        ]

        client = LLMClient(self.llm_config)
        deltas: List[SceneDelta] = []
        steps_taken = 0
        step_log: List[Dict[str, Any]] = []
        final_text = ""

        while steps_taken < max_steps:
            try:
                response = await client.complete(
                    messages=messages,
                    tools=available_schemas,
                    system=system_prompt,
                    model=model,
                )
            except Exception as exc:
                logger.exception("Sub-agent mutating complete() failed")
                return ToolResult(
                    success=False,
                    message=f"Sub-agent LLM call failed: {exc}",
                    deltas=deltas,
                    data={"task": task, "mode": "mutating", "steps_taken": steps_taken, "steps": step_log},
                )

            if response.finish_reason == "error":
                return ToolResult(
                    success=False,
                    message=f"Sub-agent error: {response.content}",
                    deltas=deltas,
                    data={"task": task, "mode": "mutating", "steps_taken": steps_taken, "steps": step_log},
                )

            # Append the assistant turn (with any tool_calls) to the loop
            # messages so the next iteration sees the full transcript.
            assistant_msg: Dict[str, Any] = {"role": "assistant", "content": response.content or ""}
            if response.tool_calls:
                assistant_msg["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments, ensure_ascii=False),
                        },
                    }
                    for tc in response.tool_calls
                ]
            messages.append(assistant_msg)
            final_text = response.content or ""

            if not response.tool_calls:
                # No more tool calls — sub-agent is done reasoning.
                break

            # Execute each tool call from this turn. Tool calls within a
            # single LLM turn are executed sequentially to keep scene
            # mutations predictable; the parent executor handles parallel
            # batching across independent dispatch_subagent invocations.
            for tc in response.tool_calls:
                if steps_taken >= max_steps:
                    break
                tool = self.registry.get(tc.name) if self.registry else None
                if tool is None or tc.name in _FORBIDDEN_SUBAGENT_TOOLS:
                    tool_result = ToolResult(
                        success=False,
                        message=f"Tool '{tc.name}' is not available to the sub-agent.",
                    )
                else:
                    try:
                        tool_result = await tool.execute(scene, tc.arguments)
                    except Exception as exc:
                        logger.exception("Sub-agent tool %s raised", tc.name)
                        tool_result = ToolResult(success=False, message=f"Execution error: {exc}")
                deltas.extend(tool_result.deltas)
                step_log.append(
                    {
                        "tool": tc.name,
                        "success": tool_result.success,
                        "message": tool_result.message[:200],
                    }
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": tool_result.message,
                    }
                )
                steps_taken += 1

        summary_line = (
            final_text.strip()
            or f"Sub-agent completed {steps_taken} tool call(s); produced {len(deltas)} scene delta(s)."
        )
        data = {
            "task": task,
            "mode": "mutating",
            "model": model or self.llm_config.model,
            "steps_taken": steps_taken,
            "steps": step_log,
        }
        if profile is not None:
            # Surface the profile name (key in SUBAGENT_PROFILES) so callers
            # can audit which specialist ran. We pass the resolved profile
            # dict in via execute(); recover the name by reverse lookup.
            for k, v in SUBAGENT_PROFILES.items():
                if v is profile:
                    data["profile"] = k
                    break
        return ToolResult(
            success=True,
            message=summary_line,
            deltas=deltas,
            data=data,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_whitelist(raw: Any) -> List[str]:
        if not isinstance(raw, list):
            return []
        names: List[str] = []
        seen: set = set()
        for item in raw:
            if isinstance(item, str):
                clean = item.strip()
                if clean and clean not in seen:
                    seen.add(clean)
                    names.append(clean)
        return names

    @staticmethod
    def _scene_summary(scene: Scene) -> str:
        scene_dict = scene.to_dict()
        obj_lines: List[str] = []
        for obj in scene_dict.get("objects", []):
            geo = obj.get("geometry", {})
            mat = obj.get("material", {})
            pos = obj.get("transform", {}).get("position", [0, 0, 0])
            obj_lines.append(
                f"- {obj.get('name','?')} ({geo.get('type','?')}) "
                f"color={mat.get('color','?')} pos={pos}"
            )
        light_lines: List[str] = []
        for light in scene_dict.get("lights", []):
            light_lines.append(
                f"- {light.get('name','?')} ({light.get('type','?')}) "
                f"intensity={light.get('intensity','?')}"
            )
        return (
            f"Scene summary: {len(obj_lines)} objects, {len(light_lines)} lights, "
            f"background={scene_dict.get('background','?')}\n"
            f"Objects:\n" + ("\n".join(obj_lines) if obj_lines else "(empty)") + "\n"
            f"Lights:\n" + ("\n".join(light_lines) if light_lines else "(empty)")
        )
