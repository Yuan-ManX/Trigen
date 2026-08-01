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
    FocusPanelTool,
    PauseAnimationTool,
    PlayAnimationTool,
    RedoSceneTool,
    SeekAnimationTool,
    SetPlaybackSpeedTool,
    SetRenderQualityTool,
    SetSelectionTool,
    SetViewportCameraTool,
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
]
