"""Trigen Agent tools module / Trigen Agent 工具模块.

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

__all__ = [
    "ToolBase",
    "ToolRegistry",
    "ToolResult",
    "SceneDelta",
    # Geometry / 几何
    "CreateObjectTool",
    "TransformObjectTool",
    "ModifyGeometryTool",
    "DuplicateObjectTool",
    "DeleteObjectTool",
    "ListObjectsTool",
    # Material / 材质
    "ApplyMaterialTool",
    "ApplyMaterialPresetTool",
    # Lighting / 灯光
    "AddLightTool",
    "ModifyLightTool",
    "DeleteLightTool",
    # Scene organization / 场景组织
    "GroupObjectsTool",
    "UngroupObjectsTool",
    "SetBackgroundTool",
    "SetFogTool",
    "ArrangeLayoutTool",
    # Editor control / 编辑器控制
    "SelectObjectTool",
    "FocusObjectTool",
    # Export / 导出
    "ExportSceneTool",
]
