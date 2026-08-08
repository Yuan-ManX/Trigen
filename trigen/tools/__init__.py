"""Trigen Agent tools module.

Exposes every editor capability as an Agent-callable tool, covering
geometry creation/editing, material orchestration, lighting, scene
organization, editor control, and export.
"""

from trigen.tools.base import ToolBase, ToolRegistry, ToolResult, SceneDelta
from trigen.tools.mesh_generator import CreateObjectTool
from trigen.tools.mesh_editor import (
    DeleteObjectTool,
    DuplicateObjectTool,
    ListObjectsTool,
    ModifyGeometryTool,
    TransformObjectTool,
)
from trigen.tools.material_tool import ApplyMaterialPresetTool, ApplyMaterialTool
from trigen.tools.light_tool import AddLightTool, DeleteLightTool, ModifyLightTool
from trigen.tools.scene_tools import (
    ArrangeLayoutTool,
    GroupObjectsTool,
    SetBackgroundTool,
    SetFogTool,
    UngroupObjectsTool,
)
from trigen.tools.editor_tools import (
    FocusObjectTool,
    FrameViewTool,
    LockObjectTool,
    RenameObjectTool,
    SelectObjectTool,
    SetTransformModeTool,
    SetVisibilityTool,
)
from trigen.tools.editor_control_tools import (
    CaptureViewportTool,
    ClearMeasurementTool,
    ControlRadialMenuTool,
    FocusPanelTool,
    PauseAnimationTool,
    PlayAnimationTool,
    RedoSceneTool,
    SeekAnimationTool,
    SetPlaybackSpeedTool,
    SetRenderQualityTool,
    SetSelectionTool,
    SetViewportCameraTool,
    StopCameraFlythroughTool,
    ToggleGridSnappingTool,
    UndoSceneTool,
)
from trigen.tools.exporter import ExportSceneTool
from trigen.tools.camera_tools import AddCameraTool, ModifyCameraTool, SetViewTool
from trigen.tools.scene_info_tool import SceneInfoTool
from trigen.tools.grid_toggle_tool import SetGridSizeTool, ToggleGridTool
from trigen.tools.smart_compose import SmartComposeTool
from trigen.tools.multimodal_tools import (
    Generate3DAssetTool,
    GenerateAnimationTool,
    GenerateImageTool,
    GenerateMusicTool,
    GenerateVideoTool,
    SynthesizeSpeechTool,
    TranscribeAudioTool,
)
from trigen.tools.spatial_tools import (
    AlignObjectsTool,
    AnimateCameraTool,
    DistributeObjectsTool,
    MeasureDistanceTool,
    SetEnvironmentTool,
    SnapshotViewTool,
)
from trigen.tools.subagent_tool import DispatchSubagentTool
from trigen.tools.composite_tools import (
    ArrayPatternTool,
    BooleanOperationTool,
    MirrorObjectTool,
    SnapToGridTool,
)
from trigen.tools.procedural_tools import (
    LSystemTool,
    SpiralStaircaseTool,
    TerrainGeneratorTool,
    VoronoiShatterTool,
)
from trigen.tools.animation_tools import (
    BounceAnimationTool,
    KeyframeAnimationTool,
    OrbitAnimationTool,
    WaveAnimationTool,
)
from trigen.tools.material_tools import (
    GradientMaterialTool,
    MaterialBlendTool,
    RandomizePaletteTool,
)
from trigen.tools.skill_tool import InvokeSkillTool
from trigen.tools.macro_tools import (
    DefineMacroTool,
    DeleteMacroTool,
    InvokeMacroTool,
    ListMacrosTool,
)
from trigen.tools.workflow_tools import (
    DeleteWorkflowTool,
    InvokeWorkflowTool,
    ListWorkflowsTool,
    SaveWorkflowTool,
)
from trigen.tools.variant_tools import (
    ListVariantsTool,
    LoadVariantTool,
    RandomizeVariantTool,
    SaveVariantTool,
)
from trigen.tools.scene_management_tools import (
    AssignToGroupTool,
    DeleteCameraTool,
    ReorderLayerTool,
    RenameGroupTool,
    SelectAllTool,
)
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
from trigen.tools.rigging_tools import (
    ApplyScenePresetTool,
    CreateLightingRigTool,
    SetAmbientLevelTool,
    SetExposureTool,
)
from trigen.tools.keyframe_tools import (
    CreateAnimationClipTool,
    FitCameraToSelectionTool,
    SetKeyframeTool,
)
from trigen.tools.layer_tools import (
    CreateLayerTool,
    DeleteLayerTool,
    PaintVertexColorsTool,
    SetLayerColorTool,
)
from trigen.tools.node_graph_tools import (
    ConfigureNodeGraphTool,
    DeleteNodeGraphTool,
    ExecuteNodeGraphTool,
    ListNodeGraphsTool,
)
from trigen.tools.physics_tools import (
    ApplyPhysicsTool,
    ClearPhysicsTool,
    ListPhysicsTool,
)
from trigen.tools.text_tools import CreateTextTool

__all__ = [
    "ToolBase",
    "ToolRegistry",
    "ToolResult",
    "SceneDelta",
    # Geometry
    "CreateObjectTool",
    "TransformObjectTool",
    "ModifyGeometryTool",
    "DuplicateObjectTool",
    "DeleteObjectTool",
    "ListObjectsTool",
    # Material
    "ApplyMaterialTool",
    "ApplyMaterialPresetTool",
    "GradientMaterialTool",
    "MaterialBlendTool",
    "RandomizePaletteTool",
    # Lighting
    "AddLightTool",
    "ModifyLightTool",
    "DeleteLightTool",
    # Camera
    "AddCameraTool",
    "ModifyCameraTool",
    "SetViewTool",
    # Scene organization
    "GroupObjectsTool",
    "UngroupObjectsTool",
    "SetBackgroundTool",
    "SetFogTool",
    "ArrangeLayoutTool",
    "AssignToGroupTool",
    "RenameGroupTool",
    "ReorderLayerTool",
    "SelectAllTool",
    "DeleteCameraTool",
    # Spatial manipulation & measurement
    "AlignObjectsTool",
    "DistributeObjectsTool",
    "AnimateCameraTool",
    "SetEnvironmentTool",
    "SnapshotViewTool",
    "MeasureDistanceTool",
    # Composite modelling
    "ArrayPatternTool",
    "MirrorObjectTool",
    "BooleanOperationTool",
    "SnapToGridTool",
    # Procedural generation
    "TerrainGeneratorTool",
    "LSystemTool",
    "SpiralStaircaseTool",
    "VoronoiShatterTool",
    # Object animation
    "KeyframeAnimationTool",
    "OrbitAnimationTool",
    "WaveAnimationTool",
    "BounceAnimationTool",
    # Scene inspection
    "SceneInfoTool",
    # Grid control
    "ToggleGridTool",
    "SetGridSizeTool",
    # Smart composition
    "SmartComposeTool",
    # Editor control
    "SelectObjectTool",
    "FocusObjectTool",
    "LockObjectTool",
    "SetVisibilityTool",
    "RenameObjectTool",
    "SetTransformModeTool",
    "FrameViewTool",
    # Viewport / playback / session editor control
    "SetViewportCameraTool",
    "PlayAnimationTool",
    "PauseAnimationTool",
    "SeekAnimationTool",
    "SetSelectionTool",
    "CaptureViewportTool",
    "SetPlaybackSpeedTool",
    "ToggleGridSnappingTool",
    "FocusPanelTool",
    "UndoSceneTool",
    "RedoSceneTool",
    "SetRenderQualityTool",
    "ControlRadialMenuTool",
    "ClearMeasurementTool",
    "StopCameraFlythroughTool",
    # Export
    "ExportSceneTool",
    # Multimodal generation
    "GenerateImageTool",
    "Generate3DAssetTool",
    "GenerateVideoTool",
    "GenerateAnimationTool",
    "GenerateMusicTool",
    "SynthesizeSpeechTool",
    "TranscribeAudioTool",
    # Sub-agent
    "DispatchSubagentTool",
    # Creative skills
    "InvokeSkillTool",
    # Macros — reusable user-defined tool-call recipes
    "DefineMacroTool",
    "InvokeMacroTool",
    "ListMacrosTool",
    "DeleteMacroTool",
    # Agentic Workflow Templates — saveable named tool-graph recipes
    "SaveWorkflowTool",
    "InvokeWorkflowTool",
    "ListWorkflowsTool",
    "DeleteWorkflowTool",
    # Scene variants — named snapshots + jittered alternatives
    "SaveVariantTool",
    "LoadVariantTool",
    "ListVariantsTool",
    "RandomizeVariantTool",
    # Advanced editor control (solo, presets, clipping, pivot, batch, layers)
    "IsolateObjectTool",
    "ResetTransformTool",
    "SetClippingPlaneTool",
    "SetObjectPivotTool",
    "ApplyMaterialBatchTool",
    "SetObjectLayerTool",
    # Viewport & editor-state tools (minimap, shadows, projection, mode, slots)
    "SetMinimapTool",
    "SetShadowsTool",
    "SetViewportProjectionTool",
    "SetEditorModeTool",
    "SaveSceneSlotTool",
    "LoadSceneSlotTool",
    # Extended editor capabilities (per-field material/geometry, hierarchy,
    # annotations, shortcut config)
    "SetMaterialPropertyTool",
    "SetGeometryParamsTool",
    "SetObjectParentTool",
    "AddAnnotationTool",
    "RemoveAnnotationTool",
    "ConfigureShortcutsTool",
    # Scene workflow intelligence (query, style, batch transform, stats,
    # annotation listing, cinematic camera flythrough)
    "QuerySceneTool",
    "StyleSceneTool",
    "BatchTransformTool",
    "SceneStatisticsTool",
    "ListAnnotationsTool",
    "CameraFlythroughTool",
    # Pipeline authoring — compose / inspect multimodal node-graphs
    "ComposePipelineTool",
    "ListPipelineTemplatesTool",
    # Agent scene intelligence — semantic description + creative suggestions
    "DescribeSceneTool",
    "SuggestNextActionsTool",
    "ReflectOnSessionTool",
    # Prescriptive design review — ranked findings with concrete fix proposals
    "SceneCritiqueTool",
    # Self-healing orchestration — review + auto-apply fixes in one call
    "AutoFixSceneTool",
    # Agent explicit memory — pin / recall / forget durable user facts
    "PinFactTool",
    "RecallFactsTool",
    "ForgetFactTool",
    # Asset library — place pre-built assets, scatter-paint clusters,
    # snap to surface (creation category)
    "AssetLibraryTool",
    "ScatterPaintTool",
    "SnapToSurfaceTool",
    # Cinematic storyboard — sequence-level camera direction
    "ComposeStoryTool",
    "AddShotTool",
    "UpdateShotTool",
    "RemoveShotTool",
    "ListStoryTool",
    "ClearStoryTool",
    "PlayStoryTool",
    # Frontend-editor coverage gap tools — template catalog, viewport orbit,
    # per-layer visibility, skill catalog
    "ListSceneTemplatesTool",
    "OrbitViewportTool",
    "SetLayerVisibilityTool",
    "ListSkillsTool",
    # Constraint-authoring — declarative spatial relationships + greedy solver
    "AddConstraintTool",
    "ListConstraintsTool",
    "ClearConstraintsTool",
    "SolveConstraintsTool",
    # Goal-driven refinement — multi-iteration critique+autofix loop
    "RefineSceneTool",
    # Generative geometry — radial symmetry + jittered clones
    "RadialSymmetryTool",
    "CloneWithJitterTool",
    # Mesh detail editing — geometry-type conversion + segment subdivision
    "ConvertGeometryTool",
    "SubdivideMeshTool",
    # Lighting rigs + scene presets + exposure
    "CreateLightingRigTool",
    "SetAmbientLevelTool",
    "SetExposureTool",
    "ApplyScenePresetTool",
    # Per-property keyframing + camera framing + named clips
    "SetKeyframeTool",
    "CreateAnimationClipTool",
    "FitCameraToSelectionTool",
    # Layer management + vertex paint
    "CreateLayerTool",
    "DeleteLayerTool",
    "SetLayerColorTool",
    "PaintVertexColorsTool",
    # Procedural node-graph authoring + execution
    "ConfigureNodeGraphTool",
    "ExecuteNodeGraphTool",
    "ListNodeGraphsTool",
    "DeleteNodeGraphTool",
    # Rigid-body physics — gravity, bouncing, friction, resting floor
    "ApplyPhysicsTool",
    "ClearPhysicsTool",
    "ListPhysicsTool",
    # Text / sprite authoring — 3D labels and captions
    "CreateTextTool",
]
