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
from trigen.tools.editor_tools import FocusObjectTool, SelectObjectTool
from trigen.tools.exporter import ExportSceneTool
from trigen.tools.camera_tools import AddCameraTool, ModifyCameraTool, SetViewTool
from trigen.tools.scene_info_tool import SceneInfoTool
from trigen.tools.grid_toggle_tool import SetGridSizeTool, ToggleGridTool
from trigen.tools.smart_compose import SmartComposeTool
from trigen.tools.multimodal_tools import (
    Generate3DAssetTool,
    GenerateAnimationTool,
    GenerateImageTool,
    GenerateVideoTool,
    SynthesizeSpeechTool,
    TranscribeAudioTool,
)

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
    # Export
    "ExportSceneTool",
    # Multimodal generation
    "GenerateImageTool",
    "Generate3DAssetTool",
    "GenerateVideoTool",
    "GenerateAnimationTool",
    "SynthesizeSpeechTool",
    "TranscribeAudioTool",
]
