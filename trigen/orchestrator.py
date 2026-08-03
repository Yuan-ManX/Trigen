"""Agent orchestrator — Trigen intelligent body's central scheduling core.

Unifies LLM reasoning, task planning, tool execution, and conversation
memory, driving real-time frontend updates via streaming events. Supports
multi-round tool-call loops, parallel execution, and thinking-process
exposure until the LLM yields its final text reply.

Event stream:
  thinking     — Agent reasoning trace
  text_delta   — LLM text fragment
  tool_call    — Tool call start
  tool_result  — Tool execution result
  scene_update — Scene mutation
  done         — End of this conversation turn
  error        — Error
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, AsyncIterator, Dict, List, Optional

from trigen.config import AgentConfig
from trigen.executor import TaskExecutor
from trigen.hooks import HookEvent, HookRegistry
from trigen.memory import ConversationMemory
from trigen.memory_persistence import persistence as memory_persistence
from trigen.planner import TaskPlanner, TaskPlan, TokenBudget, prevalidate_step
from trigen.llm.client import LLMClient, LLMStreamChunk
from trigen.llm.prompts import SYSTEM_PROMPT, build_scene_summary
from trigen.llm.router import router as model_router
from trigen.llm.scene_edit_parser import SceneEditOp, parse_scene_edit
from trigen.intent_parser import parse_message, ParsedIntent
from trigen.scene import Scene, LightObject
from trigen.suggestions import generate_suggestions
from trigen.tools import (
    AddCameraTool,
    AddLightTool,
    AlignObjectsTool,
    AnimateCameraTool,
    ApplyMaterialTool,
    ApplyMaterialPresetTool,
    ArrayPatternTool,
    ArrangeLayoutTool,
    BounceAnimationTool,
    BooleanOperationTool,
    CaptureViewportTool,
    CreateObjectTool,
    DeleteLightTool,
    DeleteObjectTool,
    DispatchSubagentTool,
    DistributeObjectsTool,
    DuplicateObjectTool,
    ExportSceneTool,
    FocusObjectTool,
    FocusPanelTool,
    FrameViewTool,
    Generate3DAssetTool,
    GenerateAnimationTool,
    GenerateImageTool,
    GenerateMusicTool,
    GenerateVideoTool,
    GradientMaterialTool,
    GroupObjectsTool,
    InvokeSkillTool,
    KeyframeAnimationTool,
    LSystemTool,
    ListObjectsTool,
    LockObjectTool,
    MaterialBlendTool,
    MeasureDistanceTool,
    MirrorObjectTool,
    ModifyCameraTool,
    ModifyGeometryTool,
    ModifyLightTool,
    OrbitAnimationTool,
    PauseAnimationTool,
    PlayAnimationTool,
    RandomizePaletteTool,
    RedoSceneTool,
    RenameObjectTool,
    SceneInfoTool,
    SeekAnimationTool,
    SelectObjectTool,
    SetBackgroundTool,
    SetEnvironmentTool,
    SetFogTool,
    SetGridSizeTool,
    SetPlaybackSpeedTool,
    SetRenderQualityTool,
    SetSelectionTool,
    SetTransformModeTool,
    SetViewTool,
    SetViewportCameraTool,
    SetVisibilityTool,
    SnapToGridTool,
    SnapshotViewTool,
    SmartComposeTool,
    SpiralStaircaseTool,
    SynthesizeSpeechTool,
    TerrainGeneratorTool,
    ToggleGridSnappingTool,
    ToggleGridTool,
    TranscribeAudioTool,
    TransformObjectTool,
    UndoSceneTool,
    UngroupObjectsTool,
    VoronoiShatterTool,
    WaveAnimationTool,
)
from trigen.tools.base import ToolRegistry, ToolResult
from trigen.tools.scene_management_tools import (
    AssignToGroupTool,
    DeleteCameraTool,
    ReorderLayerTool,
    RenameGroupTool,
    SelectAllTool,
)
from trigen.tools.img2scene_tool import ImageToSceneTool
from trigen.tools.scene_analyzer import SceneAnalyzerTool
from trigen.tools.code_exporter import CodeExporterTool
from trigen.tools.advanced_editor_tools import (
    ApplyMaterialBatchTool,
    IsolateObjectTool,
    ResetTransformTool,
    SetClippingPlaneTool,
    SetObjectLayerTool,
    SetObjectPivotTool,
)

logger = logging.getLogger("trigen.orchestrator")


# Central tool taxonomy. Maps every registered tool name to a coarse
# functional category. Applied at the end of ``_build_registry`` so the
# canonical taxonomy lives in one place and individual tool modules stay
# free of category declarations. Categories are surfaced via the
# /api/tools/categories endpoint and used by smart tool selection to
# inject only the relevant subset into each LLM call.
_TOOL_CATEGORIES: Dict[str, str] = {
    # creation — bring new geometry into the scene
    "create_object": "creation",
    "modify_geometry": "creation",
    "duplicate_object": "creation",
    "delete_object": "creation",
    "array_pattern": "creation",
    "boolean_operation": "creation",
    # transform — move / scale / rotate / snap existing objects
    "transform_object": "transform",
    "mirror_object": "transform",
    "align_objects": "transform",
    "distribute_objects": "transform",
    "snap_to_grid": "transform",
    "reset_transform": "transform",
    # material — surface appearance
    "apply_material": "material",
    "apply_material_preset": "material",
    "gradient_material": "material",
    "material_blend": "material",
    "randomize_palette": "material",
    "apply_material_batch": "material",
    # lighting
    "add_light": "lighting",
    "modify_light": "lighting",
    "delete_light": "lighting",
    # camera
    "add_camera": "camera",
    "modify_camera": "camera",
    "delete_camera": "camera",
    "set_view": "camera",
    "snapshot_view": "camera",
    "capture_viewport": "camera",
    "animate_camera": "camera",
    # scene — scene-level organization & environment
    "group_objects": "scene",
    "ungroup_objects": "scene",
    "assign_to_group": "scene",
    "rename_group": "scene",
    "reorder_layer": "scene",
    "arrange_layout": "scene",
    "set_background": "scene",
    "set_fog": "scene",
    "set_environment": "scene",
    "toggle_grid": "scene",
    "set_grid_size": "scene",
    "smart_compose": "scene",
    # editor — viewport / selection / session editor control
    "select_object": "editor",
    "select_all": "editor",
    "set_selection": "editor",
    "focus_object": "editor",
    "focus_panel": "editor",
    "lock_object": "editor",
    "set_visibility": "editor",
    "rename_object": "editor",
    "set_transform_mode": "editor",
    "frame_view": "editor",
    "set_viewport_camera": "editor",
    "toggle_grid_snapping": "editor",
    "set_render_quality": "editor",
    "set_clipping_plane": "editor",
    "set_object_pivot": "editor",
    "set_object_layer": "editor",
    "isolate_object": "editor",
    "undo_scene": "editor",
    "redo_scene": "editor",
    # animation — keyframe / playback control
    "keyframe_animation": "animation",
    "orbit_animation": "animation",
    "wave_animation": "animation",
    "bounce_animation": "animation",
    "play_animation": "animation",
    "pause_animation": "animation",
    "seek_animation": "animation",
    "set_playback_speed": "animation",
    # procedural — generative geometry recipes
    "terrain_generator": "procedural",
    "l_system": "procedural",
    "spiral_staircase": "procedural",
    "create_spiral_staircase": "procedural",
    "voronoi_shatter": "procedural",
    # multimodal — external generative media
    "generate_image": "multimodal",
    "generate_3d_asset": "multimodal",
    "generate_video": "multimodal",
    "generate_animation": "multimodal",
    "generate_music": "multimodal",
    "synthesize_speech": "multimodal",
    "transcribe_audio": "multimodal",
    "image_to_3d": "multimodal",
    # export
    "export_scene": "export",
    "export_code": "export",
    # inspection — read-only queries
    "scene_info": "inspection",
    "list_objects": "inspection",
    "analyze_scene": "inspection",
    "measure_distance": "inspection",
    # skills — creative recipes & sub-agent dispatch
    "invoke_skill": "skills",
    "dispatch_subagent": "skills",
}


class EventType(str, Enum):
    THINKING = "thinking"
    TEXT_DELTA = "text_delta"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    SCENE_UPDATE = "scene_update"
    # Structured plan roadmap emitted at the planning phase, plus per-step
    # status transitions as the turn executes. The frontend renders these as
    # a live checklist so the user can follow the agent's decomposition.
    PLAN = "plan"
    PLAN_UPDATE = "plan_update"
    DONE = "done"
    ERROR = "error"


@dataclass
class AgentEvent:
    """Agent output event.

    ``seq`` is a monotonically increasing sequence number assigned by the
    orchestrator so consumers can order events deterministically. ``ts`` is
    the Unix timestamp (seconds) at which the event was stamped.
    """

    type: EventType
    data: Dict[str, Any]
    seq: int = 0
    ts: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type.value,
            "data": self.data,
            "seq": self.seq,
            "ts": self.ts,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)


class AgentOrchestrator:
    """Trigen Agent orchestrator."""

    def __init__(self, config: Optional[AgentConfig] = None):
        self.config = config or AgentConfig()
        self.config.ensure_workspace()
        self.llm = LLMClient(self.config.llm)
        self.registry = self._build_registry()
        self.planner = TaskPlanner()
        self.executor = TaskExecutor(self.registry)
        self.hooks = HookRegistry()
        self._sessions: Dict[str, ConversationMemory] = {}
        self._scenes: Dict[str, Scene] = {}
        self._event_seq = 0
        # Per-session scene history stacks for undo/redo. Each entry is a
        # full scene snapshot (dict) captured before a mutating operation.
        self._scene_history: Dict[str, List[Dict[str, Any]]] = {}
        self._scene_redo: Dict[str, List[Dict[str, Any]]] = {}
        # Per-session interrupt flags. When set, the running turn exits at
        # the next iteration boundary.
        self._interrupts: Dict[str, bool] = {}
        self._max_history = 50  # cap per session to bound memory

    def _build_registry(self) -> ToolRegistry:
        registry = ToolRegistry()
        # Geometry creation & editing
        registry.register(CreateObjectTool())
        registry.register(TransformObjectTool())
        registry.register(ModifyGeometryTool())
        registry.register(DuplicateObjectTool())
        registry.register(DeleteObjectTool())
        registry.register(ListObjectsTool())
        # Material
        registry.register(ApplyMaterialTool())
        registry.register(ApplyMaterialPresetTool())
        # Lighting
        registry.register(AddLightTool())
        registry.register(ModifyLightTool())
        registry.register(DeleteLightTool())
        # Camera
        registry.register(AddCameraTool())
        registry.register(ModifyCameraTool())
        registry.register(SetViewTool())
        # Scene organization
        registry.register(GroupObjectsTool())
        registry.register(UngroupObjectsTool())
        registry.register(SetBackgroundTool())
        registry.register(SetFogTool())
        registry.register(ArrangeLayoutTool())
        registry.register(AssignToGroupTool())
        registry.register(RenameGroupTool())
        registry.register(ReorderLayerTool())
        registry.register(SelectAllTool())
        registry.register(DeleteCameraTool())
        # Spatial manipulation & measurement
        registry.register(AlignObjectsTool())
        registry.register(DistributeObjectsTool())
        registry.register(AnimateCameraTool())
        registry.register(SetEnvironmentTool())
        registry.register(SnapshotViewTool())
        registry.register(MeasureDistanceTool())
        # Composite modelling
        registry.register(ArrayPatternTool())
        registry.register(MirrorObjectTool())
        registry.register(BooleanOperationTool())
        registry.register(SnapToGridTool())
        # Scene inspection
        registry.register(SceneInfoTool())
        # Grid control
        registry.register(ToggleGridTool())
        registry.register(SetGridSizeTool())
        # Smart composition
        registry.register(SmartComposeTool())
        # Editor control
        registry.register(SelectObjectTool())
        registry.register(FocusObjectTool())
        registry.register(LockObjectTool())
        registry.register(SetVisibilityTool())
        registry.register(RenameObjectTool())
        registry.register(SetTransformModeTool())
        registry.register(FrameViewTool())
        # Viewport / playback / session editor control
        registry.register(SetViewportCameraTool())
        registry.register(PlayAnimationTool())
        registry.register(PauseAnimationTool())
        registry.register(SeekAnimationTool())
        registry.register(SetSelectionTool())
        registry.register(CaptureViewportTool())
        registry.register(SetPlaybackSpeedTool())
        registry.register(ToggleGridSnappingTool())
        registry.register(FocusPanelTool())
        registry.register(UndoSceneTool())
        registry.register(RedoSceneTool())
        registry.register(SetRenderQualityTool())
        # Export
        registry.register(ExportSceneTool(workspace_dir=self.config.workspace_dir))
        registry.register(CodeExporterTool(workspace_dir=self.config.workspace_dir))
        # Multimodal reconstruction — receives the registry so the optional
        # refine step can invoke generate_3d_asset (Meshy/Tripo) internally.
        registry.register(ImageToSceneTool(self.config.llm, registry=registry))
        # Scene analysis
        registry.register(SceneAnalyzerTool())
        # Sub-agent dispatch — receives the registry so mutating mode can
        # resolve and execute whitelisted tools against the parent scene.
        registry.register(DispatchSubagentTool(self.config.llm, registry=registry))
        # Multimodal generation (image / 3D / video / animation / speech / transcription / music)
        registry.register(GenerateImageTool())
        registry.register(Generate3DAssetTool())
        registry.register(GenerateVideoTool())
        registry.register(GenerateAnimationTool())
        registry.register(GenerateMusicTool())
        registry.register(SynthesizeSpeechTool())
        registry.register(TranscribeAudioTool())
        # Procedural generation
        registry.register(TerrainGeneratorTool())
        registry.register(LSystemTool())
        registry.register(SpiralStaircaseTool())
        registry.register(VoronoiShatterTool())
        # Object animation
        registry.register(KeyframeAnimationTool())
        registry.register(OrbitAnimationTool())
        registry.register(WaveAnimationTool())
        registry.register(BounceAnimationTool())
        # Advanced material
        registry.register(GradientMaterialTool())
        registry.register(MaterialBlendTool())
        registry.register(RandomizePaletteTool())
        # Creative skills — receives the registry so expanded steps can execute
        registry.register(InvokeSkillTool(registry=registry))
        # Advanced editor control (solo mode, transform presets, clipping,
        # pivot editing, batch material, named-layer organization)
        registry.register(IsolateObjectTool())
        registry.register(ResetTransformTool())
        registry.register(SetClippingPlaneTool())
        registry.register(SetObjectPivotTool())
        registry.register(ApplyMaterialBatchTool())
        registry.register(SetObjectLayerTool())

        # Apply the central category taxonomy to every registered tool so
        # the canonical mapping lives in one place (_TOOL_CATEGORIES above).
        # Tools not present in the map keep their default "general" category.
        for tool in registry.all():
            cat = _TOOL_CATEGORIES.get(tool.name)
            if cat:
                tool.category = cat
        return registry

    def get_memory(self, session_id: str) -> ConversationMemory:
        if session_id not in self._sessions:
            # Try to load from persistence first
            loaded = memory_persistence.load(session_id)
            if loaded is not None:
                self._sessions[session_id] = loaded
            else:
                self._sessions[session_id] = ConversationMemory(
                    session_id=session_id, window_size=self.config.memory_window
                )
        return self._sessions[session_id]

    def get_scene(self, session_id: str) -> Scene:
        if session_id not in self._scenes:
            scene = Scene()
            # Default scene: a directional key light + ambient fill
            scene.lights.append(
                LightObject(name="KeyLight", type="directional", intensity=1.2, position=[5, 8, 5])
            )
            scene.lights.append(
                LightObject(name="Ambient", type="ambient", intensity=0.4, position=[0, 0, 0])
            )
            self._scenes[session_id] = scene
        return self._scenes[session_id]

    def reset_session(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)
        self._scenes.pop(session_id, None)
        self._scene_history.pop(session_id, None)
        self._scene_redo.pop(session_id, None)
        self._interrupts.pop(session_id, None)
        memory_persistence.delete(session_id)

    # ------------------------------------------------------------------
    # Scene history (undo / redo) — backend snapshot stack
    # ------------------------------------------------------------------

    def push_scene_history(self, session_id: str) -> None:
        """Snapshot the current scene before a mutating API operation."""
        scene = self.get_scene(session_id)
        self._scene_history.setdefault(session_id, []).append(scene.to_dict())
        # Cap the stack to bound memory.
        if len(self._scene_history[session_id]) > self._max_history:
            self._scene_history[session_id].pop(0)
        # Any new mutation clears the redo stack.
        self._scene_redo.pop(session_id, None)

    def undo_scene(self, session_id: str) -> Dict[str, Any]:
        """Restore the previous scene snapshot.

        Returns a dict with ``applied`` (bool), ``scene`` (current snapshot),
        and ``remaining`` (how many undo entries still remain). When the
        history stack is empty, ``applied`` is False and the scene is unchanged.
        """
        history = self._scene_history.get(session_id, [])
        if not history:
            return {"applied": False, "scene": self.get_scene(session_id).to_dict(), "remaining": 0}
        scene = self.get_scene(session_id)
        # Push the current state onto the redo stack before restoring.
        self._scene_redo.setdefault(session_id, []).append(scene.to_dict())
        prev = history.pop()
        # Scene.from_dict returns a NEW instance; replace the stored scene
        # so all subsequent get_scene() callers see the restored state.
        restored = Scene.from_dict(prev)
        self._scenes[session_id] = restored
        return {"applied": True, "scene": restored.to_dict(), "remaining": len(history)}

    def redo_scene(self, session_id: str) -> Dict[str, Any]:
        """Re-apply the most recently undone scene snapshot.

        Returns a dict with ``applied`` (bool), ``scene`` (current snapshot),
        and ``remaining`` (how many redo entries still remain).
        """
        redo = self._scene_redo.get(session_id, [])
        if not redo:
            return {"applied": False, "scene": self.get_scene(session_id).to_dict(), "remaining": 0}
        scene = self.get_scene(session_id)
        # Push the current state back onto the history stack.
        self._scene_history.setdefault(session_id, []).append(scene.to_dict())
        nxt = redo.pop()
        restored = Scene.from_dict(nxt)
        self._scenes[session_id] = restored
        return {"applied": True, "scene": restored.to_dict(), "remaining": len(redo)}

    def history_status(self, session_id: str) -> Dict[str, int]:
        """Return the undo/redo stack depths for a session."""
        return {
            "undo_depth": len(self._scene_history.get(session_id, [])),
            "redo_depth": len(self._scene_redo.get(session_id, [])),
        }

    @staticmethod
    def _scene_suggestions(scene: Scene) -> List[Dict[str, Any]]:
        """Compute proactive next-action suggestions for the current scene.

        Wrapped so a failure in the suggestion engine never breaks the
        turn's ``done`` event — the suggestions field simply falls back
        to an empty list.
        """
        try:
            return generate_suggestions(scene.to_dict())
        except Exception:
            logger.exception("Suggestion generation failed")
            return []

    # ------------------------------------------------------------------
    # Interrupt — cooperative cancellation of a running turn
    # ------------------------------------------------------------------

    def request_interrupt(self, session_id: str) -> bool:
        """Request cancellation of the currently running turn for a session.

        The running turn checks the flag at each iteration boundary and
        exits cleanly. Returns True if a flag was set (a turn may or may
        not be running — the flag is sticky until consumed).
        """
        self._interrupts[session_id] = True
        return True

    def _consume_interrupt(self, session_id: str) -> bool:
        """Return True if an interrupt was requested, clearing the flag."""
        if self._interrupts.get(session_id):
            self._interrupts[session_id] = False
            return True
        return False

    # ------------------------------------------------------------------
    # Plan-only — produce a structured plan without executing tools
    # ------------------------------------------------------------------

    async def plan_only(
        self, user_message: str, session_id: str = "default", model: Optional[str] = None
    ) -> Dict[str, Any]:
        """Run a single LLM pass and return the structured plan, no execution.

        Adds the user message to memory, streams the LLM once to collect
        any tool calls + reasoning, then builds a TaskPlan via the planner
        and returns its structured payload. Tools are NOT executed and the
        scene is NOT mutated. Useful for previewing what the agent would do.

        Each tool_call entry is tagged with ``requires_approval`` and the
        response carries ``has_destructive_steps`` + ``destructive_steps`` so
        the frontend can surface a confirmation dialog before execution.

        When no LLM is configured, falls back to the offline rule parser to
        produce a preview so the destructive-action confirmation flow still
        works in offline mode.
        """
        memory = self.get_memory(session_id)
        scene = self.get_scene(session_id)
        memory.add_user(user_message)

        # Offline fallback: when no usable LLM is available, derive the plan
        # from the rule-based intent parser so the preview/confirm flow still
        # functions in offline mode.
        use_offline = False
        if model == "trigen-default":
            use_offline = True
        elif model and model_router.is_generation_model(model):
            use_offline = True
        elif not model and not self.config.llm.is_configured:
            use_offline = True
        if use_offline:
            from trigen.intent_parser import parse_message
            scene_dict = scene.to_dict()
            intents, _ = parse_message(user_message, scene_dict.get("objects", []), scene_dict.get("lights", []))
            tool_calls_collected = []
            for idx, intent in enumerate(intents):
                tc_id = f"plan_offline_{idx}"
                from trigen.llm.types import ToolCall
                tool_calls_collected.append(ToolCall(id=tc_id, name=intent.tool_name, arguments=intent.arguments))
            plan = self.planner.from_tool_calls(tool_calls_collected, reasoning="offline plan preview")
            return self._plan_payload_with_approval(plan, tool_calls_collected, "", session_id, offline=True)

        tool_schemas, _active_categories, _matched_signals = self._select_tool_schemas(user_message)
        scene_context = self.planner.build_context_message(scene.to_dict())
        messages = memory.to_openai_messages()
        messages.insert(-1, {"role": "system", "content": scene_context})

        tool_calls_collected: List = []
        full_text = ""
        token_usage: Dict[str, int] = {}
        async for chunk in self.llm.stream(
            messages=messages,
            tools=tool_schemas,
            system=SYSTEM_PROMPT,
            model=model,
        ):
            if chunk.finish_reason == "error":
                return {
                    "error": chunk.content or "LLM streaming error",
                    "plan": None,
                }
            if chunk.content:
                full_text += chunk.content
            if chunk.tool_calls:
                tool_calls_collected.extend(chunk.tool_calls)
            if getattr(chunk, "usage", None):
                token_usage = chunk.usage
            if chunk.finish_reason and not chunk.tool_calls:
                break

        plan = self.planner.from_tool_calls(tool_calls_collected, reasoning=full_text)
        return self._plan_payload_with_approval(plan, tool_calls_collected, full_text, session_id, token_usage=token_usage)

    def _plan_payload_with_approval(
        self,
        plan,
        tool_calls_collected: List,
        reasoning: str,
        session_id: str,
        token_usage: Optional[Dict[str, int]] = None,
        offline: bool = False,
    ) -> Dict[str, Any]:
        """Shape the plan payload with per-step approval flags + summary.

        Tags each tool_call with ``requires_approval`` (read off the
        registered tool's class attribute) and computes
        ``has_destructive_steps`` + ``destructive_steps`` so the frontend
        can render a confirmation dialog before the real run fires.
        """
        tool_calls_out = []
        destructive_steps = []
        for tc in tool_calls_collected:
            tool = self.registry.get(tc.name)
            needs_approval = bool(getattr(tool, "requires_approval", False)) if tool else False
            entry = {"id": tc.id, "name": tc.name, "arguments": tc.arguments, "requires_approval": needs_approval}
            tool_calls_out.append(entry)
            if needs_approval:
                destructive_steps.append(entry)
        payload = {
            "plan": plan.to_plan_payload(),
            "reasoning": reasoning,
            "tool_calls": tool_calls_out,
            "has_destructive_steps": len(destructive_steps) > 0,
            "destructive_steps": destructive_steps,
            "session_id": session_id,
            "offline": offline,
        }
        if token_usage:
            payload["token_usage"] = token_usage
        return payload

    def save_memory(self, session_id: str, model: str = "") -> None:
        """Persist the current conversation memory to disk."""
        memory = self._sessions.get(session_id)
        if memory is not None:
            memory_persistence.save(memory, model=model)

    def list_sessions(self) -> List[Dict[str, Any]]:
        """List all persisted sessions."""
        return memory_persistence.list_sessions()

    def list_tools(self) -> List[Dict[str, Any]]:
        """Expose all registered tool schemas."""
        return self.registry.schemas()

    async def run(
        self,
        user_message: str,
        session_id: str = "default",
        model: Optional[str] = None,
        images: Optional[List[Dict[str, str]]] = None,
    ) -> AsyncIterator[AgentEvent]:
        """Run a conversation turn, streaming out events. Overrides LLM model if provided.

        Wraps ``_run_turn`` to fire lifecycle hooks (``BEFORE_TURN`` once
        at the start; ``TOOL_CALL`` / ``TOOL_RESULT`` / ``SCENE_UPDATE`` /
        ``ERROR`` per event; ``AFTER_TURN`` when the DONE event is emitted).
        Hooks are observers and cannot alter the event stream.

        ``images`` is an optional list of ``{"base64", "mime"}`` dicts
        resolved from uploaded image attachments. When present, the
        orchestrator injects them into the LLM's vision context and exposes
        a ``__ATTACHED__`` sentinel so the LLM can request image-to-3D
        reconstruction without handling raw base64 strings.
        """
        await self.hooks.fire(
            HookEvent.BEFORE_TURN,
            {
                "session_id": session_id,
                "user_message": user_message,
                "model": model,
            },
        )
        async for event in self._run_turn(user_message, session_id, model, images=images):
            self._event_seq += 1
            event.seq = self._event_seq
            event.ts = time.time()
            await self._dispatch_hooks(event, session_id)
            yield event

    async def _dispatch_hooks(self, event: AgentEvent, session_id: str) -> None:
        """Map an emitted AgentEvent to the matching lifecycle hook."""
        payload = {"session_id": session_id, **event.data}
        if event.type == EventType.TOOL_CALL:
            await self.hooks.fire(HookEvent.TOOL_CALL, payload)
        elif event.type == EventType.TOOL_RESULT:
            await self.hooks.fire(HookEvent.TOOL_RESULT, payload)
        elif event.type == EventType.SCENE_UPDATE:
            await self.hooks.fire(HookEvent.SCENE_UPDATE, payload)
        elif event.type == EventType.ERROR:
            await self.hooks.fire(HookEvent.ERROR, payload)
        elif event.type == EventType.DONE:
            await self.hooks.fire(HookEvent.AFTER_TURN, payload)

    @staticmethod
    def _inject_image_attachments(
        messages: List[Dict[str, Any]], images: List[Dict[str, str]]
    ) -> None:
        """Convert the latest user message to multimodal content in-place.

        Appends OpenAI ``image_url`` content blocks for each attached image
        to the last user message in ``messages``. Also inserts a system note
        explaining the ``__ATTACHED__`` sentinel so the LLM can request
        image-to-3D reconstruction without handling raw base64 strings.
        """
        if not messages:
            return
        # Find the last user message.
        idx = len(messages) - 1
        while idx >= 0 and messages[idx].get("role") != "user":
            idx -= 1
        if idx < 0:
            return
        original_text = messages[idx].get("content", "")
        if not isinstance(original_text, str):
            original_text = str(original_text or "")

        # Build multimodal content: text block + one image_url block per attachment.
        content_blocks: List[Dict[str, Any]] = [{"type": "text", "text": original_text}]
        for img in images:
            mime = img.get("mime", "image/png")
            b64 = img.get("base64", "")
            content_blocks.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime};base64,{b64}"},
                }
            )
        messages[idx]["content"] = content_blocks

        # Insert a system note (before the user message) explaining the sentinel.
        sentinel_note = (
            "An image is attached to the user's message. You can see it via vision. "
            "To reconstruct the attached image as a 3D scene, call the image_to_3d tool "
            "with image_base64 set to the literal string __ATTACHED__ — the system will "
            "replace it with the actual image data before execution. You may also pass "
            "a text prompt to guide the reconstruction."
        )
        messages.insert(idx, {"role": "system", "content": sentinel_note})

    @staticmethod
    def _resolve_attached_sentinel(
        steps: List, images: Optional[List[Dict[str, str]]]
    ) -> None:
        """Replace ``__ATTACHED__`` in image_to_3d tool-call args in-place.

        Scans each step's arguments for ``image_base64 == "__ATTACHED__"``
        and replaces it with the base64 of the first attached image, also
        setting ``image_mime`` to the matching MIME type. Steps that don't
        reference the sentinel are left untouched.
        """
        if not images:
            return
        first = images[0]
        b64 = first.get("base64", "")
        mime = first.get("mime", "image/png")
        for step in steps:
            args = getattr(step, "arguments", None)
            if not isinstance(args, dict):
                continue
            if step.tool_name == "image_to_3d" and args.get("image_base64") == "__ATTACHED__":
                args["image_base64"] = b64
                args["image_mime"] = mime

    async def _apply_scene_edit_ops(
        self, scene: Scene, ops: List[SceneEditOp]
    ) -> List[Any]:
        """Dispatch parsed ``<scene_edit>`` ops through the tool registry.

        Each op is routed to its matching registered tool (create_object /
        transform_object / …), reusing the exact same execution path as
        explicit LLM tool calls. Returns the accumulated ``SceneDelta``
        list so the caller can emit a single ``SCENE_UPDATE`` event.
        """
        from trigen.tools.base import SceneDelta

        all_deltas: List[Any] = []
        for op in ops:
            tool = self.registry.get(op.tool)
            if tool is None:
                logger.warning("scene_edit op '%s' maps to unknown tool '%s'", op.op, op.tool)
                continue
            try:
                result = await tool.execute(scene, op.arguments)
            except Exception as exc:
                logger.exception("scene_edit op '%s' execution error", op.op)
                continue
            if result.deltas:
                all_deltas.extend(result.deltas)
        return all_deltas

    # Tools that mutate an existing object's transform/properties — used by
    # self-verification to decide whether a later step overrides an earlier
    # absolute-transform intent on the same object.
    _PER_TARGET_MUTATORS = {
        "transform_object", "modify_geometry", "apply_material",
        "apply_material_preset", "delete_object", "snap_to_grid",
        "lock_object", "set_visibility", "rename_object",
    }
    _MULTI_TARGET_MUTATORS = {"align_objects", "distribute_objects"}
    _CREATION_TOOLS_VER = {"create_object", "add_light", "add_camera"}

    def _step_touched_ids(self, scene: Scene, step) -> set:
        """Return ids of existing objects a step mutates (heuristic).

        Creation tools return an empty set since they introduce new objects
        rather than touching existing ones. Used only by self-verification.
        """
        name = step.tool_name
        if name in self._CREATION_TOOLS_VER:
            return set()
        if name in self._PER_TARGET_MUTATORS:
            obj = scene.find_object(str(step.arguments.get("target", "")))
            return {obj.id} if obj else set()
        if name in self._MULTI_TARGET_MUTATORS:
            targets = step.arguments.get("targets", [])
            if not isinstance(targets, list):
                return set()
            ids = set()
            for t in targets:
                obj = scene.find_object(str(t))
                if obj:
                    ids.add(obj.id)
            return ids
        if name == "boolean_operation":
            ids = set()
            for key in ("target_a", "target_b"):
                obj = scene.find_object(str(step.arguments.get(key, "")))
                if obj:
                    ids.add(obj.id)
            return ids
        if name in ("modify_light", "delete_light", "modify_camera"):
            return set()
        return set()

    def _collect_corrections(self, scene: Scene, plan) -> list:
        """Inspect post-execution scene state and produce correction steps.

        For each ``transform_object`` step using an absolute position/scale
        that is the *last* mutation of that object in the plan, verify the
        object's final state matches. When a mismatch is detected, emit a
        correction ``transform_object`` step restoring the intended value.
        Returns at most 3 corrections to bound the cost per turn.
        """
        from trigen.planner import TaskStep

        # Map obj_id -> index of the last step that mutated it
        last_touch: Dict[str, int] = {}
        for i, step in enumerate(plan.steps):
            for oid in self._step_touched_ids(scene, step):
                last_touch[oid] = i

        corrections = []
        for i, step in enumerate(plan.steps):
            if step.tool_name != "transform_object":
                continue
            if bool(step.arguments.get("relative", False)):
                continue
            obj = scene.find_object(str(step.arguments.get("target", "")))
            if not obj:
                continue
            # Skip when a later step also mutated this object — its intent wins
            if last_touch.get(obj.id, i) != i:
                continue

            pos_arg = step.arguments.get("position")
            if isinstance(pos_arg, list) and len(pos_arg) == 3:
                expected = [float(v) for v in pos_arg]
                actual = obj.transform.position
                if any(abs(actual[k] - expected[k]) > 1e-2 for k in range(3)):
                    corrections.append(TaskStep(
                        tool_name="transform_object",
                        arguments={"target": obj.id, "position": expected, "relative": False},
                        tool_call_id=f"verify_pos_{obj.id}_{i}",
                        description="Self-verification: restore absolute position",
                    ))
                    continue  # one correction per object

            scale_arg = step.arguments.get("scale")
            if isinstance(scale_arg, list) and len(scale_arg) == 3:
                expected = [float(v) for v in scale_arg]
                actual = obj.transform.scale
                if any(abs(actual[k] - expected[k]) > 1e-2 for k in range(3)):
                    corrections.append(TaskStep(
                        tool_name="transform_object",
                        arguments={"target": obj.id, "scale": expected, "relative": False},
                        tool_call_id=f"verify_scale_{obj.id}_{i}",
                        description="Self-verification: restore absolute scale",
                    ))

        return corrections[:3]

    # ------------------------------------------------------------------
    # Smart tool selection — narrow the LLM-visible schema set per turn
    # ------------------------------------------------------------------

    # Keyword -> category signals. Each entry is a list of substrings; if
    # any substring appears in the (lowercased) user message the category
    # is added to the active set. Conservative by design: when no signal
    # matches, the full schema set is returned so the LLM is never boxed
    # out of a capability it might need.
    _INTENT_CATEGORY_SIGNALS: Dict[str, List[str]] = {
        "creation": [
            "create", "add a", "add an", "new ", "make a", "make an", "generate a box",
            "duplicate", "copy", "delete", "remove", "boolean", "union", "subtract",
            "intersect", "array", "pattern", "instance",
            "立方体", "球", "圆柱", "圆锥", "圆环", "平面", "创建", "新建", "添加",
            "复制", "删除", "布尔", "阵列",
        ],
        "transform": [
            "move", "translate", "rotate", "scale", "align", "distribute", "mirror",
            "snap", "reset transform", "position", "ground", "center to origin",
            "移动", "旋转", "缩放", "对齐", "镜像", "居中", "落地", "重置变换",
        ],
        "material": [
            "material", "color", "colour", "paint", "texture", "preset", "metalness",
            "roughness", "wireframe", "emissive", "palette", "blend", "gradient",
            "metal", "glass", "wood", "plastic", "rubber", "ceramic", "marble",
            "neon", "shiny", "matte", "glossy", "opaque", "transparent",
            "金属", "玻璃", "木头", "塑料", "陶瓷", "大理石", "霓虹", "材质", "颜色",
            "配色", "渐变", "混合", "光泽", "哑光",
        ],
        "lighting": [
            "light", "lighting", "intensity", "ambient", "directional", "spotlight",
            "point light", "hemisphere", "shadow",
            "灯光", "环境光", "平行光", "点光源", "聚光灯", "半球光", "阴影",
        ],
        "camera": [
            "camera", "view", "snapshot", "capture", "viewport", "look at", "frame",
            "相机", "视图", "截图", "视口",
        ],
        "scene": [
            "group", "ungroup", "background", "fog", "environment", "grid", "arrange",
            "layout", "compose", "layer", "reorder", "background color",
            "分组", "解组", "背景", "雾", "环境", "网格", "布局", "排列", "层",
        ],
        "editor": [
            "select", "focus", "lock", "hide", "show", "rename", "isolate", "solo",
            "undo", "redo", "pivot", "clipping", "render quality", "transform mode",
            "选择", "聚焦", "锁定", "隐藏", "重命名", "隔离", "撤销", "重做", "轴心",
            "剖切", "渲染质量",
        ],
        "animation": [
            "animate", "animation", "keyframe", "orbit", "wave", "bounce", "play",
            "pause", "seek", "playback", "speed",
            "动画", "关键帧", "轨道", "波浪", "弹跳", "播放", "暂停", "进度", "速度",
        ],
        "procedural": [
            "terrain", "l-system", "lsystem", "plant", "tree", "shatter", "staircase",
            "spiral stair", "voronoi",
            "地形", "植物", "树", "碎裂", "楼梯", "螺旋",
        ],
        "multimodal": [
            "generate image", "generate 3d", "generate video", "generate music",
            "synthesize speech", "transcribe", "image to 3d", "text to image",
            "tts", "speech to text", "audio",
            "生成图片", "生成3d", "生成视频", "生成音乐", "语音合成", "语音识别", "图片转3d",
        ],
        "export": [
            "export", "download", "save as", "glb", "gltf", ".obj", "obj file",
            "export code", "export scene",
            "导出", "下载",
        ],
        "inspection": [
            "list", "info", "scene info", "measure", "analyze", "how many",
            "what is", "inspect",
            "列出", "信息", "测量", "分析", "多少",
        ],
        "skills": [
            "skill", "colonnade", "forest", "crystal garden", "dna", "galaxy",
            "atom", "bridge", "zen garden", "gear", "molecule", "snowman",
            "solar system", "city", "studio lighting",
            "柱廊", "树林", "水晶", "星系", "银河", "原子", "桥", "禅", "齿轮",
            "分子", "雪人", "太阳系", "城市",
        ],
    }

    # Categories always injected regardless of signal matching, so the
    # agent can always inspect the scene and fall back to skill recipes
    # even when the user message is terse.
    _ALWAYS_ON_CATEGORIES = {"inspection", "skills", "editor"}

    def _select_tool_schemas(self, user_message: str) -> tuple:
        """Pick the tool schema subset relevant to this user message.

        Returns a ``(schemas, categories, matched_signals)`` triple where
        ``schemas`` is the filtered list to inject into the LLM call,
        ``categories`` is the active category set, and ``matched_signals``
        is the list of category names whose keyword signals fired.

        Falls back to the full schema set when no signal matches, so the
        agent is never silently stripped of a capability it might need.
        """
        msg = (user_message or "").lower()
        matched: List[str] = []
        for category, signals in self._INTENT_CATEGORY_SIGNALS.items():
            if any(sig in msg for sig in signals):
                matched.append(category)
        if not matched:
            # Ambiguous / no signal — return the full set so the LLM
            # retains access to every capability.
            return self.registry.schemas(), sorted({t.category for t in self.registry.all()}), []
        active = set(matched) | self._ALWAYS_ON_CATEGORIES
        names = [t.name for t in self.registry.all() if t.category in active]
        return self.registry.schemas_for(names), sorted(active), matched

    # ------------------------------------------------------------------
    # Quality self-assessment — score the turn's outcome
    # ------------------------------------------------------------------

    def _assess_turn_quality(self, scene: Scene, results: List[ToolResult], plan) -> Dict[str, Any]:
        """Score the turn's outcome on a 0-100 scale.

        Combines three cheap signals:
          - success rate of executed tool results
          - whether the scene actually changed (object/light deltas)
          - whether corrections were needed (self-verification friction)
        Returns a dict with ``score``, ``success_rate``, ``scene_mutated``,
        and a short ``verdict`` label. Used only for the checkpoint
        thinking event — never blocks the turn.
        """
        total = len(results)
        if total == 0:
            return {"score": 100, "success_rate": 1.0, "scene_mutated": False,
                    "verdict": "noop", "note": "no tools executed"}
        successes = sum(1 for r in results if r.success)
        success_rate = successes / total
        scene_dict = scene.to_dict()
        scene_mutated = len(scene_dict.get("objects", [])) > 0 or len(scene_dict.get("lights", [])) > 0
        # Penalize when verification corrections were issued (friction).
        corrections_count = getattr(plan, "_verification_corrections", 0) or 0
        score = int(success_rate * 80)
        if scene_mutated:
            score += 15
        score -= min(15, corrections_count * 5)
        score = max(0, min(100, score))
        if score >= 90:
            verdict = "excellent"
        elif score >= 70:
            verdict = "good"
        elif score >= 40:
            verdict = "partial"
        else:
            verdict = "poor"
        return {
            "score": score,
            "success_rate": round(success_rate, 2),
            "scene_mutated": scene_mutated,
            "corrections": corrections_count,
            "verdict": verdict,
        }

    async def _run_turn(
        self,
        user_message: str,
        session_id: str = "default",
        model: Optional[str] = None,
        images: Optional[List[Dict[str, str]]] = None,
    ) -> AsyncIterator[AgentEvent]:
        """Run a conversation turn, streaming out events. Overrides LLM model if provided."""
        start_ts = time.time()
        memory = self.get_memory(session_id)
        scene = self.get_scene(session_id)
        memory.add_user(user_message)

        # Determine whether to use offline mode:
        # - model is "trigen-default" — user explicitly chose the offline engine
        # - model is a generation-only model (image/3D/video) — these cannot
        #   power conversational chat directly; fall back to the rule engine
        #   so the editor remains controllable, while the frontend can still
        #   invoke the generation model through its dedicated endpoint.
        # - model has no API key — try the fallback chain to find an alternative
        #   configured model before resorting to the offline rule engine.
        use_offline = False
        if model == "trigen-default":
            use_offline = True
        elif model:
            if model_router.is_generation_model(model):
                use_offline = True
            else:
                resolved = model_router.resolve(model)
                if not resolved.get("api_key"):
                    # Primary model lacks credentials — scan the fallback chain
                    # for the first model with a valid API key.
                    alternative = self._find_available_alternative(model)
                    if alternative:
                        logger.info("Primary model %s has no API key, falling back to %s", model, alternative)
                        model = alternative
                    else:
                        use_offline = True
        elif not self.config.llm.is_configured:
            # No model specified and no default LLM configured — try the chain
            alternative = self._find_available_alternative(None)
            if alternative:
                model = alternative
            else:
                use_offline = True

        if use_offline:
            async for event in self._run_offline(user_message, scene, session_id, images=images):
                yield event
            return

        # Smart tool selection: narrow the LLM-visible schema set to the
        # categories implicated by the user message. Falls back to the full
        # set when no intent signal matches. Always keeps inspection +
        # skills + editor essentials available so the agent can introspect.
        tool_schemas, active_categories, matched_signals = self._select_tool_schemas(user_message)
        scene_context = self.planner.build_context_message(scene.to_dict())
        messages = memory.to_openai_messages()
        # Inject scene context before the latest user message
        messages.insert(-1, {"role": "system", "content": scene_context})

        # When image attachments are present, convert the latest user message
        # to OpenAI multimodal content (text + image_url blocks) so a vision-
        # capable LLM can perceive the image. A system note tells the LLM it
        # can request 3D reconstruction via image_to_3d with the
        # ``__ATTACHED__`` sentinel — the orchestrator swaps in the real
        # base64 just before execution so the LLM never handles raw base64.
        if images:
            self._inject_image_attachments(messages, images)

        # Per-turn token budget (approximate). 0 means unlimited.
        budget = TokenBudget(limit=self.config.max_tokens_per_turn)
        budget.add(scene_context)
        budget.add(user_message)
        # Map tool name -> schema for pre-validation lookups.
        tool_schema_map: Dict[str, Dict[str, Any]] = {
            s["name"]: s for s in tool_schemas
        }

        # Emit a thinking event describing the plan
        yield AgentEvent(
            type=EventType.THINKING,
            data={
                "phase": "understanding",
                "content": f"Understanding user intent: {user_message[:120]}",
                "scene_summary": build_scene_summary(scene.to_dict()),
                "active_categories": active_categories,
                "matched_signals": matched_signals,
                "tool_subset_size": len(tool_schemas),
                "tool_total": len(self.registry.all()),
            },
        )

        full_text = ""
        iteration = 0
        tried_models: set = {model} if model else set()
        retry_count = 0
        max_retries = 3
        max_reflections = 2  # Cap reflection rounds to avoid loops
        reflection_count = 0
        edit_ops_applied = 0
        total_tool_calls = 0
        budget_warning_emitted = False
        # Accumulated token usage across all LLM iterations in this turn.
        token_usage_total: Dict[str, int] = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        # Accumulate results + last plan across iterations for the
        # post-turn quality self-assessment.
        all_results: List[ToolResult] = []
        last_plan = None
        for iteration in range(self.config.max_iterations):
            # Cooperative interrupt: if requested, stop the turn early.
            if self._consume_interrupt(session_id):
                yield AgentEvent(
                    type=EventType.THINKING,
                    data={
                        "phase": "interrupted",
                        "content": "Turn interrupted by user request.",
                        "iteration": iteration,
                    },
                )
                break
            # Guard: stop if the per-turn token budget is exhausted.
            if budget.exhausted:
                if not budget_warning_emitted:
                    yield AgentEvent(
                        type=EventType.THINKING,
                        data={
                            "phase": "budget",
                            "content": (
                                f"Token budget exhausted ({budget.used}/{budget.limit}); "
                                "stopping further iterations."
                            ),
                            "token_budget_used": budget.used,
                            "token_budget_limit": budget.limit,
                        },
                    )
                    budget_warning_emitted = True
                break
            tool_calls_collected: List = []
            try:
                async for chunk in self.llm.stream(
                    messages=messages,
                    tools=tool_schemas,
                    system=SYSTEM_PROMPT,
                    model=model,
                ):
                    # Detect error chunks yielded by the LLM client (which
                    # swallows exceptions and returns them as content)
                    if chunk.finish_reason == "error":
                        raise RuntimeError(chunk.content or "LLM streaming error")
                    if chunk.content:
                        full_text += chunk.content
                        budget.add(chunk.content)
                        yield AgentEvent(
                            type=EventType.TEXT_DELTA,
                            data={"content": chunk.content, "iteration": iteration},
                        )
                        # Inline <scene_edit> blocks: parse newly completed
                        # blocks and apply them to the scene immediately so
                        # the editor updates while the LLM is still talking.
                        all_edit_ops = parse_scene_edit(full_text)
                        if len(all_edit_ops) > edit_ops_applied:
                            new_ops = all_edit_ops[edit_ops_applied:]
                            edit_ops_applied = len(all_edit_ops)
                            edit_deltas = await self._apply_scene_edit_ops(scene, new_ops)
                            if edit_deltas:
                                yield AgentEvent(
                                    type=EventType.SCENE_UPDATE,
                                    data={
                                        "deltas": [d.__dict__ if hasattr(d, "__dict__") else d for d in edit_deltas],
                                        "scene": scene.to_dict(),
                                        "source": "scene_edit",
                                    },
                                )
                    if chunk.tool_calls:
                        tool_calls_collected.extend(chunk.tool_calls)
                    # Accumulate token usage reported by the transport.
                    if getattr(chunk, "usage", None):
                        u = chunk.usage
                        token_usage_total["prompt_tokens"] += int(u.get("prompt_tokens", 0))
                        token_usage_total["completion_tokens"] += int(u.get("completion_tokens", 0))
                        token_usage_total["total_tokens"] += int(u.get("total_tokens", 0))
                    if chunk.finish_reason and not chunk.tool_calls:
                        break
            except Exception as e:
                # Try alternative models from the fallback chain before
                # reporting an error to the user. Up to max_retries attempts.
                if retry_count < max_retries:
                    alternative = self._find_available_alternative(model, exclude=tried_models)
                    if alternative:
                        retry_count += 1
                        logger.warning(
                            "LLM streaming failed with %s (%s), retrying with %s (attempt %d/%d)",
                            model, str(e)[:80], alternative, retry_count, max_retries,
                        )
                        tried_models.add(alternative)
                        model = alternative
                        full_text = ""
                        continue
                # All alternatives exhausted — fall back to offline rule engine
                # so the editor remains controllable even without a working LLM.
                logger.warning("All model alternatives exhausted, falling back to offline mode")
                async for event in self._run_offline(user_message, scene, session_id):
                    yield event
                return

            # No tool calls → end of this turn
            if not tool_calls_collected:
                break

            total_tool_calls += len(tool_calls_collected)

            # Build the structured plan (goal/assumptions/risks + steps).
            plan = self.planner.from_tool_calls(tool_calls_collected, reasoning=full_text)
            plan.token_budget_used = budget.used
            plan.token_budget_limit = budget.limit
            last_plan = plan
            # Persist the plan's goal as the session's project headline so
            # subsequent turns and the frontend can show a stable objective.
            memory.set_project_goal(plan.goal)

            # Emit a structured plan event so the frontend can render the
            # agent's reasoning before any tool fires.
            yield AgentEvent(
                type=EventType.THINKING,
                data={
                    "phase": "planning",
                    "content": plan.goal or f"Planning to execute {len(tool_calls_collected)} tool calls",
                    "tools": [tc.name for tc in tool_calls_collected],
                    "iteration": iteration,
                    "plan": plan.to_plan_payload(),
                    "token_budget_used": budget.used,
                    "token_budget_limit": budget.limit,
                    "token_budget_remaining": budget.remaining,
                },
            )

            # Emit a dedicated PLAN roadmap event. Unlike the thinking
            # payload, this carries a stable per-step id (tool_call_id) and
            # an initial status so the frontend can render a live checklist
            # and correlate subsequent PLAN_UPDATE transitions by id.
            yield AgentEvent(
                type=EventType.PLAN,
                data={
                    "goal": plan.goal,
                    "assumptions": list(plan.assumptions),
                    "risks": list(plan.risks),
                    "iteration": iteration,
                    "steps": [
                        {
                            "id": s.tool_call_id,
                            "tool": s.tool_name,
                            "description": s.description,
                            "arguments": s.arguments,
                            "status": "pending",
                        }
                        for s in plan.steps
                    ],
                },
            )

            # Append assistant message (with tool_calls structure) to LLM messages
            assistant_msg: Dict[str, Any] = {"role": "assistant", "content": full_text or ""}
            assistant_msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": json.dumps(tc.arguments, ensure_ascii=False),
                    },
                }
                for tc in tool_calls_collected
            ]
            messages.append(assistant_msg)

            # Pre-validate each step's arguments against the tool schema.
            # Invalid steps are reported as failed tool_result events and
            # skipped — they never reach the executor. This avoids wasting
            # a tool execution on obviously broken inputs (missing required
            # field, wrong type, out-of-enum value) and gives the LLM a
            # clean error to correct in the next reflection round.
            valid_steps: List = []
            invalid_steps: List[tuple] = []  # (step, error_list)
            for step in plan.steps:
                errors = prevalidate_step(step, tool_schema_map.get(step.tool_name))
                if errors:
                    invalid_steps.append((step, errors))
                else:
                    valid_steps.append(step)

            # Replace the __ATTACHED__ sentinel in image_to_3d tool calls
            # with the actual base64 of the first attached image, so the
            # LLM never has to handle raw base64 strings in its arguments.
            self._resolve_attached_sentinel(valid_steps, images)

            for step in plan.steps:
                # Mark the step as running so the frontend checklist can
                # flip its indicator before the tool_result lands.
                yield AgentEvent(
                    type=EventType.PLAN_UPDATE,
                    data={
                        "id": step.tool_call_id,
                        "tool": step.tool_name,
                        "status": "running",
                    },
                )
                yield AgentEvent(
                    type=EventType.TOOL_CALL,
                    data={
                        "id": step.tool_call_id,
                        "name": step.tool_name,
                        "arguments": step.arguments,
                    },
                )

            # Execution checkpoint: surface the boundary between planning
            # and tool dispatch so the frontend can render a phase marker.
            yield AgentEvent(
                type=EventType.THINKING,
                data={
                    "phase": "execution",
                    "content": f"Executing {len(valid_steps)} step(s)"
                               + (f", {len(invalid_steps)} skipped by pre-validation" if invalid_steps else ""),
                    "iteration": iteration,
                    "valid_steps": len(valid_steps),
                    "invalid_steps": len(invalid_steps),
                },
            )

            # Execute only the valid subset; build a sub-plan so the
            # executor's parallel batching still applies.
            valid_plan = TaskPlan(steps=valid_steps, reasoning=plan.reasoning)
            executed_results = await self.executor.execute_plan(scene, valid_plan)

            # Build the merged result list aligned with plan.steps order so
            # the frontend can correlate tool_call ↔ tool_result by id.
            results_by_id: Dict[str, Any] = {}
            for s, r in zip(valid_steps, executed_results):
                results_by_id[s.tool_call_id] = r
            # Synthesize failure results for invalid steps.
            for step, errors in invalid_steps:
                msg = "Pre-validation failed: " + "; ".join(errors)
                results_by_id[step.tool_call_id] = ToolResult(
                    success=False, message=msg
                )

            results: List[ToolResult] = []
            failed_steps: List[tuple] = []  # (step, result) pairs for reflection
            for step in plan.steps:
                result = results_by_id.get(step.tool_call_id)
                if result is None:
                    # Fallback: should not happen, but stay safe.
                    result = ToolResult(success=False, message="Step not executed")
                    results_by_id[step.tool_call_id] = result
                results.append(result)
                yield AgentEvent(
                    type=EventType.TOOL_RESULT,
                    data={
                        "id": step.tool_call_id,
                        "name": step.tool_name,
                        "success": result.success,
                        "message": result.message,
                        "data": result.data,
                    },
                )
                # Flip the checklist step to its terminal status so the
                # frontend can mark it done (or failed) immediately.
                yield AgentEvent(
                    type=EventType.PLAN_UPDATE,
                    data={
                        "id": step.tool_call_id,
                        "tool": step.tool_name,
                        "status": "done" if result.success else "failed",
                        "message": result.message,
                    },
                )
                # Append tool result to messages so the LLM sees the outcome.
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": step.tool_call_id,
                        "content": result.message,
                    }
                )
                budget.add(result.message)
                if not result.success:
                    failed_steps.append((step, result))

            # Scene mutation event
            deltas = self.executor.collect_deltas(results)
            if deltas:
                yield AgentEvent(
                    type=EventType.SCENE_UPDATE,
                    data={
                        "deltas": [d.__dict__ if hasattr(d, "__dict__") else d for d in deltas],
                        "scene": scene.to_dict(),
                    },
                )

            # Self-verification: inspect the final scene state against each
            # step's intent and emit lightweight correction tool calls when a
            # mismatch is detected (e.g. a later op clobbered an absolute
            # transform). Skipped for intents overridden by a subsequent step
            # targeting the same object. Capped at 3 corrections/turn.
            try:
                corrections = self._collect_corrections(scene, plan)
            except Exception:
                logger.exception("Self-verification collection failed")
                corrections = []
            # Stash the correction count on the plan so the post-turn
            # quality assessment can penalize verification friction.
            plan._verification_corrections = len(corrections)
            if corrections:
                yield AgentEvent(
                    type=EventType.THINKING,
                    data={
                        "phase": "verification",
                        "content": f"Self-verification found {len(corrections)} mismatch(es); applying correction(s)",
                        "corrections": [c.tool_name for c in corrections],
                        "iteration": iteration,
                    },
                )
                for c in corrections:
                    yield AgentEvent(
                        type=EventType.TOOL_CALL,
                        data={
                            "id": c.tool_call_id,
                            "name": c.tool_name,
                            "arguments": c.arguments,
                        },
                    )
                correction_plan = self.planner.from_tool_calls(
                    [], reasoning="self-verification"
                )
                correction_plan.steps = list(corrections)
                correction_results = await self.executor.execute_plan(scene, correction_plan)
                for ci, cr in enumerate(correction_results):
                    cstep = corrections[ci]
                    yield AgentEvent(
                        type=EventType.TOOL_RESULT,
                        data={
                            "id": cstep.tool_call_id,
                            "name": cstep.tool_name,
                            "success": cr.success,
                            "message": cr.message,
                            "data": cr.data,
                        },
                    )
                correction_deltas = self.executor.collect_deltas(correction_results)
                if correction_deltas:
                    yield AgentEvent(
                        type=EventType.SCENE_UPDATE,
                        data={
                            "deltas": [d.__dict__ if hasattr(d, "__dict__") else d for d in correction_deltas],
                            "scene": scene.to_dict(),
                            "source": "verification",
                        },
                    )
                results.extend(correction_results)
            all_results.extend(results)

            # Reflection: when one or more tool calls failed, surface a
            # structured reflection prompt to the LLM so the next iteration
            # can adjust arguments and retry. Capped to avoid loops.
            if failed_steps and reflection_count < max_reflections and iteration < self.config.max_iterations - 1:
                reflection_count += 1
                lines = [
                    f"One or more tool calls failed (reflection {reflection_count}/{max_reflections}).",
                    "Review the failures below, identify the root cause (wrong id, bad argument, missing prerequisite), and retry with corrected parameters.",
                    "",
                ]
                for s, r in failed_steps:
                    lines.append(
                        f"- tool={s.tool_name} arguments={json.dumps(s.arguments, ensure_ascii=False)} error={r.message}"
                    )
                lines.append("")
                lines.append("Do NOT repeat the exact same arguments. Adjust them or call a different tool.")
                reflection_msg = {"role": "system", "content": "\n".join(lines)}
                messages.append(reflection_msg)
                yield AgentEvent(
                    type=EventType.THINKING,
                    data={
                        "phase": "reflection",
                        "content": f"{len(failed_steps)} tool call(s) failed; asking model to reflect and retry ({reflection_count}/{max_reflections})",
                        "failed_tools": [s.tool_name for s, _ in failed_steps],
                        "iteration": iteration,
                    },
                )

            # Update scene context
            new_context = self.planner.build_context_message(scene.to_dict())
            budget.add(new_context)
            messages.append({"role": "system", "content": new_context})
            full_text = ""

        elapsed = round(time.time() - start_ts, 2)
        memory.add_assistant(full_text)

        # Quality self-assessment: score the turn's outcome from the
        # accumulated results + verification friction. Surfaced as a
        # checkpoint thinking event so the frontend can render a quality
        # marker; never blocks the turn.
        try:
            quality = self._assess_turn_quality(scene, all_results, last_plan)
        except Exception:
            logger.exception("Quality self-assessment failed")
            quality = {"score": -1, "verdict": "unknown"}
        yield AgentEvent(
            type=EventType.THINKING,
            data={
                "phase": "assessment",
                "content": (
                    f"Turn quality: {quality.get('verdict', 'unknown')} "
                    f"(score {quality.get('score', -1)}/100, "
                    f"success_rate {quality.get('success_rate', 0)})"
                ),
                "quality": quality,
                "elapsed": elapsed,
                "iterations": iteration + 1,
            },
        )

        # Emit final thinking event summarizing the turn
        yield AgentEvent(
            type=EventType.THINKING,
            data={
                "phase": "complete",
                "content": f"Turn complete, {iteration + 1} iterations, elapsed {elapsed}s",
                "elapsed": elapsed,
                "iterations": iteration + 1,
                "token_budget_used": budget.used,
                "token_budget_limit": budget.limit,
                "quality": quality,
            },
        )

        yield AgentEvent(
            type=EventType.DONE,
            data={
                "content": full_text,
                "scene": scene.to_dict(),
                "session_id": session_id,
                "elapsed": elapsed,
                "stats": {
                    "iterations": iteration + 1,
                    "tool_calls": total_tool_calls,
                    "elapsed": elapsed,
                    "token_budget_used": budget.used,
                    "token_budget_limit": budget.limit,
                    "token_usage": token_usage_total,
                    "quality": quality,
                },
                "token_usage": token_usage_total,
                "suggestions": self._scene_suggestions(scene),
                "project_goal": memory.project_goal,
            },
        )

        # Persist conversation memory after each turn
        self.save_memory(session_id, model or "")

    def _find_available_alternative(
        self, primary: Optional[str], exclude: Optional[set] = None
    ) -> Optional[str]:
        """Scan the fallback chain for the first model with a valid API key.

        Called when the primary model lacks credentials. Returns the model
        id of the first usable alternative, or None when no model in the
        chain has a configured API key (excluding the offline default).
        The `exclude` set skips models that have already been tried.
        """
        chain = model_router.build_fallback_chain(primary)
        skip = exclude or set()
        for candidate in chain:
            if candidate == primary or candidate in skip:
                continue
            if candidate == "trigen-default":
                continue
            if model_router.is_generation_model(candidate):
                continue
            resolved = model_router.resolve(candidate)
            if resolved.get("api_key"):
                return candidate
        return None

    # Maps pipeline node types to the tool names the frontend's multimodal
    # renderer recognizes, so pipeline steps render with the right media widget.
    _PIPELINE_NODE_TO_TOOL_NAME: Dict[str, str] = {
        "generate_image": "generate_image",
        "generate_3d": "generate_3d_asset",
        "generate_video": "generate_video",
        "generate_animation": "generate_animation",
        "tts": "synthesize_speech",
        "transcribe": "transcribe_audio",
        "llm_complete": "llm_complete",
        "llm_stream": "llm_stream",
        "image_to_3d": "image_to_3d",
    }

    @staticmethod
    def _pipeline_outputs_to_data(node_type: str, outputs: Dict[str, Any]) -> Dict[str, Any]:
        """Shape pipeline node outputs to match the frontend's multimodal renderer."""
        if node_type == "generate_image":
            return {
                "modality": "image",
                "url": outputs.get("url", ""),
                "base64_data": outputs.get("base64_data", ""),
                "mime_type": outputs.get("mime_type", "image/png"),
            }
        if node_type == "generate_3d":
            return {
                "modality": "3d",
                "url": outputs.get("url", ""),
                "output_format": outputs.get("output_format", "glb"),
            }
        if node_type == "generate_video":
            return {
                "modality": "video",
                "url": outputs.get("url", ""),
                "mime_type": outputs.get("mime_type", "video/mp4"),
            }
        if node_type == "generate_animation":
            return {
                "modality": "animation",
                "url": outputs.get("url", ""),
                "base64_data": outputs.get("base64_data", ""),
                "mime_type": outputs.get("mime_type", "image/png"),
            }
        if node_type == "tts":
            return {
                "modality": "voice",
                "base64_data": outputs.get("base64_data", ""),
                "mime_type": outputs.get("mime_type", "audio/mpeg"),
            }
        if node_type == "transcribe":
            return {
                "modality": "audio",
                "text": outputs.get("text", ""),
            }
        if node_type in ("llm_complete", "llm_stream"):
            return {"modality": "text", "content": outputs.get("content", "")}
        if node_type == "image_to_3d":
            return {
                "modality": "3d",
                "object_count": outputs.get("object_count", 0),
                "message": outputs.get("message", ""),
            }
        return dict(outputs)

    async def _run_pipeline(
        self,
        nodes: List[Dict[str, Any]],
        user_message: str,
        scene: Scene,
        session_id: str,
        start_ts: float,
    ) -> AsyncIterator[AgentEvent]:
        """Execute a multi-step generation pipeline declared via chat.

        Streams node-by-node progress through the same event types the
        offline engine uses (thinking / tool_call / tool_result /
        scene_update / done), so the frontend renders each pipeline step
        as a tool call card with inline rich-media output.
        """
        from trigen.llm.pipeline import orchestrator as pipeline_orchestrator, parse_pipeline

        pipeline = parse_pipeline({"name": "chat_pipeline", "nodes": nodes})

        # Phase 1: Understanding
        yield AgentEvent(
            type=EventType.THINKING,
            data={
                "phase": "understanding",
                "content": f"Pipeline request: {len(nodes)} step(s)",
                "scene_summary": build_scene_summary(scene.to_dict()),
            },
        )

        # Phase 2: Planning — describe the node chain
        step_descs = [f"{n.get('type', '?')}({n.get('id', '')})" for n in nodes]
        yield AgentEvent(
            type=EventType.THINKING,
            data={
                "phase": "planning",
                "content": f"Pipeline plan: {' -> '.join(step_descs)}",
                "tools": [n.get("type", "") for n in nodes],
            },
        )

        text_parts: List[str] = []
        scene_changed = False

        # Phase 3: Execution — stream node results as tool_call/tool_result pairs
        async for event in pipeline_orchestrator.execute_stream(pipeline):
            ev_type = event.get("event")
            if ev_type == "start":
                node_id = event.get("node_id", "")
                node_type = event.get("node_type", "")
                node_def = next((n for n in nodes if n.get("id") == node_id), {})
                yield AgentEvent(
                    type=EventType.TOOL_CALL,
                    data={
                        "id": node_id,
                        "name": self._PIPELINE_NODE_TO_TOOL_NAME.get(node_type, node_type),
                        "arguments": node_def.get("inputs", {}),
                    },
                )
            elif ev_type == "result":
                node_id = event.get("node_id", "")
                node_type = next(
                    (n.get("type", "") for n in nodes if n.get("id") == node_id), ""
                )
                status = event.get("status", "failed")
                outputs = event.get("outputs", {}) or {}
                error = event.get("error", "")
                # Node ran without throwing, but generation handlers embed a
                # "success" flag in their outputs — use it to report the real
                # outcome so the frontend shows failures correctly.
                success = status == "success"
                if success and isinstance(outputs, dict) and "success" in outputs:
                    success = bool(outputs.get("success"))
                    if not success and outputs.get("error"):
                        error = outputs.get("error", "")

                tool_name = self._PIPELINE_NODE_TO_TOOL_NAME.get(node_type, node_type)
                message = error if not success else f"{tool_name} completed"
                data = self._pipeline_outputs_to_data(node_type, outputs) if success else {}

                yield AgentEvent(
                    type=EventType.TOOL_RESULT,
                    data={
                        "id": node_id,
                        "name": tool_name,
                        "success": success,
                        "message": message,
                        "data": data,
                    },
                )

                # Apply scene mutations from image_to_3d nodes
                if node_type == "image_to_3d" and success and outputs.get("scene"):
                    try:
                        scene.from_dict(outputs["scene"])
                        scene_changed = True
                        yield AgentEvent(
                            type=EventType.SCENE_UPDATE,
                            data={"scene": scene.to_dict()},
                        )
                    except Exception:
                        pass

                text_parts.append(message)
            elif ev_type == "done":
                succeeded = event.get("succeeded", 0)
                failed = event.get("failed", 0)
                total_ms = event.get("total_elapsed_ms", 0)
                text_parts.append(
                    f"Pipeline complete: {succeeded} succeeded, {failed} failed ({total_ms}ms)"
                )

        # Phase 4: Complete
        elapsed = round(time.time() - start_ts, 2)
        yield AgentEvent(
            type=EventType.THINKING,
            data={
                "phase": "complete",
                "content": f"Pipeline turn complete, elapsed {elapsed}s",
                "elapsed": elapsed,
                "iterations": 1,
            },
        )

        full_text = "(Pipeline mode) " + "\n".join(text_parts)
        yield AgentEvent(type=EventType.TEXT_DELTA, data={"content": full_text, "iteration": 0})
        memory = self.get_memory(session_id)
        memory.add_assistant(full_text)
        yield AgentEvent(
            type=EventType.DONE,
            data={
                "content": full_text,
                "scene": scene.to_dict(),
                "session_id": session_id,
                "elapsed": elapsed,
                "stats": {
                    "iterations": 1,
                    "tool_calls": len(nodes),
                    "elapsed": elapsed,
                },
                "suggestions": self._scene_suggestions(scene),
            },
        )
        self.save_memory(session_id)

    async def _run_offline(
        self,
        user_message: str,
        scene: Scene,
        session_id: str,
        images: Optional[List[Dict[str, str]]] = None,
    ) -> AsyncIterator[AgentEvent]:
        """Offline rule engine when LLM is not configured.

        Uses the intent parser to decompose user messages into structured
        tool-call intents, then executes them sequentially with thinking
        and scene-update events — mirroring the online LLM flow.

        When image attachments are present, auto-injects an ``image_to_3d``
        intent with the first image's base64 so the offline path can still
        reconstruct scenes from uploaded images.
        """
        start_ts = time.time()
        scene_dict = scene.to_dict()
        scene_objects = scene_dict.get("objects", [])
        scene_lights = scene_dict.get("lights", [])

        # Phase 1: Understanding
        yield AgentEvent(
            type=EventType.THINKING,
            data={
                "phase": "understanding",
                "content": f"Parsing user instruction: {user_message[:120]}",
                "scene_summary": build_scene_summary(scene_dict),
            },
        )

        # Phase 2: Intent parsing
        intents, _ = parse_message(user_message, scene_objects, scene_lights)

        # When image attachments are present, auto-inject an image_to_3d
        # intent at the front so the offline path reconstructs the scene
        # from the uploaded image. The user's text message (if any) is
        # passed as the ``prompt`` argument to guide reconstruction.
        if images:
            from trigen.intent_parser import ParsedIntent

            first_img = images[0]
            intents = [
                ParsedIntent(
                    tool_name="image_to_3d",
                    arguments={
                        "image_base64": first_img.get("base64", ""),
                        "image_mime": first_img.get("mime", "image/png"),
                        "prompt": user_message,
                        "clear_scene": True,
                    },
                    description="Reconstruct scene from attached image",
                )
            ] + intents

        if not intents:
            text = (
                "(Offline mode) I couldn't parse that command. Try:\n"
                "- \"create a red cube\"\n"
                "- \"add a blue sphere\"\n"
                "- \"move the cube to [2, 0, 0]\"\n"
                "- \"apply metal material to the sphere\"\n"
                "- \"add a point light\"\n"
                "- \"create solar system\"\n"
                "- \"arrange in circle\"\n"
                "- \"export as GLB\""
            )
            yield AgentEvent(type=EventType.TEXT_DELTA, data={"content": text, "iteration": 0})
            memory = self.get_memory(session_id)
            memory.add_assistant(text)
            yield AgentEvent(
                type=EventType.DONE,
                data={
                    "content": text,
                    "scene": scene.to_dict(),
                    "session_id": session_id,
                    "elapsed": 0.0,
                    "stats": {
                        "iterations": 0,
                        "tool_calls": 0,
                        "elapsed": 0.0,
                    },
                },
            )
            return

        # Pipeline dispatch — when the parsed intent is a multi-step pipeline,
        # hand off to the dedicated pipeline runner instead of the per-intent
        # tool executor below.
        if intents[0].tool_name == "run_pipeline":
            async for event in self._run_pipeline(
                intents[0].arguments.get("nodes", []),
                user_message,
                scene,
                session_id,
                start_ts,
            ):
                yield event
            return

        # Phase 3: Planning
        tool_names = [i.tool_name for i in intents]
        offline_goal = f"Planned {len(intents)} operation(s): {', '.join(tool_names)}"
        yield AgentEvent(
            type=EventType.THINKING,
            data={
                "phase": "planning",
                "content": offline_goal,
                "tools": tool_names,
            },
        )
        # Mirror the online path: emit a structured PLAN roadmap with stable
        # per-step ids so the frontend checklist works in offline mode too.
        memory = self.get_memory(session_id)
        memory.set_project_goal(offline_goal)
        yield AgentEvent(
            type=EventType.PLAN,
            data={
                "goal": offline_goal,
                "iteration": 0,
                "steps": [
                    {
                        "id": f"offline_{idx}",
                        "tool": intent.tool_name,
                        "description": intent.description or f"Call {intent.tool_name}",
                        "arguments": intent.arguments,
                        "status": "pending",
                    }
                    for idx, intent in enumerate(intents)
                ],
            },
        )

        text_parts: List[str] = []
        scene_changed = False

        # Phase 4: Execution
        for idx, intent in enumerate(intents):
            tool = self.registry.get(intent.tool_name)
            if tool is None:
                text_parts.append(f"Unknown tool: {intent.tool_name}")
                continue

            step_id = f"offline_{idx}"
            # Emit tool_call event (for tools that modify the scene)
            if intent.emit_tool_call:
                yield AgentEvent(
                    type=EventType.PLAN_UPDATE,
                    data={"id": step_id, "tool": intent.tool_name, "status": "running"},
                )
                yield AgentEvent(
                    type=EventType.TOOL_CALL,
                    data={
                        "id": step_id,
                        "name": intent.tool_name,
                        "arguments": intent.arguments,
                    },
                )

            try:
                result = await tool.execute(scene, intent.arguments)
            except Exception as e:
                logger.exception("Offline tool %s execution error", intent.tool_name)
                from trigen.tools.base import ToolResult
                result = ToolResult(success=False, message=f"Execution error: {e}")

            yield AgentEvent(
                type=EventType.TOOL_RESULT,
                data={
                    "id": step_id,
                    "name": intent.tool_name,
                    "success": result.success,
                    "message": result.message,
                    "data": result.data,
                },
            )
            yield AgentEvent(
                type=EventType.PLAN_UPDATE,
                data={
                    "id": step_id,
                    "tool": intent.tool_name,
                    "status": "done" if result.success else "failed",
                    "message": result.message,
                },
            )

            if result.deltas:
                scene_changed = True
                yield AgentEvent(
                    type=EventType.SCENE_UPDATE,
                    data={
                        "deltas": [d.__dict__ if hasattr(d, "__dict__") else d for d in result.deltas],
                        "scene": scene.to_dict(),
                    },
                )

            text_parts.append(result.message if result.success else f"Failed: {result.message}")

        # Phase 4b: Offline self-verification — inspect the post-execution
        # scene against each step's intent and apply lightweight corrections
        # when a later op clobbered an earlier absolute transform. Mirrors
        # the LLM path's _collect_corrections so offline mode is equally
        # self-correcting. Capped at 3 corrections/turn.
        try:
            from trigen.planner import TaskStep as _Step
            offline_plan = self.planner.from_tool_calls([], reasoning="offline")
            offline_plan.steps = [
                _Step(
                    tool_name=intent.tool_name,
                    arguments=intent.arguments,
                    tool_call_id=f"offline_{i}",
                    description=intent.description or f"Call {intent.tool_name}",
                )
                for i, intent in enumerate(intents)
            ]
            corrections = self._collect_corrections(scene, offline_plan)
        except Exception:
            logger.exception("Offline self-verification collection failed")
            corrections = []
        if corrections:
            yield AgentEvent(
                type=EventType.THINKING,
                data={
                    "phase": "verification",
                    "content": f"Self-verification found {len(corrections)} mismatch(es); applying correction(s)",
                    "corrections": [c.tool_name for c in corrections],
                },
            )
            for c in corrections:
                yield AgentEvent(
                    type=EventType.TOOL_CALL,
                    data={"id": c.tool_call_id, "name": c.tool_name, "arguments": c.arguments},
                )
            correction_plan = self.planner.from_tool_calls([], reasoning="self-verification")
            correction_plan.steps = list(corrections)
            correction_results = await self.executor.execute_plan(scene, correction_plan)
            for ci, cr in enumerate(correction_results):
                cstep = corrections[ci]
                yield AgentEvent(
                    type=EventType.TOOL_RESULT,
                    data={
                        "id": cstep.tool_call_id,
                        "name": cstep.tool_name,
                        "success": cr.success,
                        "message": cr.message,
                        "data": cr.data,
                    },
                )
            correction_deltas = self.executor.collect_deltas(correction_results)
            if correction_deltas:
                scene_changed = True
                yield AgentEvent(
                    type=EventType.SCENE_UPDATE,
                    data={
                        "deltas": [d.__dict__ if hasattr(d, "__dict__") else d for d in correction_deltas],
                        "scene": scene.to_dict(),
                        "source": "verification",
                    },
                )

        # Phase 5: Complete
        elapsed = round(time.time() - start_ts, 2)
        yield AgentEvent(
            type=EventType.THINKING,
            data={
                "phase": "complete",
                "content": f"Turn complete, {len(intents)} operation(s), elapsed {elapsed}s",
                "elapsed": elapsed,
                "iterations": 1,
            },
        )

        full_text = "(Offline mode) " + "\n".join(text_parts)
        yield AgentEvent(type=EventType.TEXT_DELTA, data={"content": full_text, "iteration": 0})
        memory = self.get_memory(session_id)
        memory.add_assistant(full_text)
        yield AgentEvent(
            type=EventType.DONE,
            data={
                "content": full_text,
                "scene": scene.to_dict(),
                "session_id": session_id,
                "elapsed": elapsed,
                "stats": {
                    "iterations": 1,
                    "tool_calls": len(intents),
                    "elapsed": elapsed,
                },
                "suggestions": self._scene_suggestions(scene),
                "project_goal": memory.project_goal,
            },
        )

        # Persist conversation memory after each offline turn
        self.save_memory(session_id)
