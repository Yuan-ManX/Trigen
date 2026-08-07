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
  plan_update  — Per-step execution progress (started/completed/failed)
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
from trigen.context import compress_session, should_compress
from trigen.episodic_memory import store as episodic_store
from trigen.macros import macro_store
from trigen.workflows import workflow_store
from trigen.variants import variant_store
from trigen.checkpoints import checkpoint_store
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
    # New tool exports added below
    ClearMeasurementTool,
    ControlRadialMenuTool,
    StopCameraFlythroughTool,
    DefineMacroTool,
    DeleteMacroTool,
    InvokeMacroTool,
    ListMacrosTool,
    SaveVariantTool,
    LoadVariantTool,
    ListVariantsTool,
    RandomizeVariantTool,
    SaveWorkflowTool,
    InvokeWorkflowTool,
    ListWorkflowsTool,
    DeleteWorkflowTool,
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
    AddAnnotationTool,
    ApplyMaterialBatchTool,
    ConfigureShortcutsTool,
    IsolateObjectTool,
    LoadSceneSlotTool,
    RemoveAnnotationTool,
    ResetTransformTool,
    SaveSceneSlotTool,
    SetClippingPlaneTool,
    SetEditorModeTool,
    SetGeometryParamsTool,
    SetMaterialPropertyTool,
    SetMinimapTool,
    SetObjectLayerTool,
    SetObjectParentTool,
    SetObjectPivotTool,
    SetShadowsTool,
    SetViewportProjectionTool,
)
from trigen.tools.scene_workflow_tools import (
    BatchTransformTool,
    CameraFlythroughTool,
    ListAnnotationsTool,
    QuerySceneTool,
    SceneStatisticsTool,
    StyleSceneTool,
)
from trigen.tools.pipeline_tools import (
    ComposePipelineTool,
    ListPipelineTemplatesTool,
)
from trigen.tools.scene_intelligence_tools import (
    DescribeSceneTool,
    SuggestNextActionsTool,
)
from trigen.tools.reflection_tools import ReflectOnSessionTool
from trigen.tools.scene_critique import SceneCritiqueTool
from trigen.tools.auto_fix import AutoFixSceneTool
from trigen.tools.memory_tools import (
    ForgetFactTool,
    PinFactTool,
    RecallFactsTool,
)
from trigen.tools.asset_library_tools import (
    AssetLibraryTool,
    ScatterPaintTool,
    SnapToSurfaceTool,
)
from trigen.tools.checkpoint_tools import (
    CheckpointDiffTool,
    CheckpointSceneTool,
    ListCheckpointsTool,
    RestoreCheckpointTool,
)
from trigen.tools.storyboard_tools import (
    AddShotTool,
    ClearStoryTool,
    ComposeStoryTool,
    ListStoryTool,
    PlayStoryTool,
    RemoveShotTool,
    UpdateShotTool,
)
from trigen.tools.editor_gap_tools import (
    ListSceneTemplatesTool,
    ListSkillsTool,
    OrbitViewportTool,
    SetLayerVisibilityTool,
)
from trigen.tools.constraint_tools import (
    AddConstraintTool,
    ClearConstraintsTool,
    ListConstraintsTool,
    SolveConstraintsTool,
)
from trigen.tools.refine_tool import RefineSceneTool
from trigen.tools.generative_geometry_tools import (
    CloneWithJitterTool,
    RadialSymmetryTool,
)
from trigen.tools.mesh_detail_tools import (
    ConvertGeometryTool,
    SubdivideMeshTool,
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
    "set_geometry_params": "creation",
    # Asset library — higher-level creation abstractions (place pre-built
    # assets, scatter-paint clusters, snap to surface).
    "place_asset": "creation",
    "scatter_paint": "creation",
    "snap_to_surface": "creation",
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
    "set_material_property": "material",
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
    "set_minimap": "editor",
    "set_shadows": "editor",
    "set_viewport_projection": "editor",
    "set_editor_mode": "editor",
    "save_scene_slot": "editor",
    "load_scene_slot": "editor",
    "undo_scene": "editor",
    "redo_scene": "editor",
    "set_object_parent": "editor",
    "add_annotation": "editor",
    "remove_annotation": "editor",
    "configure_shortcuts": "editor",
    # scene workflow — bulk / query / stylization / cinematic tools
    "query_scene": "inspection",
    "scene_statistics": "inspection",
    "list_annotations": "inspection",
    "style_scene": "material",
    "batch_transform": "transform",
    "camera_flythrough": "camera",
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
    # macros — user-defined reusable tool-call recipes
    "define_macro": "skills",
    "invoke_macro": "skills",
    "list_macros": "skills",
    "delete_macro": "skills",
    # Agentic Workflow Templates — saveable named tool-graph recipes
    "save_workflow": "skills",
    "invoke_workflow": "skills",
    "list_workflows": "skills",
    "delete_workflow": "skills",
    # variants — named scene snapshots + jittered alternatives
    "save_variant": "scene",
    "load_variant": "scene",
    "list_variants": "scene",
    "randomize_variant": "scene",
    # editor gap tools — dismiss overlays (radial menu, measurement, flythrough)
    "control_radial_menu": "editor",
    "clear_measurement": "editor",
    "stop_camera_flythrough": "editor",
    # pipeline authoring — compose / inspect multimodal node-graphs
    "compose_pipeline": "multimodal",
    "list_pipeline_templates": "multimodal",
    # scene intelligence — semantic scene description + actionable suggestions
    "describe_scene": "inspection",
    "suggest_next_actions": "inspection",
    "reflect_on_session": "inspection",
    "critique_scene": "inspection",
    "auto_fix_scene": "inspection",
    # Agent explicit memory — pin / recall / forget durable user facts
    "pin_fact": "memory",
    "recall_facts": "memory",
    "forget_fact": "memory",
    # Scene checkpoints — revisioned version history (semantic timeline)
    "checkpoint_scene": "scene",
    "list_checkpoints": "scene",
    "restore_checkpoint": "scene",
    "checkpoint_diff": "scene",
    # Cinematic storyboard — sequence-level camera direction
    "compose_story": "camera",
    "add_shot": "camera",
    "update_shot": "camera",
    "remove_shot": "camera",
    "list_story": "camera",
    "clear_story": "camera",
    "play_story": "camera",
    # Frontend-editor coverage gap tools — template catalog, viewport orbit,
    # per-layer visibility, skill catalog
    "list_scene_templates": "scene",
    "orbit_viewport": "editor",
    "set_layer_visibility": "editor",
    "list_skills": "skills",
    # Constraint-authoring — declarative spatial relationships + greedy solver
    "add_constraint": "constraints",
    "list_constraints": "constraints",
    "clear_constraints": "constraints",
    "solve_constraints": "constraints",
    # Goal-driven refinement — multi-iteration critique+autofix loop
    "refine_scene": "intelligence",
    # Generative geometry — radial symmetry rings + jittered clones
    "radial_symmetry": "creation",
    "clone_with_jitter": "transform",
    # Mesh detail editing — type conversion + segment subdivision
    "convert_geometry": "creation",
    "subdivide_mesh": "creation",
}


def _levenshtein(a: str, b: str) -> int:
    """Classic iterative Levenshtein edit distance (case-insensitive)."""
    a = a.lower()
    b = b.lower()
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        curr = [i]
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            curr.append(min(curr[-1] + 1, prev[j] + 1, prev[j - 1] + cost))
        prev = curr
    return prev[-1]


# Multimodal 3D-generating tools whose output should trigger a perception
# check on the resulting scene state. These tools either fetch an external
# mesh (generate_3d_asset) or reconstruct primitives from an image
# (image_to_3d); after either one, a heuristic viewport check surfaces
# composition issues (empty scene, oversized extent, object overlaps) so
# the agent can self-correct in the next reflection round.
_MULTIMODAL_3D_TOOLS = {"generate_3d_asset", "image_to_3d"}

# Phrases in a tool result message that signal a target-naming miss. The
# offline auto-recovery hook keys off these to attempt a fuzzy re-resolve
# of the requested target against the live scene objects.
_TARGET_MISS_PHRASES = (
    "not found",
    "no matching",
    "no object",
    "unknown object",
    "unknown light",
    "unknown camera",
    "unknown variant",
    "unknown macro",
    "couldn't find",
    "could not find",
    "无法找到",
    "未找到",
    "找不到",
    "不存在",
)


def _fuzzy_resolve_target(
    requested: str,
    candidate_names: List[str],
    max_distance: int = 2,
) -> Optional[str]:
    """Resolve a requested name against candidate names using fuzzy matching.

    Matching strategy (in priority order):
      1. Exact case-insensitive match.
      2. Case-insensitive substring containment (either direction).
      3. Levenshtein edit distance ≤ ``max_distance`` (closest wins, ties
         broken alphabetically for determinism).

    Returns the resolved candidate name, or None if no candidate is close
    enough. Empty / whitespace-only ``requested`` always returns None.
    """
    if not requested or not requested.strip():
        return None
    requested = requested.strip()
    requested_lower = requested.lower()

    # 1. Exact case-insensitive match.
    for name in candidate_names:
        if name.lower() == requested_lower:
            return name

    # 2. Substring containment (either direction).
    substr_hits: List[str] = []
    for name in candidate_names:
        name_lower = name.lower()
        if requested_lower in name_lower or name_lower in requested_lower:
            substr_hits.append(name)
    if len(substr_hits) == 1:
        return substr_hits[0]
    if substr_hits:
        # Prefer the shortest candidate (closest to a direct rename) —
        # e.g. "Cube" should resolve to "Cube" rather than "Cube_001".
        return min(substr_hits, key=lambda n: (len(n), n))

    # 3. Levenshtein distance ≤ max_distance.
    best: Optional[str] = None
    best_dist = max_distance + 1
    for name in candidate_names:
        dist = _levenshtein(requested, name)
        if dist < best_dist or (dist == best_dist and best is not None and name < best):
            best_dist = dist
            best = name
    if best is not None and best_dist <= max_distance:
        return best
    return None


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
    # Emitted when the agent revises its plan mid-turn (reflection after a
    # tool failure, budget-driven pruning, or an alternative-tool retry).
    # Carries the refined step list so the frontend checklist can reconcile
    # against the original PLAN roadmap.
    PLAN_REFINE = "plan_refine"
    # Dependency-graph view of the plan: nodes (steps) + edges (predecessor
    # links) + layers (parallel waves). Emitted once per planning round so
    # the frontend node-graph view can render the agent's decomposition as a
    # true DAG instead of a flat checklist.
    PLAN_GRAPH = "plan_graph"
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


@dataclass
class _PlanCritique:
    """Result of the pre-execution critique gate.

    ``findings`` are advisory diagnostics surfaced to the user/LLM.
    ``pruned_step_ids`` are step ids that must not execute (provably dead
    or ambiguous); the orchestrator routes them to invalid_steps so they
    emit a failed tool_result without invoking the tool.
    """

    summary: str
    findings: List[Dict[str, Any]]
    pruned_step_ids: List[str]


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
        # Holds the most recent ToolResult list emitted by
        # ``_stream_execute_plan``. Set as an instance attribute so the
        # async-generator helper can hand results back to the caller
        # without a non-None return value (which is awkward in async
        # generators).
        self._last_streamed_results: List[ToolResult] = []
        # Last request complexity classification set by
        # ``_select_model_by_complexity`` so the model_routing thinking event
        # can surface it without recomputing. One of "simple"|"moderate"|"complex".
        self._last_complexity: str = "moderate"
        # Per-turn self-correction counter. Reset at the start of each turn
        # (_run_turn / _run_offline). Capped at 2 per turn so a genuinely
        # broken tool cannot loop the offline auto-recovery indefinitely.
        self._self_corrections_this_turn: int = 0
        # Cross-session episodic memory — preferences + plan-pattern cache.
        # Loaded from <workspace>/episodic_memory.json and updated after
        # each turn so subsequent sessions can personalize responses and
        # reuse successful tool sequences.
        try:
            episodic_store.init(self.config.workspace_dir)
        except Exception:
            logger.exception("Episodic memory init failed; continuing without it")
        # Macro registry + scene-variant store — same workspace-local JSON
        # persistence pattern as episodic memory. Loaded once at agent
        # construction so subsequent tool calls can read/write without
        # re-initializing.
        try:
            macro_store.init(self.config.workspace_dir)
        except Exception:
            logger.exception("Macro store init failed; continuing without it")
        try:
            workflow_store.init(self.config.workspace_dir)
        except Exception:
            logger.exception("Workflow store init failed; continuing without it")
        try:
            variant_store.init(self.config.workspace_dir)
        except Exception:
            logger.exception("Variant store init failed; continuing without it")
        # Scene checkpoint store — persistent revision history of the scene.
        # Same workspace-local JSON persistence pattern as the stores above.
        try:
            checkpoint_store.init(self.config.workspace_dir)
        except Exception:
            logger.exception("Checkpoint store init failed; continuing without it")

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
        # Asset library — drop pre-built assets, scatter-paint clusters,
        # and snap objects to the highest surface below them. Higher-
        # level creation abstractions for level-design style authoring.
        registry.register(AssetLibraryTool())
        registry.register(ScatterPaintTool())
        registry.register(SnapToSurfaceTool())
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
        # Viewport & editor-state control — toggle minimap/shadows, switch
        # projection, switch edit/run mode, save/load named scene slots.
        registry.register(SetMinimapTool())
        registry.register(SetShadowsTool())
        registry.register(SetViewportProjectionTool())
        registry.register(SetEditorModeTool())
        registry.register(SaveSceneSlotTool())
        registry.register(LoadSceneSlotTool())
        # Extended editor capabilities — per-field material/geometry editing,
        # object parenting, on-canvas annotations, shortcut config.
        registry.register(SetMaterialPropertyTool())
        registry.register(SetGeometryParamsTool())
        registry.register(SetObjectParentTool())
        registry.register(AddAnnotationTool())
        registry.register(RemoveAnnotationTool())
        registry.register(ConfigureShortcutsTool())
        # Scene workflow intelligence — read-only scene queries, thematic
        # style presets, bulk transforms, scene statistics, annotation
        # listing, and cinematic camera flythrough. These give the Agent
        # higher-level authoring capabilities beyond the primitive tools.
        registry.register(QuerySceneTool())
        registry.register(StyleSceneTool())
        registry.register(BatchTransformTool())
        registry.register(SceneStatisticsTool())
        registry.register(ListAnnotationsTool())
        registry.register(CameraFlythroughTool())
        # Editor gap tools — dismiss overlays the frontend already supports
        # (radial menu, measurement overlay, camera flythrough) but had no
        # agent-callable tool counterpart.
        registry.register(ControlRadialMenuTool())
        registry.register(ClearMeasurementTool())
        registry.register(StopCameraFlythroughTool())
        # Macros — user-defined reusable tool-call recipes. invoke_macro
        # receives the registry so it can replay steps through the same
        # executor pipeline as normal tool calls.
        registry.register(DefineMacroTool())
        registry.register(InvokeMacroTool(registry=registry))
        registry.register(ListMacrosTool())
        registry.register(DeleteMacroTool())
        # Agentic Workflow Templates — saveable named tool-graph recipes.
        # invoke_workflow receives the registry so it can replay steps
        # through the same executor pipeline as normal tool calls.
        registry.register(SaveWorkflowTool())
        registry.register(InvokeWorkflowTool(registry=registry))
        registry.register(ListWorkflowsTool())
        registry.register(DeleteWorkflowTool())
        # Scene variants — named snapshots + jittered alternatives for
        # design exploration. randomize_variant loads a saved variant then
        # jitters material hue + object positions to spawn an alternative.
        registry.register(SaveVariantTool())
        registry.register(LoadVariantTool())
        registry.register(ListVariantsTool())
        registry.register(RandomizeVariantTool())
        # Pipeline authoring — let the Agent compose multimodal node-graph
        # DAGs (text→image→3D etc.) without executing them. The frontend
        # renders the returned graph in NodeGraphView; the user triggers
        # execution via the existing Run button on the rendered graph.
        registry.register(ComposePipelineTool())
        registry.register(ListPipelineTemplatesTool())
        # Agent scene intelligence — semantic scene description + actionable
        # creative next-step proposals. These give the Agent the ability to
        # "see" the scene and reason about it spatially/aesthetically, and
        # underpin the proactive-suggestion flow on the DONE event.
        registry.register(DescribeSceneTool())
        registry.register(SuggestNextActionsTool())
        registry.register(ReflectOnSessionTool())
        registry.register(SceneCritiqueTool())
        registry.register(AutoFixSceneTool(registry=registry))
        # Agent explicit memory — pin / recall / forget durable user
        # facts. Pinned facts survive session resets and are injected
        # into the LLM system note so the Agent personalizes its
        # reasoning across turns without the user repeating themselves.
        registry.register(PinFactTool())
        registry.register(RecallFactsTool())
        registry.register(ForgetFactTool())
        # Scene checkpoints — persistent, revisioned version history of the
        # scene with semantic summaries and structural diffs. Distinct from
        # variants (exploration alternatives): checkpoints are ordered and
        # immutable, forming a true timeline of the scene's evolution.
        registry.register(CheckpointSceneTool())
        registry.register(ListCheckpointsTool())
        registry.register(RestoreCheckpointTool())
        registry.register(CheckpointDiffTool())
        # Cinematic storyboard — sequence-level camera direction. Lets the
        # Agent compose, edit, and play a storyboard of camera shots that
        # narrates the scene like a film sequence.
        registry.register(ComposeStoryTool())
        registry.register(AddShotTool())
        registry.register(UpdateShotTool())
        registry.register(RemoveShotTool())
        registry.register(ListStoryTool())
        registry.register(ClearStoryTool())
        registry.register(PlayStoryTool())
        # Frontend-editor coverage gap tools — list scene templates,
        # turntable viewport orbit, per-layer visibility toggle, list
        # creative skills. These close remaining gaps between the backend
        # tool registry and the frontend editor surface (SceneTemplates
        # modal, LayersTab per-layer eye toggle, SkillsTab catalog).
        registry.register(ListSceneTemplatesTool())
        registry.register(OrbitViewportTool())
        registry.register(SetLayerVisibilityTool())
        registry.register(ListSkillsTool())
        # Constraint-authoring — let the Agent declare spatial
        # relationships (above / below / faces / centered / min_distance /
        # aligned / above_floor) and solve them in one call. Distinct
        # from critique (post-hoc problem finder) and auto_fix (single-
        # pass healer): constraints are declarative and user-authored.
        registry.register(AddConstraintTool())
        registry.register(ListConstraintsTool())
        registry.register(ClearConstraintsTool())
        registry.register(SolveConstraintsTool())
        # Goal-driven refinement — multi-iteration critique+autofix loop
        # with a user-stated goal. Receives the registry so autofix can
        # resolve proposed fixes to registered tools.
        registry.register(RefineSceneTool(registry=registry))
        # Generative geometry — radial symmetry (petals / blades / spokes)
        # and clone-with-jitter (organic scatter: forests, crowds, rubble).
        # Both emit standard create deltas using the existing SceneObject
        # shape, so the frontend renders them without any changes.
        registry.register(RadialSymmetryTool())
        registry.register(CloneWithJitterTool())
        # Mesh detail editing — convert geometry type in place (preserving
        # transform/material/parent) and scale segment counts in one call
        # for smoother or lower-poly surfaces.
        registry.register(ConvertGeometryTool())
        registry.register(SubdivideMeshTool())

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

    def scene_diff(
        self, session_id: str, from_label: str = "prev", to_label: str = "current"
    ) -> Dict[str, Any]:
        """Compute a structural diff between two scene snapshots.

        ``from_label`` / ``to_label`` may be either ``"prev"`` (the most
        recent entry on the undo stack), ``"current"`` (the live scene), or
        ``"redo"`` (the most recent entry on the redo stack). Returns a dict
        with ``added`` / ``removed`` / ``changed`` lists keyed by object id,
        plus per-snapshot object counts so the caller can summarize.
        """
        def _resolve(label: str) -> Optional[Dict[str, Any]]:
            if label == "current":
                return self.get_scene(session_id).to_dict()
            if label == "prev":
                hist = self._scene_history.get(session_id, [])
                return hist[-1] if hist else None
            if label == "redo":
                redo = self._scene_redo.get(session_id, [])
                return redo[-1] if redo else None
            return None

        from_scene = _resolve(from_label)
        to_scene = _resolve(to_label)
        if from_scene is None or to_scene is None:
            return {
                "available": False,
                "from_label": from_label,
                "to_label": to_label,
                "message": "One or both snapshots are unavailable for this session.",
            }

        from_objs = {o.get("id"): o for o in from_scene.get("objects", [])}
        to_objs = {o.get("id"): o for o in to_scene.get("objects", [])}
        from_lights = {l.get("id"): l for l in from_scene.get("lights", [])}
        to_lights = {l.get("id"): l for l in to_scene.get("lights", [])}

        added = sorted(set(to_objs) - set(from_objs))
        removed = sorted(set(from_objs) - set(to_objs))
        changed: List[Dict[str, Any]] = []
        for oid in sorted(set(from_objs) & set(to_objs)):
            a = from_objs[oid]
            b = to_objs[oid]
            fields: List[str] = []
            for key in ("name", "transform", "material", "geometry", "visible", "locked", "group_id", "tags", "animation"):
                if a.get(key) != b.get(key):
                    fields.append(key)
            if fields:
                changed.append({"id": oid, "name": b.get("name", ""), "fields": fields})

        lights_added = sorted(set(to_lights) - set(from_lights))
        lights_removed = sorted(set(from_lights) - set(to_lights))
        lights_changed: List[str] = []
        for lid in sorted(set(from_lights) & set(to_lights)):
            if from_lights[lid] != to_lights[lid]:
                lights_changed.append(lid)

        scene_fields: List[str] = []
        for key in ("background", "environment", "fog", "grid_visible", "grid_size"):
            if from_scene.get(key) != to_scene.get(key):
                scene_fields.append(key)

        return {
            "available": True,
            "from_label": from_label,
            "to_label": to_label,
            "from_object_count": len(from_objs),
            "to_object_count": len(to_objs),
            "objects": {
                "added": added,
                "removed": removed,
                "changed": changed,
            },
            "lights": {
                "added": lights_added,
                "removed": lights_removed,
                "changed": lights_changed,
            },
            "scene_fields_changed": scene_fields,
            "annotations_from_count": len(from_scene.get("annotations", [])),
            "annotations_to_count": len(to_scene.get("annotations", [])),
        }

    async def _scene_suggestions(self, scene: Scene) -> List[Dict[str, Any]]:
        """Compute proactive next-action suggestions for the current scene.

        Invokes the registered ``suggest_next_actions`` tool so the tool
        surface and the post-turn DONE event share a single source of
        truth — changes to the tool's logic (direction bias, count cap)
        automatically apply to the proactive-suggestion flow.

        Wrapped so a failure in the suggestion engine never breaks the
        turn's ``done`` event — the suggestions field simply falls back
        to an empty list.
        """
        try:
            tool = self.registry.get("suggest_next_actions")
            if tool is None:
                # Defensive fallback if the tool is not registered.
                return generate_suggestions(scene.to_dict())
            result = await tool.execute(scene, {"count": 3, "direction": "any"})
            return list(result.data.get("suggestions", []))
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

    async def _stream_execute_plan(
        self,
        scene: Scene,
        plan: TaskPlan,
        session_id: str,
    ) -> AsyncIterator[AgentEvent]:
        """Execute a plan while streaming per-step PLAN_UPDATE events.

        Bridges the executor's progress-callback API with the orchestrator's
        async-generator event stream using an asyncio.Queue. The executor
        task runs concurrently with a queue-draining loop so the frontend
        sees ``started`` / ``completed`` / ``failed`` transitions in real
        time, even when a batch contains long-running tools (image/3D
        generation) that finish out of order.

        Yields PLAN_UPDATE events as each step progresses. After the
        generator is exhausted, the final ToolResult list is available
        on ``self._last_streamed_results`` so the caller can correlate
        steps with their outcomes.
        """
        queue: asyncio.Queue = asyncio.Queue()

        async def _progress(idx, total, step, phase, result):
            await queue.put({
                "id": step.tool_call_id,
                "tool": step.tool_name,
                "status": phase,
                "index": idx,
                "total": total,
                "message": result.message if result else "",
            })

        async def _runner():
            return await self.executor.execute_plan(scene, plan, progress=_progress)

        runner_task = asyncio.ensure_future(_runner())
        try:
            while True:
                # Wait for either a progress event or task completion.
                done, _pending = await asyncio.wait(
                    {asyncio.ensure_future(queue.get()), runner_task},
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if runner_task in done:
                    # Drain any remaining queued events before returning.
                    while not queue.empty():
                        ev = queue.get_nowait()
                        yield AgentEvent(type=EventType.PLAN_UPDATE, data=ev)
                    break
                # A progress event is ready.
                ev = queue.get_nowait()
                yield AgentEvent(type=EventType.PLAN_UPDATE, data=ev)
        finally:
            if not runner_task.done():
                runner_task.cancel()
                try:
                    await runner_task
                except Exception:
                    pass
        self._last_streamed_results = runner_task.result()

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
        built = await self._build_preview_plan(user_message, session_id, model=model)
        if built.get("error"):
            return {"error": built["error"], "plan": None}
        return self._plan_payload_with_approval(
            built["plan"],
            built["tool_calls"],
            built["reasoning"],
            session_id,
            token_usage=built.get("token_usage"),
            offline=built["offline"],
        )

    async def _build_preview_plan(
        self, user_message: str, session_id: str = "default", model: Optional[str] = None
    ) -> Dict[str, Any]:
        """Shared core of ``plan_only`` / ``plan_graph``.

        Runs a single LLM pass (or the offline rule parser fallback) and
        returns the built ``TaskPlan`` plus the raw tool calls, reasoning
        text, token usage, the live ``Scene`` (for downstream critique /
        perception checks), and an ``offline`` flag. Does NOT shape the
        approval payload — callers do that. On an LLM streaming error,
        returns ``{"error": ...}`` and no plan.
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
            return {
                "plan": plan,
                "tool_calls": tool_calls_collected,
                "reasoning": "",
                "token_usage": None,
                "offline": True,
                "scene": scene,
            }

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
                return {"error": chunk.content or "LLM streaming error"}
            if chunk.content:
                full_text += chunk.content
            if chunk.tool_calls:
                tool_calls_collected.extend(chunk.tool_calls)
            if getattr(chunk, "usage", None):
                token_usage = chunk.usage
            if chunk.finish_reason and not chunk.tool_calls:
                break

        plan = self.planner.from_tool_calls(tool_calls_collected, reasoning=full_text)
        return {
            "plan": plan,
            "tool_calls": tool_calls_collected,
            "reasoning": full_text,
            "token_usage": token_usage,
            "offline": False,
            "scene": scene,
        }

    async def plan_graph(
        self, user_message: str, session_id: str = "default", model: Optional[str] = None
    ) -> Dict[str, Any]:
        """Plan-only preview enriched with the DAG graph + critique + perception.

        Mirrors ``plan_only`` (single LLM pass, no execution, no scene
        mutation) but returns the plan payload alongside:
          - ``graph``: the plan dependency DAG (``plan.to_graph_payload()``)
            for node-graph rendering.
          - ``critique``: pre-execution critique findings
            (``_critique_plan``) — advisory diagnostics + pruned step ids.
          - ``perception``: heuristic scene-perception findings
            (``_run_perception_check``) when the plan contains a multimodal
            3D-generation step; ``None`` otherwise.

        The DAG node ``status`` is always ``"pending"`` here (this is a
        preview, not a live turn); the frontend merges ``plan_update``
        transitions during a real run.
        """
        built = await self._build_preview_plan(user_message, session_id, model=model)
        if built.get("error"):
            return {"error": built["error"], "plan": None, "graph": None, "critique": None, "perception": None}
        plan = built["plan"]
        scene = built["scene"]
        base = self._plan_payload_with_approval(
            plan,
            built["tool_calls"],
            built["reasoning"],
            session_id,
            token_usage=built.get("token_usage"),
            offline=built["offline"],
        )
        critique = self._critique_plan(plan, scene)
        # Perception check only fires for multimodal 3D-generation plans;
        # mirror the _run_turn gate so simple edits don't pay the cost.
        has_3d = any(s.tool_name in _MULTIMODAL_3D_TOOLS for s in plan.steps)
        perception = self._run_perception_check(scene, plan) if has_3d else None
        return {
            **base,
            "graph": plan.to_graph_payload(),
            "critique": {
                "summary": critique.summary,
                "findings": critique.findings,
                "pruned_step_ids": critique.pruned_step_ids,
            },
            "perception": perception,
        }

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
            "minimap", "shadow", "orthographic", "perspective", "edit mode", "run mode",
            "preview mode", "save scene", "load scene", "scene slot", "snapshot slot",
            "选择", "聚焦", "锁定", "隐藏", "重命名", "隔离", "撤销", "重做", "轴心",
            "剖切", "渲染质量", "小地图", "阴影", "正交", "透视", "编辑模式", "运行模式",
            "预览模式", "保存场景", "加载场景", "场景存档",
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

    # Curated core categories used when no intent signal matches. Keeps the
    # common-case toolset (geometry/material/lighting/camera/scene/export
    # essentials) on top of the always-on set, so an ambiguous or terse
    # message does not bloat the prompt with all 155+ tool schemas.
    # Specialized categories (animation/procedural/multimodal/constraints/
    # intelligence/memory) are excluded — they only activate when their
    # keyword signal fires.
    _CORE_FALLBACK_CATEGORIES = {
        "creation", "transform", "material", "lighting", "camera",
        "scene", "export",
    }

    def _select_tool_schemas(self, user_message: str) -> tuple:
        """Pick the tool schema subset relevant to this user message.

        Returns a ``(schemas, categories, matched_signals)`` triple where
        ``schemas`` is the filtered list to inject into the LLM call,
        ``categories`` is the active category set, and ``matched_signals``
        is the list of category names whose keyword signals fired.

        When no signal matches, returns the curated core set (always-on +
        the common-case creation/transform/material/lighting/camera/scene/
        export categories) instead of the full 155+ tool registry, so an
        ambiguous or terse message does not bloat the prompt. Specialized
        categories still activate when their keyword signal fires.

        Recency bias: when the message has no keyword signal AND the
        episodic memory has a recent successful tool chain, the chain's
        categories are also injected. This handles follow-up turns like
        "make it bigger" / "now another one" where the user's prior intent
        is the strongest signal but the message itself is terse.
        """
        msg = (user_message or "").lower()
        matched: List[str] = []
        for category, signals in self._INTENT_CATEGORY_SIGNALS.items():
            if any(sig in msg for sig in signals):
                matched.append(category)
        if not matched:
            # Ambiguous / no signal — return the curated core set so the
            # LLM retains the common-case capabilities without the token
            # cost of the full 155+ tool registry. Recency bias adds the
            # categories of the last successful tool chain so follow-up
            # turns to a successful creation stay in-context.
            active = self._ALWAYS_ON_CATEGORIES | self._CORE_FALLBACK_CATEGORIES
            try:
                last_tools = episodic_store.get().last_successful_tools
            except Exception:
                last_tools = []
            if last_tools:
                for tn in last_tools:
                    cat = _TOOL_CATEGORIES.get(tn)
                    if cat:
                        active = active | {cat}
            names = [t.name for t in self.registry.all() if t.category in active]
            return self.registry.schemas_for(names), sorted(active), []
        active = set(matched) | self._ALWAYS_ON_CATEGORIES
        names = [t.name for t in self.registry.all() if t.category in active]
        return self.registry.schemas_for(names), sorted(active), matched

    # ------------------------------------------------------------------
    # Quality self-assessment — score the turn's outcome
    # ------------------------------------------------------------------

    def _assess_turn_quality(self, scene: Scene, results: List[ToolResult], plan) -> Dict[str, Any]:
        """Score the turn's outcome on a 0-100 scale.

        Combines five cheap signals:
          - success rate of executed tool results (base weight)
          - goal achievement proxy: plan steps executed vs failed
          - scene mutation: whether any tool produced a mutating delta
            (create/update/delete/create_light/update_light/delete_light)
          - retry friction: per-turn self-corrections applied
          - verification corrections: post-execution fixup steps issued
        Returns a dict with ``score``, ``success_rate``, ``scene_mutated``,
        ``goal_achievement``, ``retries``, ``corrections``, and a short
        ``verdict`` label. Used only for the checkpoint thinking event —
        never blocks the turn.
        """
        total = len(results)
        if total == 0:
            return {"score": 100, "success_rate": 1.0, "scene_mutated": False,
                    "goal_achievement": 1.0, "retries": 0, "corrections": 0,
                    "verdict": "noop", "note": "no tools executed"}
        successes = sum(1 for r in results if r.success)
        success_rate = successes / total

        # Goal-achievement proxy — fraction of plan steps that succeeded.
        # Caps at 1.0 so extra successful corrections don't inflate the score.
        plan_steps = list(getattr(plan, "steps", []) or [])
        if plan_steps:
            goal_achievement = min(1.0, successes / max(1, len(plan_steps)))
        else:
            goal_achievement = success_rate

        # Scene mutation — detect whether any tool produced a mutating delta.
        # Replaces the old "objects > 0" check which was always true after
        # the first creation and gave no signal about whether THIS turn
        # actually changed the scene.
        mutating_actions = {
            "create", "update", "delete",
            "create_light", "update_light", "delete_light",
        }
        scene_mutated = any(
            getattr(d, "action", "") in mutating_actions
            for r in results
            for d in (r.deltas or [])
        )

        # Retry friction — per-turn self-corrections applied by
        # _maybe_self_correct. Each retry is friction even when it succeeds.
        retries = getattr(self, "_self_corrections_this_turn", 0) or 0
        # Verification corrections — post-execution fixup steps.
        corrections_count = getattr(plan, "_verification_corrections", 0) or 0

        # Weighted score (max 100):
        #   success_rate * 55  — base outcome
        #   goal_achievement * 20 — plan completion
        #   scene_mutated * 10  — actual scene change
        #   clean_turn_bonus * 15 — full success with no friction
        score = int(success_rate * 55)
        score += int(goal_achievement * 20)
        if scene_mutated:
            score += 10
        if success_rate == 1.0 and retries == 0 and corrections_count == 0:
            score += 15
        # Friction penalties (capped).
        score -= min(15, retries * 5)
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
            "goal_achievement": round(goal_achievement, 2),
            "retries": retries,
            "corrections": corrections_count,
            "verdict": verdict,
        }

    def _build_turn_reflection(
        self,
        user_message: str,
        plan,
        results: List[ToolResult],
        scene: Scene,
        quality: Dict[str, Any],
        iteration: int,
        elapsed: float,
    ) -> str:
        """Compose a short end-of-turn narrative summary.

        Surfaces what the Agent accomplished, what failed (if anything),
        the resulting scene state, and what it would consider next. The
        reflection is rendered as a distinct ``reflection`` thinking phase
        so the user can see the Agent's self-assessment beyond the raw
        numeric quality score. Purely advisory.
        """
        total = len(results)
        successes = sum(1 for r in results if r.success)
        failures = total - successes
        verdict = quality.get("verdict", "unknown")
        score = quality.get("score", -1)

        # Collect the distinct tool names that ran.
        tool_names: List[str] = []
        seen: set = set()
        if plan is not None:
            for step in getattr(plan, "steps", []) or []:
                tn = getattr(step, "tool_name", "") or ""
                if tn and tn not in seen:
                    seen.add(tn)
                    tool_names.append(tn)
        tools_str = ", ".join(tool_names) if tool_names else "none"

        # Scene state snapshot.
        n_objects = len(scene.objects)
        n_lights = len(scene.lights)
        n_cameras = len(scene.cameras) if hasattr(scene, "cameras") else 0

        # Build the narrative.
        parts: List[str] = []
        # 1. Outcome headline.
        if total == 0:
            parts.append("No tools were executed this turn — the response was purely conversational.")
        else:
            head = f"Executed {total} tool call(s) across {iteration + 1} iteration(s)"
            if failures > 0:
                head += f"; {successes} succeeded, {failures} failed"
            else:
                head += "; all succeeded"
            parts.append(head + f". Tools: {tools_str}.")

        # 2. Quality verdict.
        parts.append(
            f"Self-assessment: {verdict} (score {score}/100, "
            f"success_rate {quality.get('success_rate', 0)})."
        )

        # 3. Resulting scene.
        parts.append(
            f"Scene now holds {n_objects} object(s), {n_lights} light(s)"
            + (f", {n_cameras} camera(s)." if n_cameras else ".")
        )

        # 4. Failure detail (when any).
        if failures > 0:
            failed_msgs: List[str] = []
            for r in results:
                if not r.success and r.message:
                    failed_msgs.append(r.message)
            if failed_msgs:
                # Keep the failure digest short — first 2 messages.
                digest = " | ".join(failed_msgs[:2])
                if len(failed_msgs) > 2:
                    digest += f" (+{len(failed_msgs) - 2} more)"
                parts.append(f"Friction: {digest}")

        # 5. Forward-looking note.
        if verdict in ("excellent", "good"):
            parts.append("Ready for the user's next instruction.")
        elif verdict == "partial":
            parts.append("Consider rephrasing or refining the request for a fuller outcome.")
        elif verdict == "poor":
            parts.append("The turn underperformed — a follow-up with more specific intent may help.")
        return " ".join(parts)

    # ------------------------------------------------------------------
    # Cost-aware model routing
    # ------------------------------------------------------------------

    def _classify_complexity(self, message: str, scene: Scene) -> str:
        """Classify a request's complexity as simple / moderate / complex.

        Heuristic signal count, not an LLM call. Combines four cheap signals:
          - intent breadth (how many category signals fire)
          - read-only vs mutating intent (inspection phrases cap at simple)
          - scene density (empty scene keeps single creations simple;
            dense scene bumps mutating ops to moderate)
          - heavy procedural / multimodal / skill keywords (bump to complex)

        Tiers:
          - simple: a single short intent (one creation, one transform, a
            yes/no inspection, or a single editor toggle). Routed to the
            cheapest available tier.
          - moderate: 2-3 intents, multi-target ops, or material/lighting
            changes. Routed to a mid tier.
          - complex: 4+ distinct intents, procedural generation, multimodal
            pipelines, multi-step skills, or long messages. Routed to the
            strongest tier.
        """
        msg = (message or "").lower()
        intents_hit = 0
        for signals in self._INTENT_CATEGORY_SIGNALS.values():
            if any(sig in msg for sig in signals):
                intents_hit += 1

        # Read-only intent phrases — queries that never mutate the scene.
        # These cap at "simple" regardless of length, unless a heavy
        # keyword escalates the request to complex.
        read_only_phrases = (
            "show ", "list", "info", "what is", "what's", "how many",
            "describe", "measure", "query", "inspect", "analyze", "statistics",
            "suggest", "reflect", "critique", "snapshot", "capture",
            "列出", "信息", "测量", "分析", "多少", "描述", "建议", "查询",
        )
        is_read_only = any(p in msg for p in read_only_phrases)

        # Scene density — count live scene entities the request must reason over.
        scene_dict = scene.to_dict() if scene is not None else {}
        n_objects = len(scene_dict.get("objects", []))
        n_lights = len(scene_dict.get("lights", []))
        scene_dense = (n_objects + n_lights) >= 12
        scene_empty = (n_objects + n_lights) == 0

        # Mutating-intent detection — keywords that change the scene.
        mutating_phrases = (
            "create", "add", "make", "generate", "build", "transform", "move",
            "rotate", "scale", "delete", "remove", "apply", "set background",
            "set fog", "arrange", "group", "ungroup", "duplicate", "mirror",
            "scatter", "shatter", "refine", "solve",
            "创建", "新建", "添加", "生成", "构建", "移动", "旋转", "缩放",
            "删除", "应用", "排列", "分组",
        )
        is_mutating = any(p in msg for p in mutating_phrases)

        # Procedural / multimodal / skill / agentic keywords bump complexity
        # directly. Expanded beyond the original list to cover the full
        # capability surface (procedural, multimodal, constraints, subagent,
        # pipeline, storyboard, checkpoint, variant, refine, etc.).
        heavy_keywords = (
            "terrain", "l-system", "voronoi", "staircase", "forest", "city",
            "solar system", "galaxy", "atom", "molecule", "crystal", "zen garden",
            "image to 3d", "generate 3d", "generate video", "generate music",
            "generate image", "synthesize speech", "transcribe",
            "animate", "keyframe", "flythrough", "procedural",
            "refine scene", "refine the scene", "auto fix", "auto_fix",
            "constraint", "subagent", "sub-agent", "dispatch", "pipeline",
            "storyboard", "checkpoint", "variant", "macro", "workflow",
            "radial symmetry", "clone with jitter", "scatter paint",
            "boolean", "l system",
            "地形", "森林", "城市", "太阳系", "原子", "分子", "水晶",
            "图片转3d", "生成3d", "生成视频", "生成音乐", "生成图片",
            "动画", "关键帧", "约束", "子代理", "管道", "故事板",
            "检查点", "变体", "宏", "工作流", "布尔",
        )
        if any(k in msg for k in heavy_keywords) or intents_hit >= 4 or len(message) > 240:
            return "complex"

        # Read-only requests cap at simple (cheap to answer, no mutation).
        if is_read_only and not is_mutating:
            return "simple"

        # Empty scene + single mutating intent → simple (one creation).
        # Dense scene + mutating intent → moderate (more targets to reason over).
        if intents_hit <= 1 and len(message) <= 80:
            if scene_empty or not is_mutating:
                return "simple"
            if scene_dense:
                return "moderate"
            return "simple"
        # Dense scene bumps a moderate single-intent mutation up — but only
        # to moderate, not complex (complex is reserved for the heavy path).
        if scene_dense and is_mutating and intents_hit >= 2:
            return "moderate"
        if intents_hit <= 1:
            return "simple"
        return "moderate"

    def _select_model_by_complexity(self, message: str, scene: Scene) -> Optional[str]:
        """Pick a chat model id whose cost tier matches request complexity.

        Returns ``None`` when fewer than two chat models are available (so
        routing is a no-op and the LLM client's configured default is used),
        or when no model satisfies the chosen tier cap. Simple → cost tier
        ≤1, moderate → ≤2, complex → ≤4 (strongest available). Ties broken
        by latency tier (faster first).
        """
        complexity = self._classify_complexity(message, scene)
        self._last_complexity = complexity
        tier_cap = {"simple": 1, "moderate": 2, "complex": 4}.get(complexity, 2)
        available = model_router.list_available_chat_models()
        # Exclude the offline default — it's only a last resort, never a
        # complexity-routed pick.
        available = [m for m in available if m != "trigen-default"]
        if len(available) < 2:
            return None
        candidates: List[tuple] = []
        for mid in available:
            entry = model_router.get_model(mid)
            if entry is None:
                continue
            if entry.cost_tier > tier_cap:
                continue
            candidates.append((entry.cost_tier, entry.latency_tier, mid))
        if not candidates:
            # Relax to the cheapest available if the tier cap is too strict.
            for mid in available:
                entry = model_router.get_model(mid)
                if entry is None:
                    continue
                candidates.append((entry.cost_tier, entry.latency_tier, mid))
        if not candidates:
            return None
        candidates.sort()
        return candidates[0][2]

    # ------------------------------------------------------------------
    # Pre-execution critique gate
    # ------------------------------------------------------------------

    def _critique_plan(self, plan: TaskPlan, scene: Scene) -> "_PlanCritique":
        """Cheap deterministic self-review of a plan before execution.

        Surfaces findings (advisory) and a set of provably-dead step ids to
        prune (hard skip). Findings never block the turn — they are surfaced
        to the user as a ``critique`` thinking phase and feed the LLM a clean
        signal to correct on its next reflection round.

        Checks performed:
          - dead-after-delete: a step mutating/inspecting a target that an
            earlier ``delete_object`` step already removed (pruned).
          - target-miss: a step referencing a name not present in the scene
            and not created earlier in the plan (flagged, not pruned — the
            fuzzy resolver may still recover it at execution).
          - redundant repeat: three or more consecutive transforms on the
            same target (flagged as collapsible).
          - duplicate create: two creation steps producing the same name
            (the second is pruned to avoid an ambiguous id resolution race).
        """
        findings: List[Dict[str, Any]] = []
        pruned: List[str] = []
        step_ids = {s.tool_call_id for s in plan.steps}

        # Names created within this plan (skip duplicates of the same name).
        created_names: Dict[str, str] = {}  # name -> first creator step id
        for s in plan.steps:
            if s.tool_name in {"create_object", "add_light", "add_camera"}:
                nm = s.arguments.get("name")
                if isinstance(nm, str) and nm:
                    if nm in created_names:
                        pruned.append(s.tool_call_id)
                        findings.append({
                            "kind": "duplicate_create",
                            "step_id": s.tool_call_id,
                            "tool": s.tool_name,
                            "target": nm,
                            "message": f"Duplicate creation of '{nm}'; second instance pruned.",
                        })
                    else:
                        created_names[nm] = s.tool_call_id

        # Track targets deleted within this plan; later steps on the same
        # target are provably dead and pruned.
        deleted_names: set = set()
        # Live scene object/light/camera names for target-miss detection.
        scene_names = {o.name for o in scene.objects}
        scene_names |= {l.name for l in scene.lights}
        scene_names |= {c.name for c in scene.cameras}

        # Consecutive-transform counter per target (redundant-repeat flag).
        consec_transforms: Dict[str, int] = {}

        for s in plan.steps:
            if s.tool_call_id in pruned:
                continue
            targets = self.planner._step_target_names(s)
            # dead-after-delete check
            if s.tool_name == "delete_object":
                for t in targets:
                    deleted_names.add(t)
                continue
            dead_targets = [t for t in targets if t in deleted_names]
            if dead_targets:
                pruned.append(s.tool_call_id)
                findings.append({
                    "kind": "dead_after_delete",
                    "step_id": s.tool_call_id,
                    "tool": s.tool_name,
                    "targets": dead_targets,
                    "message": (
                        f"{s.tool_name} on '{dead_targets[0]}' runs after a delete_object "
                        f"that removed it; pruned as provably dead."
                    ),
                })
                continue
            # target-miss check (advisory — fuzzy resolver may still recover)
            for t in targets:
                if t in created_names:
                    continue
                if t not in scene_names:
                    findings.append({
                        "kind": "target_miss",
                        "step_id": s.tool_call_id,
                        "tool": s.tool_name,
                        "target": t,
                        "message": (
                            f"'{t}' is not in the scene and not created in this plan; "
                            f"execution may fail (fuzzy resolver will attempt recovery)."
                        ),
                    })
            # redundant-repeat transform check
            if s.tool_name in {"transform_object", "modify_geometry"}:
                for t in targets:
                    consec_transforms[t] = consec_transforms.get(t, 0) + 1
                    if consec_transforms[t] == 3:
                        findings.append({
                            "kind": "redundant_repeat",
                            "step_id": s.tool_call_id,
                            "tool": s.tool_name,
                            "target": t,
                            "message": (
                                f"Three consecutive transforms on '{t}'; consider collapsing "
                                f"into a single step."
                            ),
                        })
            else:
                # Reset the counter when a non-transform step touches a target.
                for t in targets:
                    consec_transforms.pop(t, None)

        if not findings:
            summary = "Plan critique passed: no dead steps or target misses detected."
        else:
            kinds = sorted({f["kind"] for f in findings})
            pruned_note = f" {len(pruned)} step(s) pruned." if pruned else ""
            summary = f"Plan critique found {len(findings)} issue(s): {', '.join(kinds)}.{pruned_note}"

        return _PlanCritique(
            summary=summary,
            findings=findings,
            pruned_step_ids=pruned,
        )

    # ------------------------------------------------------------------
    # Multimodal perception loop
    # ------------------------------------------------------------------

    def _run_perception_check(self, scene: Scene, plan) -> Dict[str, Any]:
        """Heuristic viewport-perception check on the current scene state.

        Runs deterministic geometry checks (object count, scene bounding
        box, pairwise AABB overlaps, scene scale, off-center framing,
        object visibility, missing lights) that approximate what a vision
        model would see after a multimodal 3D-generation step. Returns a
        dict with ``summary``, ``findings`` (advisory list), and
        ``metrics`` (raw signals). Surfaced as a THINKING phase="perception"
        event; never blocks the turn.

        Only meant to fire when the plan contained a 3D-generating tool
        (``generate_3d_asset`` / ``image_to_3d``); the caller gates on
        ``_MULTIMODAL_3D_TOOLS`` so simple edits don't pay the cost of
        running the checks.
        """
        findings: List[Dict[str, Any]] = []
        metrics: Dict[str, Any] = {}

        objects = list(scene.objects)
        obj_count = len(objects)
        metrics["object_count"] = obj_count
        metrics["light_count"] = len(scene.lights)
        metrics["camera_count"] = len(scene.cameras)

        if obj_count == 0:
            findings.append({
                "kind": "empty_scene",
                "severity": "high",
                "message": (
                    "Scene is empty after multimodal generation; no objects "
                    "to render. The 3D asset may not have been ingested."
                ),
            })
        else:
            # Build per-object AABBs from transform.position + scale. Use
            # scale × 0.5 as the half-extent (heuristic; matches the box
            # primitive default and is a reasonable proxy for other shapes).
            aabbs: List[List[Any]] = []  # [name, min[3], max[3]]
            for obj in objects:
                try:
                    pos = obj.transform.position
                    scale = obj.transform.scale
                    if not (isinstance(pos, list) and len(pos) == 3
                            and isinstance(scale, list) and len(scale) == 3):
                        continue
                    hx, hy, hz = abs(scale[0]) * 0.5, abs(scale[1]) * 0.5, abs(scale[2]) * 0.5
                    mn = [pos[0] - hx, pos[1] - hy, pos[2] - hz]
                    mx = [pos[0] + hx, pos[1] + hy, pos[2] + hz]
                    aabbs.append([obj.name, mn, mx])
                except Exception:
                    continue

            # Scene-wide bounding box + center.
            if aabbs:
                all_min = [min(a[1][i] for a in aabbs) for i in range(3)]
                all_max = [max(a[2][i] for a in aabbs) for i in range(3)]
                extent = [all_max[i] - all_min[i] for i in range(3)]
                center = [(all_min[i] + all_max[i]) / 2.0 for i in range(3)]
                metrics["scene_extent"] = extent
                metrics["scene_center"] = center
                metrics["scene_min"] = all_min
                metrics["scene_max"] = all_max

                max_extent = max(extent) if extent else 0.0
                # Scale sanity.
                if max_extent > 100.0:
                    findings.append({
                        "kind": "oversized_scene",
                        "severity": "medium",
                        "message": (
                            f"Scene extent ({max_extent:.1f} units) is very large; "
                            f"objects may be hard to frame together."
                        ),
                    })
                elif 0.0 < max_extent < 0.1:
                    findings.append({
                        "kind": "undersized_scene",
                        "severity": "medium",
                        "message": (
                            f"Scene extent ({max_extent:.3f} units) is very small; "
                            f"objects may be hard to see."
                        ),
                    })

                # Off-center framing: when the scene center is farther from
                # the origin than half the scene's largest extent, the
                # default camera (targeting origin) will miss most of it.
                offset = sum(c * c for c in center) ** 0.5
                metrics["center_offset"] = round(offset, 3)
                if max_extent > 0.0 and offset > max_extent * 0.5:
                    findings.append({
                        "kind": "off_center",
                        "severity": "low",
                        "message": (
                            f"Scene center is offset {offset:.1f} units from origin; "
                            f"the default viewport camera may not frame it."
                        ),
                    })

                # Pairwise AABB overlap test (n² — fine for typical scene
                # sizes after a multimodal step which produces <= ~30 objs).
                overlap_count = 0
                overlap_pairs: List[List[str]] = []
                for i in range(len(aabbs)):
                    for j in range(i + 1, len(aabbs)):
                        n1, mn1, mx1 = aabbs[i]
                        n2, mn2, mx2 = aabbs[j]
                        # Standard slab intersection test.
                        if all(mx1[k] >= mn2[k] and mx2[k] >= mn1[k] for k in range(3)):
                            overlap_count += 1
                            if len(overlap_pairs) < 5:
                                overlap_pairs.append([n1, n2])
                metrics["overlap_count"] = overlap_count
                if overlap_count > 0:
                    severity = "high" if overlap_count >= max(3, obj_count // 2) else "medium"
                    findings.append({
                        "kind": "object_overlap",
                        "severity": severity,
                        "message": (
                            f"{overlap_count} pair(s) of overlapping objects detected; "
                            f"consider repositioning to avoid interpenetration."
                        ),
                        "overlap_pairs": overlap_pairs,
                    })

            # Visibility audit.
            invisible = [o.name for o in objects if not o.visible]
            if invisible:
                findings.append({
                    "kind": "invisible_objects",
                    "severity": "low",
                    "message": (
                        f"{len(invisible)} object(s) are invisible: "
                        f"{', '.join(invisible[:5])}."
                    ),
                })

        # Lighting audit — without any lights the rendered viewport is dark.
        if obj_count > 0 and not scene.lights:
            findings.append({
                "kind": "no_lights",
                "severity": "medium",
                "message": (
                    "Scene has objects but no lights; rendering will be dark. "
                    "Consider calling add_light."
                ),
            })

        if not findings:
            summary = "Perception check passed: scene composition looks balanced."
        else:
            kinds = sorted({f["kind"] for f in findings})
            summary = f"Perception found {len(findings)} issue(s): {', '.join(kinds)}."

        return {
            "summary": summary,
            "findings": findings,
            "metrics": metrics,
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
        # Reset the per-turn self-correction counter. The cap is 2 per turn.
        self._self_corrections_this_turn = 0
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

        # Cost-aware model routing: when the user has not pinned a specific
        # model, classify the request complexity and pick a model tier from
        # the available chat models. Simple requests (single creation, a
        # transform, a yes/no inspection) route to a cheaper/faster tier;
        # complex multi-intent or procedural requests route to a stronger
        # tier. No-op when only one model is available or the user pinned
        # an explicit model — never overrides an explicit choice.
        if not model:
            picked = self._select_model_by_complexity(user_message, scene)
            if picked:
                model = picked
                yield AgentEvent(
                    type=EventType.THINKING,
                    data={
                        "phase": "model_routing",
                        "content": (
                            f"Cost-aware routing selected {picked} based on request complexity."
                        ),
                        "selected_model": picked,
                        "complexity": self._last_complexity,
                    },
                )

        # Smart tool selection: narrow the LLM-visible schema set to the
        # categories implicated by the user message. Falls back to the full
        # set when no intent signal matches. Always keeps inspection +
        # skills + editor essentials available so the agent can introspect.
        tool_schemas, active_categories, matched_signals = self._select_tool_schemas(user_message)
        scene_context = self.planner.build_context_message(scene.to_dict())
        messages = memory.to_openai_messages()
        # Inject scene context before the latest user message
        messages.insert(-1, {"role": "system", "content": scene_context})
        # Inject the learned cross-session user-preferences note (if any)
        # so the LLM can personalize tone and tool defaults this turn.
        try:
            pref_note = episodic_store.get().to_system_note()
        except Exception:
            logger.exception("Episodic memory note lookup failed")
            pref_note = ""
        if pref_note:
            messages.insert(-1, {"role": "system", "content": pref_note})

        # Structured context compression for long sessions. When the message
        # history has grown past the trigger threshold, inject a scene-aware
        # trajectory summary (tool usage, dominant intents, project goal) so
        # the LLM retains a coherent picture of the session without re-reading
        # every prior turn. Cheaper than the sliding-window compaction and
        # complementary to it.
        try:
            if should_compress(memory):
                report = compress_session(memory, scene.to_dict(), _TOOL_CATEGORIES)
                note = report.to_system_note()
                if note:
                    messages.insert(-1, {"role": "system", "content": note})
        except Exception:
            logger.exception("Context compression failed; continuing without it")

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

        # Proactive episodic pattern recall: if a high-quality cached plan
        # exists for this intent signature, surface it both as a thinking
        # event (so the user sees the agent recalling prior success) and as
        # a system note for the LLM (so it can bias tool selection toward
        # the previously successful chain). This is advisory — the LLM is
        # free to deviate when the scene state or user phrasing warrants.
        # Two-stage recall: exact signature first, then a fuzzy token-
        # overlap fallback so paraphrases of a previously successful intent
        # still benefit from cached experience.
        try:
            mem = episodic_store.get()
            cached_pattern = mem.lookup_pattern(user_message)
            if cached_pattern is None:
                cached_pattern = mem.lookup_similar_pattern(user_message)
        except Exception:
            logger.exception("Episodic pattern lookup failed")
            cached_pattern = None
        if cached_pattern is not None and cached_pattern.quality >= 70:
            recall_note = (
                f"Episodic memory: a similar past request succeeded with tools "
                f"[{', '.join(cached_pattern.tool_names)}] (quality={cached_pattern.quality}, "
                f"hits={cached_pattern.hits}). Consider reusing this chain when appropriate."
            )
            messages.insert(-1, {"role": "system", "content": recall_note})
            yield AgentEvent(
                type=EventType.THINKING,
                data={
                    "phase": "memory_recall",
                    "content": (
                        f"Recalled cached plan pattern (quality {cached_pattern.quality}, "
                        f"hits {cached_pattern.hits}): {' -> '.join(cached_pattern.tool_names)}"
                    ),
                    "cached_tools": cached_pattern.tool_names,
                    "cached_quality": cached_pattern.quality,
                    "cached_hits": cached_pattern.hits,
                },
            )

        # Episodic anti-pattern warning: when a similar past request
        # underperformed, advise the LLM against reusing that chain. Purely
        # advisory — surfaces the prior failure as context, never blocks.
        try:
            caution = episodic_store.get().anti_pattern_warning(user_message)
        except Exception:
            caution = None
        if caution:
            messages.insert(-1, {"role": "system", "content": caution})
            yield AgentEvent(
                type=EventType.THINKING,
                data={
                    "phase": "memory_caution",
                    "content": caution,
                },
            )

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

            # Emit the dependency-graph view so the frontend node-graph panel
            # can render the plan as a DAG (nodes + edges + parallel waves).
            # Derived from the planner's explicit edge map; safe to emit even
            # when the graph is linear (single chain of edges).
            yield AgentEvent(
                type=EventType.PLAN_GRAPH,
                data={
                    "iteration": iteration,
                    "goal": plan.goal,
                    "graph": plan.to_graph_payload(),
                },
            )

            # Pre-execution critique gate: a cheap, deterministic self-review
            # of the plan before any tool fires. Flags provably-dead steps
            # (e.g. transform after delete of the same target), undeclared
            # target misses, and redundant repeat mutations. Findings are
            # surfaced as a thinking event; provably-dead steps are pruned
            # from the valid set so the executor never wastes a call on them.
            critique = self._critique_plan(plan, scene)
            yield AgentEvent(
                type=EventType.THINKING,
                data={
                    "phase": "critique",
                    "content": critique.summary,
                    "findings": critique.findings,
                    "pruned_step_ids": critique.pruned_step_ids,
                    "iteration": iteration,
                },
            )
            # Drop provably-dead steps from validation so they never execute.
            # ``critique.pruned_step_ids`` is applied in the pre-validation
            # loop below (pruned steps are routed to invalid_steps).
            pruned_ids = set(critique.pruned_step_ids)

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
            # clean error to correct in the next reflection round. Steps
            # pruned by the critique gate are routed here as invalid too.
            valid_steps: List = []
            invalid_steps: List[tuple] = []  # (step, error_list)
            for step in plan.steps:
                if step.tool_call_id in pruned_ids:
                    invalid_steps.append((step, ["pruned by pre-execution critique gate"]))
                    continue
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
            # executor's parallel batching still applies. Stream per-step
            # PLAN_UPDATE events as execution unfolds so the frontend can
            # render true real-time progress (started/completed/failed)
            # rather than only the final tool_result events.
            valid_plan = TaskPlan(steps=valid_steps, reasoning=plan.reasoning)
            async for _ev in self._stream_execute_plan(scene, valid_plan, session_id):
                yield _ev
            executed_results = self._last_streamed_results

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

            # Multimodal perception loop: when the plan contained a
            # 3D-generating tool (generate_3d_asset / image_to_3d), run a
            # cheap deterministic viewport check on the resulting scene.
            # Findings are surfaced as a perception thinking event so the
            # user can see what the agent "saw" without a separate vision-
            # model call; the LLM also receives the findings as a system
            # hint to inform the next reflection round.
            if any(s.tool_name in _MULTIMODAL_3D_TOOLS for s in plan.steps):
                try:
                    perception = self._run_perception_check(scene, plan)
                except Exception:
                    logger.exception("Perception check failed")
                    perception = {
                        "summary": "Perception check errored.",
                        "findings": [],
                        "metrics": {},
                    }
                yield AgentEvent(
                    type=EventType.THINKING,
                    data={
                        "phase": "perception",
                        "content": perception["summary"],
                        "findings": perception["findings"],
                        "metrics": perception["metrics"],
                        "iteration": iteration,
                    },
                )
                # Feed the perception findings back to the LLM as a system
                # hint so the next reflection round can act on them (e.g.
                # add a light when ``no_lights`` is flagged, or reposition
                # objects when ``object_overlap`` is detected). Only appended
                # when findings exist to avoid bloating the prompt.
                if perception["findings"]:
                    hints = [f"- {f['kind']}: {f['message']}" for f in perception["findings"]]
                    messages.append({
                        "role": "system",
                        "content": (
                            "Perception check on the generated scene found: \n"
                            + "\n".join(hints)
                            + "\nConsider correcting these in the next step."
                        ),
                    })

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
            # can adjust arguments and retry. Capped to avoid loops. For
            # each failed tool, also propose a same-category alternative via
            # _find_alternative_tool so the model can switch tools instead of
            # only re-arguing the same one — this recovers from cases where
            # the chosen tool was fundamentally wrong (e.g. capture_viewport
            # failing because no canvas is mounted, switching to snapshot_view).
            if failed_steps and reflection_count < max_reflections and iteration < self.config.max_iterations - 1:
                reflection_count += 1
                lines = [
                    f"One or more tool calls failed (reflection {reflection_count}/{max_reflections}).",
                    "Review the failures below, identify the root cause (wrong id, bad argument, missing prerequisite), and retry with corrected parameters.",
                    "",
                ]
                alternative_proposals: List[Dict[str, str]] = []
                for s, r in failed_steps:
                    lines.append(
                        f"- tool={s.tool_name} arguments={json.dumps(s.arguments, ensure_ascii=False)} error={r.message}"
                    )
                    alt = self._find_alternative_tool(s.tool_name, scene, s.arguments)
                    if alt:
                        alternative_proposals.append({"failed": s.tool_name, "alternative": alt})
                        lines.append(
                            f"  -> suggested alternative: '{alt}' (same category; "
                            "consider switching if the original tool is unsuitable)"
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
                        "alternative_proposals": alternative_proposals,
                        "iteration": iteration,
                    },
                )
                # Emit a PLAN_REFINE event so the frontend can surface the
                # proposed alternative tools as a refined plan hint. This is
                # advisory only — the LLM still decides whether to take the
                # suggestion in the next iteration.
                if alternative_proposals:
                    yield AgentEvent(
                        type=EventType.PLAN_REFINE,
                        data={
                            "reason": "tool_failure_alternative_suggestion",
                            "iteration": iteration,
                            "proposals": alternative_proposals,
                        },
                    )

                # Budget-aware schema pruning: if the per-turn token budget is
                # running low, narrow the visible toolset for the next
                # iteration so the model still has room to reply. This keeps
                # long multi-iteration turns from stalling on prompt size.
                try:
                    pruned_schemas, pruned_cats, did_prune = self._budget_aware_prune(
                        tool_schemas, active_categories, budget, matched_signals
                    )
                    if did_prune:
                        tool_schemas = pruned_schemas
                        active_categories = pruned_cats
                        tool_schema_map = {s["name"]: s for s in tool_schemas}
                        yield AgentEvent(
                            type=EventType.PLAN_REFINE,
                            data={
                                "reason": "budget_prune",
                                "iteration": iteration,
                                "active_categories": active_categories,
                                "tool_subset_size": len(tool_schemas),
                                "budget_remaining": budget.remaining,
                            },
                        )
                except Exception:
                    logger.exception("Budget-aware prune failed; keeping full toolset")

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

        # End-of-turn reflection: a short narrative summary of what the
        # Agent accomplished, what failed, and what it would do next.
        # Surfaced as a 'reflection' thinking phase so the frontend can
        # render it distinctly from the raw assessment score. Purely
        # advisory — never blocks the turn.
        try:
            reflection_text = self._build_turn_reflection(
                user_message=user_message,
                plan=last_plan,
                results=all_results,
                scene=scene,
                quality=quality,
                iteration=iteration,
                elapsed=elapsed,
            )
            yield AgentEvent(
                type=EventType.THINKING,
                data={
                    "phase": "reflection",
                    "content": reflection_text,
                    "quality": quality,
                    "elapsed": elapsed,
                    "iterations": iteration + 1,
                },
            )
        except Exception:
            logger.exception("Reflection trace emission failed")

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
                "suggestions": await self._scene_suggestions(scene),
                "project_goal": memory.project_goal,
            },
        )

        # Record this turn into cross-session episodic memory so future
        # sessions can reuse the plan pattern and personalize responses.
        # Best-effort: never let a persistence failure break the turn.
        try:
            plan_steps = list(last_plan.steps) if last_plan else []
            episodic_store.get().record_turn(
                user_message=user_message,
                plan_steps=plan_steps,
                results=all_results,
                quality=int(quality.get("score", 0)) if isinstance(quality, dict) else 0,
            )
            episodic_store.save()
        except Exception:
            logger.exception("Episodic memory record/save failed")

        # Learning signal: when the turn underperformed (quality ≤ 40),
        # emit a distinct thinking phase so the frontend can surface what
        # the Agent learned from the failure. The anti-pattern is already
        # cached by ``record_turn`` above; this event makes the learning
        # visible to the user without requiring an LLM call. Skipped on
        # unknown-quality turns (e.g. assessment raised an exception).
        try:
            score = int(quality.get("score", -1)) if isinstance(quality, dict) else -1
            if 0 <= score <= 40 and last_plan is not None:
                failed_tools = sorted({
                    getattr(s, "tool_name", "")
                    for s, r in zip(last_plan.steps, all_results)
                    if getattr(s, "tool_name", "") and not getattr(r, "success", True)
                })
                learning_note = (
                    f"Recorded a low-quality turn (score {score}) as an anti-pattern "
                    f"so similar future requests can avoid this path."
                )
                if failed_tools:
                    learning_note += f" Friction concentrated on: {', '.join(failed_tools)}."
                yield AgentEvent(
                    type=EventType.THINKING,
                    data={
                        "phase": "learning",
                        "content": learning_note,
                        "quality": quality,
                        "failed_tools": failed_tools,
                    },
                )
        except Exception:
            logger.exception("Learning event emission failed")

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

    def _find_alternative_tool(
        self,
        failed_tool: str,
        scene: Scene,
        failed_args: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """Suggest a same-category substitute when a tool call fails.

        Scans the registry for another tool in the same category whose
        parameter shape is compatible with the failed call. Returns the
        alternative tool name, or None when no plausible substitute exists.

        Selection order:
          1. Hand-curated fallback pair (encodes domain knowledge about
             natural substitutes — e.g. apply_material_preset substitutes
             for apply_material since both mutate material on a target).
          2. Argument-shape overlap scoring across same-category siblings.
             Each sibling is scored by how many of the failed call's
             argument keys appear in its schema properties, plus a bonus
             when its required keys are a subset of the failed call's
             arguments. The highest-scoring sibling wins; ties broken
             alphabetically for determinism. Falls back to first sibling
             when no failed_args are available.

        Used by the reflection path: instead of asking the LLM to retry the
        exact same tool with tweaked arguments, the orchestrator emits a
        PLAN_REFINE event proposing the alternative so the next iteration
        can try a different path to the same goal.
        """
        category = _TOOL_CATEGORIES.get(failed_tool)
        if not category:
            return None
        # Hand-curated fallback pairs for tools that have a natural
        # substitute. Keys are the failed tool; values are the preferred
        # alternative. Chosen so the substitute accepts a compatible
        # argument shape (e.g. apply_material_preset takes target+preset
        # while apply_material takes target+color, both mutate material).
        fallback_pairs: Dict[str, str] = {
            "apply_material": "apply_material_preset",
            "apply_material_preset": "apply_material",
            "apply_material_batch": "apply_material",
            "gradient_material": "apply_material",
            "material_blend": "apply_material_preset",
            "transform_object": "snap_to_grid",
            "snap_to_grid": "transform_object",
            "align_objects": "distribute_objects",
            "distribute_objects": "align_objects",
            "array_pattern": "duplicate_object",
            "mirror_object": "duplicate_object",
            "boolean_operation": "group_objects",
            "set_view": "frame_view",
            "frame_view": "set_view",
            "capture_viewport": "snapshot_view",
            "snapshot_view": "capture_viewport",
            "scene_info": "list_objects",
            "list_objects": "scene_info",
            "export_scene": "export_code",
            "export_code": "export_scene",
        }
        preferred = fallback_pairs.get(failed_tool)
        if preferred and self.registry.get(preferred) is not None:
            return preferred

        # Collect same-category siblings.
        siblings = [
            t for t in self.registry.all()
            if t.name != failed_tool and _TOOL_CATEGORIES.get(t.name) == category
        ]
        if not siblings:
            return None

        # Without the failed call's arguments, fall back to the first sibling.
        if not failed_args or not isinstance(failed_args, dict):
            return siblings[0].name

        # Score each sibling by argument-shape overlap with the failed call.
        failed_keys = set(failed_args.keys())
        best_name: Optional[str] = None
        best_score = -1
        for sib in siblings:
            try:
                sib_schema = sib.schema() or {}
            except Exception:
                continue
            sib_props = (sib_schema.get("properties", {}) or {})
            sib_required = set(sib_schema.get("required", []) or [])
            sib_keys = set(sib_props.keys())
            # Overlap: how many of the failed call's args this sibling accepts.
            overlap = len(failed_keys & sib_keys)
            # Bonus: sibling's required keys are all present in the failed call
            # (the alternative can be invoked with the same argument shape).
            required_satisfied = 1 if sib_required and sib_required <= failed_keys else 0
            # Penalty: sibling has many more required keys the failed call lacks
            # (would need new arguments the model hasn't provided).
            missing_required = len(sib_required - failed_keys)
            score = overlap * 2 + required_satisfied - missing_required
            # Tie-break: prefer shorter name (often the more general tool),
            # then alphabetical for determinism.
            if score > best_score or (score == best_score and best_name is not None and sib.name < best_name):
                best_score = score
                best_name = sib.name
        # Only return a sibling with a positive score (at least some overlap).
        if best_name is not None and best_score > 0:
            return best_name
        # Fallback: first sibling when scoring didn't find a clear winner.
        return siblings[0].name if siblings else None

    def _budget_aware_prune(
        self,
        schemas: List[Dict[str, Any]],
        active_categories: List[str],
        budget: "TokenBudget",
        matched_signals: List[str],
    ) -> tuple:
        """Prune the tool schema set when the token budget is running low.

        Returns a ``(schemas, categories, pruned)`` triple. When the budget
        has more than 25% remaining, returns the input unchanged. Below
        that threshold, keeps only the always-on categories plus the single
        top-ranked matched category so the LLM still has a workable toolset
        but the prompt stays small enough to finish the turn.

        This prevents the degenerate case where a long turn with many
        iterations burns the budget on tool schemas alone, leaving no room
        for the model's reply.
        """
        if budget.limit <= 0 or budget.remaining > budget.limit * 0.25:
            return schemas, active_categories, False
        # Keep always-on + the first matched category (most relevant signal).
        keep = set(self._ALWAYS_ON_CATEGORIES)
        if matched_signals:
            keep.add(matched_signals[0])
        names = [t.name for t in self.registry.all() if t.category in keep]
        pruned = self.registry.schemas_for(names)
        return pruned, sorted(keep), True

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

    # ------------------------------------------------------------------
    # Self-correction — rule-based arg fixup after a tool failure
    # ------------------------------------------------------------------

    # Argument keys whose value is treated as a scene-object reference.
    # When a tool reports a target-naming miss, _maybe_self_correct scans
    # these keys and fuzzy-resolves each against the live scene names.
    _TARGET_ARG_KEYS = ("target", "target_a", "target_b", "object", "name")

    def _maybe_self_correct(
        self,
        failed_step,
        failure_msg: str,
        scene: Scene,
        plan: Optional["TaskPlan"] = None,
    ) -> Optional[Dict[str, Any]]:
        """Try to produce corrected arguments for a failed step.

        Rule-based corrector (no LLM call) — used by the offline engine
        and as a fast first attempt in the online path. Returns the
        corrected arguments dict (a full new arguments dict, not a delta)
        or None when no rule could derive a correction.

        Rules (tried in order; first hit wins):
          1. **Target miss**: when the failure message matches a
             ``_TARGET_MISS_PHRASES`` entry, fuzzy-resolve each
             target-like argument against the live scene names.
          2. **Type coercion**: when the failure mentions a type
             mismatch ("must be a number", "must be an integer",
             "must be a 3-element array", etc.), coerce each string
             argument to the schema-declared type.
          3. **Enum closest-match**: when the failure mentions an
             invalid/unknown enum value, replace each enum-typed
             argument with the closest schema enum entry by edit distance.
          4. **Numeric clamp**: when the failure mentions an out-of-range
             numeric value, clamp each numeric argument to the schema
             minimum/maximum bounds.
          5. **Geometry-type fallback**: when the failure mentions an
             unsupported geometry type, replace ``geometry_type`` with
             the closest entry in GEOMETRY_DEFAULTS by edit distance.
          6. **Invalid argument**: when the failure mentions "invalid
             argument" / "missing required", drop the offending optional
             argument so the tool falls back to its default. Conservative
             — only drops keys not in the tool's required list.

        Caps: caller is responsible for the per-turn cap
        (``self._self_corrections_this_turn < 2``) and the per-step cap
        (call at most once per failed step).
        """
        if failed_step is None:
            return None
        args = getattr(failed_step, "arguments", None)
        if not isinstance(args, dict):
            return None
        msg_lower = (failure_msg or "").lower()

        # Rule 1: target miss → fuzzy resolve.
        looks_like_target_miss = any(
            phrase in msg_lower or phrase in (failure_msg or "")
            for phrase in _TARGET_MISS_PHRASES
        )
        if looks_like_target_miss:
            candidate_names: List[str] = []
            for obj in scene.objects:
                candidate_names.extend([obj.name, obj.id])
            for light in scene.lights:
                candidate_names.extend([light.name, light.id])
            for cam in scene.cameras:
                candidate_names.extend([cam.name, cam.id])
            for grp in scene.groups:
                candidate_names.extend([grp.name, grp.id])

            corrected: Dict[str, Any] = {}
            for key in self._TARGET_ARG_KEYS:
                if key not in args:
                    continue
                requested_val = args[key]
                if not isinstance(requested_val, str):
                    continue
                resolved = _fuzzy_resolve_target(requested_val, candidate_names)
                if resolved is not None and resolved != requested_val:
                    corrected[key] = resolved
            if corrected:
                new_args = dict(args)
                new_args.update(corrected)
                return new_args

        tool_name = getattr(failed_step, "tool_name", "")
        tool = self.registry.get(tool_name) if tool_name else None
        schema = tool.schema() if tool is not None else None
        props = (schema or {}).get("properties", {}) or {}

        # Rule 2: type coercion (string → number/integer/array).
        type_mismatch_phrases = (
            "must be a number", "must be an integer", "must be a boolean",
            "must be a 3-element array", "must be a non-empty array",
            "must be a 3-vector", "must be an array", "must be a list",
            "must be an object", "must be a non-empty object",
        )
        if any(p in msg_lower for p in type_mismatch_phrases):
            new_args = dict(args)
            changed = False
            for key, val in list(args.items()):
                if key not in props:
                    continue
                decl = props.get(key) or {}
                t = decl.get("type")
                coerced = self._coerce_arg_value(val, t)
                if coerced is not None and coerced != val:
                    new_args[key] = coerced
                    changed = True
            if changed:
                return new_args

        # Rule 3: enum closest-match.
        enum_mismatch_phrases = (
            "must be one of", "expected one of", "invalid axis", "invalid mode",
            "invalid preset", "invalid value", "invalid kind", "invalid type",
            "unknown preset", "unknown mode", "unknown kind", "unknown type",
            "unsupported geometry", "axis must be", "mode must be",
            "expected play/pause/stop",
        )
        if any(p in msg_lower for p in enum_mismatch_phrases):
            new_args = dict(args)
            changed = False
            for key, val in list(args.items()):
                if key not in props:
                    continue
                decl = props.get(key) or {}
                enum_vals = decl.get("enum")
                if not isinstance(enum_vals, list) or not enum_vals:
                    continue
                if not isinstance(val, str):
                    continue
                if val in enum_vals:
                    continue
                # Closest enum entry by Levenshtein distance (case-insensitive).
                best = min(
                    enum_vals,
                    key=lambda e: (_levenshtein(val, str(e)), len(str(e))),
                )
                if _levenshtein(val, str(best)) <= max(2, len(val) // 2):
                    new_args[key] = best
                    changed = True
            if changed:
                return new_args

        # Rule 4: numeric clamp to schema min/max.
        numeric_range_phrases = (
            "out of range", "must be positive", "must be non-negative",
            "must be ≥", "must be >=", "must be >", "must be <",
            "exceeds", "too large", "too small", "must be between",
            "must be at least", "must be at most", "grid size must be positive",
            "radius must be", "scale must be",
        )
        if any(p in msg_lower for p in numeric_range_phrases):
            new_args = dict(args)
            changed = False
            for key, val in list(args.items()):
                if key not in props:
                    continue
                decl = props.get(key) or {}
                if decl.get("type") not in ("number", "integer"):
                    continue
                if isinstance(val, bool):
                    continue
                if not isinstance(val, (int, float)):
                    continue
                lo = decl.get("minimum")
                hi = decl.get("maximum")
                clamped = val
                if isinstance(lo, (int, float)) and clamped < lo:
                    clamped = lo
                if isinstance(hi, (int, float)) and clamped > hi:
                    clamped = hi
                if clamped != val:
                    new_args[key] = clamped
                    changed = True
            if changed:
                return new_args

        # Rule 5: geometry-type fallback.
        if "unsupported geometry" in msg_lower or "geometry type" in msg_lower:
            try:
                from trigen.scene import GEOMETRY_DEFAULTS
                geo_keys = list(GEOMETRY_DEFAULTS.keys())
            except Exception:
                geo_keys = []
            cur = args.get("geometry_type")
            if isinstance(cur, str) and cur not in geo_keys and geo_keys:
                best = min(
                    geo_keys,
                    key=lambda g: (_levenshtein(cur, g), len(g)),
                )
                if _levenshtein(cur, best) <= max(2, len(cur) // 2):
                    new_args = dict(args)
                    new_args["geometry_type"] = best
                    return new_args

        # Rule 6: invalid argument → drop optional offender.
        if "invalid argument" in msg_lower or "missing required" in msg_lower:
            if tool is not None:
                required = set((schema or {}).get("required", []) or [])
                # Drop the first optional arg that is not in the required
                # list — conservative single-drop, not a sweep.
                for key in list(args.keys()):
                    if key not in required:
                        new_args = dict(args)
                        new_args.pop(key, None)
                        return new_args

        return None

    @staticmethod
    def _coerce_arg_value(value: Any, type_name: Optional[str]) -> Any:
        """Coerce a value to the JSON schema type name.

        Returns the coerced value, or None when coercion is not applicable
        or fails. Only fires when the source value is a string (the common
        case when the LLM emits numbers as strings); other types are passed
        through so the caller can detect "no change".
        """
        if not isinstance(value, str) or not type_name:
            return None
        if type_name == "number":
            try:
                return float(value)
            except (TypeError, ValueError):
                return None
        if type_name == "integer":
            try:
                return int(float(value))
            except (TypeError, ValueError):
                return None
        if type_name == "boolean":
            v = value.strip().lower()
            if v in ("true", "1", "yes", "on"):
                return True
            if v in ("false", "0", "no", "off"):
                return False
            return None
        if type_name in ("array", "object"):
            try:
                import json as _json
                return _json.loads(value)
            except (TypeError, ValueError):
                return None
        return None

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
                "suggestions": await self._scene_suggestions(scene),
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
        # Reset the per-turn self-correction counter. The cap is 2 per turn.
        self._self_corrections_this_turn = 0
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

        # Episodic memory reuse: if a previous successful plan pattern
        # exists for this (normalized) intent signature, surface it as a
        # thinking hint. Offline mode skips LLM re-planning entirely, so
        # the hint helps the user understand why a familiar tool sequence
        # is being applied.
        try:
            cached = episodic_store.get().lookup_pattern(user_message)
        except Exception:
            logger.exception("Episodic memory lookup failed")
            cached = None
        if cached is not None:
            yield AgentEvent(
                type=EventType.THINKING,
                data={
                    "phase": "memory_recall",
                    "content": (
                        f"Reusing cached plan pattern (quality {cached.quality}, "
                        f"hits {cached.hits}): {' -> '.join(cached.tool_names)}"
                    ),
                    "cached_tools": cached.tool_names,
                    "cached_quality": cached.quality,
                    "cached_hits": cached.hits,
                },
            )

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
        # Accumulate offline results + plan steps for episodic recording.
        offline_results: List[Any] = []
        offline_steps: List[Any] = []

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

            # Phase 4a: Offline self-correction — when a tool fails, try a
            # rule-based corrector (fuzzy target resolution, default-arg
            # fallback) to produce corrected arguments, emit a
            # ``phase="self_correction"`` thinking event, then retry the
            # step once. Capped at 1 self-correction per failed step and
            # 2 self-corrections per turn so a genuinely broken tool
            # cannot loop the offline engine indefinitely.
            if not result.success and self._self_corrections_this_turn < 2:
                corrected_args = self._maybe_self_correct(
                    intent, result.message, scene, None
                )
                if corrected_args is not None:
                    self._self_corrections_this_turn += 1
                    # Build a human-readable diff of the corrected args for
                    # the self_correction event payload.
                    corrections_log: List[Dict[str, Any]] = []
                    for key, new_val in corrected_args.items():
                        old_val = intent.arguments.get(key)
                        if old_val != new_val:
                            corrections_log.append({
                                "arg": key,
                                "from": old_val,
                                "to": new_val,
                            })
                        elif key not in intent.arguments:
                            corrections_log.append({
                                "arg": key,
                                "from": None,
                                "to": new_val,
                                "kind": "added",
                            })
                    # Dropped keys (present in original, absent in corrected).
                    for key in intent.arguments:
                        if key not in corrected_args:
                            corrections_log.append({
                                "arg": key,
                                "from": intent.arguments[key],
                                "to": None,
                                "kind": "dropped",
                            })

                    # Emit the self-correction thinking event so the
                    # frontend can surface what the agent changed and why.
                    yield AgentEvent(
                        type=EventType.THINKING,
                        data={
                            "phase": "self_correction",
                            "content": (
                                f"Self-correction: retrying {intent.tool_name} with "
                                f"{len(corrections_log)} argument change(s) after failure."
                            ),
                            "failed_step": {
                                "id": step_id,
                                "tool": intent.tool_name,
                                "arguments": intent.arguments,
                            },
                            "failure": result.message,
                            "corrected_step": {
                                "id": step_id,
                                "tool": intent.tool_name,
                                "arguments": corrected_args,
                            },
                            "corrections": corrections_log,
                            "iteration": idx,
                        },
                    )

                    # Also emit PLAN_REFINE so existing frontend surfaces
                    # that consume plan_refine events still light up.
                    yield AgentEvent(
                        type=EventType.PLAN_REFINE,
                        data={
                            "reason": "offline_fuzzy_target_recovery",
                            "step_id": step_id,
                            "tool": intent.tool_name,
                            "corrections": corrections_log,
                            "original_message": result.message,
                        },
                    )

                    try:
                        retry_result = await tool.execute(scene, corrected_args)
                    except Exception as e:
                        logger.exception(
                            "Offline tool %s retry execution error",
                            intent.tool_name,
                        )
                        from trigen.tools.base import ToolResult as _TR
                        retry_result = _TR(
                            success=False,
                            message=f"Retry execution error: {e}",
                        )
                    # Emit a TOOL_CALL for the retry so the frontend
                    # sees the corrected invocation.
                    yield AgentEvent(
                        type=EventType.TOOL_CALL,
                        data={
                            "id": f"{step_id}_retry",
                            "name": intent.tool_name,
                            "arguments": corrected_args,
                            "corrections": corrections_log,
                        },
                    )
                    # Adopt the retry result if it succeeded; otherwise
                    # keep the original failure (so the user sees the
                    # original error message rather than a confusing
                    # secondary failure).
                    if retry_result.success:
                        result = retry_result
                        result.message = (
                            f"[auto-recovered] {result.message} "
                            f"(resolved: {', '.join(c['arg'] + ': ' + str(c['from']) + ' -> ' + str(c['to']) for c in corrections_log if c.get('kind') in (None, 'added'))})"
                        )

            # Track for episodic memory recording at end of turn.
            try:
                from trigen.planner import TaskStep as _OfflineStep
                offline_steps.append(_OfflineStep(
                    tool_name=intent.tool_name,
                    arguments=intent.arguments,
                    tool_call_id=step_id,
                    description=intent.description or f"Call {intent.tool_name}",
                ))
                offline_results.append(result)
            except Exception:
                pass

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
                "suggestions": await self._scene_suggestions(scene),
                "project_goal": memory.project_goal,
            },
        )

        # Persist conversation memory after each offline turn
        self.save_memory(session_id)

        # Record the offline turn into cross-session episodic memory. The
        # offline engine has no LLM, so reusing a cached successful tool
        # sequence is especially valuable for repeat requests.
        try:
            quality_score = 0
            if offline_results:
                qa = self._assess_turn_quality(scene, offline_results, type("_P", (), {"_verification_corrections": 0})())
                quality_score = int(qa.get("score", 0))
            episodic_store.get().record_turn(
                user_message=user_message,
                plan_steps=offline_steps,
                results=offline_results,
                quality=quality_score,
            )
            episodic_store.save()
        except Exception:
            logger.exception("Episodic memory record/save failed (offline)")
