"""Natural language intent parser for offline mode.

Parses user messages into structured tool-call intents, enabling the
offline rule engine to handle transforms, materials, lights, grouping,
deletion, duplication, focus, fog, and scene-level operations without
requiring an LLM API key.
"""

from __future__ import annotations

import math
import random
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class ParsedIntent:
    """A single parsed intent representing one or more tool calls."""

    tool_name: str
    arguments: Dict[str, Any] = field(default_factory=dict)
    description: str = ""

    # Whether this intent should emit a tool_call event (some are informational only)
    emit_tool_call: bool = True


# ---------------------------------------------------------------------------
# Keyword maps
# ---------------------------------------------------------------------------

GEO_MAP: Dict[str, str] = {
    "立方体": "box", "cube": "box", "方块": "box", "盒子": "box", "box": "box",
    "球": "sphere", "sphere": "sphere", "球体": "sphere",
    "圆柱": "cylinder", "cylinder": "cylinder", "柱子": "cylinder",
    "圆锥": "cone", "cone": "cone",
    "圆环": "torus", "torus": "torus", "环": "torus",
    "平面": "plane", "plane": "plane", "地面": "plane",
    "二十面体": "icosahedron", "icosahedron": "icosahedron",
    "十二面体": "dodecahedron", "dodecahedron": "dodecahedron",
    "八面体": "octahedron", "octahedron": "octahedron",
    "四面体": "tetrahedron", "tetrahedron": "tetrahedron",
    "扭结": "torusKnot", "knot": "torusKnot",
    "胶囊": "capsule", "capsule": "capsule",
    "圆环面": "ring", "ring": "ring",
}

COLOR_MAP: Dict[str, str] = {
    "红": "#e84a4a", "red": "#e84a4a",
    "绿": "#3acc66", "green": "#3acc66",
    "蓝": "#3a7aff", "blue": "#3a7aff",
    "黄": "#ffc933", "yellow": "#ffc933",
    "紫": "#9a3aff", "purple": "#9a3aff",
    "橙": "#ff8a3a", "orange": "#ff8a3a",
    "粉": "#ff7acc", "pink": "#ff7acc",
    "白": "#ffffff", "white": "#ffffff",
    "黑": "#1a1a1a", "black": "#1a1a1a",
    "青": "#00F0FF", "cyan": "#00F0FF",
    "金": "#ffc933", "gold": "#ffc933",
    "银": "#c0c0c8", "silver": "#c0c0c8",
    "灰": "#888888", "gray": "#888888", "grey": "#888888",
}

PRESET_MAP: Dict[str, str] = {
    "金属": "metal", "metal": "metal", "metallic": "metal", "shiny": "metal",
    "玻璃": "glass", "glass": "glass", "transparent": "glass",
    "木头": "wood", "wood": "wood", "wooden": "wood",
    "塑料": "plastic", "plastic": "plastic",
    "橡胶": "rubber", "rubber": "rubber",
    "陶瓷": "ceramic", "ceramic": "ceramic", "porcelain": "ceramic",
    "大理石": "marble", "marble": "marble",
    "霓虹": "neon", "neon": "neon",
    "发光": "emissive", "emissive": "emissive", "glow": "emissive", "glowing": "emissive",
    "线框": "wireframe", "wireframe": "wireframe",
    "matte": "rubber", "dull": "rubber",
    "rough": "rubber", "磨砂": "rubber", "粗糙": "rubber",
    "smooth": "plastic", "光滑": "plastic",
    "glossy": "plastic", "光泽": "plastic",
}

LIGHT_TYPE_MAP: Dict[str, str] = {
    "ambient": "ambient", "环境光": "ambient", "ambient light": "ambient",
    "directional": "directional", "平行光": "directional", "directional light": "directional",
    "point": "point", "点光源": "point", "point light": "point",
    "spot": "spot", "聚光灯": "spot", "spotlight": "spot", "spot light": "spot",
    "hemisphere": "hemisphere", "半球光": "hemisphere", "hemisphere light": "hemisphere",
}

VIEW_MAP: Dict[str, str] = {
    "top view": "top", "top": "top", "顶视图": "top",
    "front view": "front", "front": "front", "前视图": "front",
    "back view": "back", "back": "back", "后视图": "back",
    "left view": "left", "left": "left", "左视图": "left",
    "right view": "right", "right": "right", "右视图": "right",
    "bottom view": "bottom", "bottom": "bottom", "底视图": "bottom",
    "perspective": "perspective", "iso": "perspective", "透视": "perspective",
}

COMPOSE_MAP: Dict[str, str] = {
    "solar system": "solar_system", "solar": "solar_system", "planet": "solar_system",
    "太阳系": "solar_system",
    "city": "city_block", "building": "city_block", "城市": "city_block",
    "studio": "studio", "three-point": "studio", "3-point": "studio", "工作室": "studio",
    "crystal": "crystal_cluster", "水晶": "crystal_cluster",
    "showcase": "product_showcase", "product": "product_showcase",
    "pedestal": "product_showcase", "展示台": "product_showcase",
}


# Creative skill triggers — when matched, route to invoke_skill with the
# named skill so the offline engine can fire multi-step recipes.
SKILL_TRIGGERS: List[Tuple[str, str]] = [
    ("spiral staircase", "spiral_staircase"),
    ("螺旋楼梯", "spiral_staircase"),
    ("spiral stair", "spiral_staircase"),
    ("colonnade", "colonnade"),
    ("柱廊", "colonnade"),
    ("列柱", "colonnade"),
    ("forest", "forest"),
    ("树林", "forest"),
    ("森林", "forest"),
    ("一片树", "forest"),
    ("crystal garden", "crystal_garden"),
    ("水晶花园", "crystal_garden"),
    ("crystal cluster", "crystal_garden"),
    ("dna helix", "dna_helix"),
    ("dna", "dna_helix"),
    ("双螺旋", "dna_helix"),
    ("spiral galaxy", "spiral_galaxy"),
    ("galaxy", "spiral_galaxy"),
    ("星系", "spiral_galaxy"),
    ("银河", "spiral_galaxy"),
    ("studio lighting", "studio_lighting"),
    ("三点光", "studio_lighting"),
    ("三点布光", "studio_lighting"),
    ("atom", "atom"),
    ("原子", "atom"),
    ("electron orbit", "atom"),
    ("电子轨道", "atom"),
    ("bridge", "bridge"),
    ("桥", "bridge"),
    ("桥梁", "bridge"),
    ("拱桥", "bridge"),
    ("zen garden", "zen_garden"),
    ("枯山水", "zen_garden"),
    ("禅意花园", "zen_garden"),
    ("rock garden", "zen_garden"),
    ("gear assembly", "gear_assembly"),
    ("gear", "gear_assembly"),
    ("gears", "gear_assembly"),
    ("齿轮", "gear_assembly"),
    ("齿轮组", "gear_assembly"),
    ("molecule", "molecule"),
    ("ball and stick", "molecule"),
    ("ball-and-stick", "molecule"),
    ("分子", "molecule"),
    ("分子模型", "molecule"),
    ("snowman", "snowman"),
    ("snow man", "snowman"),
    ("雪人", "snowman"),
]


# Procedural / advanced tool triggers — single-shot tool invocations that
# do not require the LLM to compose arguments. Each entry maps a phrase
# to a (tool_name, arguments-factory) pair.
PROCEDURAL_TRIGGERS: List[Tuple[str, str]] = [
    ("terrain", "terrain_generator"),
    ("地形", "terrain_generator"),
    ("l-system", "l_system"),
    ("lsystem", "l_system"),
    # Fractal recursion is more specific than the generic 'tree' -> l_system
    # trigger, so it must be checked first to win the routing decision.
    ("fractal tree", "create_fractal"),
    ("fractal", "create_fractal"),
    ("sierpinski", "create_fractal"),
    ("分形", "create_fractal"),
    ("分形树", "create_fractal"),
    ("递归", "create_fractal"),
    ("plant", "l_system"),
    ("植物", "l_system"),
    ("tree", "l_system"),
    ("树", "l_system"),
    ("shatter", "voronoi_shatter"),
    ("碎裂", "voronoi_shatter"),
    ("碎块", "voronoi_shatter"),
    ("碎片", "voronoi_shatter"),
    ("geodesic dome", "create_geodesic_dome"),
    ("geodesic", "create_geodesic_dome"),
    ("dome", "create_geodesic_dome"),
    ("测地穹顶", "create_geodesic_dome"),
    ("穹顶", "create_geodesic_dome"),
    ("圆顶", "create_geodesic_dome"),
    ("gyroid", "create_gyroid"),
    ("gyroid lattice", "create_gyroid"),
    ("minimal surface", "create_gyroid"),
    ("lattice", "create_gyroid"),
    ("晶格", "create_gyroid"),
    ("random palette", "randomize_palette"),
    ("randomize palette", "randomize_palette"),
    ("随机配色", "randomize_palette"),
    ("随机调色", "randomize_palette"),
    # Advanced editor-control triggers
    ("isolate", "isolate_object"),
    ("solo", "isolate_object"),
    ("隔离", "isolate_object"),
    ("单独显示", "isolate_object"),
    ("center to origin", "reset_transform"),
    ("ground to floor", "reset_transform"),
    ("reset transform", "reset_transform"),
    ("居中", "reset_transform"),
    ("落地", "reset_transform"),
    ("重置变换", "reset_transform"),
    ("clipping plane", "set_clipping_plane"),
    ("section view", "set_clipping_plane"),
    ("cutaway", "set_clipping_plane"),
    ("剖切", "set_clipping_plane"),
    ("截面", "set_clipping_plane"),
    ("set pivot", "set_object_pivot"),
    ("change pivot", "set_object_pivot"),
    ("设置轴心", "set_object_pivot"),
    ("轴心", "set_object_pivot"),
    # Voxel sculpting triggers
    ("voxel sphere", "voxel_sculpt"),
    ("voxel box", "voxel_sculpt"),
    ("voxel pyramid", "voxel_sculpt"),
    ("voxel sculpt", "voxel_sculpt"),
    ("voxel", "voxel_sculpt"),
    ("体素", "voxel_sculpt"),
    ("体素球", "voxel_sculpt"),
    ("体素方块", "voxel_sculpt"),
    # Particle system triggers
    ("particle fire", "create_particle_system"),
    ("particle smoke", "create_particle_system"),
    ("particle sparks", "create_particle_system"),
    ("particle fountain", "create_particle_system"),
    ("particle explosion", "create_particle_system"),
    ("fire effect", "create_particle_system"),
    ("smoke effect", "create_particle_system"),
    ("sparks effect", "create_particle_system"),
    ("粒子火焰", "create_particle_system"),
    ("粒子烟雾", "create_particle_system"),
    ("粒子系统", "create_particle_system"),
    # LOD chain triggers
    ("lod chain", "generate_lod_chain"),
    ("level of detail", "generate_lod_chain"),
    ("lod", "generate_lod_chain"),
    ("细节层次", "generate_lod_chain"),
    # Mesh repair triggers
    ("repair mesh", "repair_mesh"),
    ("watertight", "repair_mesh"),
    ("fix mesh", "repair_mesh"),
    ("manifold", "repair_mesh"),
    ("修复网格", "repair_mesh"),
    ("水密", "repair_mesh"),
    # Self-evaluation triggers
    ("self evaluate", "self_evaluate"),
    ("evaluate scene", "self_evaluate"),
    ("score scene", "self_evaluate"),
    ("quality check", "self_evaluate"),
    ("评估场景", "self_evaluate"),
    ("场景评分", "self_evaluate"),
    # Consensus voting triggers
    ("consensus vote", "consensus_vote"),
    ("multi-model", "consensus_vote"),
    ("共识投票", "consensus_vote"),
    # Deformation modifier triggers
    ("noise deform", "noise_deform"),
    ("noise displacement", "noise_deform"),
    ("displace vertices", "noise_deform"),
    ("add noise", "noise_deform"),
    ("噪声变形", "noise_deform"),
    ("顶点位移", "noise_deform"),
    ("bend it", "bend_object"),
    ("bend the", "bend_object"),
    ("apply bend", "bend_object"),
    ("弯曲", "bend_object"),
    ("twist it", "twist_object"),
    ("twist the", "twist_object"),
    ("apply twist", "twist_object"),
    ("helix", "twist_object"),
    ("扭转", "twist_object"),
    ("螺旋", "twist_object"),
    ("taper it", "taper_object"),
    ("taper the", "taper_object"),
    ("apply taper", "taper_object"),
    ("make it thinner", "taper_object"),
    ("锥形", "taper_object"),
    ("渐缩", "taper_object"),
    ("wave deform", "wave_deform"),
    ("ripple deform", "wave_deform"),
    ("add ripples", "wave_deform"),
    ("波浪变形", "wave_deform"),
    ("波纹", "wave_deform"),
    ("clear modifiers", "clear_modifiers"),
    ("remove modifiers", "clear_modifiers"),
    ("reset modifiers", "clear_modifiers"),
    ("去除修饰器", "clear_modifiers"),
    ("清除变形", "clear_modifiers"),
    # Post-processing effect triggers
    ("enable bloom", "set_bloom"),
    ("add bloom", "set_bloom"),
    ("bloom effect", "set_bloom"),
    ("glow effect", "set_bloom"),
    ("辉光效果", "set_bloom"),
    ("泛光", "set_bloom"),
    ("tone mapping", "set_tone_mapping"),
    ("change tone", "set_tone_mapping"),
    ("set tone", "set_tone_mapping"),
    ("色调映射", "set_tone_mapping"),
    ("color grading", "set_color_grading"),
    ("grade colors", "set_color_grading"),
    ("color correct", "set_color_grading"),
    ("调色", "set_color_grading"),
    ("色彩分级", "set_color_grading"),
    ("add vignette", "set_vignette"),
    ("vignette effect", "set_vignette"),
    ("暗角", "set_vignette"),
    ("渐晕", "set_vignette"),
    ("film grain", "set_film_grain"),
    ("grain effect", "set_film_grain"),
    ("film noise", "set_film_grain"),
    ("胶片颗粒", "set_film_grain"),
    ("颗粒感", "set_film_grain"),
    ("depth of field", "set_depth_of_field"),
    ("dof effect", "set_depth_of_field"),
    ("bokeh", "set_depth_of_field"),
    ("景深", "set_depth_of_field"),
    ("散景", "set_depth_of_field"),
    ("chromatic aberration", "set_chromatic_aberration"),
    ("rgb split", "set_chromatic_aberration"),
    ("色差", "set_chromatic_aberration"),
    ("色散", "set_chromatic_aberration"),
    ("reset postfx", "reset_postfx"),
    ("clear effects", "reset_postfx"),
    ("remove postfx", "reset_postfx"),
    ("重置后期", "reset_postfx"),
    ("清除效果", "reset_postfx"),
    # Pattern generator triggers
    ("hex grid", "hex_grid_pattern"),
    ("hexagonal grid", "hex_grid_pattern"),
    ("honeycomb grid", "hex_grid_pattern"),
    ("六边形网格", "hex_grid_pattern"),
    ("蜂窝网格", "hex_grid_pattern"),
    ("fibonacci", "fibonacci_lattice"),
    ("fibonacci spiral", "fibonacci_lattice"),
    ("sunflower pattern", "fibonacci_lattice"),
    ("phyllotaxis", "fibonacci_lattice"),
    ("斐波那契", "fibonacci_lattice"),
    ("向日葵", "fibonacci_lattice"),
    ("generate maze", "generate_maze"),
    ("make a maze", "generate_maze"),
    ("maze", "generate_maze"),
    ("labyrinth", "generate_maze"),
    ("迷宫", "generate_maze"),
    ("honeycomb", "honeycomb_truss"),
    ("honeycomb truss", "honeycomb_truss"),
    ("sandwich panel", "honeycomb_truss"),
    ("蜂窝结构", "honeycomb_truss"),
    ("夹芯板", "honeycomb_truss"),
    ("knotwork", "knotwork_lattice"),
    ("celtic knot", "knotwork_lattice"),
    ("knot pattern", "knotwork_lattice"),
    ("凯尔特结", "knotwork_lattice"),
    ("绳结图案", "knotwork_lattice"),
    # Advanced scene intelligence triggers
    ("analyze scene", "analyze_scene"),
    ("scene analysis", "analyze_scene"),
    ("analyze the scene", "analyze_scene"),
    ("scene critique", "critique_scene"),
    ("critique scene", "critique_scene"),
    ("auto fix", "auto_fix_scene"),
    ("auto fix scene", "auto_fix_scene"),
    ("suggest next", "suggest_next_actions"),
    ("what should i do next", "suggest_next_actions"),
    ("refine scene", "refine_scene"),
    ("improve scene", "refine_scene"),
    # Surface-detail operator triggers: shell / bevel / inflate / clear
    ("add a shell", "shell_modifier"),
    ("hollow shell", "shell_modifier"),
    ("thicken shell", "shell_modifier"),
    ("apply shell", "shell_modifier"),
    ("carve cavity", "shell_modifier"),
    ("inner cavity", "shell_modifier"),
    ("空心", "shell_modifier"),
    ("外壳", "shell_modifier"),
    ("壳体", "shell_modifier"),
    ("挖空", "shell_modifier"),
    ("bevel edges", "bevel_modifier"),
    ("bevel corners", "bevel_modifier"),
    ("round edges", "bevel_modifier"),
    ("chamfer", "bevel_modifier"),
    ("soften edges", "bevel_modifier"),
    ("倒角", "bevel_modifier"),
    ("倒圆角", "bevel_modifier"),
    ("磨边", "bevel_modifier"),
    ("inflate mesh", "inflate_modifier"),
    ("inflate it", "inflate_modifier"),
    ("puff up", "inflate_modifier"),
    ("deflate", "inflate_modifier"),
    ("shrink along normal", "inflate_modifier"),
    ("膨胀", "inflate_modifier"),
    ("充气", "inflate_modifier"),
    ("放气", "inflate_modifier"),
    ("clear surface effects", "clear_surface_ops"),
    ("remove surface ops", "clear_surface_ops"),
    ("reset surface", "clear_surface_ops"),
    ("清除表面效果", "clear_surface_ops"),
    # UV / texture mapping triggers
    ("uv projection", "uv_map"),
    ("set uv", "uv_map"),
    ("planar mapping", "uv_map"),
    ("spherical mapping", "uv_map"),
    ("box mapping", "uv_map"),
    ("triplanar mapping", "uv_map"),
    ("UV映射", "uv_map"),
    ("贴图坐标", "uv_map"),
    ("tile texture", "texture_tile"),
    ("repeat texture", "texture_tile"),
    ("offset texture", "texture_tile"),
    ("rotate uv", "texture_tile"),
    ("纹理平铺", "texture_tile"),
    ("重复纹理", "texture_tile"),
    # LOD baking trigger
    ("bake lod", "bake_lod"),
    ("lod levels", "bake_lod"),
    ("distance detail", "bake_lod"),
    ("烘焙LOD", "bake_lod"),
    ("细节层次烘焙", "bake_lod"),
    # Theme + workspace UX triggers
    ("switch theme", "set_theme"),
    ("set theme", "set_theme"),
    ("change theme", "set_theme"),
    ("warm theme", "set_theme"),
    ("studio theme", "set_theme"),
    ("rainbow theme", "set_theme"),
    ("moonlight theme", "set_theme"),
    ("dark mode", "set_theme"),
    ("切换主题", "set_theme"),
    ("深色模式", "set_theme"),
    ("浅色模式", "set_theme"),
    # Undo-history browse / restore
    ("browse history", "browse_history"),
    ("undo history", "browse_history"),
    ("history list", "browse_history"),
    ("浏览历史", "browse_history"),
    ("restore history", "restore_history_entry"),
    ("jump to history", "restore_history_entry"),
    ("还原历史", "restore_history_entry"),
    # Render presets
    ("cinematic preset", "apply_render_preset"),
    ("film look", "apply_render_preset"),
    ("architectural preset", "apply_render_preset"),
    ("clean cad look", "apply_render_preset"),
    ("sketch look", "apply_render_preset"),
    ("hand-drawn look", "apply_render_preset"),
    ("neon night look", "apply_render_preset"),
    ("cyberpunk look", "apply_render_preset"),
    ("watercolor look", "apply_render_preset"),
    ("studio showcase", "apply_render_preset"),
    ("product render", "apply_render_preset"),
    ("渲染预设", "apply_render_preset"),
    ("电影感", "apply_render_preset"),
    # Workspace layout
    ("modeler layout", "set_workspace_layout"),
    ("animator layout", "set_workspace_layout"),
    ("review layout", "set_workspace_layout"),
    ("minimal layout", "set_workspace_layout"),
    ("immersion mode", "set_workspace_layout"),
    ("full canvas", "set_workspace_layout"),
    ("建模布局", "set_workspace_layout"),
    ("动画布局", "set_workspace_layout"),
    ("评审布局", "set_workspace_layout"),
    ("极简布局", "set_workspace_layout"),
    ("沉浸模式", "set_workspace_layout"),
    ("优化场景", "refine_scene"),
    ("场景分析", "analyze_scene"),
    ("场景批评", "critique_scene"),
    ("自动修复", "auto_fix_scene"),
    ("智能建议", "suggest_next_actions"),
    ("snapshot scene", "snapshot_scene"),
    ("save snapshot", "snapshot_scene"),
    ("capture snapshot", "snapshot_scene"),
    ("version save", "snapshot_scene"),
    ("保存快照", "snapshot_scene"),
    ("保存版本", "snapshot_scene"),
    ("list snapshots", "list_snapshots"),
    ("show snapshots", "list_snapshots"),
    ("查看快照", "list_snapshots"),
    ("版本列表", "list_snapshots"),
    ("restore snapshot", "restore_snapshot"),
    ("load snapshot", "restore_snapshot"),
    ("revert to", "restore_snapshot"),
    ("恢复快照", "restore_snapshot"),
    ("还原版本", "restore_snapshot"),
    ("compare snapshots", "snapshot_diff"),
    ("diff snapshots", "snapshot_diff"),
    ("版本对比", "snapshot_diff"),
    ("快照差异", "snapshot_diff"),
    ("delete snapshot", "delete_snapshot"),
    ("remove snapshot", "delete_snapshot"),
    ("删除快照", "delete_snapshot"),
    # Scene composition tool triggers
    ("scatter", "scatter_objects"),
    ("random scatter", "scatter_objects"),
    ("随机散布", "scatter_objects"),
    ("create staircase", "create_staircase"),
    ("make stairs", "create_staircase"),
    ("创建楼梯", "create_staircase"),
    ("create bridge", "create_bridge"),
    ("make a bridge", "create_bridge"),
    ("创建桥", "create_bridge"),
    ("create terrain mesh", "create_terrain_mesh"),
    ("terrain mesh", "create_terrain_mesh"),
    ("地形网格", "create_terrain_mesh"),
    ("clone chain", "clone_chain"),
    ("chain along path", "clone_chain"),
    ("链式克隆", "clone_chain"),
]


# Object animation triggers — map phrases to (tool_name, default args).
ANIMATION_TRIGGERS: List[Tuple[str, str, str]] = [
    # (phrase, tool_name, animation_kind) — animation_kind becomes part of args
    ("orbit animation", "orbit_animation", "orbit"),
    ("orbit", "orbit_animation", "orbit"),
    ("轨道动画", "orbit_animation", "orbit"),
    ("环绕动画", "orbit_animation", "orbit"),
    ("wave animation", "wave_animation", "wave"),
    ("wave", "wave_animation", "wave"),
    ("波浪动画", "wave_animation", "wave"),
    ("正弦动画", "wave_animation", "wave"),
    ("bounce animation", "bounce_animation", "bounce"),
    ("bounce", "bounce_animation", "bounce"),
    ("弹跳动画", "bounce_animation", "bounce"),
    ("keyframe animation", "keyframe_animation", "keyframe"),
    ("关键帧动画", "keyframe_animation", "keyframe"),
    ("spin animation", "spin_animation", "spin"),
    ("make it spin", "spin_animation", "spin"),
    ("spin", "spin_animation", "spin"),
    ("旋转动画", "spin_animation", "spin"),
    ("自转", "spin_animation", "spin"),
    ("pulse animation", "pulse_animation", "pulse"),
    ("make it pulse", "pulse_animation", "pulse"),
    ("pulse", "pulse_animation", "pulse"),
    ("脉冲动画", "pulse_animation", "pulse"),
    # Generic "animate" triggers — default to spin when no specific kind is
    # named. Covers "animate the cube", "animate it", "add an animation".
    ("animate the", "spin_animation", "spin"),
    ("animate it", "spin_animation", "spin"),
    ("add an animation", "spin_animation", "spin"),
    ("add a animation", "spin_animation", "spin"),
    ("add animation", "spin_animation", "spin"),
    ("make it move", "spin_animation", "spin"),
    ("give it motion", "spin_animation", "spin"),
    ("动起来", "spin_animation", "spin"),
    ("加个动画", "spin_animation", "spin"),
    ("添加动画", "spin_animation", "spin"),
]


# Editor-overlay gap tools — dismiss the radial menu, measurement overlay,
# or camera flythrough. Single-phrase → tool_name mappings with no args.
OVERLAY_TRIGGERS: List[Tuple[str, str]] = [
    ("clear measurement", "clear_measurement"),
    ("remove measurement", "clear_measurement"),
    ("hide measurement", "clear_measurement"),
    ("清除测量", "clear_measurement"),
    ("清除标尺", "clear_measurement"),
    ("取消测量", "clear_measurement"),
    ("stop flythrough", "stop_camera_flythrough"),
    ("stop camera flythrough", "stop_camera_flythrough"),
    ("end flythrough", "stop_camera_flythrough"),
    ("停止飞越", "stop_camera_flythrough"),
    ("停止飞行", "stop_camera_flythrough"),
    ("结束飞越", "stop_camera_flythrough"),
    ("show radial menu", "control_radial_menu"),
    ("open radial menu", "control_radial_menu"),
    ("显示环形菜单", "control_radial_menu"),
    ("打开环形菜单", "control_radial_menu"),
    ("hide radial menu", "control_radial_menu"),
    ("close radial menu", "control_radial_menu"),
    ("关闭环形菜单", "control_radial_menu"),
    ("隐藏环形菜单", "control_radial_menu"),
]


# Panel-visibility triggers — toggle / show / hide the left chat panel or
# the right workspace panel. Each entry maps a phrase to (panel, visible)
# where ``visible`` is True to show, False to hide, or None to toggle.
PANEL_TOGGLE_TRIGGERS: List[Tuple[str, str, Optional[bool]]] = [
    # Left chat panel — toggle / show / hide
    ("toggle chat panel", "chat", None),
    ("toggle left panel", "chat", None),
    ("show chat panel", "chat", True),
    ("open chat panel", "chat", True),
    ("expand chat panel", "chat", True),
    ("hide chat panel", "chat", False),
    ("close chat panel", "chat", False),
    ("collapse chat panel", "chat", False),
    ("显示聊天面板", "chat", True),
    ("打开聊天面板", "chat", True),
    ("展开聊天面板", "chat", True),
    ("隐藏聊天面板", "chat", False),
    ("关闭聊天面板", "chat", False),
    ("收起聊天面板", "chat", False),
    ("切换聊天面板", "chat", None),
    # Right workspace panel — toggle / show / hide
    ("toggle right panel", "right", None),
    ("toggle side panel", "right", None),
    ("show right panel", "right", True),
    ("open right panel", "right", True),
    ("expand right panel", "right", True),
    ("hide right panel", "right", False),
    ("close right panel", "right", False),
    ("collapse right panel", "right", False),
    ("显示右侧面板", "right", True),
    ("打开右侧面板", "right", True),
    ("展开右侧面板", "right", True),
    ("隐藏右侧面板", "right", False),
    ("关闭右侧面板", "right", False),
    ("收起右侧面板", "right", False),
    ("切换右侧面板", "right", None),
]

# Deselect-all triggers — clear the current selection. Mirrors the
# Ctrl+Shift+A keyboard shortcut so the offline engine understands the
# same natural-language requests the LLM would handle online.
DESELECT_TRIGGERS: List[str] = [
    "deselect all", "clear selection", "drop selection", "unselect all",
    "取消选择", "取消选中", "清除选择", "清除选中", "取消所有选择", "取消所有选中",
]

# Animation-loop triggers — enable or disable looping at the timeline end.
# Each entry maps a phrase to the target ``enabled`` boolean.
ANIMATION_LOOP_TRIGGERS: List[Tuple[str, bool]] = [
    ("loop animation", True), ("enable loop", True), ("enable looping", True),
    ("turn on loop", True), ("loop playback", True), ("make it loop", True),
    ("animation loop on", True), ("enable animation loop", True),
    ("循环播放", True), ("开启循环", True), ("启用循环", True), ("打开循环", True),
    ("disable animation loop", False), ("disable loop", False),
    ("turn off animation loop", False), ("turn off loop", False),
    ("stop looping", False), ("stop animation loop", False),
    ("animation loop off", False), ("no loop", False),
    ("play once", False), ("single play", False),
    ("关闭循环", False), ("禁用循环", False), ("取消循环", False), ("播放一次", False),
    ("单次播放", False), ("不循环", False),
]


# Macro and variant tool triggers — single-shot tool calls that don't need
# the LLM to compose arguments. Phrases that imply listing map to
# list_macros / list_variants (no args). Phrases that imply saving a
# variant extract the name from the message.
MACRO_TRIGGERS: List[Tuple[str, str]] = [
    ("list macros", "list_macros"),
    ("show macros", "list_macros"),
    ("列出宏", "list_macros"),
    ("显示宏", "list_macros"),
    ("宏列表", "list_macros"),
]

WORKFLOW_TRIGGERS: List[Tuple[str, str]] = [
    ("list workflows", "list_workflows"),
    ("show workflows", "list_workflows"),
    ("列出工作流", "list_workflows"),
    ("显示工作流", "list_workflows"),
    ("工作流列表", "list_workflows"),
]

# Generative geometry triggers — radial symmetry rings + jittered clones.
# These tools need a target so the handler block below defaults target to
# the most recently created object when the user does not name one, and
# parses count / radius / jitter from the message.
GENERATIVE_GEOMETRY_TRIGGERS: List[Tuple[str, str]] = [
    ("radial symmetry", "radial_symmetry"),
    ("radially symmetric", "radial_symmetry"),
    ("petal ring", "radial_symmetry"),
    ("propeller", "radial_symmetry"),
    ("around the ring", "radial_symmetry"),
    ("radial array", "radial_symmetry"),
    ("环形阵列", "radial_symmetry"),
    ("径向对称", "radial_symmetry"),
    ("花瓣环", "radial_symmetry"),
    ("环形分布", "radial_symmetry"),
    ("clone with jitter", "clone_with_jitter"),
    ("with jitter", "clone_with_jitter"),
    ("jittered clones", "clone_with_jitter"),
    ("scatter clones", "clone_with_jitter"),
    ("jittered copies", "clone_with_jitter"),
    ("jittered duplicates", "clone_with_jitter"),
    ("jittered", "clone_with_jitter"),
    ("抖动克隆", "clone_with_jitter"),
    ("随机散布", "clone_with_jitter"),
    ("抖动复制", "clone_with_jitter"),
    ("抖动", "clone_with_jitter"),
]

VARIANT_TRIGGERS: List[Tuple[str, str]] = [
    ("list variants", "list_variants"),
    ("show variants", "list_variants"),
    ("列出变体", "list_variants"),
    ("显示变体", "list_variants"),
    ("变体列表", "list_variants"),
]


# Scene-template and skill catalog listing — single-shot read-only tools
# that return their full catalog without arguments. Triggered by phrases
# like "list templates", "which templates are available", "list skills".
TEMPLATE_TRIGGERS: List[Tuple[str, str]] = [
    ("list templates", "list_scene_templates"),
    ("list scene templates", "list_scene_templates"),
    ("show templates", "list_scene_templates"),
    ("show scene templates", "list_scene_templates"),
    ("which templates", "list_scene_templates"),
    ("what templates", "list_scene_templates"),
    ("available templates", "list_scene_templates"),
    ("列出模板", "list_scene_templates"),
    ("列出场景模板", "list_scene_templates"),
    ("显示模板", "list_scene_templates"),
    ("可用模板", "list_scene_templates"),
    ("模板列表", "list_scene_templates"),
]

SKILL_CATALOG_TRIGGERS: List[Tuple[str, str]] = [
    ("list skills", "list_skills"),
    ("show skills", "list_skills"),
    ("which skills", "list_skills"),
    ("what skills", "list_skills"),
    ("available skills", "list_skills"),
    ("列出技能", "list_skills"),
    ("显示技能", "list_skills"),
    ("可用技能", "list_skills"),
    ("技能列表", "list_skills"),
]


# Constraint-authoring + goal-driven refinement triggers. These map
# natural-language requests to the constraint tools (add/list/clear/solve)
# and the refine_scene multi-iteration loop. Single-phrase → tool_name
# mappings; richer argument composition is left to the LLM path.
CONSTRAINT_TRIGGERS: List[Tuple[str, str]] = [
    ("list constraints", "list_constraints"),
    ("show constraints", "list_constraints"),
    ("which constraints", "list_constraints"),
    ("what constraints", "list_constraints"),
    ("列出约束", "list_constraints"),
    ("显示约束", "list_constraints"),
    ("约束列表", "list_constraints"),
    ("clear constraints", "clear_constraints"),
    ("remove constraints", "clear_constraints"),
    ("reset constraints", "clear_constraints"),
    ("清除约束", "clear_constraints"),
    ("清空约束", "clear_constraints"),
    ("删除约束", "clear_constraints"),
    ("solve constraints", "solve_constraints"),
    ("enforce constraints", "solve_constraints"),
    ("apply constraints", "solve_constraints"),
    ("求解约束", "solve_constraints"),
    ("执行约束", "solve_constraints"),
    ("应用约束", "solve_constraints"),
    ("约束求解", "solve_constraints"),
]

REFINE_TRIGGERS: List[Tuple[str, str]] = [
    ("refine scene", "refine_scene"),
    ("refine the scene", "refine_scene"),
    ("iteratively refine", "refine_scene"),
    ("polish the scene", "refine_scene"),
    ("presentation ready", "refine_scene"),
    ("presentation-ready", "refine_scene"),
    ("hero shot", "refine_scene"),
    ("make it presentable", "refine_scene"),
    ("迭代优化", "refine_scene"),
    ("迭代精修", "refine_scene"),
    ("精修场景", "refine_scene"),
    ("演示级", "refine_scene"),
    ("打磨场景", "refine_scene"),
]


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def _find_color(msg: str) -> Optional[str]:
    """Detect a color keyword in the message."""
    for kw, hex_val in COLOR_MAP.items():
        if kw in msg:
            return hex_val
    # Try hex color pattern
    hex_match = re.search(r'#([0-9a-fA-F]{6})', msg)
    if hex_match:
        return f"#{hex_match.group(1)}"
    return None


def _find_preset(msg: str) -> Optional[str]:
    """Detect a material preset keyword."""
    for kw, preset in PRESET_MAP.items():
        if kw in msg:
            return preset
    return None


def _find_target_name(msg: str, scene_objects: List[Dict]) -> Optional[str]:
    """Try to find which object the user is referring to by name or type."""
    msg_lower = msg.lower()
    # Check for explicit name mentions
    for obj in scene_objects:
        name = obj.get("name", "")
        if name and name.lower() in msg_lower:
            return name
    # Check for type mentions using both user-facing words ("cube", "球")
    # and canonical geometry types ("box", "sphere"). GEO_MAP keys are the
    # user-facing synonyms, values are the canonical types stored on each
    # scene object. We check keys first so "cube" matches before "box".
    for user_word, geo_type in GEO_MAP.items():
        if user_word in msg_lower:
            for obj in scene_objects:
                geo = obj.get("geometry", {})
                if geo.get("type") == geo_type:
                    return obj.get("name", "")
    # Check for "last" or "it" referring to the most recent object
    if any(w in msg_lower for w in ["it", "that", "last", "the object", "这个", "那个", "上一个"]):
        if scene_objects:
            return scene_objects[-1].get("name", "")
    return None


def _parse_number_list(text: str) -> Optional[List[float]]:
    """Parse a bracketed number list like [1, 2, 3] or (1, 2, 3)."""
    match = re.search(r'[\[\(]\s*([\d.\-,\s]+)\s*[\]\)]', text)
    if match:
        parts = re.split(r'[,\s]+', match.group(1).strip())
        try:
            return [float(p) for p in parts if p]
        except ValueError:
            pass
    return None


def _parse_number_after(text: str, anchor: str) -> Optional[float]:
    """Find the first number that follows an anchor word in text.

    Matches patterns like "radius 0.8", "radius=0.8", "radius to 0.8",
    "radius: 0.8". Returns None when no number follows the anchor.
    """
    pattern = rf'{re.escape(anchor)}\s*(?:to|=|:|of)?\s*(-?\d+(?:\.\d+)?)'
    m = re.search(pattern, text)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            return None
    return None


def _parse_axis_value(msg: str, axis_names: List[str]) -> Optional[Tuple[str, float]]:
    """Parse a single axis value like 'x 5' or 'y to 3.5'."""
    for axis in axis_names:
        pattern = rf'{axis}\s*(?:to|=|:)?\s*(-?\d+(?:\.\d+)?)'
        match = re.search(pattern, msg)
        if match:
            return (axis, float(match.group(1)))
    return None


# ---------------------------------------------------------------------------
# Compound intent chaining
# ---------------------------------------------------------------------------

# Conjunctions that separate compound clauses in a single message. The
# message is split on these to isolate trailing transform/material/light
# clauses that should operate on the just-created object.
_COMPOUND_CONJUNCTIONS = [
    " and then ", " then ", " after that ", "接着", "然后", "再",
    " and ", " and also ",
]

# Recursion guard — prevents _chain_compound_intents from re-entering
# itself via the recursive parse_message call. The chaining only needs to
# run one level deep: the outer call chains trailing clauses onto the
# primary creation step; sub-parses must not chain again.
_compound_chaining_active = False

# Minimal geometry-type → display-name map mirroring the create_object
# tool's GEOMETRY_DISPLAY_NAMES so chained intents can synthesise a target
# name that matches what the tool will actually assign.
_GEO_DISPLAY: Dict[str, str] = {
    "box": "Cube", "sphere": "Sphere", "cylinder": "Cylinder",
    "cone": "Cone", "torus": "Torus", "plane": "Plane",
    "torusKnot": "TorusKnot", "dodecahedron": "Dodecahedron",
    "icosahedron": "Icosahedron", "octahedron": "Octahedron",
    "tetrahedron": "Tetrahedron", "ring": "Ring", "capsule": "Capsule",
}

# Keywords that signal a trailing clause operates on an object (rather than
# being a new creation or scene-level command).
_TRAILING_ACTION_KEYWORDS = [
    "move", "translate", "position", "rotate", "rotation", "scale", "resize",
    "shrink", "enlarge", "grow", "color", "colour", "make it", "paint",
    "material", "metal", "glass", "wood", "plastic", "rubber", "ceramic",
    "marble", "neon", "emissive", "glow", "wireframe", "matte", "glossy",
    "rough", "smooth", "transparent", "opacity", "metalness", "roughness",
    "移动", "旋转", "缩放", "颜色", "材质", "发光", "透明",
]


def _chain_compound_intents(
    msg_lower: str,
    intents: List[ParsedIntent],
    scene_objects: List[Dict[str, Any]],
) -> List[ParsedIntent]:
    """Chain trailing transform/material clauses onto creation intents.

    When the user says "create a sphere then move it up 2 units and make it
    red", the initial parse only produces a ``create_object`` intent because
    the transform/material sections require existing scene objects. This
    function detects such compound messages, builds a synthetic scene from
    the created objects, and re-parses the trailing clauses to emit the
    missing transform/material intents — producing a complete multi-step
    plan in one pass.

    Only appends intents that are NOT already present (de-duplicated by
    tool_name + target) to avoid doubling the creation step.
    """
    global _compound_chaining_active
    if _compound_chaining_active:
        return intents
    _compound_chaining_active = True
    try:
        return _do_chain_compound_intents(msg_lower, intents, scene_objects)
    finally:
        _compound_chaining_active = False


def _parse_trailing_clause(
    clause: str,
    target_name: str,
    synthetic_objects: List[Dict[str, Any]],
) -> List[ParsedIntent]:
    """Directly parse a trailing clause for common transform / material /
    color patterns without invoking the full parse_message.

    This avoids the create-pattern swallowing issue: when the target name is
    also a geometry keyword (e.g. "Sphere"), the full parser would match the
    create pattern and generate a create_object intent that we then discard.
    This function instead emits transform_object / apply_material_preset /
    set_object_color intents directly.

    Returns an empty list when no pattern matches so the caller can fall
    back to the full re-parse.
    """
    results: List[ParsedIntent] = []
    c = clause.strip()

    # Find the current object state from the synthetic scene.
    obj = next((o for o in synthetic_objects if o.get("name") == target_name), None)
    cur_pos = obj.get("transform", {}).get("position", [0, 0, 0]) if obj else [0, 0, 0]
    cur_rot = obj.get("transform", {}).get("rotation", [0, 0, 0]) if obj else [0, 0, 0]
    cur_scl = obj.get("transform", {}).get("scale", [1, 1, 1]) if obj else [1, 1, 1]

    # 1. Color change — "make [target] red", "paint [target] blue",
    #    "color [target] green", "[target] red".
    for color_kw, color_hex in COLOR_MAP.items():
        if color_kw in c and any(v in c for v in ["make", "paint", "color", "colour", "染", "涂"]):
            results.append(ParsedIntent(
                tool_name="set_object_color",
                arguments={"target": target_name, "color": color_hex},
                description=f"Set {target_name} color to {color_kw}",
            ))
            return results

    # 2. Material preset — "make [target] metal/glass/wood/...".
    for preset_kw, preset_name in PRESET_MAP.items():
        if preset_kw in c and any(v in c for v in ["make", "apply", "material", "材质"]):
            results.append(ParsedIntent(
                tool_name="apply_material_preset",
                arguments={"target": target_name, "preset": preset_name},
                description=f"Apply {preset_name} material to {target_name}",
            ))
            return results

    # 3. Scale — "scale [target] 2", "scale it 1.5", "resize [target] 3".
    scale_m = re.search(r'(?:scale|resize|缩放)\s*(?:it|' + re.escape(target_name) + r')?\s*(?:to\s*)?(\d+(?:\.\d+)?)', c)
    if not scale_m:
        scale_m = re.search(r'(?:scale|resize)\s+(\d+(?:\.\d+)?)', c)
    if scale_m:
        sv = float(scale_m.group(1))
        results.append(ParsedIntent(
            tool_name="transform_object",
            arguments={"target": target_name, "scale": [sv, sv, sv]},
            description=f"Scale {target_name} to {sv}",
        ))
        return results

    # 4. Move — "move [target] up/down/left/right N", "move it N".
    dir_map = {"up": 1, "down": -1, "left": -1, "right": 1, "forward": 1, "back": -1, "backward": -1}
    move_m = re.search(r'(?:move|translate|移动)\s*(?:it|' + re.escape(target_name) + r')?\s*(\w+)\s*(\d+(?:\.\d+)?)', c)
    if move_m and move_m.group(1) in dir_map:
        direction = move_m.group(1)
        amount = float(move_m.group(2)) * dir_map[direction]
        new_pos = list(cur_pos)
        if direction in ("up", "down"):
            new_pos[1] += amount
        elif direction in ("left", "right"):
            new_pos[0] += amount
        elif direction in ("forward", "back", "backward"):
            new_pos[2] += amount
        results.append(ParsedIntent(
            tool_name="transform_object",
            arguments={"target": target_name, "position": new_pos},
            description=f"Move {target_name} {direction} by {abs(amount)}",
        ))
        return results

    # 5. Move by amount (no direction) — "move it 3" → X axis.
    move_by_m = re.search(r'(?:move|translate)\s*(?:it|' + re.escape(target_name) + r')?\s*(?:by\s*)?(\d+(?:\.\d+)?)', c)
    if move_by_m:
        val = float(move_by_m.group(1))
        new_pos = [cur_pos[0] + val, cur_pos[1], cur_pos[2]]
        results.append(ParsedIntent(
            tool_name="transform_object",
            arguments={"target": target_name, "position": new_pos},
            description=f"Move {target_name} by {val} on X",
        ))
        return results

    # 6. Rotate — "rotate [target] X 90", "rotate it 45 degrees".
    rot_m = re.search(r'rotate\s*(?:it|' + re.escape(target_name) + r')?\s*([xyz])?\s*(?:by\s*)?(\d+(?:\.\d+)?)', c)
    if rot_m:
        axis_letter = (rot_m.group(1) or "y").lower()
        deg = float(rot_m.group(2))
        rad = round(deg * 3.141592653589793 / 180.0, 4)
        axis_idx = {"x": 0, "y": 1, "z": 2}[axis_letter]
        new_rot = list(cur_rot)
        new_rot[axis_idx] = rad
        results.append(ParsedIntent(
            tool_name="transform_object",
            arguments={"target": target_name, "rotation": new_rot},
            description=f"Rotate {target_name} {deg}° on {axis_letter.upper()}",
        ))
        return results

    # 7. Emissive / glow — "make [target] glow", "make it emissive".
    if any(k in c for k in ["glow", "emissive", "发光", "自发光"]) and any(v in c for v in ["make", "set", "apply"]):
        results.append(ParsedIntent(
            tool_name="set_object_color",
            arguments={"target": target_name, "emissive": "#ffaa00"},
            description=f"Make {target_name} emissive",
        ))
        return results

    return results


def _do_chain_compound_intents(
    msg_lower: str,
    intents: List[ParsedIntent],
    scene_objects: List[Dict[str, Any]],
) -> List[ParsedIntent]:
    """Inner implementation of compound intent chaining (no recursion guard)."""
    # Collect names + default transforms of objects created in this pass.
    # When the create_object intent lacks a "name" argument, synthesise one
    # from the geometry_type (mirroring the tool's GEOMETRY_DISPLAY_NAMES)
    # and inject it back into the intent so the tool uses that exact name.
    created: List[Tuple[str, Dict[str, Any]]] = []
    for intent in intents:
        if intent.tool_name == "create_object":
            name = str(intent.arguments.get("name", "") or "")
            if not name:
                geo = str(intent.arguments.get("geometry_type", "") or "")
                name = _GEO_DISPLAY.get(geo, "Object")
                intent.arguments["name"] = name
            pos = intent.arguments.get("position", [0, 0, 0])
            if not isinstance(pos, list):
                pos = [0, 0, 0]
            created.append((name, {
                "id": name,
                "name": name,
                "transform": {
                    "position": list(pos),
                    "rotation": [0, 0, 0],
                    "scale": [1, 1, 1],
                },
            }))

    if not created:
        return intents

    # Build a synthetic scene that merges existing objects with the
    # just-created ones so trailing clauses can resolve targets.
    synthetic_objects = list(scene_objects) + [obj for _, obj in created]

    # Split the message into clauses by all conjunctions. Unlike a simple
    # left-to-right split, this finds every conjunction boundary in one
    # pass so compound messages like "create X then make it red and scale
    # it 2" yield three segments: ["create X", "make it red", "scale it 2"].
    # The first segment (the creation clause) is discarded — it's already
    # handled by the primary parse. Remaining segments are trailing clauses.
    segments = [msg_lower]
    for conj in _COMPOUND_CONJUNCTIONS:
        new_segments: List[str] = []
        for seg in segments:
            parts = seg.split(conj)
            new_segments.extend(parts)
        segments = new_segments
    segments = [s.strip() for s in segments if s.strip()]

    # The first segment is the creation clause (already parsed). Trailing
    # segments are candidates for chaining — but only those that contain
    # action keywords or are very short (likely pronoun references).
    trailing_clauses: List[str] = []
    for seg in segments[1:]:
        if any(kw in seg for kw in _TRAILING_ACTION_KEYWORDS) or len(seg.split()) <= 4:
            trailing_clauses.append(seg)

    if not trailing_clauses:
        return intents

    # Existing intent keys for de-duplication.
    existing_keys: set = set()
    for intent in intents:
        tgt = str(intent.arguments.get("target", "") or intent.arguments.get("name", "") or "")
        existing_keys.add((intent.tool_name, tgt))

    # Re-parse each trailing clause against the synthetic scene.
    for clause in trailing_clauses:
        if not clause.strip():
            continue
        # Resolve pronouns ("it", "the object") to the first created name.
        target_name = created[0][0]
        resolved_clause = clause
        if any(ref in clause for ref in [" it ", " it,", " it.", "it up", "it down", "it left", "it right", " the object", "the shape", "the mesh"]):
            resolved_clause = clause.replace(" it ", f" {target_name} ")
            resolved_clause = resolved_clause.replace("it up", f"{target_name} up")
            resolved_clause = resolved_clause.replace("it down", f"{target_name} down")
            resolved_clause = resolved_clause.replace("it left", f"{target_name} left")
            resolved_clause = resolved_clause.replace("it right", f"{target_name} right")
            resolved_clause = resolved_clause.replace(" the object", f" {target_name}")
            resolved_clause = resolved_clause.replace("the shape", target_name)
            resolved_clause = resolved_clause.replace("the mesh", target_name)
            if resolved_clause.startswith("it "):
                resolved_clause = resolved_clause.replace("it ", f"{target_name} ", 1)
        # Also resolve bare "make it" at the start of the clause.
        if resolved_clause.startswith("make it "):
            resolved_clause = resolved_clause.replace("make it ", f"make {target_name} ", 1)

        # Try the direct trailing-clause parser first — it handles common
        # transform / material / color patterns without invoking the full
        # parse_message (which would re-trigger the create pattern because
        # geometry names like "Sphere" are also GEO_MAP keys).
        direct = _parse_trailing_clause(resolved_clause, target_name, synthetic_objects)
        if direct:
            for sub in direct:
                tgt = str(sub.arguments.get("target", "") or sub.arguments.get("name", "") or "")
                key = (sub.tool_name, tgt)
                if key in existing_keys:
                    continue
                existing_keys.add(key)
                intents.append(sub)
            continue

        # Fallback: full re-parse for clauses the direct parser missed.
        sub_intents, _ = parse_message(resolved_clause, synthetic_objects, [])
        for sub in sub_intents:
            tgt = str(sub.arguments.get("target", "") or sub.arguments.get("name", "") or "")
            key = (sub.tool_name, tgt)
            if key in existing_keys:
                continue
            # Skip creation intents from the sub-parse — the main create
            # step already handles object creation.
            if sub.tool_name == "create_object":
                continue
            existing_keys.add(key)
            intents.append(sub)

    return intents


# ---------------------------------------------------------------------------
# Intent parsing functions
# ---------------------------------------------------------------------------

def parse_message(
    msg: str,
    scene_objects: List[Dict[str, Any]],
    scene_lights: List[Dict[str, Any]],
) -> Tuple[List[ParsedIntent], str]:
    """Parse a user message into a list of intents and a response text.

    Returns (intents, text_prefix) where text_prefix is prepended to the
    final response. If no intents are matched, returns ([], "").
    """
    msg_lower = msg.lower()
    intents: List[ParsedIntent] = []
    text_parts: List[str] = []
    matched_any = False

    # 0. Scene composition patterns — compound scene requests that produce
    # multi-step tool sequences (atmospheres, natural features, cityscapes,
    # gardens, solar systems, etc.). These take priority over the generic
    # skill/macro triggers because they produce richer, more tailored
    # results for each named scene.
    composition = _match_scene_composition(msg_lower)
    if composition:
        intents.extend(composition)
        matched_any = True

    # E. Compound scene descriptions — "make it look like X" pattern.
    # Maps atmosphere keywords to multi-tool sequences (background, fog,
    # ambient, particles, emissive objects). Runs before skill invocation
    # so the specific look is not swallowed by a generic rule.
    if not matched_any and "make it look like" in msg_lower:
        _look_scene_intents: List[ParsedIntent] = []
        if "dusk" in msg_lower:
            _look_scene_intents = [
                ParsedIntent(tool_name="set_background", arguments={"color": "#ff9a5a"}, description="Set dusk warm sky background"),
                ParsedIntent(tool_name="set_fog", arguments={"color": "#ffb88a", "density": 0.018}, description="Add soft dusk horizon fog"),
                ParsedIntent(tool_name="set_ambient_level", arguments={"intensity": 0.55, "color": "#ffcc99"}, description="Set warm dusk ambient light"),
                ParsedIntent(tool_name="add_light", arguments={"light_type": "directional", "color": "#ff8844", "intensity": 1.3, "position": [-4, 1, -3]}, description="Add low-angle dusk sun"),
            ]
        elif "underwater" in msg_lower:
            _look_scene_intents = [
                ParsedIntent(tool_name="set_background", arguments={"color": "#0a4a6a"}, description="Set deep blue underwater background"),
                ParsedIntent(tool_name="set_viewport_background", arguments={"mode": "gradient", "top_color": "#0a4a6a", "bottom_color": "#052a3a"}, description="Set underwater depth gradient"),
                ParsedIntent(tool_name="set_fog", arguments={"color": "#1a5a7a", "density": 0.04}, description="Add dense water caustic fog"),
                ParsedIntent(tool_name="create_particle_system", arguments={"target": "bubbles", "count": 250, "spread": [12, 8, 12], "color": "#aadfff", "size": 0.04}, description="Create underwater bubble particles"),
            ]
        elif "alien world" in msg_lower or "alien" in msg_lower:
            _look_scene_intents = [
                ParsedIntent(tool_name="set_background", arguments={"color": "#3a0a4a"}, description="Set alien purple sky background"),
                ParsedIntent(tool_name="create_particle_system", arguments={"target": "stars", "count": 350, "spread": [35, 20, 35], "color": "#cc88ff", "size": 0.06}, description="Create purple-tinted starfield particles"),
                ParsedIntent(tool_name="create_object", arguments={"geometry_type": "sphere", "name": "AlienCrystal_A", "radius": 0.6, "position": [2, 0.6, -1], "color": "#aa44ff", "emissive": "#6622aa"}, description="Create emissive alien crystal A"),
                ParsedIntent(tool_name="create_object", arguments={"geometry_type": "icosahedron", "name": "AlienCrystal_B", "radius": 0.4, "position": [-1.5, 0.4, 1], "color": "#ff44aa", "emissive": "#aa2266"}, description="Create emissive alien crystal B"),
                ParsedIntent(tool_name="set_ambient_level", arguments={"intensity": 0.4, "color": "#7a4aaa"}, description="Set purple alien ambient glow"),
            ]
        if _look_scene_intents:
            intents.extend(_look_scene_intents)
            matched_any = True

    # Lighting mood — "make it cozy/dramatic/bright/moody" sets up an
    # appropriate lighting configuration in one step. cozy = warm point
    # lights at low intensity; dramatic = strong directional with deep
    # shadows; bright = high ambient + directional; moody = low ambient
    # + colored point lights. Parsed early so the mood keyword is not
    # swallowed by the generic single-light section.
    if not matched_any:
        _mood_match: Optional[str] = None
        for _mood_kw in ("cozy", "dramatic", "bright", "moody"):
            if _mood_kw in msg_lower:
                _mood_match = _mood_kw
                break
        if _mood_match and any(v in msg_lower for v in (
            "make", "set", "lighting", "feel", "atmosphere", "mood", "灯光", "氛围", "感觉",
        )):
            _mood_intents: List[ParsedIntent] = []
            if _mood_match == "cozy":
                _mood_intents = [
                    ParsedIntent(tool_name="set_ambient_level", arguments={"intensity": 0.35, "color": "#ffb066"}, description="Warm low ambient for cozy mood"),
                    ParsedIntent(tool_name="add_light", arguments={"light_type": "point", "color": "#ffaa55", "intensity": 0.8, "position": [2.5, 1.5, 2.5]}, description="Warm point light A for cozy mood"),
                    ParsedIntent(tool_name="add_light", arguments={"light_type": "point", "color": "#ffaa55", "intensity": 0.6, "position": [-2.5, 1.5, -2.0]}, description="Warm point light B for cozy mood"),
                ]
            elif _mood_match == "dramatic":
                _mood_intents = [
                    ParsedIntent(tool_name="set_ambient_level", arguments={"intensity": 0.12, "color": "#4466aa"}, description="Low cool ambient for dramatic mood"),
                    ParsedIntent(tool_name="add_light", arguments={"light_type": "directional", "color": "#ffffff", "intensity": 2.5, "position": [6, 9, 4], "cast_shadow": True}, description="Strong directional key with deep shadows for dramatic mood"),
                ]
            elif _mood_match == "bright":
                _mood_intents = [
                    ParsedIntent(tool_name="set_ambient_level", arguments={"intensity": 0.85, "color": "#ffffff"}, description="High ambient for bright mood"),
                    ParsedIntent(tool_name="add_light", arguments={"light_type": "directional", "color": "#ffffff", "intensity": 1.8, "position": [5, 8, 5]}, description="Bright directional fill for bright mood"),
                ]
            elif _mood_match == "moody":
                _mood_intents = [
                    ParsedIntent(tool_name="set_ambient_level", arguments={"intensity": 0.18, "color": "#223355"}, description="Low blue ambient for moody atmosphere"),
                    ParsedIntent(tool_name="add_light", arguments={"light_type": "point", "color": "#5577ff", "intensity": 1.2, "position": [3, 2, 3]}, description="Colored point light A for moody atmosphere"),
                    ParsedIntent(tool_name="add_light", arguments={"light_type": "point", "color": "#aa44cc", "intensity": 0.9, "position": [-3, 2, -2]}, description="Colored point light B for moody atmosphere"),
                ]
            if _mood_intents:
                intents.extend(_mood_intents)
                matched_any = True

    # Material batch apply — "apply metal to all spheres" / "make all
    # cubes red" applies a material or color to every object matching a
    # geometry type in one step. Parsed before the generic single-target
    # material section so the batch operation takes priority.
    if not matched_any:
        _batch_all = any(w in msg_lower for w in ("all ", "every ", "each "))
        if _batch_all and scene_objects:
            _batch_preset = _find_preset(msg_lower)
            _batch_color = _find_color(msg_lower)
            _batch_target_geo: Optional[str] = None
            for _kw, _geo in GEO_MAP.items():
                if _kw in msg_lower:
                    _batch_target_geo = _geo
                    break
            if _batch_target_geo and (_batch_preset or _batch_color):
                _batch_targets = [
                    o.get("name", "") for o in scene_objects
                    if (o.get("geometry") or {}).get("type") == _batch_target_geo and o.get("name")
                ]
                if _batch_targets:
                    for _bt in _batch_targets:
                        if _batch_preset:
                            intents.append(ParsedIntent(
                                tool_name="apply_material_preset",
                                arguments={"target": _bt, "preset": _batch_preset},
                                description=f"Apply {_batch_preset} to {_bt}",
                            ))
                        elif _batch_color:
                            intents.append(ParsedIntent(
                                tool_name="apply_material",
                                arguments={"target": _bt, "color": _batch_color},
                                description=f"Apply {_batch_color} to {_bt}",
                            ))
                    matched_any = True

    # Duplicate and arrange — "duplicate the X and arrange in
    # circle/grid/line" creates duplicates AND arranges them in one step.
    # Parsed before the generic duplicate section so the compound intent
    # takes priority.
    if not matched_any and scene_objects:
        _dup_arrange = any(w in msg_lower for w in ("duplicate", "copy", "复制"))
        _arrange_kw: Optional[str] = None
        if any(w in msg_lower for w in ("circle", "圆形", "环形")):
            _arrange_kw = "circle"
        elif "grid" in msg_lower:
            _arrange_kw = "grid"
        elif any(w in msg_lower for w in ("line", "row", "linear", "一排", "线性")):
            _arrange_kw = "linear"
        if _dup_arrange and _arrange_kw:
            _da_target = _find_target_name(msg_lower, scene_objects) or scene_objects[-1].get("name", "")
            _da_count_match = re.search(r'(\d+)\s*(?:copies|份|个|times)', msg_lower)
            _da_count = int(_da_count_match.group(1)) if _da_count_match else 4
            intents.append(ParsedIntent(
                tool_name="duplicate_object",
                arguments={"target": _da_target, "count": _da_count},
                description=f"Duplicate {_da_target} ({_da_count} copies)",
            ))
            intents.append(ParsedIntent(
                tool_name="arrange_layout",
                arguments={"layout_type": _arrange_kw},
                description=f"Arrange objects in {_arrange_kw} layout",
            ))
            matched_any = True

    # Scene variant — "create a variation" / "make an alternative" uses
    # the randomize_variant tool to produce a scene variant. Excludes
    # explicit save/load/restore phrases so those still route to their
    # dedicated tools.
    if not matched_any:
        _variant_exclude = any(k in msg_lower for k in (
            "save variant", "save scene", "load variant", "load scene",
            "restore variant", "restore scene", "snapshot",
            "保存变体", "加载变体", "恢复变体", "保存场景", "加载场景",
        ))
        if not _variant_exclude:
            _variant_kw = any(k in msg_lower for k in (
                "create a variation", "create a variant", "make a variation",
                "make an alternative", "make a variant", "create an alternative",
                "变体", "变型", "替代",
            ))
            if _variant_kw:
                intents.append(ParsedIntent(
                    tool_name="randomize_variant",
                    arguments={"name": "scene_variation"},
                    description="Create a randomized scene variant",
                ))
                matched_any = True

    # 1. Creative skill invocation (multi-step recipes).
    if not matched_any:
        for phrase, skill_name in SKILL_TRIGGERS:
            if phrase in msg_lower:
                intents.append(ParsedIntent(
                    tool_name="invoke_skill",
                    arguments={"skill": skill_name, "arguments": {}},
                    description=f"Invoke skill {skill_name}",
                ))
                matched_any = True
                break

    # Procedural generation tools (terrain / l_system / shatter / palette)
    if not matched_any:
        for phrase, tool_name in PROCEDURAL_TRIGGERS:
            if phrase in msg_lower:
                args: Dict[str, Any] = {}
                if tool_name == "voronoi_shatter" and scene_objects:
                    # Default to the most recently created object as the shatter target
                    args["target"] = scene_objects[-1].get("name", "")
                elif tool_name == "l_system":
                    # Allow "tree" / "plant" to also set position via parse_number_list
                    pos = _parse_number_list(msg_lower)
                    if pos and len(pos) >= 3:
                        args["position"] = pos[:3]
                elif tool_name == "isolate_object" and scene_objects:
                    args["target"] = scene_objects[-1].get("name", "")
                elif tool_name == "reset_transform" and scene_objects:
                    args["target"] = scene_objects[-1].get("name", "")
                    # Infer the preset from the matched phrase
                    if "ground" in phrase or "落地" in phrase:
                        args["preset"] = "ground_to_floor"
                    elif "center" in phrase or "居中" in phrase:
                        args["preset"] = "center_origin"
                    else:
                        args["preset"] = "reset_all"
                elif tool_name == "set_object_pivot" and scene_objects:
                    args["target"] = scene_objects[-1].get("name", "")
                    pos = _parse_number_list(msg_lower)
                    if pos and len(pos) >= 3:
                        args["pivot"] = pos[:3]
                    else:
                        args["pivot"] = [0.0, -0.5, 0.0]
                elif tool_name == "set_clipping_plane":
                    args["enabled"] = True
                    args["axis"] = "y"
                    if "x轴" in msg_lower or "x axis" in msg_lower:
                        args["axis"] = "x"
                    elif "z轴" in msg_lower or "z axis" in msg_lower:
                        args["axis"] = "z"
                    pos = _parse_number_list(msg_lower)
                    if pos and len(pos) >= 1:
                        args["position"] = float(pos[0])
                intents.append(ParsedIntent(
                    tool_name=tool_name,
                    arguments=args,
                    description=f"Run {tool_name}",
                ))
                matched_any = True
                break

    # 0c. Compound surface-detail / workspace / render-preset triggers.
    # Unlike the procedural block above, these are **additive**: each
    # matching trigger appends an intent without breaking, so compound
    # messages like "shell the cube then set theme to studio and apply
    # cinematic preset" produce three separate intents in one pass.
    _compound_triggers: List[Tuple[str, str]] = [
        ("shell modifier", "shell_modifier"),
        ("apply shell", "shell_modifier"),
        ("add a shell", "shell_modifier"),
        ("hollow shell", "shell_modifier"),
        ("shell the", "shell_modifier"),
        ("bevel", "bevel_modifier"),
        ("chamfer", "bevel_modifier"),
        ("round edges", "bevel_modifier"),
        ("round the edges", "bevel_modifier"),
        ("inflate", "inflate_modifier"),
        ("puff", "inflate_modifier"),
        ("deflate", "inflate_modifier"),
        ("uv map", "uv_map"),
        ("uv projection", "uv_map"),
        ("triplanar", "uv_map"),
        ("texture tile", "texture_tile"),
        ("tile texture", "texture_tile"),
        ("bake lod", "bake_lod"),
        ("lod chain", "bake_lod"),
        ("level of detail", "bake_lod"),
        ("clear surface", "clear_surface_ops"),
        ("remove surface ops", "clear_surface_ops"),
        ("set theme", "set_theme"),
        ("switch theme", "set_theme"),
        ("change theme", "set_theme"),
        ("studio theme", "set_theme"),
        ("rainbow theme", "set_theme"),
        ("moonlight theme", "set_theme"),
        ("warm theme", "set_theme"),
        ("dark mode", "set_theme"),
        ("render preset", "apply_render_preset"),
        ("cinematic preset", "apply_render_preset"),
        ("cinematic look", "apply_render_preset"),
        ("neon night", "apply_render_preset"),
        ("architectural preset", "apply_render_preset"),
        ("sketch look", "apply_render_preset"),
        ("watercolor", "apply_render_preset"),
        ("studio showcase", "apply_render_preset"),
        ("workspace layout", "set_workspace_layout"),
        ("modeler layout", "set_workspace_layout"),
        ("animator layout", "set_workspace_layout"),
        ("review layout", "set_workspace_layout"),
        ("minimal layout", "set_workspace_layout"),
        ("browse history", "browse_history"),
        ("undo history", "browse_history"),
        ("list render presets", "list_render_presets"),
        ("list themes", "list_themes"),
        ("list layouts", "list_workspace_layouts"),
        # Precision modeling — edge crease, bevel weight, vertex groups
        ("edge crease", "set_edge_crease"),
        ("crease edge", "set_edge_crease"),
        ("sharp edge", "set_edge_crease"),
        ("crease the", "set_edge_crease"),
        ("crease weight", "set_edge_crease"),
        ("bevel weight", "set_bevel_weight"),
        ("edge bevel weight", "set_bevel_weight"),
        ("vertex group", "manage_vertex_group"),
        ("vertex groups", "manage_vertex_group"),
        ("create vertex group", "manage_vertex_group"),
        ("list vertex groups", "manage_vertex_group"),
        ("assign vertex", "manage_vertex_group"),
    ]
    _already_matched: set = set()
    for phrase, tool_name in _compound_triggers:
        if tool_name in _already_matched:
            continue
        if phrase in msg_lower:
            _already_matched.add(tool_name)
            args: Dict[str, Any] = {}
            # Extract target object name from the message for tools that need it
            target_name = _find_target_name(msg_lower, scene_objects) if scene_objects else ""
            if tool_name in ("shell_modifier", "bevel_modifier", "inflate_modifier",
                             "uv_map", "texture_tile", "bake_lod", "clear_surface_ops",
                             "set_edge_crease", "set_bevel_weight", "manage_vertex_group"):
                args["target"] = target_name or (scene_objects[-1].get("name", "") if scene_objects else "")
            # Shell thickness extraction: look for "0.04 thickness" or "thickness 0.04"
            if tool_name == "shell_modifier":
                nums = _parse_number_list(msg_lower) or []
                if nums:
                    args["thickness"] = float(nums[0])
                else:
                    args["thickness"] = 0.05
            # Bevel radius extraction
            if tool_name == "bevel_modifier":
                nums = _parse_number_list(msg_lower) or []
                if nums:
                    args["radius"] = float(nums[0])
                else:
                    args["radius"] = 0.03
            # Inflate amount extraction
            if tool_name == "inflate_modifier":
                nums = _parse_number_list(msg_lower) or []
                if nums:
                    args["amount"] = float(nums[0])
                else:
                    args["amount"] = 0.05
            # UV projection mode
            if tool_name == "uv_map":
                for proj in ("triplanar", "spherical", "cylindrical", "planar", "box"):
                    if proj in msg_lower:
                        args["projection"] = proj
                        break
                else:
                    args["projection"] = "box"
                for ax in ("x", "y", "z"):
                    if f"axis {ax}" in msg_lower or f"{ax} axis" in msg_lower:
                        args["axis"] = ax
                        break
                else:
                    args["axis"] = "y"
            # Texture tile multiplier
            if tool_name == "texture_tile":
                nums = _parse_number_list(msg_lower) or []
                if nums:
                    args["tile"] = float(nums[0])
                else:
                    args["tile"] = 2.0
            # Theme name extraction
            if tool_name == "set_theme":
                for tn in ("studio", "rainbow", "moonlight", "warm"):
                    if tn in msg_lower:
                        args["theme"] = tn
                        break
                else:
                    args["theme"] = "warm"
            # Render preset name extraction
            if tool_name == "apply_render_preset":
                for pn in ("cinematic", "architectural", "sketch", "neon_night",
                           "watercolor", "studio_showcase"):
                    if pn in msg_lower or pn.replace("_", " ") in msg_lower:
                        args["preset"] = pn
                        break
                else:
                    args["preset"] = "cinematic"
            # Workspace layout name extraction
            if tool_name == "set_workspace_layout":
                for ln in ("modeler", "animator", "review", "minimal"):
                    if ln in msg_lower:
                        args["layout"] = ln
                        break
                else:
                    args["layout"] = "modeler"
            # Browse history limit
            if tool_name == "browse_history":
                nums = _parse_number_list(msg_lower) or []
                if nums:
                    args["limit"] = int(nums[0])
                else:
                    args["limit"] = 20
            # Edge crease weight extraction: "crease 0.8", "sharp edge 1.0"
            if tool_name == "set_edge_crease":
                nums = _parse_number_list(msg_lower) or []
                if nums:
                    args["weight"] = max(0.0, min(1.0, float(nums[0])))
                else:
                    # "sharp" without a number defaults to fully sharp (1.0);
                    # "soft" defaults to a mild crease (0.3).
                    if "sharp" in msg_lower:
                        args["weight"] = 1.0
                    elif "soft" in msg_lower:
                        args["weight"] = 0.3
                    else:
                        args["weight"] = 0.5
                if "clear" in msg_lower or "remove" in msg_lower:
                    args["clear"] = True
            # Bevel weight extraction
            if tool_name == "set_bevel_weight":
                nums = _parse_number_list(msg_lower) or []
                if nums:
                    args["weight"] = max(0.0, min(1.0, float(nums[0])))
                else:
                    args["weight"] = 1.0
                if "clear" in msg_lower or "remove" in msg_lower:
                    args["clear"] = True
            # Vertex group action extraction
            if tool_name == "manage_vertex_group":
                if "list" in msg_lower:
                    args["action"] = "list"
                elif "create" in msg_lower or "new " in msg_lower or "add group" in msg_lower:
                    args["action"] = "create"
                elif "rename" in msg_lower:
                    args["action"] = "rename"
                elif "delete" in msg_lower or "remove group" in msg_lower:
                    args["action"] = "delete"
                elif "assign" in msg_lower:
                    args["action"] = "assign"
                elif "remove vertex" in msg_lower:
                    args["action"] = "remove_vertices"
                else:
                    args["action"] = "list"
                # Name extraction: look for "group 'X'", "group X", "named X"
                name_match = re.search(r"(?:group|named|called)\s+['\"]?([a-zA-Z0-9_\- ]+?)['\"]?(?:\s+(?:with|to|from|on|vertices|vertex)|$)", msg_lower)
                if name_match:
                    args["name"] = name_match.group(1).strip()
                # Vertex indices extraction: "vertices 0,1,2" or "vertices 0 1 2"
                verts_match = re.search(r"vertices?\s+([0-9,\s]+)", msg_lower)
                if verts_match:
                    verts = [int(v) for v in re.findall(r"\d+", verts_match.group(1))]
                    if verts:
                        args["vertices"] = verts
            intents.append(ParsedIntent(
                tool_name=tool_name,
                arguments=args,
                description=f"Run {tool_name}",
            ))
            matched_any = True
        for phrase, tool_name in GENERATIVE_GEOMETRY_TRIGGERS:
            if phrase in msg_lower:
                target_name = _find_target_name(msg_lower, scene_objects) or scene_objects[-1].get("name", "")
                args: Dict[str, Any] = {"target": target_name}
                nums = _parse_number_list(msg_lower) or []
                if tool_name == "radial_symmetry":
                    # Default count=6, radius=3.0. If user mentioned a number
                    # >=2 it is treated as count; a second distinct number
                    # (or a float) is treated as radius.
                    count = 6
                    radius = 3.0
                    int_nums = [n for n in nums if isinstance(n, (int, float)) and n == int(n) and n >= 2]
                    float_nums = [n for n in nums if isinstance(n, (int, float))]
                    if int_nums:
                        count = max(2, min(100, int(int_nums[0])))
                        remaining = [n for n in float_nums if n != int_nums[0]]
                        if remaining:
                            radius = max(0.0, float(remaining[0]))
                    elif float_nums:
                        # Single float -> treat as radius
                        radius = max(0.0, float(float_nums[0]))
                    args["count"] = count
                    args["radius"] = radius
                    args["axis"] = "y"
                    args["face_outward"] = True
                elif tool_name == "clone_with_jitter":
                    # Default count=5, plus small jitter magnitudes.
                    count = 5
                    pos_jitter = 0.5
                    rot_jitter = 0.0
                    scale_jitter = 0.0
                    hue_jitter = 0.0
                    int_nums = [n for n in nums if isinstance(n, (int, float)) and n == int(n) and n >= 1]
                    if int_nums:
                        count = max(1, min(100, int(int_nums[0])))
                    if "color" in msg_lower or "颜色" in msg_lower or "hue" in msg_lower:
                        hue_jitter = 30.0
                    if "scale" in msg_lower or "缩放" in msg_lower or "大小" in msg_lower:
                        scale_jitter = 0.2
                    if "rotation" in msg_lower or "旋转" in msg_lower:
                        rot_jitter = 0.3
                    args["count"] = count
                    args["pos_jitter"] = pos_jitter
                    args["rot_jitter"] = rot_jitter
                    args["scale_jitter"] = scale_jitter
                    args["hue_jitter"] = hue_jitter
                intents.append(ParsedIntent(
                    tool_name=tool_name,
                    arguments=args,
                    description=f"Run {tool_name}",
                ))
                matched_any = True
                break

    # Object animation tools — require a target object to exist. When the
    # user does not name a target (e.g. "add a bounce animation", "animate
    # the cube") we fall back to the most recently created object so the
    # animation is still attached instead of being silently dropped.
    if not matched_any and scene_objects:
        for phrase, tool_name, kind in ANIMATION_TRIGGERS:
            if phrase in msg_lower:
                target_name = _find_target_name(msg_lower, scene_objects)
                # Default to the most recent object when no explicit target
                # is mentioned. This covers phrases like "add a bounce
                # animation" or "animate it" without requiring the user to
                # restate the object name.
                if not target_name and scene_objects:
                    target_name = scene_objects[-1].get("name", "")
                if target_name:
                    args: Dict[str, Any] = {"target": target_name}
                    if tool_name == "orbit_animation":
                        args["radius"] = 3.0
                        args["duration"] = 6.0
                        args["loop"] = True
                    elif tool_name == "wave_animation":
                        args["amplitude"] = 1.0
                        args["frequency"] = 0.5
                        args["loop"] = True
                    elif tool_name == "bounce_animation":
                        args["height"] = 1.5
                        args["bounces"] = 3
                        args["loop"] = True
                    elif tool_name == "spin_animation":
                        args["speed"] = 1.0
                        args["axis"] = "y"
                        args["loop"] = True
                    elif tool_name == "pulse_animation":
                        args["scale_factor"] = 1.2
                        args["frequency"] = 1.0
                        args["loop"] = True
                    intents.append(ParsedIntent(
                        tool_name=tool_name,
                        arguments=args,
                        description=f"Attach {kind} animation to {target_name}",
                    ))
                    matched_any = True
                    break

    # Procedural modifier patterns — extrude, bevel/chamfer, object blend.
    # Require a target object; fall back to the most recently created object
    # when the user does not explicitly name one.
    if not matched_any and scene_objects:
        _target_name = _find_target_name(msg_lower, scene_objects) or scene_objects[-1].get("name", "")
        _mod_args: Dict[str, Any] = {}
        _mod_tool: Optional[str] = None
        _mod_desc: str = ""

        if "extrude" in msg_lower or "挤出" in msg_lower:
            _mod_tool = "extrude_face"
            _mod_args = {"target": _target_name, "amount": 1.0, "faces": "all"}
            _extrude_nums = _parse_number_list(msg_lower)
            if _extrude_nums:
                _mod_args["amount"] = float(_extrude_nums[0])
            _mod_desc = f"Extrude faces of {_target_name}"
        elif any(k in msg_lower for k in ["bevel", "chamfer", "倒角", "倒边"]):
            _mod_tool = "chamfer_edges"
            _mod_args = {"target": _target_name, "amount": 0.1}
            _chamfer_nums = _parse_number_list(msg_lower)
            if _chamfer_nums:
                _mod_args["amount"] = float(_chamfer_nums[0])
            _mod_desc = f"Chamfer/bevel edges of {_target_name}"
        elif "morph" in msg_lower or "blend" in msg_lower or "融合" in msg_lower or "形变" in msg_lower:
            _targets: List[str] = []
            for _kw, _geo in GEO_MAP.items():
                if _kw in msg_lower:
                    _obj_match = next((o for o in scene_objects if o.get("geometry_type") == _geo), None)
                    if _obj_match and _obj_match.get("name") not in _targets:
                        _targets.append(_obj_match.get("name", ""))
            if len(_targets) < 2 and len(scene_objects) >= 2:
                _targets = [scene_objects[-2].get("name", ""), scene_objects[-1].get("name", "")]
            if len(_targets) >= 2:
                _mod_tool = "blend_objects"
                _mod_args = {"object_a": _targets[0], "object_b": _targets[1], "factor": 0.5}
                _factor_match = re.search(r'(?:factor|blend|morph|融合)\s*(\d+(?:\.\d+)?)', msg_lower)
                if _factor_match:
                    _mod_args["factor"] = max(0.0, min(1.0, float(_factor_match.group(1))))
                _mod_desc = f"Blend {_targets[0]} into {_targets[1]} (factor {_mod_args['factor']})"

        if _mod_tool and _target_name:
            intents.append(ParsedIntent(
                tool_name=_mod_tool,
                arguments=_mod_args,
                description=_mod_desc,
            ))
            matched_any = True

    # Workflow patterns — save / record / run named workflows.
    # Since step tracking is not yet available, compose_workflow creates a
    # demo 3-step workflow placeholder. run_workflow references the stored
    # workflow by name.
    if not matched_any:
        _wf_save_match = re.search(
            r'(?:save this workflow as|record workflow|save workflow)\s+["\']?([\w\s\-一-龥]+)["\']?',
            msg_lower,
        )
        if _wf_save_match:
            _wf_name = _wf_save_match.group(1).strip()
            intents.append(ParsedIntent(
                tool_name="compose_workflow",
                arguments={
                    "name": _wf_name,
                    "steps": [
                        {"tool": "create_object", "args": {"geometry_type": "box", "name": "Step1_Box"}},
                        {"tool": "apply_material_preset", "args": {"target": "Step1_Box", "preset": "metal"}},
                        {"tool": "transform_object", "args": {"target": "Step1_Box", "position": [0, 1, 0]}},
                    ],
                },
                description=f"Save workflow '{_wf_name}' (3-step demo)",
            ))
            matched_any = True
        else:
            _wf_run_match = re.search(
                r'(?:run workflow|execute workflow|apply workflow)\s+["\']?([\w\s\-一-龥]+)["\']?',
                msg_lower,
            )
            if _wf_run_match:
                _wf_name = _wf_run_match.group(1).strip()
                intents.append(ParsedIntent(
                    tool_name="run_workflow",
                    arguments={"name": _wf_name},
                    description=f"Run workflow '{_wf_name}'",
                ))
                matched_any = True

    # Editor-overlay gap tools + macro/variant listing — single-shot
    # tools with no required arguments. Matched before smart_compose so a
    # phrase like "list variants" doesn't get hijacked by another rule.
    if not matched_any:
        for phrase, tool_name in OVERLAY_TRIGGERS:
            if phrase in msg_lower:
                args: Dict[str, Any] = {}
                # control_radial_menu needs an explicit show flag; "hide" /
                # "close" / "关闭" / "隐藏" map to show=False, otherwise show=True.
                if tool_name == "control_radial_menu":
                    show = not any(
                        p in msg_lower for p in (
                            "hide", "close", "关闭", "隐藏", "dismiss",
                        )
                    )
                    args["show"] = show
                intents.append(ParsedIntent(
                    tool_name=tool_name,
                    arguments=args,
                    description=f"Run {tool_name}",
                ))
                matched_any = True
                break

    # 0d-bis. Panel-visibility triggers — toggle / show / hide the left
    # chat panel or the right workspace panel. The Agent-callable tool
    # emits an editor_toggle_panel delta the frontend dispatches to the
    # editor store, so the conversation can control layout focus without
    # the user touching the keyboard.
    if not matched_any:
        for phrase, panel, visible in PANEL_TOGGLE_TRIGGERS:
            if phrase in msg_lower:
                args: Dict[str, Any] = {"panel": panel}
                if visible is not None:
                    args["visible"] = visible
                intents.append(ParsedIntent(
                    tool_name="toggle_panel",
                    arguments=args,
                    description=f"Toggle {panel} panel",
                ))
                matched_any = True
                break

    # 0d-ter. Deselect-all triggers — clear the current selection. Mirrors
    # the Ctrl+Shift+A keyboard shortcut.
    if not matched_any:
        for phrase in DESELECT_TRIGGERS:
            if phrase in msg_lower:
                intents.append(ParsedIntent(
                    tool_name="deselect_all",
                    arguments={},
                    description="Clear the current selection",
                ))
                matched_any = True
                break

    # 0d-quater. Animation-loop triggers — enable or disable looping at
    # the timeline end. Maps phrases to the target ``enabled`` boolean.
    if not matched_any:
        for phrase, enabled in ANIMATION_LOOP_TRIGGERS:
            if phrase in msg_lower:
                intents.append(ParsedIntent(
                    tool_name="set_animation_loop",
                    arguments={"enabled": enabled},
                    description=f"Set animation loop to {enabled}",
                ))
                matched_any = True
                break

    if not matched_any:
        for phrase, tool_name in MACRO_TRIGGERS + WORKFLOW_TRIGGERS + VARIANT_TRIGGERS + TEMPLATE_TRIGGERS + SKILL_CATALOG_TRIGGERS + CONSTRAINT_TRIGGERS + REFINE_TRIGGERS:
            if phrase in msg_lower:
                intents.append(ParsedIntent(
                    tool_name=tool_name,
                    arguments={},
                    description=f"Run {tool_name}",
                ))
                matched_any = True
                break

    # 0e-bis. add_constraint — "add a constraint: <subject> <kind> <anchor>",
    # "约束 <subject> <kind> <anchor>". Parses the kind keyword (above /
    # below / faces / centered / min_distance / aligned / above_floor) and
    # the subject/anchor object names from the message. Falls back to a
    # bare add_constraint call (no args) when the phrase is detected but
    # the structure can't be parsed, so the LLM can compose arguments.
    if not matched_any:
        _cn_constraint_verb = any(k in msg_lower for k in [
            "add constraint", "add a constraint", "add an constraint",
            "constrain", "约束",
        ])
        if _cn_constraint_verb and scene_objects:
            _kind_map = {
                "above": "above", "above_floor": "above_floor",
                "above floor": "above_floor", "above the floor": "above_floor",
                "above ground": "above_floor",
                "落地": "above_floor", "在地面": "above_floor",
                "below": "below",
                "faces": "faces", "face": "faces", "facing": "faces",
                "朝向": "faces", "面向": "faces", "对着": "faces",
                "centered on": "centered", "centered": "centered",
                "centre on": "centered", "centre": "centered",
                "居中于": "centered", "居中": "centered", "在...中心": "centered",
                "min_distance": "min_distance", "min distance": "min_distance",
                "minimum distance": "min_distance", "at least": "min_distance",
                "最小距离": "min_distance", "至少": "min_distance",
                "aligned": "aligned", "align": "aligned",
                "对齐": "aligned", "对齐于": "aligned",
                "在...之上": "above", "在...下方": "below",
            }
            _detected_kind: Optional[str] = None
            for _trig, _kind in _kind_map.items():
                if _trig in msg_lower:
                    _detected_kind = _kind
                    break
            # Try to extract subject/anchor: prefer explicit "subject <kind> anchor"
            # pattern by walking scene object names. Simpler heuristic: pick
            # the last two distinct object names mentioned in the message.
            _mentioned: List[str] = []
            for _obj in scene_objects:
                _n = _obj.get("name", "")
                if _n and _n.lower() in msg_lower and _n not in _mentioned:
                    _mentioned.append(_n)
            if _detected_kind and len(_mentioned) >= 2:
                _args: Dict[str, Any] = {
                    "kind": _detected_kind,
                    "subject": _mentioned[0],
                    "anchor": _mentioned[1],
                }
                intents.append(ParsedIntent(
                    tool_name="add_constraint",
                    arguments=_args,
                    description=f"Add {_detected_kind} constraint: {_mentioned[0]} -> {_mentioned[1]}",
                ))
                matched_any = True
            elif _detected_kind and len(_mentioned) == 1 and _detected_kind == "above_floor":
                # above_floor only needs a subject
                intents.append(ParsedIntent(
                    tool_name="add_constraint",
                    arguments={"kind": "above_floor", "subject": _mentioned[0]},
                    description=f"Add above_floor constraint on {_mentioned[0]}",
                ))
                matched_any = True

    # Variant save / load / randomize — extract variant name from the
    # message via the "named/called <name>" or "<verb> <name>" patterns.
    if not matched_any:
        variant_save_match = re.search(
            r'(?:save|snapshot)\s+(?:variant|scene)\s+(?:named|called)?\s*["\']?([\w\-]+)["\']?',
            msg_lower,
        )
        variant_load_match = re.search(
            r'(?:load|restore|recall)\s+(?:variant|scene)\s+(?:named|called)?\s*["\']?([\w\-]+)["\']?',
            msg_lower,
        )
        variant_rand_match = re.search(
            r'(?:randomize|jitter)\s+(?:variant|scene)\s+(?:named|called)?\s*["\']?([\w\-]+)["\']?',
            msg_lower,
        )
        # Chinese variants
        variant_save_zh = re.search(r'(?:保存|存储)\s*(?:变体|场景)\s*["\']?([\w\-]+)["\']?', msg)
        variant_load_zh = re.search(r'(?:加载|载入|读取)\s*(?:变体|场景)\s*["\']?([\w\-]+)["\']?', msg)
        variant_rand_zh = re.search(r'(?:随机|抖动)\s*(?:变体|场景)\s*["\']?([\w\-]+)["\']?', msg)
        if variant_save_match or variant_save_zh:
            name = (variant_save_match or variant_save_zh).group(1)  # type: ignore[union-attr]
            intents.append(ParsedIntent(
                tool_name="save_variant",
                arguments={"name": name},
                description=f"Save variant '{name}'",
            ))
            matched_any = True
        elif variant_load_match or variant_load_zh:
            name = (variant_load_match or variant_load_zh).group(1)  # type: ignore[union-attr]
            intents.append(ParsedIntent(
                tool_name="load_variant",
                arguments={"name": name},
                description=f"Load variant '{name}'",
            ))
            matched_any = True
        elif variant_rand_match or variant_rand_zh:
            name = (variant_rand_match or variant_rand_zh).group(1)  # type: ignore[union-attr]
            intents.append(ParsedIntent(
                tool_name="randomize_variant",
                arguments={"name": name},
                description=f"Randomize variant '{name}'",
            ))
            matched_any = True

    # 1. Smart compose (check first to allow scene replacement)
    if not matched_any:
        for kw, template in COMPOSE_MAP.items():
            if kw in msg_lower:
                intents.append(ParsedIntent(
                    tool_name="smart_compose",
                    arguments={"template": template},
                    description=f"Generate {template} scene",
                ))
                matched_any = True
                break

    # 2. Object creation
    detected_color = _find_color(msg_lower)
    detected_preset = _find_preset(msg_lower)
    # Guard: skip creation when the message is actually about applying a
    # material preset to an existing object. "make the sphere metallic"
    # mentions "sphere" + "make" (creation triggers) but the user wants to
    # change the existing sphere's material, not spawn a new one. We detect
    # this by checking: (a) a material preset keyword is present, AND
    # (b) the scene already has at least one object whose geometry type
    # matches the mentioned geometry keyword. Also skip when the message
    # is clearly about lights ("add a point light above the sphere") so
    # the light-management section handles it without also creating a
    # geometry.
    _mentions_light = any(w in msg_lower for w in ["light", "灯光", "光源"])
    _existing_geo_types = {
        o.get("geometry", {}).get("type", "").lower() for o in scene_objects
    }
    _preset_targets_existing = False
    if detected_preset:
        for _kw, _geo in GEO_MAP.items():
            if _kw in msg_lower and _geo.lower() in _existing_geo_types:
                _preset_targets_existing = True
                break
    # Also skip creation when the message is about recoloring an existing
    # object — e.g. "make the cube gold" mentions "cube" + "make" + a color
    # but the user wants to change the existing cube's color, not spawn a
    # new gold cube.
    _color_targets_existing = False
    if detected_color:
        for _kw, _geo in GEO_MAP.items():
            if _kw in msg_lower and _geo.lower() in _existing_geo_types:
                _color_targets_existing = True
                break
    # Also skip creation when the message is about scaling an existing
    # object — e.g. "make the cube bigger" mentions "cube" + "make" but
    # the user wants to resize the existing cube, not spawn a new one.
    _scale_targets_existing = False
    if any(w in msg_lower for w in [
        "bigger", "smaller", "larger", "shrink", "enlarge", "grow",
        "放大", "缩小",
    ]):
        for _kw, _geo in GEO_MAP.items():
            if _kw in msg_lower and _geo.lower() in _existing_geo_types:
                _scale_targets_existing = True
                break
    # Skip regular creation when the message is a batch request — e.g.
    # "create 5 cubes" has a count prefix that should route to
    # batch_create_objects instead of a single create_object.
    _is_batch_request = bool(re.search(
        r'(?:create|make|add|generate|生成|创建|添加)\s+\d+\s+',
        msg_lower,
    ))
    if (
        any(kw in msg_lower for kw in list(GEO_MAP.keys())[:20])
        and any(w in msg_lower for w in ["create", "add", "make", "生成", "创建", "添加", "做一个", "来一个"])
        and not _mentions_light
        and not _preset_targets_existing
        and not _color_targets_existing
        and not _scale_targets_existing
        and not _is_batch_request
    ):
        # Parse explicit position / rotation / scale from the message
        init_position = _parse_number_list(msg_lower)
        # Disambiguate: a 3-tuple after "position/at/到" is a position; otherwise
        # treat the first 3-tuple as position (most common create intent).
        pos_match = re.search(r'(?:position|at|到|位于)\s*[\[\(]?\s*([\d.\-,\s]+)\s*[\]\)]?', msg_lower)
        if pos_match:
            try:
                parts = re.split(r'[,\s]+', pos_match.group(1).strip())
                init_position = [float(p) for p in parts if p][:3]
            except ValueError:
                init_position = None
        matched_types = set()
        for kw, geo_type in GEO_MAP.items():
            if kw in msg_lower and geo_type not in matched_types:
                matched_types.add(geo_type)
                args: Dict[str, Any] = {"geometry_type": geo_type}
                if detected_color:
                    args["color"] = detected_color
                if detected_preset == "metal":
                    args["metalness"] = 1.0
                    args["roughness"] = 0.25
                elif detected_preset == "glass":
                    args["opacity"] = 0.35
                    args["roughness"] = 0.05
                if init_position and len(init_position) >= 3:
                    args["position"] = init_position[:3]
                # Optional scale keyword: "scale 2" or "size 1.5"
                scale_match = re.search(r'(?:scale|size|缩放|大小)\s*(\d+(?:\.\d+)?)', msg_lower)
                if scale_match:
                    s = float(scale_match.group(1))
                    args["scale"] = [s, s, s]
                intents.append(ParsedIntent(
                    tool_name="create_object",
                    arguments=args,
                    description=f"Create {geo_type}",
                ))
                matched_any = True

    # Better numeric parsing — compact transform patterns that don't
    # require an explicit 3-tuple. Handles:
    #   "move by 3.2"           -> translate X by 3.2 (default axis)
    #   "rotate Z by 90 degrees" -> rotate Z axis by 90° (parsed letter)
    #   "scale uniformly to 2.5" -> uniform scale on all axes
    if not matched_any and scene_objects:
        _np_target = _find_target_name(msg_lower, scene_objects) or scene_objects[-1].get("name", "")
        _np_current = next((o for o in scene_objects if o.get("name") == _np_target), None)

        _move_by_match = re.search(
            r'(?:move|translate|平移|移动)\s*(?:by\s*)?(\d+(?:\.\d+)?)',
            msg_lower,
        )
        _has_explicit_axis = bool(re.search(r'\b[xyz]\b', msg_lower)) or bool(re.search(r'[xyz]轴', msg_lower))
        if _move_by_match and not _has_explicit_axis:
            _val = float(_move_by_match.group(1))
            _cur = _np_current.get("transform", {}).get("position", [0, 0, 0]) if _np_current else [0, 0, 0]
            intents.append(ParsedIntent(
                tool_name="transform_object",
                arguments={"target": _np_target, "position": [_cur[0] + _val, _cur[1], _cur[2]]},
                description=f"Move {_np_target} by {_val} on X (default axis)",
            ))
            matched_any = True

        if not matched_any:
            _rot_letter_match = re.search(
                r'rotate\s*([xyz])\s*(?:by\s*)?(\d+(?:\.\d+)?)\s*(?:degrees?|deg|°|度)?',
                msg_lower,
            )
            if _rot_letter_match:
                _axis_letter = _rot_letter_match.group(1).lower()
                _axis_idx = {"x": 0, "y": 1, "z": 2}[_axis_letter]
                _deg = float(_rot_letter_match.group(2))
                _rad = round(_deg * 3.141592653589793 / 180.0, 4)
                _cur = _np_current.get("transform", {}).get("rotation", [0, 0, 0]) if _np_current else [0, 0, 0]
                _new = list(_cur)
                _new[_axis_idx] = _rad
                intents.append(ParsedIntent(
                    tool_name="transform_object",
                    arguments={"target": _np_target, "rotation": _new},
                    description=f"Rotate {_np_target} {_deg}° on {_axis_letter.upper()} axis",
                ))
                matched_any = True

        if not matched_any and any(k in msg_lower for k in ["scale uniformly", "uniform scale", "uniformly scale", "均匀缩放"]):
            _uni_match = re.search(
                r'(?:scale uniformly to|uniform scale to|uniformly scale to|scale uniformly|均匀缩放)\s*(?:to\s*)?(\d+(?:\.\d+)?)',
                msg_lower,
            )
            if _uni_match:
                _sv = float(_uni_match.group(1))
                _cur = _np_current.get("transform", {}).get("scale", [1, 1, 1]) if _np_current else [1, 1, 1]
                intents.append(ParsedIntent(
                    tool_name="transform_object",
                    arguments={"target": _np_target, "scale": [_sv, _sv, _sv]},
                    description=f"Uniformly scale {_np_target} to {_sv} on all axes",
                ))
                matched_any = True

    # 3. Transform (move, rotate, scale)
    transform_verbs = [
        "move", "translate", "position", "rotate", "rotation", "scale", "resize",
        "shrink", "enlarge", "grow", "bigger", "smaller", "larger",
        "移动", "旋转", "缩放", "调整", "放大", "缩小",
    ]
    if any(v in msg_lower for v in transform_verbs) and scene_objects:
        target_name = _find_target_name(msg_lower, scene_objects)
        if target_name:
            is_rotate = any(v in msg_lower for v in ["rotate", "rotation", "旋转"])
            is_scale = any(v in msg_lower for v in [
                "scale", "resize", "缩放", "shrink", "enlarge", "grow",
                "bigger", "smaller", "larger", "放大", "缩小",
            ])
            field_name = "rotation" if is_rotate else ("scale" if is_scale else "position")

            # Try to parse coordinate list
            coords = _parse_number_list(msg_lower)
            if coords and len(coords) >= 3:
                intents.append(ParsedIntent(
                    tool_name="transform_object",
                    arguments={"target": target_name, field_name: coords[:3]},
                    description=f"Set {field_name} of {target_name}",
                ))
                matched_any = True
            else:
                # Try single axis
                axis_result = _parse_axis_value(msg_lower, ["x", "y", "z"])
                if axis_result:
                    axis, val = axis_result
                    axis_idx = {"x": 0, "y": 1, "z": 2}[axis]
                    current_obj = next((o for o in scene_objects if o.get("name") == target_name), None)
                    if current_obj:
                        current_vals = current_obj.get("transform", {}).get(field_name, [0, 0, 0])
                        new_vals = list(current_vals)
                        if field_name == "scale":
                            new_vals[axis_idx] = max(0.01, val)
                        else:
                            new_vals[axis_idx] = val
                        intents.append(ParsedIntent(
                            tool_name="transform_object",
                            arguments={"target": target_name, field_name: new_vals},
                            description=f"Set {field_name} {axis} of {target_name} to {val}",
                        ))
                        matched_any = True
                # Degree parsing for rotation — "rotate the cube 45
                # degrees" or "rotate 90 deg". Without an explicit axis,
                # default to Y (the most common rotation for objects
                # sitting on the ground plane). Convert degrees to radians.
                if not matched_any and is_rotate:
                    deg_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:degrees?|deg|°|度)', msg_lower)
                    if deg_match:
                        deg = float(deg_match.group(1))
                        # Detect explicit axis: "rotate x 45", "rotate y 90"
                        axis_idx = 1  # default Y
                        if re.search(r'\b(x|px|rx)\b', msg_lower):
                            axis_idx = 0
                        elif re.search(r'\b(y|py|ry)\b', msg_lower):
                            axis_idx = 1
                        elif re.search(r'\b(z|pz|rz)\b', msg_lower):
                            axis_idx = 2
                        rad = round(deg * 3.141592653589793 / 180.0, 4)
                        current_obj = next(
                            (o for o in scene_objects if o.get("name") == target_name), None
                        )
                        if current_obj:
                            cur = current_obj.get("transform", {}).get("rotation", [0, 0, 0])
                            new_vals = list(cur)
                        else:
                            new_vals = [0, 0, 0]
                        new_vals[axis_idx] = rad
                        intents.append(ParsedIntent(
                            tool_name="transform_object",
                            arguments={"target": target_name, "rotation": new_vals},
                            description=f"Rotate {target_name} {deg}° on {'XYZ'[axis_idx]}",
                        ))
                        matched_any = True
                # Directional movement — "move the sphere up", "move
                # the cube to the right", "move forward". Map natural
                # direction words to axis offsets and apply a default
                # step of 1.0 unit.
                if not matched_any and field_name == "position":
                    _dir_map = {
                        "up": (1, 1.0), "down": (1, -1.0),
                        "left": (0, -1.0), "right": (0, 1.0),
                        "forward": (2, 1.0), "forwards": (2, 1.0),
                        "back": (2, -1.0), "backward": (2, -1.0), "backwards": (2, -1.0),
                        "上": (1, 1.0), "下": (1, -1.0),
                        "左": (0, -1.0), "右": (0, 1.0),
                        "前": (2, 1.0), "后": (2, -1.0),
                    }
                    _matched_dir = None
                    for _dw, (_ax, _sgn) in _dir_map.items():
                        if _dw in msg_lower:
                            _matched_dir = (_ax, _sgn, _dw)
                            break
                    if _matched_dir:
                        _ax, _sgn, _dw = _matched_dir
                        # Check for explicit distance: "move up 2", "move up 2.5"
                        _dist_match = re.search(r'(?:up|down|left|right|forward|back)\s*(\d+(?:\.\d+)?)', msg_lower)
                        _step = float(_dist_match.group(1)) if _dist_match else 1.0
                        _delta = _sgn * _step
                        current_obj = next(
                            (o for o in scene_objects if o.get("name") == target_name), None
                        )
                        if current_obj:
                            cur = current_obj.get("transform", {}).get("position", [0, 0, 0])
                            new_vals = list(cur)
                        else:
                            new_vals = [0, 0, 0]
                        new_vals[_ax] = round(new_vals[_ax] + _delta, 3)
                        intents.append(ParsedIntent(
                            tool_name="transform_object",
                            arguments={"target": target_name, "position": new_vals},
                            description=f"Move {target_name} {_dw} by {_step}",
                        ))
                        matched_any = True
                # Fallback for relative scale changes without explicit
                # numbers — e.g. "make the cube bigger", "shrink the
                # sphere". Apply a sensible default factor so the offline
                # engine still responds.
                if not matched_any and is_scale:
                    grow = any(v in msg_lower for v in [
                        "bigger", "larger", "enlarge", "grow", "放大",
                    ])
                    factor = 1.5 if grow else 0.5
                    current_obj = next(
                        (o for o in scene_objects if o.get("name") == target_name), None
                    )
                    if current_obj:
                        cur = current_obj.get("transform", {}).get("scale", [1, 1, 1])
                        new_vals = [round(c * factor, 3) for c in cur]
                    else:
                        new_vals = [factor, factor, factor]
                    intents.append(ParsedIntent(
                        tool_name="transform_object",
                        arguments={"target": target_name, "scale": new_vals},
                        description=f"Scale {target_name} by {factor}x",
                    ))
                    matched_any = True

    # 4. Apply material (also triggers when a material preset keyword is
    # detected even without an explicit "material"/"color" word — e.g.
    # "make the sphere metallic" reaches here because section 2 skipped
    # creation when the preset targets an existing object). Also triggers
    # when a color targets an existing object — e.g. "make the cube gold"
    # — because section 2 skipped creation via _color_targets_existing.
    if not matched_any and (
        any(w in msg_lower for w in ["material", "color", "paint", "材质", "颜色", "涂", "上色"])
        or detected_preset is not None
        or _color_targets_existing
    ) and scene_objects:
        target_name = _find_target_name(msg_lower, scene_objects)
        # Default to the most recent object when a preset/material/color
        # keyword is detected but no specific target is mentioned.
        if not target_name and (detected_preset or _color_targets_existing) and scene_objects:
            target_name = scene_objects[-1].get("name", "")
        if target_name:
            if detected_preset:
                intents.append(ParsedIntent(
                    tool_name="apply_material_preset",
                    arguments={"target": target_name, "preset": detected_preset},
                    description=f"Apply {detected_preset} preset to {target_name}",
                ))
                matched_any = True
            elif detected_color:
                intents.append(ParsedIntent(
                    tool_name="apply_material",
                    arguments={"target": target_name, "color": detected_color},
                    description=f"Apply color to {target_name}",
                ))
                matched_any = True

    # 5. Light management
    if any(w in msg_lower for w in ["light", "灯光", "光源", "add light", "add a light"]):
        if any(w in msg_lower for w in ["delete", "remove", "删除", "去掉"]):
            # Delete light
            target_light = None
            for light in scene_lights:
                name = light.get("name", "")
                if name.lower() in msg_lower or light.get("type", "") in msg_lower:
                    target_light = name
                    break
            if target_light:
                intents.append(ParsedIntent(
                    tool_name="delete_light",
                    arguments={"target": target_light},
                    description=f"Delete light {target_light}",
                ))
                matched_any = True
        else:
            # Add light
            light_type = "directional"
            for kw, lt in LIGHT_TYPE_MAP.items():
                if kw in msg_lower:
                    light_type = lt
                    break
            args: Dict[str, Any] = {"light_type": light_type}
            if detected_color:
                args["color"] = detected_color
            intents.append(ParsedIntent(
                tool_name="add_light",
                arguments=args,
                description=f"Add {light_type} light",
            ))
            matched_any = True

    # 6. Delete object
    if any(w in msg_lower for w in ["delete", "remove", "删除", "去掉", "remove object"]) and scene_objects:
        if not any(w in msg_lower for w in ["light", "灯光"]):
            target_name = _find_target_name(msg_lower, scene_objects)
            if target_name:
                intents.append(ParsedIntent(
                    tool_name="delete_object",
                    arguments={"target": target_name},
                    description=f"Delete {target_name}",
                ))
                matched_any = True

    # 7. Duplicate object
    if not matched_any and any(w in msg_lower for w in ["duplicate", "copy", "复制", "副本"]) and scene_objects:
        target_name = _find_target_name(msg_lower, scene_objects)
        if target_name:
            count_match = re.search(r'(\d+)\s*(?:copies|份|个)', msg_lower)
            count = int(count_match.group(1)) if count_match else 1
            intents.append(ParsedIntent(
                tool_name="duplicate_object",
                arguments={"target": target_name, "count": count},
                description=f"Duplicate {target_name}",
            ))
            matched_any = True

    # 8. Focus / select
    if any(w in msg_lower for w in ["focus", "zoom to", "look at", "聚焦", "对准"]) and scene_objects:
        target_name = _find_target_name(msg_lower, scene_objects)
        if target_name:
            intents.append(ParsedIntent(
                tool_name="focus_object",
                arguments={"target": target_name},
                description=f"Focus on {target_name}",
            ))
            matched_any = True

    # Zoom in/out — "zoom in" focuses on the first scene object (moves
    # the camera closer), "zoom out" frames all objects (pulls the
    # camera back to see the whole scene).
    if "zoom in" in msg_lower or "放大视图" in msg_lower:
        if scene_objects:
            _zoom_target = _find_target_name(msg_lower, scene_objects) or scene_objects[0].get("name", "")
            if _zoom_target:
                intents.append(ParsedIntent(
                    tool_name="focus_object",
                    arguments={"target": _zoom_target},
                    description=f"Zoom in on {_zoom_target}",
                ))
                matched_any = True
    if "zoom out" in msg_lower or "缩小视图" in msg_lower:
        intents.append(ParsedIntent(
            tool_name="frame_view",
            arguments={},
            description="Zoom out — frame all",
        ))
        matched_any = True

    if any(w in msg_lower for w in ["select", "选择", "选中"]) and scene_objects:
        target_name = _find_target_name(msg_lower, scene_objects)
        if target_name:
            intents.append(ParsedIntent(
                tool_name="select_object",
                arguments={"target": target_name},
                description=f"Select {target_name}",
            ))
            matched_any = True

    # 9. Group / ungroup
    if any(w in msg_lower for w in ["group", "组合", "编组"]) and len(scene_objects) >= 2:
        group_name_match = re.search(r'(?:group|组合|编组)\s+(?:as|为)?\s*["\']?(\w+)["\']?', msg_lower)
        group_name = group_name_match.group(1) if group_name_match else "Group"
        targets = [o.get("name", "") for o in scene_objects]
        intents.append(ParsedIntent(
            tool_name="group_objects",
            arguments={"targets": targets, "name": group_name},
            description=f"Group all objects as {group_name}",
        ))
        matched_any = True

    if any(w in msg_lower for w in ["ungroup", "解散", "拆分"]) and scene_objects:
        intents.append(ParsedIntent(
            tool_name="ungroup_objects",
            arguments={"target": "all"},
            description="Ungroup all groups",
        ))
        matched_any = True

    # 10. Background
    if any(w in msg_lower for w in ["background", "背景"]):
        color = _find_color(msg_lower)
        if color:
            intents.append(ParsedIntent(
                tool_name="set_background",
                arguments={"color": color},
                description=f"Set background to {color}",
            ))
            matched_any = True

    # 11. Fog
    if any(w in msg_lower for w in ["fog", "雾", "雾效"]):
        if any(w in msg_lower for w in ["off", "disable", "remove", "关掉", "取消"]):
            intents.append(ParsedIntent(
                tool_name="set_fog",
                arguments={"enabled": False},
                description="Disable fog",
            ))
            matched_any = True
        else:
            fog_color = _find_color(msg_lower) or "#050505"
            near_match = re.search(r'near\s*(\d+(?:\.\d+)?)', msg_lower)
            far_match = re.search(r'far\s*(\d+(?:\.\d+)?)', msg_lower)
            args: Dict[str, Any] = {"enabled": True, "color": fog_color}
            if near_match:
                args["near"] = float(near_match.group(1))
            if far_match:
                args["far"] = float(far_match.group(1))
            intents.append(ParsedIntent(
                tool_name="set_fog",
                arguments=args,
                description="Configure fog",
            ))
            matched_any = True

    # 11b. Global gravity
    if not matched_any and any(k in msg_lower for k in ("gravity", "重力", "set gravity", "global gravity")):
        gravity = 9.8
        if any(k in msg_lower for k in ("moon", "月球", "低重力", "low gravity", "weak gravity")):
            gravity = 1.6
        elif any(k in msg_lower for k in ("zero", "float", "no gravity", "零重力", "无重力", "漂浮", "飘")):
            gravity = 0.0
        elif any(k in msg_lower for k in ("heavy", "strong", "高重力", "大重力")):
            gravity = 20.0
        else:
            m = re.search(r'gravity\s*[:=\s]\s*(\d+(?:\.\d+)?)', msg_lower)
            if m:
                try:
                    gravity = float(m.group(1))
                except ValueError:
                    pass
            else:
                m2 = re.search(r'(\d+(?:\.\d+)?)\s*(?:m/s|重力|gravity)', msg_lower)
                if m2:
                    try:
                        gravity = float(m2.group(1))
                    except ValueError:
                        pass
        intents.append(ParsedIntent(
            tool_name="set_global_gravity",
            arguments={"gravity": gravity},
            description=f"Set global gravity to {gravity}",
        ))
        matched_any = True

    # 11c. Scene environment preset
    if not matched_any:
        env_keywords = [
            ("sunset", "sunset"), ("sun set", "sunset"),
            ("日落", "sunset"), ("夕阳", "sunset"),
            ("night", "night"), ("夜间", "night"), ("夜晚", "night"), ("深夜", "night"),
            ("winter", "winter"), ("冬天", "winter"), ("冬季", "winter"), ("雪天", "winter"),
            ("ocean", "ocean"), ("海洋", "ocean"), ("大海", "ocean"),
            ("forest", "forest"), ("森林", "forest"), ("树林", "forest"),
            ("rain", "rainy"), ("rainy", "rainy"), ("下雨", "rainy"), ("雨天", "rainy"), ("阴雨天", "rainy"),
            ("dawn", "dawn"), ("黎明", "dawn"), ("清晨", "dawn"), ("日出", "dawn"),
            ("cave", "cave"), ("洞穴", "cave"), ("山洞", "cave"), ("地下", "cave"),
            ("underwater", "underwater"), ("水下", "underwater"), ("海底", "underwater"), ("水中", "underwater"),
            ("beach", "beach"), ("沙滩", "beach"), ("海滩", "beach"), ("海边", "beach"),
            ("default", "default"), ("reset scene", "default"), ("重置场景", "default"), ("默认", "default"),
        ]
        for kw, preset in env_keywords:
            if kw in msg_lower:
                # Avoid double-match if the phrase has already been handled by
                # scene composition patterns (which produce more detailed results).
                if not matched_any:
                    intents.append(ParsedIntent(
                        tool_name="set_scene_environment",
                        arguments={"preset": preset},
                        description=f"Apply scene environment preset '{preset}'",
                    ))
                    matched_any = True
                break

    # 12. Arrange layout
    if not matched_any and any(w in msg_lower for w in ["arrange", "layout", "排列", "排布", "布局"]):
        layout_type = "grid"
        if any(w in msg_lower for w in ["circle", "圆形", "环形"]):
            layout_type = "circle"
        elif any(w in msg_lower for w in ["linear", "line", "row", "线性", "一排"]):
            layout_type = "linear"
        intents.append(ParsedIntent(
            tool_name="arrange_layout",
            arguments={"layout_type": layout_type},
            description=f"Arrange objects in {layout_type} layout",
        ))
        matched_any = True

    # 13. Export
    export_match = re.search(r'\b(export|glb|gltf|obj|stl|save as|save|导出|保存)\b', msg_lower)
    if export_match:
        fmt = "glb"
        if re.search(r'\bobj\b', msg_lower):
            fmt = "obj"
        elif re.search(r'\bstl\b', msg_lower):
            fmt = "stl"
        elif re.search(r'\bgltf\b', msg_lower):
            fmt = "gltf"
        intents.append(ParsedIntent(
            tool_name="export_scene",
            arguments={"format": fmt},
            description=f"Export scene as {fmt.upper()}",
        ))
        matched_any = True

    # 14. List objects
    if any(k in msg_lower for k in ["list", "查看", "有哪些", "show all"]) and "info" not in msg_lower:
        intents.append(ParsedIntent(
            tool_name="list_objects",
            arguments={},
            description="List all objects",
        ))
        matched_any = True

    # 15. Scene info
    if any(k in msg_lower for k in ["scene info", "scene summary", "statistics", "inspect", "场景信息", "统计"]):
        intents.append(ParsedIntent(
            tool_name="scene_info",
            arguments={},
            description="Get scene info",
        ))
        matched_any = True

    # 16. View switching
    if any(k in msg_lower for k in ["viewport", "view", "camera view", "视图"]):
        for kw, view_name in VIEW_MAP.items():
            if kw in msg_lower:
                intents.append(ParsedIntent(
                    tool_name="set_view",
                    arguments={"view": view_name},
                    description=f"Switch to {view_name} view",
                ))
                matched_any = True
                break

    # 17. Grid control
    if any(k in msg_lower for k in ["toggle grid", "toggle the grid", "grid on", "grid off", "show grid", "hide grid", "网格"]):
        visible = None
        if any(k in msg_lower for k in ["grid off", "hide grid", "关闭网格", "隐藏网格"]):
            visible = False
        elif any(k in msg_lower for k in ["grid on", "show grid", "打开网格", "显示网格"]):
            visible = True
        args = {} if visible is None else {"visible": visible}
        intents.append(ParsedIntent(
            tool_name="toggle_grid",
            arguments=args,
            description="Toggle grid",
        ))
        matched_any = True

    if "grid size" in msg_lower:
        size_match = re.search(r'grid size\s*(\d+(?:\.\d+)?)', msg_lower)
        if size_match:
            intents.append(ParsedIntent(
                tool_name="set_grid_size",
                arguments={"size": float(size_match.group(1))},
                description=f"Set grid size to {size_match.group(1)}",
                emit_tool_call=False,
            ))
            matched_any = True

    # Post FX patterns — bloom, color grading, vignette, grain, depth of field.
    # Maps natural-language phrases (including Chinese) to the apply_post_fx tool
    # with sensible defaults for each look preset.
    if not matched_any:
        _fx_args: Dict[str, Any] = {}
        _fx_desc_parts: List[str] = []

        if "bloom on" in msg_lower or "bloom effect" in msg_lower or "bloom" in msg_lower:
            _fx_args["bloom"] = True
            _fx_desc_parts.append("enable bloom")
        if "bloom off" in msg_lower or "no bloom" in msg_lower or "disable bloom" in msg_lower:
            _fx_args["bloom"] = False
            _fx_desc_parts.append("disable bloom")
        if "vignette" in msg_lower or "加暗角" in msg_lower:
            _fx_args["vignette"] = True
            _fx_desc_parts.append("vignette")
        if "grain" in msg_lower or "胶片颗粒" in msg_lower:
            _fx_args["grain"] = 0.05
            _fx_desc_parts.append("film grain")
        if "depth of field" in msg_lower or "dof" in msg_lower:
            _fx_args["depth_of_field"] = True
            _fx_desc_parts.append("depth of field")

        if "cinematic look" in msg_lower or "cinematic" in msg_lower or "加电影效果" in msg_lower:
            _fx_args["color_grading"] = "cinematic"
            _fx_args["bloom"] = True
            _fx_args["vignette"] = True
            _fx_args["grain"] = 0.03
            _fx_desc_parts = ["cinematic look (color grading, bloom, vignette, subtle grain)"]
        elif "noir look" in msg_lower or "noir" in msg_lower:
            _fx_args["color_grading"] = "noir"
            _fx_args["bloom"] = False
            _fx_args["vignette"] = True
            _fx_args["grain"] = 0.08
            _fx_desc_parts = ["noir look (desaturated grading, vignette, heavy grain)"]
        elif "warm look" in msg_lower or "warm tone" in msg_lower:
            _fx_args["color_grading"] = "warm"
            _fx_desc_parts.append("warm color grading")
        elif "cool look" in msg_lower or "cool tone" in msg_lower:
            _fx_args["color_grading"] = "cool"
            _fx_desc_parts.append("cool color grading")

        if _fx_args:
            intents.append(ParsedIntent(
                tool_name="apply_post_fx",
                arguments=_fx_args,
                description=f"Apply post FX: {', '.join(_fx_desc_parts) or 'custom'}",
            ))
            matched_any = True

    # Viewport & editor-state control — minimap, shadows, projection,
    # edit/run mode, scene save/load slots. Each rule mirrors a tool in
    # advanced_editor_tools.py.
    if any(k in msg_lower for k in ["minimap", "小地图"]):
        enabled = not any(k in msg_lower for k in ["off", "hide", "disable", "关闭", "隐藏"])
        intents.append(ParsedIntent(
            tool_name="set_minimap",
            arguments={"enabled": enabled},
            description=f"{'Show' if enabled else 'Hide'} minimap",
        ))
        matched_any = True

    if any(k in msg_lower for k in ["shadow", "阴影"]) and not any(
        k in msg_lower for k in ["shadow map", "阴影贴图"]
    ):
        # Treat "shadows" as viewport shadow rendering. "off/disable/关掉"
        # flips to false; any other mention (on/enable/打开) flips to true.
        enabled = not any(k in msg_lower for k in ["off", "disable", "关掉", "关闭", "隐藏阴影", "无阴影"])
        intents.append(ParsedIntent(
            tool_name="set_shadows",
            arguments={"enabled": enabled},
            description=f"{'Enable' if enabled else 'Disable'} shadows",
        ))
        matched_any = True

    if any(k in msg_lower for k in ["orthographic", "正交", "2d view", "2d mode"]):
        intents.append(ParsedIntent(
            tool_name="set_viewport_projection",
            arguments={"mode": "orthographic"},
            description="Switch viewport to orthographic projection",
        ))
        matched_any = True
    elif any(k in msg_lower for k in ["perspective view", "perspective mode", "透视视图", "透视模式"]) and \
        "set_view" not in msg_lower:
        # Only route to projection when the user explicitly asks for the
        # projection mode, not the named "perspective" view preset (which
        # set_view already handles above via VIEW_MAP).
        intents.append(ParsedIntent(
            tool_name="set_viewport_projection",
            arguments={"mode": "perspective"},
            description="Switch viewport to perspective projection",
        ))
        matched_any = True

    if any(k in msg_lower for k in ["edit mode", "editing mode", "编辑模式"]):
        intents.append(ParsedIntent(
            tool_name="set_editor_mode",
            arguments={"mode": "edit"},
            description="Enter edit mode",
        ))
        matched_any = True
    elif any(k in msg_lower for k in ["run mode", "preview mode", "play mode", "运行模式", "预览模式", "播放模式"]):
        intents.append(ParsedIntent(
            tool_name="set_editor_mode",
            arguments={"mode": "run"},
            description="Enter run/preview mode",
        ))
        matched_any = True

    # Viewport shading modes — wireframe / solid / material / rendered.
    # Matches phrases like "switch to wireframe", "solid mode", "material
    # view", "rendered shading", "线框模式".
    if any(k in msg_lower for k in ["wireframe mode", "wireframe view", "wireframe shading", "线框模式", "线框视图"]):
        intents.append(ParsedIntent(
            tool_name="set_viewport_shading",
            arguments={"mode": "wireframe"},
            description="Switch viewport to wireframe shading",
        ))
        matched_any = True
    elif any(k in msg_lower for k in ["solid mode", "solid view", "solid shading", "实体模式", "实体视图"]):
        intents.append(ParsedIntent(
            tool_name="set_viewport_shading",
            arguments={"mode": "solid"},
            description="Switch viewport to solid shading",
        ))
        matched_any = True
    elif any(k in msg_lower for k in ["material mode", "material view", "material shading", "材质模式", "材质视图"]):
        intents.append(ParsedIntent(
            tool_name="set_viewport_shading",
            arguments={"mode": "material"},
            description="Switch viewport to material shading",
        ))
        matched_any = True
    elif any(k in msg_lower for k in ["rendered mode", "rendered view", "rendered shading", "渲染模式", "渲染视图"]):
        intents.append(ParsedIntent(
            tool_name="set_viewport_shading",
            arguments={"mode": "rendered"},
            description="Switch viewport to rendered shading",
        ))
        matched_any = True

    # Viewport control gap tools — X-ray see-through mode, selection
    # highlight color, bulk snap-to-ground, and granular render scale.
    # Mirror the set_xray_mode / set_selection_color /
    # snap_selection_to_ground / set_viewport_resolution tools.
    if any(k in msg_lower for k in [
        "x-ray", "xray", "see through", "see-through", "see thru",
        "透视模式", "穿透显示", "穿透模式",
    ]):
        _xray_enabled = not any(k in msg_lower for k in ["off", "disable", "关闭", "关闭透视"])
        _xray_opacity = _parse_number_after(msg_lower, "opacity")
        _xray_args: Dict[str, Any] = {"enabled": _xray_enabled}
        if _xray_opacity is not None:
            _xray_args["opacity"] = _xray_opacity
        intents.append(ParsedIntent(
            tool_name="set_xray_mode",
            arguments=_xray_args,
            description=f"{'Enable' if _xray_enabled else 'Disable'} X-ray viewport mode",
        ))
        matched_any = True

    if any(k in msg_lower for k in [
        "selection color", "highlight color", "selection highlight",
        "outline color", "选择颜色", "高亮颜色", "选中颜色",
    ]):
        _sel_color = detected_color or "#00F0FF"
        intents.append(ParsedIntent(
            tool_name="set_selection_color",
            arguments={"color": _sel_color},
            description=f"Set selection highlight color to {_sel_color}",
        ))
        matched_any = True

    if any(k in msg_lower for k in [
        "snap to ground", "snap selection to ground", "ground selection",
        "drop to floor", "drop selection", "ground all",
        "贴地", "落地", "吸附到地面",
    ]):
        _ground_targets: List[str] = []
        if scene_objects:
            _ground_t = _find_target_name(msg_lower, scene_objects)
            if _ground_t:
                _ground_targets = [_ground_t]
        _ground_floor = _parse_number_after(msg_lower, "floor")
        _ground_args: Dict[str, Any] = {}
        if _ground_targets:
            _ground_args["targets"] = _ground_targets
        if _ground_floor is not None:
            _ground_args["floor"] = _ground_floor
        intents.append(ParsedIntent(
            tool_name="snap_selection_to_ground",
            arguments=_ground_args,
            description=f"Snap selection to ground ({_ground_args or 'defaults'})",
        ))
        matched_any = True

    if any(k in msg_lower for k in [
        "viewport resolution", "render scale", "viewport scale",
        "渲染分辨率", "渲染缩放", "视口分辨率",
    ]):
        _vp_scale = _parse_number_after(msg_lower, "scale")
        if _vp_scale is None:
            _vp_scale = 1.0
        intents.append(ParsedIntent(
            tool_name="set_viewport_resolution",
            arguments={"scale": _vp_scale},
            description=f"Set viewport render scale to {_vp_scale}x",
        ))
        matched_any = True

    # Curve / path creation — "create a curve", "draw a path", "make a
    # bezier curve". Parses point coordinates if provided, otherwise
    # defaults to a gentle S-curve.
    if any(k in msg_lower for k in ["create a curve", "draw a curve", "make a curve", "bezier", "创建曲线", "画一条曲线", "路径"]):
        _curve_points: List[List[float]] = []
        _pt_matches = re.findall(r'\[?\s*(-?\d+\.?\d*)\s*,\s*(-?\d+\.?\d*)\s*,\s*(-?\d+\.?\d*)\s*\]?', msg_lower)
        for mx, my, mz in _pt_matches[:10]:
            _curve_points.append([float(mx), float(my), float(mz)])
        if not _curve_points:
            # Default S-curve when no explicit points are given
            _curve_points = [[-2, 0, 0], [-1, 1, 0], [1, -1, 0], [2, 0, 0]]
        _curve_closed = any(k in msg_lower for k in ["closed", "闭合", "封闭"])
        intents.append(ParsedIntent(
            tool_name="create_curve",
            arguments={
                "points": _curve_points,
                "name": "Curve",
                "closed": _curve_closed,
                "color": detected_color or "#ffffff",
            },
            description=f"Create a {'closed ' if _curve_closed else ''}curve with {len(_curve_points)} points",
        ))
        matched_any = True

    # Batch object creation — "create 5 cubes", "make 3 spheres and 2
    # cylinders", "add 10 random objects". Parses count + geometry type.
    if not matched_any:
        _batch_match = re.search(
            r'(?:create|make|add|generate|生成|创建|添加)\s+(\d+)\s+(?:random\s+)?(?:objects|things|cubes|spheres|cylinders|cones|torus|boxes|球|立方体|圆柱)',
            msg_lower,
        )
        if _batch_match:
            _count = min(int(_batch_match.group(1)), 50)  # cap at 50
            _batch_type = "box"  # default
            for _kw, _geo in GEO_MAP.items():
                if _kw in msg_lower:
                    _batch_type = _geo
                    break
            _batch_specs: List[Dict[str, Any]] = []
            import random as _rng
            for _i in range(_count):
                _x = round(_rng.uniform(-5, 5), 2)
                _z = round(_rng.uniform(-5, 5), 2)
                _y = round(_rng.uniform(0, 3), 2)
                _batch_specs.append({
                    "geometry_type": _batch_type,
                    "name": f"Batch_{_batch_type}_{_i}",
                    "position": [_x, _y, _z],
                    "color": random.choice(list(COLOR_MAP.values())) if COLOR_MAP else "#cccccc",
                })
            intents.append(ParsedIntent(
                tool_name="batch_create_objects",
                arguments={"objects": _batch_specs},
                description=f"Batch create {_count} {_batch_type} objects",
            ))
            matched_any = True

    # Material texture mapping — "checker texture", "noise pattern",
    # "brick texture on the cube".
    if any(k in msg_lower for k in ["checker texture", "checker pattern", "棋盘纹理"]):
        _tex_target = _find_target_name(msg_lower, scene_objects) if scene_objects else None
        intents.append(ParsedIntent(
            tool_name="set_material_texture",
            arguments={"target": _tex_target or "", "texture_type": "checker", "scale": 1.0},
            description=f"Apply checker texture to {_tex_target or 'selection'}",
        ))
        matched_any = True
    elif any(k in msg_lower for k in ["noise texture", "noise pattern", "噪声纹理"]):
        _tex_target = _find_target_name(msg_lower, scene_objects) if scene_objects else None
        intents.append(ParsedIntent(
            tool_name="set_material_texture",
            arguments={"target": _tex_target or "", "texture_type": "noise", "scale": 1.0},
            description=f"Apply noise texture to {_tex_target or 'selection'}",
        ))
        matched_any = True
    elif any(k in msg_lower for k in ["brick texture", "brick pattern", "砖块纹理"]):
        _tex_target = _find_target_name(msg_lower, scene_objects) if scene_objects else None
        intents.append(ParsedIntent(
            tool_name="set_material_texture",
            arguments={"target": _tex_target or "", "texture_type": "brick", "scale": 1.0},
            description=f"Apply brick texture to {_tex_target or 'selection'}",
        ))
        matched_any = True
    elif any(k in msg_lower for k in ["grid texture", "grid pattern", "网格纹理"]):
        _tex_target = _find_target_name(msg_lower, scene_objects) if scene_objects else None
        intents.append(ParsedIntent(
            tool_name="set_material_texture",
            arguments={"target": _tex_target or "", "texture_type": "grid", "scale": 1.0},
            description=f"Apply grid texture to {_tex_target or 'selection'}",
        ))
        matched_any = True

    # Viewport background — "gradient background", "skybox background".
    if any(k in msg_lower for k in ["gradient background", "渐变背景"]):
        intents.append(ParsedIntent(
            tool_name="set_viewport_background",
            arguments={"type": "gradient", "top_color": "#1a1a2e", "bottom_color": "#e94560"},
            description="Set gradient viewport background",
        ))
        matched_any = True
    elif any(k in msg_lower for k in ["skybox background", "skybox", "天空盒"]):
        intents.append(ParsedIntent(
            tool_name="set_viewport_background",
            arguments={"type": "skybox"},
            description="Set skybox viewport background",
        ))
        matched_any = True

    # Scene save/load slots. Matches phrases like "save scene as my-design",
    # "load scene my-design", "保存场景为xxx", "加载场景xxx".
    save_slot_match = re.search(
        r'(?:save scene(?:\s+as|\s+to)?|snapshot scene(?:\s+as|\s+to)?)\s+["\']?([\w\-]+)["\']?',
        msg_lower,
    )
    if save_slot_match:
        intents.append(ParsedIntent(
            tool_name="save_scene_slot",
            arguments={"slot": save_slot_match.group(1)},
            description=f"Save scene to slot '{save_slot_match.group(1)}'",
        ))
        matched_any = True
    else:
        cn_save_match = re.search(r'(?:保存场景|存储场景)(?:\s*为|\s*)\s*["\']?([\w\-]+)["\']?', msg)
        if cn_save_match:
            intents.append(ParsedIntent(
                tool_name="save_scene_slot",
                arguments={"slot": cn_save_match.group(1)},
                description=f"Save scene to slot '{cn_save_match.group(1)}'",
            ))
            matched_any = True

    load_slot_match = re.search(
        r'(?:load scene(?:\s+from)?|restore scene(?:\s+from)?)\s+["\']?([\w\-]+)["\']?',
        msg_lower,
    )
    if load_slot_match:
        clear_scene = not any(k in msg_lower for k in ["merge", "add", "合并", "追加"])
        intents.append(ParsedIntent(
            tool_name="load_scene_slot",
            arguments={"slot": load_slot_match.group(1), "clear_scene": clear_scene},
            description=f"Load scene from slot '{load_slot_match.group(1)}'",
        ))
        matched_any = True
    else:
        cn_load_match = re.search(r'(?:加载场景|读取场景|恢复场景)(?:\s*为|\s*从)?\s*["\']?([\w\-]+)["\']?', msg)
        if cn_load_match:
            clear_scene = not any(k in msg_lower for k in ["merge", "add", "合并", "追加"])
            intents.append(ParsedIntent(
                tool_name="load_scene_slot",
                arguments={"slot": cn_load_match.group(1), "clear_scene": clear_scene},
                description=f"Load scene from slot '{cn_load_match.group(1)}'",
            ))
            matched_any = True

    # 17b-2. orbit_viewport — turntable orbit of the viewport camera
    # around the origin or a named target. Triggered by phrases like
    # "orbit viewport", "rotate camera around", "turntable". Set stop=true
    # when the user says "stop orbit".
    if any(k in msg_lower for k in [
        "stop orbit", "stop the orbit", "end orbit", "stop turntable",
        "停止环绕", "停止旋转视角",
    ]):
        intents.append(ParsedIntent(
            tool_name="orbit_viewport",
            arguments={"stop": True},
            description="Stop the active viewport orbit",
            emit_tool_call=False,
        ))
        matched_any = True
    elif any(k in msg_lower for k in [
        "orbit viewport", "orbit camera", "orbit around", "orbit scene",
        "turntable", "turntable view", "rotate camera around",
        "auto orbit", "auto-rotate camera", "auto rotate camera",
        "环绕视角", "环绕摄像机", "环绕相机", "旋转视角", "自动旋转视角", "转盘视图",
    ]):
        _orbit_args: Dict[str, Any] = {}
        # Pick up the radius / speed / duration / height from the message.
        _orbit_radius = _parse_number_after(msg_lower, "radius")
        if _orbit_radius is not None:
            _orbit_args["radius"] = _orbit_radius
        _orbit_speed = _parse_number_after(msg_lower, "speed")
        if _orbit_speed is not None:
            _orbit_args["speed"] = _orbit_speed
        _orbit_duration = _parse_number_after(msg_lower, "duration")
        if _orbit_duration is not None:
            _orbit_args["duration"] = _orbit_duration
        _orbit_height = _parse_number_after(msg_lower, "height")
        if _orbit_height is not None:
            _orbit_args["height"] = _orbit_height
        # Optional target — "orbit around <name>" or "orbit <name>"
        if scene_objects:
            _orbit_target = _find_target_name(msg_lower, scene_objects)
            if _orbit_target:
                _orbit_args["target"] = _orbit_target
        intents.append(ParsedIntent(
            tool_name="orbit_viewport",
            arguments=_orbit_args,
            description=f"Start viewport orbit ({_orbit_args or 'defaults'})",
        ))
        matched_any = True

    # 17b-3. set_layer_visibility — show/hide every object on a named
    # layer in one call. Triggered by "hide layer X", "show layer X",
    # "隐藏层 X", "显示层 X". Distinct from per-object set_visibility
    # (single object) and set_object_layer (assigns a single object to a
    # layer then optionally toggles).
    _layer_vis_match = re.search(
        r'(?:hide|show|toggle)\s+(?:the\s+)?(?:layer|层)\s+["\']?([A-Za-z0-9_\-一-龥]+)["\']?',
        msg_lower,
    )
    if _layer_vis_match:
        _lv_layer = _layer_vis_match.group(1)
        _lv_visible = "show" in msg_lower or "显示" in msg
        intents.append(ParsedIntent(
            tool_name="set_layer_visibility",
            arguments={"layer": _lv_layer, "visible": _lv_visible},
            description=f"Set layer '{_lv_layer}' visibility to {_lv_visible}",
        ))
        matched_any = True
    else:
        _layer_vis_zh = re.search(r'(?:隐藏|显示|切换)\s*(?:层|图层)\s*["\']?([A-Za-z0-9_\-一-龥]+)["\']?', msg)
        if _layer_vis_zh:
            _lv_layer = _layer_vis_zh.group(1)
            _lv_visible = "显示" in msg
            intents.append(ParsedIntent(
                tool_name="set_layer_visibility",
                arguments={"layer": _lv_layer, "visible": _lv_visible},
                description=f"Set layer '{_lv_layer}' visibility to {_lv_visible}",
            ))
            matched_any = True

    # Extended editor & spatial control — playback, transform, selection,
    # snapping, camera, layers/groups, material, geometry, subagent, and
    # more. Each rule maps CN+EN phrases to a registered tool so the offline
    # rule engine can drive every editor capability without an LLM round-trip.
    #
    # Undo / redo — checked before generic "select"/"delete" so the
    # short keywords are not swallowed by later sections.
    if any(k in msg_lower for k in ["undo", "撤销"]) and not any(
        k in msg_lower for k in ["undo object", "撤销对象"]
    ):
        intents.append(ParsedIntent(
            tool_name="undo_scene",
            arguments={},
            description="Undo last scene change",
            emit_tool_call=False,
        ))
        matched_any = True
    if any(k in msg_lower for k in ["redo", "重做", "恢复"]):
        intents.append(ParsedIntent(
            tool_name="redo_scene",
            arguments={},
            description="Redo last undone change",
            emit_tool_call=False,
        ))
        matched_any = True

    # Playback control
    if any(k in msg_lower for k in ["play animation", "play back", "播放动画", "开始播放"]):
        intents.append(ParsedIntent(
            tool_name="play_animation",
            arguments={},
            description="Play animation",
            emit_tool_call=False,
        ))
        matched_any = True
    if any(k in msg_lower for k in ["pause animation", "pause playback", "暂停动画", "暂停播放"]):
        intents.append(ParsedIntent(
            tool_name="pause_animation",
            arguments={},
            description="Pause animation",
            emit_tool_call=False,
        ))
        matched_any = True
    seek_m = re.search(r'(?:seek to|go to frame|jump to)\s*(\d+(?:\.\d+)?)', msg_lower)
    if seek_m or any(k in msg_lower for k in ["seek", "跳转", "进度"]):
        t = float(seek_m.group(1)) if seek_m else 0.0
        intents.append(ParsedIntent(
            tool_name="seek_animation",
            arguments={"time": t},
            description=f"Seek to {t}s",
            emit_tool_call=False,
        ))
        matched_any = True
    speed_m = re.search(r'(?:playback speed|speed|速度)\s*(\d+(?:\.\d+)?)', msg_lower)
    if speed_m:
        intents.append(ParsedIntent(
            tool_name="set_playback_speed",
            arguments={"speed": float(speed_m.group(1))},
            description=f"Set playback speed to {speed_m.group(1)}",
            emit_tool_call=False,
        ))
        matched_any = True

    # Render quality
    if any(k in msg_lower for k in ["render quality", "渲染质量"]):
        q = "high"
        if "low" in msg_lower or "低" in msg_lower:
            q = "low"
        elif "medium" in msg_lower or "中" in msg_lower:
            q = "medium"
        elif "high" in msg_lower or "高" in msg_lower:
            q = "high"
        intents.append(ParsedIntent(
            tool_name="set_render_quality",
            arguments={"quality": q},
            description=f"Set render quality to {q}",
        ))
        matched_any = True

    # Grid snapping
    if any(k in msg_lower for k in ["grid snap", "snap to grid", "snapping", "网格吸附", "吸附网格"]):
        enabled = not any(k in msg_lower for k in ["off", "disable", "关闭", "取消"])
        inc_m = re.search(r'(?:increment|step|步长)\s*(\d+(?:\.\d+)?)', msg_lower)
        args: Dict[str, Any] = {"enabled": enabled}
        if inc_m:
            args["increment"] = float(inc_m.group(1))
        intents.append(ParsedIntent(
            tool_name="toggle_grid_snapping",
            arguments=args,
            description=f"{'Enable' if enabled else 'Disable'} grid snapping",
        ))
        matched_any = True

    # Panel focus
    panel_m = re.search(
        r'(?:focus panel|show panel|open panel|switch panel|打开面板|切换面板)\s*["\']?(\w+)["\']?',
        msg_lower,
    )
    if panel_m:
        intents.append(ParsedIntent(
            tool_name="focus_panel",
            arguments={"panel": panel_m.group(1)},
            description=f"Focus panel {panel_m.group(1)}",
            emit_tool_call=False,
        ))
        matched_any = True

    # Frame view
    if any(k in msg_lower for k in ["frame view", "frame all", "fit view", "fit to view", "全选视图", "适配视图", "框选全部"]):
        intents.append(ParsedIntent(
            tool_name="frame_view",
            arguments={},
            description="Frame all objects in view",
            emit_tool_call=False,
        ))
        matched_any = True

    # Capture viewport
    if any(k in msg_lower for k in ["capture viewport", "screenshot", "截图", "截屏"]):
        fn_m = re.search(r'(?:as|save as|保存为)\s*["\']?([\w\-]+)["\']?', msg_lower)
        args: Dict[str, Any] = {}
        if fn_m:
            args["filename"] = fn_m.group(1)
        intents.append(ParsedIntent(
            tool_name="capture_viewport",
            arguments=args,
            description="Capture viewport screenshot",
            emit_tool_call=False,
        ))
        matched_any = True

    # Visibility / lock / rename (require a target object)
    # Note: per-object visibility skips when "layer"/"层" is mentioned so
    # the set_layer_visibility tool (section 17b-3) handles bulk layer
    # commands without spawning a duplicate per-object set_visibility intent.
    _layer_command_in_msg = "layer" in msg_lower or "层" in msg
    if scene_objects:
        tgt = _find_target_name(msg_lower, scene_objects)
        if tgt:
            if any(k in msg_lower for k in ["hide", "隐藏"]) and not _layer_command_in_msg:
                intents.append(ParsedIntent(
                    tool_name="set_visibility",
                    arguments={"target": tgt, "visible": False},
                    description=f"Hide {tgt}",
                ))
                matched_any = True
            if any(k in msg_lower for k in ["show object", "显示对象", "显示物体", "unhide", "取消隐藏"]):
                intents.append(ParsedIntent(
                    tool_name="set_visibility",
                    arguments={"target": tgt, "visible": True},
                    description=f"Show {tgt}",
                ))
                matched_any = True
            if any(k in msg_lower for k in ["unlock", "解锁"]):
                intents.append(ParsedIntent(
                    tool_name="lock_object",
                    arguments={"target": tgt, "locked": False},
                    description=f"Unlock {tgt}",
                ))
                matched_any = True
            elif any(k in msg_lower for k in ["lock", "锁定"]):
                intents.append(ParsedIntent(
                    tool_name="lock_object",
                    arguments={"target": tgt, "locked": True},
                    description=f"Lock {tgt}",
                ))
                matched_any = True
            rename_m = re.search(r'(?:rename|重命名|改名)\s*["\']?(\w+)["\']?', msg_lower)
            if rename_m or any(k in msg_lower for k in ["rename", "重命名", "改名"]):
                new_name = rename_m.group(1) if rename_m else ""
                intents.append(ParsedIntent(
                    tool_name="rename_object",
                    arguments={"target": tgt, "name": new_name or f"{tgt}_renamed"},
                    description=f"Rename {tgt}",
                ))
                matched_any = True

    # Transform mode (move/rotate/scale gizmo)
    if any(k in msg_lower for k in ["move mode", "translate mode", "移动模式"]):
        intents.append(ParsedIntent(
            tool_name="set_transform_mode",
            arguments={"mode": "translate"},
            description="Set transform mode to translate",
        ))
        matched_any = True
    elif any(k in msg_lower for k in ["rotate mode", "旋转模式"]):
        intents.append(ParsedIntent(
            tool_name="set_transform_mode",
            arguments={"mode": "rotate"},
            description="Set transform mode to rotate",
        ))
        matched_any = True
    elif any(k in msg_lower for k in ["scale mode", "缩放模式"]):
        intents.append(ParsedIntent(
            tool_name="set_transform_mode",
            arguments={"mode": "scale"},
            description="Set transform mode to scale",
        ))
        matched_any = True

    # Select all / set selection — skip when the user said "deselect all"
    # or "unselect all" (those are handled by the deselect_all trigger
    # earlier in the pipeline). The substring check would otherwise match
    # "select all" inside "deselect all".
    _wants_deselect = any(k in msg_lower for k in ("deselect", "unselect", "clear selection", "drop selection"))
    if not _wants_deselect and any(k in msg_lower for k in ["select all", "全选", "选择全部", "选择所有"]):
        intents.append(ParsedIntent(
            tool_name="select_all",
            arguments={},
            description="Select all objects",
            emit_tool_call=False,
        ))
        matched_any = True

    # Align / distribute
    if any(k in msg_lower for k in ["align", "对齐"]) and len(scene_objects) >= 2:
        axis = "x"
        if "y axis" in msg_lower or "y轴" in msg_lower:
            axis = "y"
        elif "z axis" in msg_lower or "z轴" in msg_lower:
            axis = "z"
        intents.append(ParsedIntent(
            tool_name="align_objects",
            arguments={"axis": axis},
            description=f"Align objects on {axis} axis",
        ))
        matched_any = True
    if any(k in msg_lower for k in ["distribute", "均匀分布", "分布"]) and len(scene_objects) >= 2:
        axis = "x"
        if "y axis" in msg_lower or "y轴" in msg_lower:
            axis = "y"
        elif "z axis" in msg_lower or "z轴" in msg_lower:
            axis = "z"
        intents.append(ParsedIntent(
            tool_name="distribute_objects",
            arguments={"axis": axis},
            description=f"Distribute objects on {axis} axis",
        ))
        matched_any = True

    # Composite modelling: array / mirror / boolean / snap
    if any(k in msg_lower for k in ["array", "阵列"]) and scene_objects:
        tgt = _find_target_name(msg_lower, scene_objects) or scene_objects[-1].get("name", "")
        count_m = re.search(r'(\d+)\s*(?:copies|份|个|items|count)', msg_lower)
        count = int(count_m.group(1)) if count_m else 5
        intents.append(ParsedIntent(
            tool_name="array_pattern",
            arguments={"target": tgt, "count": count, "axis": "x", "spacing": 2.0},
            description=f"Array {tgt} x{count}",
        ))
        matched_any = True
    if any(k in msg_lower for k in ["mirror", "镜像"]) and scene_objects:
        tgt = _find_target_name(msg_lower, scene_objects) or scene_objects[-1].get("name", "")
        axis = "x"
        if "y axis" in msg_lower or "y轴" in msg_lower:
            axis = "y"
        elif "z axis" in msg_lower or "z轴" in msg_lower:
            axis = "z"
        intents.append(ParsedIntent(
            tool_name="mirror_object",
            arguments={"target": tgt, "axis": axis},
            description=f"Mirror {tgt} on {axis} axis",
        ))
        matched_any = True
    if any(k in msg_lower for k in ["boolean", "union", "subtract", "intersect", "布尔", "并集", "差集", "交集"]) and len(scene_objects) >= 2:
        op = "union"
        if any(k in msg_lower for k in ["subtract", "差集", "相减"]):
            op = "subtract"
        elif any(k in msg_lower for k in ["intersect", "交集", "相交"]):
            op = "intersect"
        names = [o.get("name", "") for o in scene_objects[:2]]
        intents.append(ParsedIntent(
            tool_name="boolean_operation",
            arguments={"target_a": names[0], "target_b": names[1], "operation": op},
            description=f"Boolean {op} on {names[0]} and {names[1]}",
        ))
        matched_any = True
    if any(k in msg_lower for k in ["snap to grid", "吸附到网格"]) and scene_objects:
        tgt = _find_target_name(msg_lower, scene_objects) or scene_objects[-1].get("name", "")
        intents.append(ParsedIntent(
            tool_name="snap_to_grid",
            arguments={"target": tgt, "grid_size": 0.5},
            description=f"Snap {tgt} to grid",
        ))
        matched_any = True
    # Mesh subdivision — raise or lower segment counts by a factor.
    if any(k in msg_lower for k in ["subdivide", "subdivision", "细分", "increase resolution", "smooth mesh", "higher poly", "lower poly", "reduce poly"]) and scene_objects:
        tgt = _find_target_name(msg_lower, scene_objects) or scene_objects[-1].get("name", "")
        # Detect an explicit factor like "x4", "by 3", "factor 2".
        fac_m = re.search(r'(?:x|by|factor\s*)?\s*(\d+(?:\.\d+)?)', msg_lower)
        factor = float(fac_m.group(1)) if fac_m else 2.0
        if any(k in msg_lower for k in ["lower poly", "reduce poly", "降低", "减面"]):
            factor = min(factor, 0.5)
        intents.append(ParsedIntent(
            tool_name="subdivide_mesh",
            arguments={"target": tgt, "factor": factor},
            description=f"Subdivide {tgt} x{factor}",
        ))
        matched_any = True

    # Advanced material: gradient / blend / batch
    if any(k in msg_lower for k in ["gradient material", "渐变材质"]) and scene_objects:
        tgt = _find_target_name(msg_lower, scene_objects) or scene_objects[-1].get("name", "")
        c1 = _find_color(msg_lower) or "#3a7aff"
        c2 = "#ff8a3a" if c1 != "#ff8a3a" else "#9a3aff"
        intents.append(ParsedIntent(
            tool_name="gradient_material",
            arguments={"target": tgt, "color_a": c1, "color_b": c2, "axis": "y"},
            description=f"Gradient material on {tgt}",
        ))
        matched_any = True
    if any(k in msg_lower for k in ["blend material", "material blend", "混合材质"]) and len(scene_objects) >= 2:
        names = [o.get("name", "") for o in scene_objects[:2]]
        intents.append(ParsedIntent(
            tool_name="material_blend",
            arguments={"target_a": names[0], "target_b": names[1], "ratio": 0.5},
            description=f"Blend materials of {names[0]} and {names[1]}",
        ))
        matched_any = True
    if any(k in msg_lower for k in ["batch material", "apply material to all", "批量材质", "全部上色"]) and scene_objects:
        preset = _find_preset(msg_lower)
        color = _find_color(msg_lower)
        args: Dict[str, Any] = {}
        if preset:
            args["preset"] = preset
        if color:
            args["color"] = color
        intents.append(ParsedIntent(
            tool_name="apply_material_batch",
            arguments=args,
            description="Apply material to all objects",
        ))
        matched_any = True

    # Layer & group management
    if any(k in msg_lower for k in ["move to layer", "set layer", "设置层", "移动到层"]) and scene_objects:
        tgt = _find_target_name(msg_lower, scene_objects) or scene_objects[-1].get("name", "")
        layer_m = re.search(r'(?:layer|层)\s*["\']?(\w+)["\']?', msg_lower)
        layer = layer_m.group(1) if layer_m else "default"
        intents.append(ParsedIntent(
            tool_name="set_object_layer",
            arguments={"target": tgt, "layer": layer},
            description=f"Set {tgt} layer to {layer}",
        ))
        matched_any = True
    if any(k in msg_lower for k in ["reorder layer", "bring to front", "send to back", "调整层级", "置顶", "置底"]):
        direction = "front"
        if any(k in msg_lower for k in ["send to back", "置底", "后退"]):
            direction = "back"
        intents.append(ParsedIntent(
            tool_name="reorder_layer",
            arguments={"direction": direction},
            description=f"Reorder layer {direction}",
            emit_tool_call=False,
        ))
        matched_any = True
    if any(k in msg_lower for k in ["assign to group", "分配到组", "加入组"]) and scene_objects:
        tgt = _find_target_name(msg_lower, scene_objects) or scene_objects[-1].get("name", "")
        grp_m = re.search(r'(?:group|组)\s*["\']?(\w+)["\']?', msg_lower)
        grp = grp_m.group(1) if grp_m else "Group"
        intents.append(ParsedIntent(
            tool_name="assign_to_group",
            arguments={"target": tgt, "group": grp},
            description=f"Assign {tgt} to {grp}",
        ))
        matched_any = True
    if any(k in msg_lower for k in ["rename group", "重命名组", "改名组"]):
        grp_m = re.search(r'(?:rename group|重命名组|改名组)\s*["\']?(\w+)["\']?', msg_lower)
        new_name = grp_m.group(1) if grp_m else "RenamedGroup"
        intents.append(ParsedIntent(
            tool_name="rename_group",
            arguments={"target": "Group", "name": new_name},
            description=f"Rename group to {new_name}",
        ))
        matched_any = True

    # Camera management
    if any(k in msg_lower for k in ["add camera", "添加相机", "新建相机"]):
        intents.append(ParsedIntent(
            tool_name="add_camera",
            arguments={},
            description="Add a camera",
        ))
        matched_any = True
    if any(k in msg_lower for k in ["delete camera", "删除相机"]) :
        intents.append(ParsedIntent(
            tool_name="delete_camera",
            arguments={},
            description="Delete camera",
        ))
        matched_any = True
    if any(k in msg_lower for k in ["modify camera", "change camera", "修改相机", "调整相机"]):
        intents.append(ParsedIntent(
            tool_name="modify_camera",
            arguments={},
            description="Modify camera",
        ))
        matched_any = True
    if any(k in msg_lower for k in ["animate camera", "camera animation", "相机动画", "相机移动"]):
        intents.append(ParsedIntent(
            tool_name="animate_camera",
            arguments={"path": "orbit", "duration": 8.0},
            description="Animate camera along a path",
        ))
        matched_any = True
    if any(k in msg_lower for k in ["set camera position", "camera position", "设置相机位置", "相机位置", "set camera to", "move camera to", "camera to"]):
        pos = _parse_number_list(msg_lower)
        args: Dict[str, Any] = {}
        if pos and len(pos) >= 3:
            args["position"] = pos[:3]
        intents.append(ParsedIntent(
            tool_name="set_viewport_camera",
            arguments=args,
            description="Set viewport camera position",
            emit_tool_call=False,
        ))
        matched_any = True

    # Zoom controls
    if any(k in msg_lower for k in ["zoom in", "zoom out", "放大视图", "缩小视图", "拉近", "拉远"]):
        zoom_factor = 0.5 if "zoom in" in msg_lower or "放大" in msg_lower or "拉近" in msg_lower else 2.0
        intents.append(ParsedIntent(
            tool_name="set_viewport_camera",
            arguments={"zoom": zoom_factor},
            description=f"Zoom {'in' if zoom_factor < 1 else 'out'}",
            emit_tool_call=False,
        ))
        matched_any = True

    # Frame / fit camera
    if any(k in msg_lower for k in ["frame the scene", "frame all", "frame scene", "fit scene", "fit all", "frame view", "frame selection", "居中显示", "全屏显示", "适应屏幕"]):
        intents.append(ParsedIntent(
            tool_name="frame_view",
            arguments={"target": "all"},
            description="Frame the entire scene",
            emit_tool_call=False,
        ))
        matched_any = True

    # Brightness / exposure controls
    if any(k in msg_lower for k in ["make it brighter", "brighter", "increase brightness", "more bright", "调亮", "更亮", "增加亮度"]):
        intents.append(ParsedIntent(
            tool_name="set_exposure",
            arguments={"exposure": 1.5},
            description="Increase scene brightness",
            emit_tool_call=False,
        ))
        matched_any = True
    if any(k in msg_lower for k in ["make it dimmer", "dimmer", "decrease brightness", "less bright", "darker", "调暗", "更暗", "降低亮度"]):
        intents.append(ParsedIntent(
            tool_name="set_exposure",
            arguments={"exposure": 0.6},
            description="Decrease scene brightness",
            emit_tool_call=False,
        ))
        matched_any = True

    # Environment & snapshot
    if any(k in msg_lower for k in ["environment", "hdr", "环境贴图", "环境光贴图"]):
        intents.append(ParsedIntent(
            tool_name="set_environment",
            arguments={"preset": "studio"},
            description="Set environment",
        ))
        matched_any = True
    if any(k in msg_lower for k in ["snapshot view", "save view", "保存视图", "快照视图"]):
        intents.append(ParsedIntent(
            tool_name="snapshot_view",
            arguments={},
            description="Snapshot current view",
            emit_tool_call=False,
        ))
        matched_any = True

    # Measurement
    if any(k in msg_lower for k in ["measure distance", "distance between", "测量距离", "测量间距"]) and len(scene_objects) >= 2:
        names = [o.get("name", "") for o in scene_objects[:2]]
        intents.append(ParsedIntent(
            tool_name="measure_distance",
            arguments={"target_a": names[0], "target_b": names[1]},
            description=f"Measure distance between {names[0]} and {names[1]}",
            emit_tool_call=False,
        ))
        matched_any = True

    # Light & geometry modification
    if any(k in msg_lower for k in ["modify light", "change light", "adjust light", "修改灯光", "调整灯光", "改变灯光"]):
        intents.append(ParsedIntent(
            tool_name="modify_light",
            arguments={},
            description="Modify light",
        ))
        matched_any = True
    if any(k in msg_lower for k in ["modify geometry", "change geometry", "change shape", "修改几何", "修改形状"]) and scene_objects:
        tgt = _find_target_name(msg_lower, scene_objects) or scene_objects[-1].get("name", "")
        intents.append(ParsedIntent(
            tool_name="modify_geometry",
            arguments={"target": tgt},
            description=f"Modify geometry of {tgt}",
        ))
        matched_any = True

    # Export code
    if any(k in msg_lower for k in ["export code", "导出代码", "生成代码"]):
        fmt = "three_js"
        if "react" in msg_lower or "r3f" in msg_lower:
            fmt = "react_r3f"
        elif "html" in msg_lower:
            fmt = "html"
        intents.append(ParsedIntent(
            tool_name="export_code",
            arguments={"format": fmt},
            description=f"Export scene as {fmt} code",
        ))
        matched_any = True

    # Music generation & audio transcription
    if any(k in msg_lower for k in ["generate music", "create music", "生成音乐", "创作音乐"]):
        prompt = msg
        for trig in ["generate music", "create music", "生成音乐", "创作音乐"]:
            prompt = prompt.replace(trig, "")
        prompt = prompt.strip(" :,.-")
        intents.append(ParsedIntent(
            tool_name="generate_music",
            arguments={"prompt": prompt or "ambient background music"},
            description="Generate music from prompt",
        ))
        matched_any = True
    if any(k in msg_lower for k in ["transcribe", "speech to text", "语音转文字", "转写"]):
        intents.append(ParsedIntent(
            tool_name="transcribe_audio",
            arguments={},
            description="Transcribe audio to text",
        ))
        matched_any = True

    # Sub-agent dispatch
    if any(k in msg_lower for k in ["dispatch subagent", "sub-agent", "子代理", "调度子代理"]):
        task = msg
        for trig in ["dispatch subagent", "sub-agent", "子代理", "调度子代理"]:
            task = task.replace(trig, "")
        task = task.strip(" :,.-")
        intents.append(ParsedIntent(
            tool_name="dispatch_subagent",
            arguments={"task": task or "help with scene editing"},
            description="Dispatch sub-agent for a sub-task",
        ))
        matched_any = True

    # Extended per-field editor tools — material/geometry/hierarchy/
    # annotation capabilities alongside the basic editor tools.
    _EXT_MATERIAL_PROPS = {
        "clearcoat": "clearcoat", "clearcoat_roughness": "clearcoat_roughness",
        "transmission": "transmission", "thickness": "thickness", "ior": "ior",
        "iridescence": "iridescence", "iridescence_ior": "iridescence_ior",
        "iridescence_thickness_min": "iridescence_thickness_min",
        "iridescence_thickness_max": "iridescence_thickness_max",
        "sheen": "sheen", "sheen_color": "sheen_color",
        "sheen_roughness": "sheen_roughness",
        "specular_intensity": "specular_intensity", "specular_color": "specular_color",
        "attenuation_color": "attenuation_color",
        "attenuation_distance": "attenuation_distance",
        "metalness": "metalness", "roughness": "roughness",
        "opacity": "opacity", "emissive_intensity": "emissive_intensity",
    }
    for _prop_phrase, _prop_name in _EXT_MATERIAL_PROPS.items():
        _pat = f"{_prop_phrase} "
        if _pat in msg_lower or f"set {_prop_phrase}" in msg_lower or f"material {_prop_phrase}" in msg_lower:
            # Capture a numeric (or hex for color props) value following the prop name.
            _val = _parse_number_after(msg_lower, _prop_phrase)
            if _prop_phrase.endswith("_color") or _prop_phrase == "emissive":
                _hex = re.search(r"#([0-9a-fA-F]{3,8})", msg)
                _val = _hex.group(0) if _hex else _val
            if _val is None:
                continue
            if scene_objects:
                _target = scene_objects[-1].get("name", "")
                intents.append(ParsedIntent(
                    tool_name="set_material_property",
                    arguments={"target": _target, "property": _prop_name, "value": _val},
                    description=f"Set material.{_prop_name} = {_val}",
                ))
                matched_any = True
            break

    # set_geometry_params — "set geometry radius to 0.8" etc.
    if any(k in msg_lower for k in ["geometry param", "set radius", "set height", "set width", "set depth", "set segments", "几何参数", "设置半径"]):
        _geo_target = scene_objects[-1].get("name", "") if scene_objects else ""
        _params: Dict[str, Any] = {}
        for _pname in ("radius", "height", "width", "depth", "widthSegments", "heightSegments", "radialSegments", "tubularSegments"):
            _val = _parse_number_after(msg_lower, _pname)
            if _val is not None:
                _params[_pname] = _val
        if _geo_target and _params:
            intents.append(ParsedIntent(
                tool_name="set_geometry_params",
                arguments={"target": _geo_target, "params": _params},
                description=f"Update geometry params: {list(_params.keys())}",
            ))
            matched_any = True

    # set_object_parent — "parent X to group Y", "把X加入组Y"
    if any(k in msg_lower for k in ["parent to", "parent object", "assign to group", "加入组", "归属组", "父级为"]):
        _target = scene_objects[-1].get("name", "") if scene_objects else ""
        # Find a group name following the trigger phrase.
        _grp_match = re.search(r"(?:parent to|parent object|assign to group|加入组|归属组|父级为)\s+(?:group\s+)?([A-Za-z0-9_\-一-龥]+)", msg)
        _group_id = _grp_match.group(1) if _grp_match else ""
        if _target and _group_id:
            intents.append(ParsedIntent(
                tool_name="set_object_parent",
                arguments={"target": _target, "group_id": _group_id},
                description=f"Parent '{_target}' to group '{_group_id}'",
            ))
            matched_any = True

    # add_annotation — "add annotation/note/label", "添加标注/注释/标签"
    if any(k in msg_lower for k in ["add an annotation", "add annotation", "add note", "add label", "add a note", "an annotation labeled", "添加标注", "添加注释", "添加标签", "加标注"]):
        _text = msg
        for _trig in ["add an annotation", "add annotation", "add note", "add label", "add a note", "an annotation labeled", "annotation labeled", "labeled", "labelled", "添加标注", "添加注释", "添加标签", "加标注"]:
            _text = _text.replace(_trig, "")
        _text = _text.strip(" :,.-")
        if not _text:
            _text = "New annotation"
        _target = scene_objects[-1].get("name", "") if scene_objects else ""
        intents.append(ParsedIntent(
            tool_name="add_annotation",
            arguments={"object_id": _target, "text": _text} if _target else {"text": _text},
            description=f"Add annotation: {_text}",
        ))
        matched_any = True

    # remove_annotation — "remove annotation", "删除标注/注释/标签"
    if any(k in msg_lower for k in ["remove annotation", "remove note", "remove label", "delete annotation", "删除标注", "删除注释", "删除标签"]):
        _id_match = re.search(r"(?:ann_|note_)[A-Za-z0-9]+", msg)
        _ann_id = _id_match.group(0) if _id_match else ""
        if _ann_id:
            intents.append(ParsedIntent(
                tool_name="remove_annotation",
                arguments={"id": _ann_id},
                description=f"Remove annotation '{_ann_id}'",
            ))
            matched_any = True

    # configure_shortcuts — "configure shortcuts / remap keys", "配置快捷键"
    if any(k in msg_lower for k in ["configure shortcut", "remap shortcut", "remap key", "rebind key", "配置快捷键", "重映射快捷键"]):
        intents.append(ParsedIntent(
            tool_name="configure_shortcuts",
            arguments={"shortcuts": {"frame_all": "A"}},
            description="Configure keyboard shortcuts (recorded)",
        ))
        matched_any = True

    # Scene workflow intelligence tools — query_scene, style_scene,
    # batch_transform, scene_statistics, list_annotations,
    # camera_flythrough. These give the offline rule engine direct access
    # to the bulk / query / stylization / cinematic capabilities.
    _STYLE_PRESET_TRIGGERS: List[Tuple[str, str]] = [
        ("cyberpunk", "cyberpunk"), ("赛博朋克", "cyberpunk"),
        ("minimalist", "minimalist"), ("极简", "minimalist"), ("minimal style", "minimalist"),
        ("photoreal", "photoreal"), ("photorealistic", "photoreal"), ("写实", "photoreal"), ("照片级", "photoreal"),
        ("noir", "noir"), ("黑色电影", "noir"),
        ("sunset", "sunset"), ("日落", "sunset"),
        ("oceanic", "oceanic"), ("海洋", "oceanic"),
    ]
    _STYLE_VERBS = [
        "style scene", "apply style", "scene style", "theme scene", "stylize",
        "apply", "use style", "make it", "theme", "restyle", "style",
        "应用风格", "场景风格", "主题风格", "改成", "风格", "应用",
    ]
    _has_style_verb = any(k in msg_lower for k in _STYLE_VERBS)
    _matched_style_preset: Optional[str] = None
    for _trig, _preset in _STYLE_PRESET_TRIGGERS:
        if _trig in msg_lower:
            _matched_style_preset = _preset
            break
    if _matched_style_preset and _has_style_verb:
        intents.append(ParsedIntent(
            tool_name="style_scene",
            arguments={"preset": _matched_style_preset},
            description=f"Apply '{_matched_style_preset}' style preset to scene",
        ))
        matched_any = True
    elif _has_style_verb and any(k in msg_lower for k in ["style scene", "apply style", "scene style", "theme scene", "stylize", "应用风格", "场景风格", "主题风格"]):
        # Style verb with no recognized preset — emit a default cyberpunk
        # fallback so the intent still triggers; the user can refine.
        intents.append(ParsedIntent(
            tool_name="style_scene",
            arguments={"preset": "cyberpunk"},
            description="Apply cyberpunk style preset (default fallback)",
            emit_tool_call=False,
        ))
        matched_any = True

    # query_scene — "find all <geometry>", "find objects with color <hex>",
    # "query scene", "filter objects", "搜索场景", "筛选物体"
    _QUERY_SCENE_TRIGGERS = [
        "query scene", "find all", "find objects", "filter objects", "search scene",
        "show me all", "list all objects", "搜索场景", "筛选物体", "查找所有", "查找物体",
    ]
    if any(k in msg_lower for k in _QUERY_SCENE_TRIGGERS):
        _args: Dict[str, Any] = {}
        # Geometry-type filter: "find all spheres" -> geometry_type=sphere
        for _phrase, _geo in GEO_MAP.items():
            if _phrase in msg_lower:
                _args["geometry_type"] = _geo
                break
        # Color filter: hex in message
        _hex = re.search(r"#([0-9a-fA-F]{3,8})", msg)
        if _hex:
            _args["color"] = _hex.group(0).lower()
        # Name regex: "named X" or "called X"
        _name_match = re.search(r"(?:named|called)\s+([A-Za-z0-9_\-]+)", msg_lower)
        if _name_match:
            _args["name_regex"] = _name_match.group(1)
        # Visibility filter
        if "hidden" in msg_lower or "隐藏" in msg_lower:
            _args["visible"] = False
        elif "visible" in msg_lower or "可见" in msg_lower:
            _args["visible"] = True
        # Layer filter
        _layer_match = re.search(r"(?:on layer|layer)\s+([A-Za-z0-9_\-]+)", msg_lower)
        if _layer_match:
            _args["layer"] = _layer_match.group(1)
        intents.append(ParsedIntent(
            tool_name="query_scene",
            arguments=_args,
            description=f"Query scene ({', '.join(_args.keys()) or 'no filters'})",
            emit_tool_call=False,
        ))
        matched_any = True

    # batch_transform — "batch move/rotate/scale all <targets> by <vec>"
    _BATCH_OP_KEYWORDS: List[Tuple[str, str, str]] = [
        ("batch move", "translate", "移动"), ("batch translate", "translate", "平移"),
        ("batch rotate", "rotate", "旋转"), ("batch scale", "scale", "缩放"),
        ("move all", "translate", "移动"), ("translate all", "translate", "平移"),
        ("rotate all", "rotate", "旋转"), ("scale all", "scale", "缩放"),
        ("批量移动", "translate", "移动"), ("批量平移", "translate", "平移"),
        ("批量旋转", "rotate", "旋转"), ("批量缩放", "scale", "缩放"),
        ("批量变换", "translate", "移动"),
    ]
    for _trig, _op, _cn in _BATCH_OP_KEYWORDS:
        if _trig in msg_lower:
            _values = _parse_number_list(msg_lower)
            if not _values or len(_values) < 3:
                # Fall back to per-axis parsing for "move all up by 1"
                _vals = [0.0, 0.0, 0.0]
                for _axis_idx, _axis_name in enumerate(("x", "y", "z")):
                    _v = _parse_axis_value(msg_lower, [_axis_name])
                    if _v:
                        _vals[_axis_idx] = _v[1]
                if any(abs(v) > 1e-9 for v in _vals):
                    _values = _vals
            if not _values:
                break
            # Targets: every scene object if user said "all"; otherwise the
            # most recently mentioned object name.
            _targets: List[str] = []
            if "all" in msg_lower or "所有" in msg_lower or "every" in msg_lower:
                _targets = [o.get("name", "") for o in scene_objects if o.get("name")]
            elif scene_objects:
                _targets = [scene_objects[-1].get("name", "")]
            if _targets and _values:
                intents.append(ParsedIntent(
                    tool_name="batch_transform",
                    arguments={"targets": _targets, "operation": _op, "values": list(_values[:3])},
                    description=f"Batch {_op} {len(_targets)} target(s) by {_values[:3]}",
                ))
                matched_any = True
            break

    # scene_statistics — "scene stats", "polygon count", "bounding box",
    # "场景统计", "多边形数"
    if any(k in msg_lower for k in ["scene stats", "scene statistics", "polygon count", "bounding box", "how many objects", "object count", "场景统计", "统计信息", "多边形数", "包围盒"]):
        intents.append(ParsedIntent(
            tool_name="scene_statistics",
            arguments={},
            description="Return detailed scene statistics",
            emit_tool_call=False,
        ))
        matched_any = True

    # list_annotations — "list annotations", "show annotations",
    # "列出标注", "显示标注"
    if any(k in msg_lower for k in ["list annotations", "list annotation", "show annotations", "show annotation", "what annotations", "列出标注", "显示标注", "所有标注"]):
        intents.append(ParsedIntent(
            tool_name="list_annotations",
            arguments={},
            description="List all annotations in scene",
            emit_tool_call=False,
        ))
        matched_any = True

    # camera_flythrough — "camera flythrough", "fly through scene",
    # "cinematic camera path", "相机巡航", "相机飞越"
    if any(k in msg_lower for k in ["camera flythrough", "camera fly through", "fly through scene", "flythrough", "cinematic camera", "camera path animation", "相机巡航", "相机飞越", "镜头飞越", "镜头巡航"]):
        # Try to parse a list of waypoint positions from the message.
        # Accept either [[x,y,z],[x,y,z],...] or a sequence of bracketed
        # 3-vectors. Fall back to a default orbit around the origin.
        _waypoints: List[Dict[str, Any]] = []
        _all_vecs = re.findall(r'\[\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*\]', msg)
        for _v in _all_vecs:
            _waypoints.append({"position": [float(_v[0]), float(_v[1]), float(_v[2])]})
        if len(_waypoints) < 2:
            # Default demo path: orbit around the origin at radius 4.
            _waypoints = [
                {"position": [4.0, 2.0, 0.0]},
                {"position": [0.0, 2.0, 4.0]},
                {"position": [-4.0, 2.0, 0.0]},
                {"position": [0.0, 2.0, -4.0]},
                {"position": [4.0, 2.0, 0.0]},
            ]
        _loop = "loop" in msg_lower or "循环" in msg_lower
        intents.append(ParsedIntent(
            tool_name="camera_flythrough",
            arguments={"waypoints": _waypoints, "loop": _loop, "speed": 2.0},
            description=f"Animate camera along {len(_waypoints)}-waypoint flythrough",
        ))
        matched_any = True

    # 18. Reset / clear scene
    if any(k in msg_lower for k in [
        "clear scene", "clear the scene", "reset scene", "reset the scene",
        "empty the scene", "start over", "清空", "重置", "清空场景", "重置场景",
    ]):
        intents.append(ParsedIntent(
            tool_name="smart_compose",
            arguments={"template": "_clear"},
            description="Clear scene",
        ))
        matched_any = True

    # 19. Scene analysis
    if any(k in msg_lower for k in [
        "analyze", "describe scene", "describe the scene", "describe this scene",
        "describe my scene", "describe the current scene",
        "what's in", "what is in", "scene analysis", "inspect",
        "what does the scene look like", "what does it look like",
        "scene summary", "overview of the scene",
        "分析场景", "描述场景", "描述一下场景", "场景里有什么", "看看场景",
    ]):
        detail = "summary"
        if any(k in msg_lower for k in ["detailed", "detail", "full", "详细", "完整"]):
            detail = "detailed"
        if any(k in msg_lower for k in ["everything", "all details", "所有", "全部"]):
            detail = "full"
        intents.append(ParsedIntent(
            tool_name="analyze_scene",
            arguments={"detail_level": detail},
            description=f"Analyze scene ({detail})",
        ))
        matched_any = True

    # Scene critique — prescriptive design review with fix proposals.
    # Triggered by critical-review phrasing that calls for an editorial
    # assessment rather than a neutral inventory.
    if any(k in msg_lower for k in [
        "critique", "review the scene", "review scene", "design review",
        "what's wrong", "what is wrong", "how does it look", "how does this look",
        "evaluate the scene", "evaluate my scene", "quality check", "check my scene",
        "scene review", "fresh eyes", "review my work",
        "评审", "审查", "检查场景问题", "场景有什么问题", "看看有没有问题",
        "设计评审", "质量问题", "我的场景怎么样", "场景评价",
    ]):
        intents.append(ParsedIntent(
            tool_name="critique_scene",
            arguments={},
            description="Run a prescriptive design review of the scene",
            emit_tool_call=False,
        ))
        matched_any = True

    # Scene auto-fix — review the scene and apply the top corrective
    # fixes automatically. Triggered by fix/cleanup phrasing.
    if any(k in msg_lower for k in [
        "auto fix", "auto-fix", "fix the scene", "fix my scene",
        "fix this scene", "clean up my scene", "cleanup", "clean up the scene",
        "make this look right", "make it look right", "fix the problems",
        "fix the issues", "tidy up", "repair the scene", "fix everything",
        "自动修复", "修复场景", "一键修复", "清理场景", "清理我的场景",
        "整理场景", "自动修正", "修复问题",
    ]):
        intents.append(ParsedIntent(
            tool_name="auto_fix_scene",
            arguments={},
            description="Review the scene and automatically apply the top fixes",
            emit_tool_call=False,
        ))
        matched_any = True

    # 20. Image-to-3D reconstruction
    # Triggered by keywords like "reconstruct", "image to 3d", "重建", "图像转3D"
    image_to_3d_triggers = [
        "reconstruct", "image to 3d", "image-to-3d",
        "from image", "convert image", "image to mesh", "photo to 3d",
        "重建", "图像转3d", "图像转3D", "图片转3d", "图片转3D",
        "从图片", "图片生成", "图像生成",
    ]
    if any(k in msg_lower for k in image_to_3d_triggers):
        # Extract a prompt description from the message by removing trigger words
        prompt_text = msg
        for trig in image_to_3d_triggers:
            prompt_text = prompt_text.replace(trig, "")
        prompt_text = prompt_text.strip(" :,.-")
        # Determine whether to clear the scene
        clear = any(w in msg_lower for w in ["clear", "replace", "清空", "替换"])
        intents.append(ParsedIntent(
            tool_name="image_to_3d",
            arguments={"prompt": prompt_text or "a 3D scene", "clear_scene": clear},
            description=f"Reconstruct 3D scene from description",
        ))
        matched_any = True

    # 21. Multi-step pipeline (checked before single-step multimodal so
    # "generate an image then convert to 3D" builds a DAG instead of a
    # single generate_image intent).
    if not matched_any:
        pipeline_intent = _parse_pipeline_intent(msg_lower, msg)
        if pipeline_intent is not None:
            intents.append(pipeline_intent)
            matched_any = True

    # 22. Multimodal generation (image / 3D asset / video / animation / speech)
    # These intents route natural language to the multimodal dispatcher via
    # dedicated Agent tools. They are checked after image-to-3D so the
    # reconstruction flow takes precedence when an image source is implied.
    if not matched_any:
        mm_intent = _parse_multimodal_intent(msg_lower, msg)
        if mm_intent is not None:
            intents.append(mm_intent)
            matched_any = True

    # Cinematic storyboard — compose / play / clear camera sequences.
    # Maps natural language to the storyboard tools so the offline engine
    # can drive a scripted camera tour without an LLM round-trip.
    story_match = re.search(
        r'(?:compose\s+(?:a\s+)?(?:cinematic\s+)?story\s*board|create\s+(?:a\s+)?(?:cinematic\s+)?story)\s*["\']?([\w\s\-]+)?["\']?',
        msg_lower,
    )
    if story_match:
        title = (story_match.group(1) or "").strip() or "Untitled scene"
        intents.append(ParsedIntent(
            tool_name="compose_story",
            arguments={"title": title, "shots": []},
            description=f"Compose cinematic storyboard '{title}'",
        ))
        matched_any = True
    elif re.search(r'(?:create\s+.*\bstory\b|编个故事|故事板|分镜)', msg_lower):
        intents.append(ParsedIntent(
            tool_name="compose_story",
            arguments={"title": "Untitled scene", "shots": []},
            description="Compose cinematic storyboard",
        ))
        matched_any = True

    if any(k in msg_lower for k in ["play story", "play the story", "play storyboard", "播放故事", "开始分镜"]):
        intents.append(ParsedIntent(
            tool_name="play_story",
            arguments={"mode": "play"},
            description="Play the cinematic storyboard",
            emit_tool_call=False,
        ))
        matched_any = True
    if any(k in msg_lower for k in ["stop story", "stop the story", "stop storyboard", "停止故事", "停止分镜"]):
        intents.append(ParsedIntent(
            tool_name="play_story",
            arguments={"mode": "stop"},
            description="Stop the cinematic storyboard",
            emit_tool_call=False,
        ))
        matched_any = True
    if any(k in msg_lower for k in ["clear story", "clear the story", "clear storyboard", "清除故事", "清除分镜"]):
        intents.append(ParsedIntent(
            tool_name="clear_story",
            arguments={},
            description="Clear the cinematic storyboard",
        ))
        matched_any = True
    if any(k in msg_lower for k in ["list story", "list the story", "list storyboard", "查看故事", "分镜列表"]):
        intents.append(ParsedIntent(
            tool_name="list_story",
            arguments={},
            description="List the cinematic storyboard",
        ))
        matched_any = True

    # Memory management — pin / recall / forget durable facts. Maps
    # natural language to the memory tools so the user can manage the
    # Agent's cross-session memory without calling tools by name.
    if any(k in msg_lower for k in [
        "remember that", "remember:", "note that", "keep in mind",
        "pin this:", "记住", "记一下", "牢记",
    ]):
        # Extract the fact text after the trigger phrase
        fact_text = ""
        for trigger in ["remember that", "remember:", "note that", "keep in mind", "pin this:"]:
            if trigger in msg_lower:
                idx = msg_lower.index(trigger) + len(trigger)
                fact_text = msg_lower[idx:].strip().strip("'\"")
                break
        if not fact_text:
            for trigger in ["记住", "记一下", "牢记"]:
                if trigger in msg_lower:
                    idx = msg_lower.index(trigger) + len(trigger)
                    fact_text = msg_lower[idx:].strip().strip("'\"")
                    break
        if fact_text:
            # Detect category from keywords
            category = "general"
            if any(w in fact_text for w in ["mobile", "desktop", "web", "ios", "android"]):
                category = "project"
            elif any(w in fact_text for w in ["prefer", "like", "want", "use"]):
                category = "preference"
            elif any(w in fact_text for w in ["must", "should", "constraint", "limit"]):
                category = "constraint"
            elif any(w in fact_text for w in ["style", "color", "theme", "design"]):
                category = "style"
            intents.append(ParsedIntent(
                tool_name="pin_fact",
                arguments={"text": fact_text, "category": category},
                description=f"Remember: {fact_text[:60]}",
            ))
            matched_any = True
    if any(k in msg_lower for k in [
        "what do you remember", "what do you know", "show memory",
        "show facts", "recall facts", "list memory", "list facts",
        "你记得什么", "你的记忆", "查看记忆", "回忆",
    ]):
        intents.append(ParsedIntent(
            tool_name="recall_facts",
            arguments={},
            description="Recall remembered facts",
        ))
        matched_any = True
    if any(k in msg_lower for k in [
        "forget ", "stop remembering", "remove memory",
        "忘记", "清除记忆",
    ]):
        # Extract what to forget
        forget_text = ""
        for trigger in ["forget ", "stop remembering", "remove memory"]:
            if trigger in msg_lower:
                idx = msg_lower.index(trigger) + len(trigger)
                forget_text = msg_lower[idx:].strip().strip("'\"")
                break
        if not forget_text:
            for trigger in ["忘记", "清除记忆"]:
                if trigger in msg_lower:
                    idx = msg_lower.index(trigger) + len(trigger)
                    forget_text = msg_lower[idx:].strip().strip("'\"")
                    break
        if forget_text:
            intents.append(ParsedIntent(
                tool_name="forget_fact",
                arguments={"query": forget_text},
                description=f"Forget: {forget_text[:60]}",
            ))
            matched_any = True

    # Checkpoint management — capture / restore / diff / list scene
    # revisions. Maps natural language to the checkpoint tools so the
    # offline engine can drive revision history without an LLM round-trip.
    if any(k in msg_lower for k in [
        "checkpoint", "save checkpoint", "snapshot the scene",
        "save a revision", "commit scene", "保存检查点", "存档", "快照",
    ]):
        label_match = re.search(r'(?:checkpoint|snapshot|revision|commit)\s+(?:as|named|called)\s+["\']?([\w\s\-]+)["\']?', msg_lower)
        label = (label_match.group(1).strip() if label_match else "") or ""
        intents.append(ParsedIntent(
            tool_name="checkpoint_scene",
            arguments={"label": label} if label else {},
            description=f"Checkpoint scene{f' as {label}' if label else ''}",
        ))
        matched_any = True
    if any(k in msg_lower for k in [
        "list checkpoint", "list revisions", "show checkpoint", "show revisions",
        "checkpoint list", "checkpoint history", "查看检查点", "检查点列表", "历史版本",
    ]):
        intents.append(ParsedIntent(
            tool_name="list_checkpoints",
            arguments={},
            description="List scene checkpoints",
        ))
        matched_any = True
    if any(k in msg_lower for k in [
        "restore checkpoint", "restore revision", "revert to", "roll back to",
        "go back to", "恢复检查点", "恢复版本", "回退到", "还原到",
    ]):
        # Try to parse a revision identifier (R1, r2, rev3, etc.) or a label
        rev_match = re.search(r'(?:restore|revert|roll back|go back)\s+(?:to\s+)?(?:checkpoint\s+|revision\s+)?["\']?(R\d+|r\d+|rev\d+|[\w\s\-]+)["\']?', msg_lower)
        rev = (rev_match.group(1).strip() if rev_match else "") or "latest"
        intents.append(ParsedIntent(
            tool_name="restore_checkpoint",
            arguments={"revision": rev},
            description=f"Restore checkpoint {rev}",
        ))
        matched_any = True
    if any(k in msg_lower for k in [
        "diff checkpoint", "compare checkpoint", "checkpoint diff",
        "diff revision", "compare revision", "对比检查点", "差异对比",
    ]):
        intents.append(ParsedIntent(
            tool_name="checkpoint_diff",
            arguments={},
            description="Diff latest checkpoints",
        ))
        matched_any = True

    if not matched_any:
        return [], ""

    # Compound intent chaining — when the message contains a creation step
    # followed by transform/material/light clauses (e.g. "create a sphere
    # then move it up 2 units and make it red"), re-parse the trailing
    # clauses against a synthetic scene containing the just-created object
    # so the offline planner emits a multi-step chain in one pass. Without
    # this, the transform/material sections skip because the real scene is
    # still empty at plan time.
    intents = _chain_compound_intents(msg_lower, intents, scene_objects)

    return intents, ""


# ---------------------------------------------------------------------------
# Scene composition patterns — maps compound natural-language requests to
# multi-step tool sequences. Each pattern is a (trigger_phrase, intent_list)
# pair. The first matching pattern wins, so order specific phrases before
# generic ones.
# ---------------------------------------------------------------------------

def _match_scene_composition(msg_lower: str) -> List[ParsedIntent]:
    """Match compound scene requests to multi-step tool sequences.

    Handles atmosphere presets (sunset/night/winter/desert), natural
    features (water/stars/mountains), room compositions (living room/
    bedroom/kitchen), furniture creation (table/chair/car), and pattern
    compositions (chess board) that a single create_object call cannot
    express.
    """
    # --- Atmosphere / environment presets ---
    _ATMOSPHERE_PRESETS: Dict[str, List[ParsedIntent]] = {
        "sunset": [
            ParsedIntent(tool_name="set_background", arguments={"color": "#ff7e3e"}, description="Set sunset sky background"),
            ParsedIntent(tool_name="set_fog", arguments={"color": "#ff9a5a", "density": 0.02}, description="Add warm sunset fog"),
            ParsedIntent(tool_name="add_light", arguments={"light_type": "directional", "color": "#ffaa55", "intensity": 1.5, "position": [-3, 2, -5]}, description="Add warm sunset directional light"),
        ],
        "night": [
            ParsedIntent(tool_name="set_background", arguments={"color": "#0a0e2a"}, description="Set dark night sky background"),
            ParsedIntent(tool_name="set_ambient_level", arguments={"intensity": 0.15, "color": "#2a3a6a"}, description="Lower ambient light for night"),
            ParsedIntent(tool_name="add_light", arguments={"light_type": "directional", "color": "#6a8aff", "intensity": 0.3, "position": [2, 5, 3]}, description="Add cool moonlight"),
        ],
        "winter": [
            ParsedIntent(tool_name="set_background", arguments={"color": "#c8dde8"}, description="Set pale winter sky background"),
            ParsedIntent(tool_name="set_fog", arguments={"color": "#dde8f0", "density": 0.03}, description="Add cold winter fog"),
            ParsedIntent(tool_name="set_ambient_level", arguments={"intensity": 0.5, "color": "#aabbcc"}, description="Set cool winter ambient"),
        ],
        "desert": [
            ParsedIntent(tool_name="set_background", arguments={"color": "#e8c890"}, description="Set warm desert sky background"),
            ParsedIntent(tool_name="set_fog", arguments={"color": "#d4a868", "density": 0.015}, description="Add hazy desert fog"),
            ParsedIntent(tool_name="add_light", arguments={"light_type": "directional", "color": "#ffd49a", "intensity": 1.8, "position": [4, 3, 2]}, description="Add hot desert sun"),
        ],
    }

    _ATMOSPHERE_TRIGGERS: List[Tuple[List[str], str]] = [
        (["make a sunset", "sunset lighting", "sunset scene", "make it sunset", "create a sunset", "日落场景", "制作日落"], "sunset"),
        (["look like night", "night scene", "make it night", "nighttime", "night time", "夜晚场景", "变成夜晚"], "night"),
        (["look like winter", "winter scene", "snow scene", "make it winter", "winter time", "冬天场景", "雪景"], "winter"),
        (["desert scene", "desert landscape", "make it desert", "sahara", "沙漠场景"], "desert"),
    ]

    for triggers, preset_name in _ATMOSPHERE_TRIGGERS:
        if any(t in msg_lower for t in triggers):
            return list(_ATMOSPHERE_PRESETS[preset_name])

    # --- Natural features ---
    if any(k in msg_lower for k in ["add water", "create water", "water plane", "ocean plane", "添加水", "创建水面"]):
        return [
            ParsedIntent(tool_name="create_object", arguments={"geometry_type": "plane", "name": "Water", "size": [20, 20], "position": [0, 0, 0]}, description="Create water plane"),
            ParsedIntent(tool_name="apply_material_preset", arguments={"target": "Water", "preset": "glass"}, description="Apply glass-like material to water"),
        ]

    if any(k in msg_lower for k in ["add stars", "stars to the sky", "starry sky", "create stars", "添加星星", "星空"]):
        return [
            ParsedIntent(tool_name="create_particle_system", arguments={"target": "stars", "count": 200, "spread": [30, 20, 30], "color": "#ffffff", "size": 0.05}, description="Create starfield particle system"),
        ]

    if any(k in msg_lower for k in ["mountain landscape", "create mountains", "mountain range", "mountain scene", "山脉", "创建山"]):
        return [
            ParsedIntent(tool_name="terrain_generator", arguments={"width": 30, "depth": 30, "height": 6, "roughness": 0.7, "seed": 42}, description="Generate mountainous terrain"),
        ]

    # --- Room / scene compositions ---
    _ROOM_COMPOSITIONS: Dict[str, List[ParsedIntent]] = {
        "living_room": [
            ParsedIntent(tool_name="create_object", arguments={"geometry_type": "box", "name": "Floor", "size": [10, 0.1, 8], "position": [0, 0, 0]}, description="Create living room floor"),
            ParsedIntent(tool_name="apply_material_preset", arguments={"target": "Floor", "preset": "wood"}, description="Apply wood floor material"),
            ParsedIntent(tool_name="create_object", arguments={"geometry_type": "box", "name": "Sofa", "size": [3, 1, 1.2], "position": [0, 0.6, -2.5]}, description="Create sofa"),
            ParsedIntent(tool_name="apply_material", arguments={"target": "Sofa", "color": "#8a7a6a", "roughness": 0.9, "metalness": 0.0}, description="Apply fabric-like material to sofa"),
            ParsedIntent(tool_name="create_object", arguments={"geometry_type": "box", "name": "Table", "size": [1.5, 0.5, 0.8], "position": [0, 0.3, 0]}, description="Create coffee table"),
            ParsedIntent(tool_name="apply_material_preset", arguments={"target": "Table", "preset": "wood"}, description="Apply wood material to table"),
            ParsedIntent(tool_name="create_lighting_rig", arguments={"rig_type": "three_point"}, description="Set up three-point lighting"),
        ],
        "bedroom": [
            ParsedIntent(tool_name="create_object", arguments={"geometry_type": "box", "name": "Floor", "size": [8, 0.1, 8], "position": [0, 0, 0]}, description="Create bedroom floor"),
            ParsedIntent(tool_name="apply_material_preset", arguments={"target": "Floor", "preset": "wood"}, description="Apply wood floor material"),
            ParsedIntent(tool_name="create_object", arguments={"geometry_type": "box", "name": "Bed", "size": [2, 0.5, 3], "position": [0, 0.3, 0]}, description="Create bed frame"),
            ParsedIntent(tool_name="apply_material", arguments={"target": "Bed", "color": "#6a7a8a", "roughness": 0.85, "metalness": 0.0}, description="Apply fabric-like material to bed"),
            ParsedIntent(tool_name="create_object", arguments={"geometry_type": "box", "name": "Nightstand", "size": [0.5, 0.5, 0.5], "position": [1.3, 0.3, 1]}, description="Create nightstand"),
            ParsedIntent(tool_name="add_light", arguments={"light_type": "point", "intensity": 0.5, "color": "#ffe4b5", "position": [1.3, 1.2, 1]}, description="Add warm bedside lamp"),
        ],
        "kitchen": [
            ParsedIntent(tool_name="create_object", arguments={"geometry_type": "box", "name": "Floor", "size": [8, 0.1, 6], "position": [0, 0, 0]}, description="Create kitchen floor"),
            ParsedIntent(tool_name="apply_material_preset", arguments={"target": "Floor", "preset": "marble"}, description="Apply marble floor material"),
            ParsedIntent(tool_name="create_object", arguments={"geometry_type": "box", "name": "Counter", "size": [4, 0.9, 0.6], "position": [0, 0.5, -2]}, description="Create kitchen counter"),
            ParsedIntent(tool_name="apply_material_preset", arguments={"target": "Counter", "preset": "marble"}, description="Apply marble counter material"),
            ParsedIntent(tool_name="create_object", arguments={"geometry_type": "box", "name": "Cabinet", "size": [4, 0.8, 0.5], "position": [0, 1.5, -2.3]}, description="Create upper cabinet"),
            ParsedIntent(tool_name="apply_material_preset", arguments={"target": "Cabinet", "preset": "wood"}, description="Apply wood cabinet material"),
            ParsedIntent(tool_name="create_lighting_rig", arguments={"rig_type": "studio"}, description="Set up studio lighting"),
        ],
        "playground": [
            ParsedIntent(tool_name="create_object", arguments={"geometry_type": "plane", "name": "Ground", "size": [20, 20], "position": [0, 0, 0]}, description="Create playground ground"),
            ParsedIntent(tool_name="apply_material", arguments={"target": "Ground", "color": "#4a8a3a", "roughness": 0.95, "metalness": 0.0}, description="Apply grass-like material to ground"),
            ParsedIntent(tool_name="create_object", arguments={"geometry_type": "cylinder", "name": "SlidePole", "radius": 0.1, "height": 3, "position": [2, 1.5, 0]}, description="Create slide pole"),
            ParsedIntent(tool_name="create_object", arguments={"geometry_type": "torus", "name": "Swing", "radius": 0.8, "tube": 0.05, "position": [-2, 1.5, 0]}, description="Create swing frame"),
            ParsedIntent(tool_name="add_light", arguments={"light_type": "directional", "intensity": 1.5, "position": [5, 8, 3]}, description="Add bright outdoor light"),
        ],
    }

    _ROOM_TRIGGERS: List[Tuple[List[str], str]] = [
        (["living room", "lounge room", "客厅"], "living_room"),
        (["bedroom", "bed room", "卧室", "睡房"], "bedroom"),
        (["kitchen scene", "kitchen room", "厨房"], "kitchen"),
        (["playground", "play ground", "游乐场", "操场"], "playground"),
    ]

    for triggers, room_key in _ROOM_TRIGGERS:
        if any(t in msg_lower for t in triggers):
            return list(_ROOM_COMPOSITIONS[room_key])

    # --- Furniture / object creation ---
    _FURNITURE_MAP: Dict[str, ParsedIntent] = {
        "table": ParsedIntent(tool_name="create_object", arguments={"geometry_type": "box", "name": "Table", "size": [1.5, 0.05, 0.8], "position": [0, 0.75, 0]}, description="Create table"),
        "chair": ParsedIntent(tool_name="create_object", arguments={"geometry_type": "box", "name": "Chair", "size": [0.5, 0.05, 0.5], "position": [0, 0.4, 0.6]}, description="Create chair"),
        "car": ParsedIntent(tool_name="create_object", arguments={"geometry_type": "box", "name": "Car", "size": [2, 0.6, 1], "position": [0, 0.4, 0]}, description="Create car body"),
    }

    # "table with chairs" — compound furniture request
    if "table with chair" in msg_lower or "table and chair" in msg_lower:
        result = [_FURNITURE_MAP["table"]]
        for offset in [-0.8, 0.8]:
            chair = ParsedIntent(
                tool_name="create_object",
                arguments={"geometry_type": "box", "name": "Chair", "size": [0.5, 0.05, 0.5], "position": [offset, 0.4, 0.6]},
                description=f"Create chair at x={offset}",
            )
            result.append(chair)
        return result

    if "furniture" in msg_lower or "家具" in msg_lower:
        return [
            ParsedIntent(tool_name="create_object", arguments={"geometry_type": "box", "name": "Table", "size": [1.5, 0.05, 0.8], "position": [0, 0.75, 0]}, description="Create table"),
            ParsedIntent(tool_name="create_object", arguments={"geometry_type": "box", "name": "Chair", "size": [0.5, 0.05, 0.5], "position": [-0.8, 0.4, 0.6]}, description="Create chair 1"),
            ParsedIntent(tool_name="create_object", arguments={"geometry_type": "box", "name": "Chair", "size": [0.5, 0.05, 0.5], "position": [0.8, 0.4, 0.6]}, description="Create chair 2"),
        ]

    for keyword, intent in _FURNITURE_MAP.items():
        if f"add a {keyword}" in msg_lower or f"create a {keyword}" in msg_lower or f"add {keyword}" in msg_lower:
            return [intent]

    # --- Chess board pattern ---
    if "chess board" in msg_lower or "chessboard" in msg_lower or "棋盘" in msg_lower:
        result: List[ParsedIntent] = []
        for row in range(8):
            for col in range(8):
                is_white = (row + col) % 2 == 0
                color = "#f0f0f0" if is_white else "#1a1a1a"
                result.append(ParsedIntent(
                    tool_name="create_object",
                    arguments={
                        "geometry_type": "box",
                        "name": f"Square_{row}_{col}",
                        "size": [0.5, 0.05, 0.5],
                        "position": [col * 0.5 - 1.75, 0.025, row * 0.5 - 1.75],
                        "color": color,
                    },
                    description=f"Create chess square ({row},{col})",
                ))
        return result

    # --- Additional atmosphere presets: ocean, forest, rainy, dawn, cave ---
    _ATMOSPHERE_PRESETS_EXTRA: Dict[str, List[ParsedIntent]] = {
        "ocean": [
            ParsedIntent(tool_name="set_background", arguments={"color": "#1a4a7a"}, description="Set deep ocean sky background"),
            ParsedIntent(tool_name="set_fog", arguments={"color": "#3a6a9a", "density": 0.01}, description="Add ocean horizon fog"),
            ParsedIntent(tool_name="set_ambient_level", arguments={"intensity": 0.4, "color": "#4a7aaa"}, description="Set blue ocean ambient"),
            ParsedIntent(tool_name="create_object", arguments={"geometry_type": "plane", "name": "Water", "size": [30, 30], "position": [0, 0, 0]}, description="Create ocean plane"),
            ParsedIntent(tool_name="apply_material_preset", arguments={"target": "Water", "preset": "glass"}, description="Apply glass water material"),
            ParsedIntent(tool_name="add_light", arguments={"light_type": "directional", "color": "#ffffff", "intensity": 1.0, "position": [3, 5, 2]}, description="Add overhead ocean sun"),
        ],
        "forest": [
            ParsedIntent(tool_name="set_background", arguments={"color": "#3a5a2a"}, description="Set deep forest background"),
            ParsedIntent(tool_name="set_fog", arguments={"color": "#5a6a4a", "density": 0.015}, description="Add misty forest fog"),
            ParsedIntent(tool_name="set_ambient_level", arguments={"intensity": 0.35, "color": "#6a7a5a"}, description="Set shaded forest ambient"),
            ParsedIntent(tool_name="create_object", arguments={"geometry_type": "plane", "name": "ForestGround", "size": [30, 30], "position": [0, 0, 0]}, description="Create forest ground"),
            ParsedIntent(tool_name="apply_material", arguments={"target": "ForestGround", "color": "#4a6a3a", "roughness": 0.95, "metalness": 0.0}, description="Apply forest floor material"),
        ],
        "rainy": [
            ParsedIntent(tool_name="set_background", arguments={"color": "#4a5a6a"}, description="Set overcast rainy sky background"),
            ParsedIntent(tool_name="set_fog", arguments={"color": "#6a7a8a", "density": 0.025}, description="Add heavy rain fog"),
            ParsedIntent(tool_name="set_ambient_level", arguments={"intensity": 0.3, "color": "#7a8a9a"}, description="Dim overcast ambient light"),
            ParsedIntent(tool_name="create_particle_system", arguments={"target": "rain", "count": 500, "spread": [15, 8, 15], "color": "#aadfff", "size": 0.03}, description="Create rain particle system"),
        ],
        "dawn": [
            ParsedIntent(tool_name="set_background", arguments={"color": "#e8a07a"}, description="Set warm dawn sky background"),
            ParsedIntent(tool_name="set_fog", arguments={"color": "#f2c4a0", "density": 0.012}, description="Add soft dawn fog"),
            ParsedIntent(tool_name="set_ambient_level", arguments={"intensity": 0.5, "color": "#f0d0b0"}, description="Set dawn ambient glow"),
            ParsedIntent(tool_name="add_light", arguments={"light_type": "directional", "color": "#ffb080", "intensity": 1.2, "position": [-5, 1, 2]}, description="Add low-angle dawn sunlight"),
        ],
        "cave": [
            ParsedIntent(tool_name="set_background", arguments={"color": "#1a1218"}, description="Set dark cave background"),
            ParsedIntent(tool_name="set_fog", arguments={"color": "#2a2028", "density": 0.035}, description="Add thick cave fog"),
            ParsedIntent(tool_name="set_ambient_level", arguments={"intensity": 0.08, "color": "#3a2030"}, description="Very low purple ambient for caves"),
            ParsedIntent(tool_name="add_light", arguments={"light_type": "point", "color": "#ffa040", "intensity": 0.8, "position": [0, 2, 0]}, description="Add torch-like warm point light"),
        ],
        "underwater": [
            ParsedIntent(tool_name="set_background", arguments={"color": "#0a3a4a"}, description="Set deep underwater background"),
            ParsedIntent(tool_name="set_fog", arguments={"color": "#1a5a6a", "density": 0.04}, description="Add dense water fog"),
            ParsedIntent(tool_name="set_ambient_level", arguments={"intensity": 0.3, "color": "#2a6a8a"}, description="Blue caustic ambient"),
            ParsedIntent(tool_name="create_particle_system", arguments={"target": "bubbles", "count": 300, "spread": [10, 6, 10], "color": "#aaddff", "size": 0.04}, description="Create bubble particle system"),
        ],
        "beach": [
            ParsedIntent(tool_name="set_background", arguments={"color": "#87ceeb"}, description="Set clear beach sky background"),
            ParsedIntent(tool_name="set_fog", arguments={"color": "#c0e0f0", "density": 0.008}, description="Light sea haze fog"),
            ParsedIntent(tool_name="set_ambient_level", arguments={"intensity": 0.7, "color": "#e0f0ff"}, description="Bright beach ambient"),
            ParsedIntent(tool_name="create_object", arguments={"geometry_type": "plane", "name": "Sand", "size": [20, 20], "position": [0, 0, 0]}, description="Create sand ground"),
            ParsedIntent(tool_name="apply_material", arguments={"target": "Sand", "color": "#e8d090", "roughness": 0.9, "metalness": 0.0}, description="Apply sandy material"),
            ParsedIntent(tool_name="add_light", arguments={"light_type": "directional", "color": "#ffffff", "intensity": 1.8, "position": [5, 8, 3]}, description="Add bright tropical sun"),
        ],
    }

    _ATMOSPHERE_TRIGGERS_EXTRA: List[Tuple[List[str], str]] = [
        (["ocean scene", "make an ocean", "under the sea", "create an ocean", "海洋场景", "海洋"], "ocean"),
        (["forest scene", "make a forest", "deep forest", "create a forest", "森林场景", "森林"], "forest"),
        (["rainy scene", "make it rain", "rain weather", "rainy day", "下雨场景", "雨天", "下雨"], "rainy"),
        (["dawn scene", "make it dawn", "early morning", "sunrise scene", "黎明场景", "日出", "清晨"], "dawn"),
        (["cave scene", "make a cave", "inside a cave", "cavern scene", "洞穴场景", "洞穴"], "cave"),
        (["underwater scene", "under water scene", "make it underwater", "海底场景", "水下"], "underwater"),
        (["beach scene", "make a beach", "tropical beach", "create a beach", "海滩场景", "沙滩"], "beach"),
    ]

    for triggers, preset_name in _ATMOSPHERE_TRIGGERS_EXTRA:
        if any(t in msg_lower for t in triggers):
            return list(_ATMOSPHERE_PRESETS_EXTRA[preset_name])

    # --- Extended natural features ---
    if any(k in msg_lower for k in ["add clouds", "cloudy sky", "create clouds", "sky with clouds", "添加云朵", "有云", "天空的云"]):
        return [
            ParsedIntent(tool_name="create_particle_system", arguments={"target": "clouds", "count": 40, "spread": [20, 5, 10], "color": "#ffffff", "size": 0.8}, description="Create fluffy cloud particles"),
        ]

    if any(k in msg_lower for k in ["add leaves falling", "falling leaves", "autumn leaves", "落叶", "秋天的叶子"]):
        return [
            ParsedIntent(tool_name="create_particle_system", arguments={"target": "leaves", "count": 150, "spread": [15, 10, 15], "color": "#d08a3a", "size": 0.1}, description="Create falling autumn leaves"),
        ]

    if any(k in msg_lower for k in [
        "add snowfall", "snow falling", "snow particles", "snowfall",
        "下雪", "雪花飘落", "降雪", "下雪天", "雪天",
    ]):
        return [
            ParsedIntent(tool_name="set_background", arguments={"color": "#d8e8f0"}, description="Set snowy sky background"),
            ParsedIntent(tool_name="create_particle_system", arguments={"target": "snow", "count": 400, "spread": [15, 12, 15], "color": "#ffffff", "size": 0.04}, description="Create snowfall particle system"),
        ]

    if any(k in msg_lower for k in ["create a city", "city scene", "cityscape", "skyscraper scene", "make a city", "城市场景", "城市", "都市"]):
        _city: List[ParsedIntent] = [
            ParsedIntent(tool_name="create_object", arguments={"geometry_type": "plane", "name": "CityGround", "size": [30, 30], "position": [0, 0, 0]}, description="Create city ground plane"),
            ParsedIntent(tool_name="apply_material", arguments={"target": "CityGround", "color": "#3a3a3a", "roughness": 0.8, "metalness": 0.2}, description="Apply asphalt ground material"),
        ]
        for i in range(12):
            rng = random.Random(1000 + i)
            h = rng.uniform(1.5, 5)
            w = rng.uniform(0.8, 1.6)
            d = rng.uniform(0.8, 1.6)
            x = rng.uniform(-10, 10)
            z = rng.uniform(-10, 10)
            bw = 0.6 + rng.random() * 0.4
            _city.append(ParsedIntent(
                tool_name="create_object",
                arguments={
                    "geometry_type": "box",
                    "name": f"Building_{i}",
                    "size": [w, h, d],
                    "position": [x, h / 2, z],
                    "color": f"#{int(bw * 80 + 80):02x}{int(bw * 80 + 80):02x}{int(bw * 80 + 100):02x}",
                },
                description=f"Create skyscraper {i}",
            ))
        _city.append(ParsedIntent(tool_name="set_ambient_level", arguments={"intensity": 0.4, "color": "#6a6a7a"}, description="Set city ambient"))
        _city.append(ParsedIntent(tool_name="add_light", arguments={"light_type": "directional", "color": "#fff0d0", "intensity": 1.0, "position": [5, 6, 3]}, description="Add city sunlight"))
        return _city

    if any(k in msg_lower for k in ["create a crystal garden", "crystal scene", "gem garden", "水晶花园", "水晶场景"]):
        _crystals: List[ParsedIntent] = [
            ParsedIntent(tool_name="create_object", arguments={"geometry_type": "plane", "name": "CrystalGround", "size": [12, 12], "position": [0, 0, 0]}, description="Create crystal garden ground"),
            ParsedIntent(tool_name="apply_material_preset", arguments={"target": "CrystalGround", "preset": "marble"}, description="Apply marble ground material"),
        ]
        _crystal_colors = ["#ff6aaa", "#6affaa", "#6aaa6a", "#ffaa6a", "#aa6aff", "#6a6aff", "#aaffff"]
        for i in range(9):
            angle = (i / 9) * 6.283
            r = 2.0 + (i % 3) * 0.8
            x = r * math.cos(angle)
            z = r * math.sin(angle)
            h = 0.8 + (i % 4) * 0.5
            _crystals.append(ParsedIntent(
                tool_name="create_object",
                arguments={
                    "geometry_type": "cone",
                    "name": f"Crystal_{i}",
                    "radius": 0.2,
                    "height": h,
                    "position": [x, h / 2, z],
                    "color": _crystal_colors[i % len(_crystal_colors)],
                    "metalness": 0.3,
                    "roughness": 0.15,
                },
                description=f"Create colored crystal {i}",
            ))
        _crystals.append(ParsedIntent(tool_name="set_background", arguments={"color": "#1a0a2a"}, description="Set dark crystalline background"))
        _crystals.append(ParsedIntent(tool_name="add_light", arguments={"light_type": "point", "color": "#ff88ff", "intensity": 0.8, "position": [0, 3, 0]}, description="Add central colored glow"))
        return _crystals

    if any(k in msg_lower for k in ["create a solar system", "solar system scene", "make a solar system", "solar system", "太阳系", "行星系统"]):
        _solar: List[ParsedIntent] = [
            ParsedIntent(tool_name="set_background", arguments={"color": "#050508"}, description="Set deep space background"),
            ParsedIntent(tool_name="create_particle_system", arguments={"target": "stars", "count": 500, "spread": [40, 25, 40], "color": "#ffffff", "size": 0.05}, description="Create starfield background"),
            ParsedIntent(tool_name="create_object", arguments={"geometry_type": "sphere", "name": "Sun", "radius": 1.2, "position": [0, 0, 0], "color": "#ffcc00", "metalness": 0.0, "roughness": 0.3, "emissive": "#ff9900"}, description="Create the sun with emissive glow"),
        ]
        _planets = [
            ("Mercury", 0.3, 2.2, "#a0a090"),
            ("Venus",   0.5, 3.0, "#e8c080"),
            ("Earth",   0.55, 3.8, "#4a7ab8"),
            ("Mars",    0.4, 4.6, "#c06040"),
            ("Jupiter", 0.9, 6.0, "#d0a070"),
            ("Saturn",  0.75, 7.5, "#e0c090"),
        ]
        for name, radius, dist, color in _planets:
            _solar.append(ParsedIntent(
                tool_name="create_object",
                arguments={
                    "geometry_type": "sphere",
                    "name": name,
                    "radius": radius,
                    "position": [dist, 0, 0],
                    "color": color,
                },
                description=f"Create planet {name}",
            ))
            _solar.append(ParsedIntent(
                tool_name="orbit_animation",
                arguments={
                    "target": name,
                    "radius": dist,
                    "height": 0,
                    "speed": 0.5 / (dist * 0.3),
                    "clockwise": False,
                },
                description=f"Orbit animation for {name}",
            ))
        return _solar

    if any(k in msg_lower for k in ["create a garden", "flower garden", "botanical garden", "花园场景", "花园", "植物园"]):
        _garden: List[ParsedIntent] = [
            ParsedIntent(tool_name="create_object", arguments={"geometry_type": "plane", "name": "GardenGround", "size": [16, 16], "position": [0, 0, 0]}, description="Create garden ground"),
            ParsedIntent(tool_name="apply_material", arguments={"target": "GardenGround", "color": "#4a8a3a", "roughness": 0.95, "metalness": 0.0}, description="Apply grass material"),
        ]
        _flower_colors = ["#e84a4a", "#e8c04a", "#e84ae8", "#4ae8e8", "#ffffff", "#e8a04a", "#aa4ae8"]
        for i in range(20):
            rng = random.Random(500 + i)
            x = rng.uniform(-6, 6)
            z = rng.uniform(-6, 6)
            color = _flower_colors[i % len(_flower_colors)]
            _garden.append(ParsedIntent(
                tool_name="create_object",
                arguments={
                    "geometry_type": "box",
                    "name": f"Stem_{i}",
                    "size": [0.04, 0.5, 0.04],
                    "position": [x, 0.25, z],
                    "color": "#3a6a2a",
                },
                description=f"Create flower stem {i}",
            ))
            _garden.append(ParsedIntent(
                tool_name="create_object",
                arguments={
                    "geometry_type": "sphere",
                    "name": f"Flower_{i}",
                    "radius": 0.08,
                    "position": [x, 0.55, z],
                    "color": color,
                },
                description=f"Create flower bloom {i}",
            ))
        _garden.append(ParsedIntent(tool_name="set_background", arguments={"color": "#87ceeb"}, description="Set clear blue sky background"))
        _garden.append(ParsedIntent(tool_name="add_light", arguments={"light_type": "directional", "intensity": 1.3, "position": [3, 5, 2]}, description="Add garden sunlight"))
        return _garden

    # --- Tower / castle ---
    if any(k in msg_lower for k in ["make a tower", "create a tower", "tower scene", "castle scene", "make a castle", "create a castle", "塔", "城堡"]):
        _tower: List[ParsedIntent] = [
            ParsedIntent(tool_name="create_object", arguments={"geometry_type": "plane", "name": "TowerGround", "size": [15, 15], "position": [0, 0, 0]}, description="Create ground"),
            ParsedIntent(tool_name="apply_material", arguments={"target": "TowerGround", "color": "#5a5a4a", "roughness": 0.9, "metalness": 0.0}, description="Apply stone ground material"),
        ]
        # Central tower
        for i in range(5):
            r = 1.2 - i * 0.12
            h = 1.5
            _tower.append(ParsedIntent(
                tool_name="create_object",
                arguments={"geometry_type": "cylinder", "name": f"TowerSeg_{i}", "radius": r, "height": h, "position": [0, 0.75 + i * 1.5, 0], "color": "#9a9a8a"},
                description=f"Create tower segment {i}",
            ))
        # Corner turrets
        for idx, (cx, cz) in enumerate([(-3, -3), (3, -3), (-3, 3), (3, 3)]):
            _tower.append(ParsedIntent(
                tool_name="create_object",
                arguments={"geometry_type": "cylinder", "name": f"Turret_{idx}", "radius": 0.6, "height": 4, "position": [cx, 2, cz], "color": "#8a8a7a"},
                description=f"Create corner turret {idx}",
            ))
        _tower.append(ParsedIntent(tool_name="set_background", arguments={"color": "#4a5a7a"}, description="Set dramatic sky background"))
        _tower.append(ParsedIntent(tool_name="add_light", arguments={"light_type": "directional", "color": "#ffe0c0", "intensity": 1.2, "position": [4, 6, 2]}, description="Add dramatic lighting"))
        return _tower

    # --- Campfire ---
    if any(k in msg_lower for k in ["make a campfire", "create a campfire", "campfire", "make a fire", "create a fire", "make fire", "add fire", "篝火", "生火"]):
        return [
            ParsedIntent(tool_name="create_object", arguments={"geometry_type": "cylinder", "name": "Log_0", "radius": 0.08, "height": 1.5, "position": [0, 0.15, 0], "rotation": [0, 0, 1.57], "color": "#4a2a1a"}, description="Create fire log 1"),
            ParsedIntent(tool_name="create_object", arguments={"geometry_type": "cylinder", "name": "Log_1", "radius": 0.08, "height": 1.5, "position": [0, 0.15, 0], "rotation": [0, 1.57, 0.3], "color": "#3a2a1a"}, description="Create fire log 2"),
            ParsedIntent(tool_name="create_object", arguments={"geometry_type": "sphere", "name": "Ember", "radius": 0.3, "position": [0, 0.3, 0], "color": "#ff4400", "emissive": "#ff6600"}, description="Create glowing ember"),
            ParsedIntent(tool_name="create_particle_system", arguments={"target": "fire", "count": 100, "spread": [1, 3, 1], "color": "#ff6600", "size": 0.12}, description="Create fire particle system"),
            ParsedIntent(tool_name="add_light", arguments={"light_type": "point", "color": "#ff8800", "intensity": 2.0, "position": [0, 1, 0]}, description="Add warm fire light"),
            ParsedIntent(tool_name="set_background", arguments={"color": "#0a0a15"}, description="Set dark night background for fire contrast"),
            ParsedIntent(tool_name="set_ambient_level", arguments={"intensity": 0.15, "color": "#3a2a1a"}, description="Dim ambient for night campfire"),
        ]

    # --- Swimming pool ---
    if any(k in msg_lower for k in ["make a pool", "create a pool", "swimming pool", "make a swimming pool", "游泳池", "泳池"]):
        return [
            ParsedIntent(tool_name="create_object", arguments={"geometry_type": "box", "name": "PoolDeck", "size": [8, 0.2, 8], "position": [0, 0, 0], "color": "#d0d0d0"}, description="Create pool deck"),
            ParsedIntent(tool_name="create_object", arguments={"geometry_type": "box", "name": "PoolWater", "size": [6, 0.8, 6], "position": [0, 0.3, 0], "color": "#2a8acc"}, description="Create pool water"),
            ParsedIntent(tool_name="apply_material_preset", arguments={"target": "PoolWater", "preset": "glass"}, description="Apply glass material to pool water"),
            ParsedIntent(tool_name="set_background", arguments={"color": "#87ceeb"}, description="Set clear sky background"),
            ParsedIntent(tool_name="add_light", arguments={"light_type": "directional", "color": "#ffffff", "intensity": 1.5, "position": [5, 8, 3]}, description="Add bright sunlight"),
            ParsedIntent(tool_name="set_ambient_level", arguments={"intensity": 0.6, "color": "#e0f0ff"}, description="Set bright ambient"),
        ]

    # --- Staircase ---
    if any(k in msg_lower for k in ["make a staircase", "create a staircase", "make stairs", "create stairs", "staircase", "楼梯", "台阶"]):
        _stairs: List[ParsedIntent] = []
        for i in range(12):
            _stairs.append(ParsedIntent(
                tool_name="create_object",
                arguments={"geometry_type": "box", "name": f"Step_{i}", "size": [2, 0.2, 0.3], "position": [0, 0.1 + i * 0.2, i * 0.3], "color": "#b0a090"},
                description=f"Create stair step {i}",
            ))
        _stairs.append(ParsedIntent(tool_name="set_ambient_level", arguments={"intensity": 0.5, "color": "#ffffff"}, description="Set ambient light"))
        _stairs.append(ParsedIntent(tool_name="add_light", arguments={"light_type": "directional", "color": "#ffffff", "intensity": 1.0, "position": [3, 5, 2]}, description="Add overhead light"))
        return _stairs

    # --- Rainbow ---
    if any(k in msg_lower for k in ["make a rainbow", "create a rainbow", "add a rainbow", "rainbow", "彩虹"]):
        _rainbow: List[ParsedIntent] = []
        _rainbow_colors = ["#ff0000", "#ff7f00", "#ffff00", "#00ff00", "#0000ff", "#4b0082", "#9400d3"]
        for i, color in enumerate(_rainbow_colors):
            _rainbow.append(ParsedIntent(
                tool_name="create_object",
                arguments={"geometry_type": "torus", "name": f"Rainbow_{i}", "radius": 5 + i * 0.15, "tube": 0.08, "position": [0, 0, 0], "rotation": [1.57, 0, 0], "color": color, "emissive": color},
                description=f"Create rainbow arc {i}",
            ))
        _rainbow.append(ParsedIntent(tool_name="set_background", arguments={"color": "#87ceeb"}, description="Set clear sky for rainbow"))
        _rainbow.append(ParsedIntent(tool_name="set_ambient_level", arguments={"intensity": 0.6, "color": "#ffffff"}, description="Set bright ambient"))
        return _rainbow

    return []


# ---------------------------------------------------------------------------
# Multimodal generation intent helpers
# ---------------------------------------------------------------------------

# Trigger phrases for each generation modality. Order matters: more specific
# phrases are listed first so the prompt extraction strips them correctly.
_IMAGE_TRIGGERS: List[str] = [
    "generate an image of", "generate a picture of", "generate image of",
    "create an image of", "create a picture of", "create image of",
    "draw a picture of", "draw an image of",
    "text to image", "text-to-image",
    "生成一张图片", "生成图片", "画一张", "画一幅",
    "生成一张图像", "生成图像",
    # Shorter forms (listed last so longer triggers match first in _strip_trigger)
    "generate an image", "generate image",
    "create an image", "create image",
    "draw an image", "draw a picture", "draw image",
]
_3D_ASSET_TRIGGERS: List[str] = [
    "generate a 3d model of", "generate a 3d asset of", "generate 3d model of",
    "generate 3d asset of", "generate a 3d asset", "generate a 3d model",
    "create a 3d model of", "create a 3d asset of", "create 3d model of",
    "create a 3d asset", "create a 3d model",
    "text to 3d", "text-to-3d", "text to 3 d",
    "生成3d模型", "生成3D模型", "生成一个3d", "生成一个3D",
    "创建3d模型", "创建3D模型",
]
_VIDEO_TRIGGERS: List[str] = [
    "generate a video of", "generate video of", "generate a video",
    "create a video of", "create video of", "create a video",
    "text to video", "text-to-video",
    "生成一段视频", "生成视频", "创建视频", "创建一段视频",
]
_ANIMATION_TRIGGERS: List[str] = [
    "generate an animation of", "generate animation of", "generate an animation",
    "generate a animation of", "generate a animation",
    "create an animation of", "create animation of", "create an animation",
    "create a animation of", "create a animation",
    "text to animation", "text-to-animation",
    "生成一段动画", "生成动画", "创建动画", "创建一段动画",
]
_SPEECH_TRIGGERS: List[str] = [
    "read aloud", "read this aloud", "read out loud", "read this out loud",
    "synthesize speech", "text to speech", "text-to-speech", "say this",
    "speak this", "朗读", "读出来", "语音合成", "转语音", "转为语音",
]


def _strip_trigger(text: str, triggers: List[str]) -> str:
    """Remove the first matching trigger phrase from the text and tidy up."""
    for trig in triggers:
        if trig in text.lower():
            # Remove the trigger (case-insensitive) from the original message
            idx = text.lower().find(trig)
            if idx >= 0:
                text = text[:idx] + text[idx + len(trig):]
            break
    return text.strip(" :,.-\"'“”‘’")


def _parse_multimodal_intent(msg_lower: str, msg_original: str) -> Optional[ParsedIntent]:
    """Detect a multimodal generation command and build the corresponding intent.

    Returns None when the message does not match any generation trigger, so
    the caller can continue with the offline fallback handling.
    """
    # Speech synthesis — checked first because "read" is a common word
    if any(k in msg_lower for k in _SPEECH_TRIGGERS):
        text_payload = _strip_trigger(msg_original, _SPEECH_TRIGGERS)
        if not text_payload:
            return None
        # Capture an optional voice name
        voice = "alloy"
        for v in ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]:
            if v in msg_lower:
                voice = v
                break
        return ParsedIntent(
            tool_name="synthesize_speech",
            arguments={"text": text_payload, "voice": voice},
            description=f"Synthesize speech from text",
        )

    # Image generation
    if any(k in msg_lower for k in _IMAGE_TRIGGERS):
        prompt = _strip_trigger(msg_original, _IMAGE_TRIGGERS)
        if not prompt:
            return None
        size = "1024x1024"
        size_match = re.search(r'(\d{3,4})\s*[x×]\s*(\d{3,4})', msg_lower)
        if size_match:
            size = f"{size_match.group(1)}x{size_match.group(2)}"
        return ParsedIntent(
            tool_name="generate_image",
            arguments={"prompt": prompt, "size": size},
            description=f"Generate image from prompt",
        )

    # 3D asset generation (distinct from image-to-3D reconstruction)
    if any(k in msg_lower for k in _3D_ASSET_TRIGGERS):
        prompt = _strip_trigger(msg_original, _3D_ASSET_TRIGGERS)
        if not prompt:
            return None
        output_format = "glb"
        for fmt in ["glb", "obj", "fbx", "usdz"]:
            if fmt in msg_lower:
                output_format = fmt
                break
        return ParsedIntent(
            tool_name="generate_3d_asset",
            arguments={"prompt": prompt, "output_format": output_format},
            description=f"Generate 3D asset from prompt",
        )

    # Video generation
    if any(k in msg_lower for k in _VIDEO_TRIGGERS):
        prompt = _strip_trigger(msg_original, _VIDEO_TRIGGERS)
        if not prompt:
            return None
        duration = 5
        dur_match = re.search(r'(\d+)\s*(?:second|sec|s|秒)', msg_lower)
        if dur_match:
            duration = max(1, min(30, int(dur_match.group(1))))
        return ParsedIntent(
            tool_name="generate_video",
            arguments={"prompt": prompt, "duration": duration},
            description=f"Generate video from prompt",
        )

    # Animation generation
    if any(k in msg_lower for k in _ANIMATION_TRIGGERS):
        prompt = _strip_trigger(msg_original, _ANIMATION_TRIGGERS)
        if not prompt:
            return None
        frames = 24
        frame_match = re.search(r'(\d+)\s*(?:frame|帧)', msg_lower)
        if frame_match:
            frames = max(1, min(120, int(frame_match.group(1))))
        return ParsedIntent(
            tool_name="generate_animation",
            arguments={"prompt": prompt, "frames": frames},
            description=f"Generate animation from prompt",
        )

    return None


# ---------------------------------------------------------------------------
# Pipeline intent helpers
# ---------------------------------------------------------------------------

# Connectors that join multi-step generation requests. Longer phrases first
# so "and then" is matched before "then" during splitting.
_PIPELINE_CONNECTORS: List[str] = [
    "and then", "after that", "then", "->", "→", "&&",
    "然后", "接着", "之后",
]

# Explicit pipeline declaration keywords.
_PIPELINE_KEYWORDS: List[str] = [
    "pipeline", "workflow", "chain", "sequence",
    "流水线", "链路", "工作流",
]

# LLM prompt-crafting step triggers.
_LLM_STEP_TRIGGERS: List[str] = [
    "write a prompt", "craft a prompt", "compose a prompt",
    "write a description", "come up with a prompt",
    "describe a", "describe the",
    "写一段", "描述", "构思", "编写",
]

# Triggers for the image-to-3D conversion step within a pipeline.
_IMG_TO_3D_STEP_TRIGGERS: List[str] = [
    "convert to 3d", "turn to 3d", "turn into 3d", "make it 3d",
    "make 3d", "to 3d", "into 3d",
    "转3d", "转3D", "变成3d", "变成3D", "转为3d", "转为3D",
]


def _triggers_for_step(step_type: str) -> List[str]:
    """Return the trigger phrase list associated with a pipeline step type."""
    return {
        "generate_image": _IMAGE_TRIGGERS,
        "generate_3d": _3D_ASSET_TRIGGERS,
        "generate_video": _VIDEO_TRIGGERS,
        "generate_animation": _ANIMATION_TRIGGERS,
        "tts": _SPEECH_TRIGGERS,
        "image_to_3d": _IMG_TO_3D_STEP_TRIGGERS,
        "llm_complete": _LLM_STEP_TRIGGERS,
    }.get(step_type, [])


def _split_pipeline_segments(msg: str) -> List[str]:
    """Split a message into pipeline segments on connector phrases.

    Uses placeholder substitution so multi-word connectors are handled
    before single-word ones, preventing double-splits.
    """
    text = msg
    for i, conn in enumerate(_PIPELINE_CONNECTORS):
        text = text.replace(conn, f"\x00P{i}\x00")
    raw = text.split("\x00")
    segments: List[str] = []
    for s in raw:
        s = s.strip()
        # Drop bare connector artifacts
        if s and not re.fullmatch(r"P\d+", s):
            segments.append(s)
    return segments


def _detect_step_type(segment_lower: str) -> Optional[str]:
    """Identify the pipeline node type for a single segment.

    Returns one of: generate_image, generate_3d, generate_video,
    generate_animation, tts, image_to_3d, llm_complete, or None.
    """
    if any(k in segment_lower for k in _IMAGE_TRIGGERS):
        return "generate_image"
    if any(k in segment_lower for k in _3D_ASSET_TRIGGERS):
        return "generate_3d"
    if any(k in segment_lower for k in _VIDEO_TRIGGERS):
        return "generate_video"
    if any(k in segment_lower for k in _ANIMATION_TRIGGERS):
        return "generate_animation"
    if any(k in segment_lower for k in _SPEECH_TRIGGERS):
        return "tts"
    if any(k in segment_lower for k in _IMG_TO_3D_STEP_TRIGGERS):
        return "image_to_3d"
    if any(k in segment_lower for k in _LLM_STEP_TRIGGERS):
        return "llm_complete"
    return None


def _parse_pipeline_intent(msg_lower: str, msg_original: str) -> Optional[ParsedIntent]:
    """Detect a multi-step pipeline request and build a node list.

    Triggers on either an explicit pipeline/workflow keyword or a connector
    phrase joining two or more generation steps. Each segment is classified
    into a node type (image / 3D / video / animation / speech / LLM) and
    wired to its predecessor: LLM output feeds the next prompt, and image
    output feeds an image-to-3D reconstruction step.

    Returns a ParsedIntent with tool_name="run_pipeline" and a list of
    pipeline node definitions, or None when the message is not a pipeline.
    """
    has_keyword = any(k in msg_lower for k in _PIPELINE_KEYWORDS)
    has_connector = any(c in msg_lower for c in _PIPELINE_CONNECTORS)
    if not (has_keyword or has_connector):
        return None

    segments = _split_pipeline_segments(msg_original)
    if len(segments) < 2:
        return None

    # Classify each segment; bail out if any segment is not a generation step
    steps: List[Tuple[str, str]] = []
    for seg in segments:
        seg_lower = seg.lower()
        step_type = _detect_step_type(seg_lower)
        if step_type is None:
            return None
        prompt = _strip_trigger(seg, _triggers_for_step(step_type))
        steps.append((step_type, prompt))

    if len(steps) < 2:
        return None

    # Build pipeline nodes with inter-node output wiring
    nodes: List[Dict[str, Any]] = []
    prev_id: Optional[str] = None
    prev_type: Optional[str] = None

    for idx, (step_type, prompt) in enumerate(steps):
        node_id = f"step_{idx + 1}"
        inputs: Dict[str, Any] = {}

        if prev_type == "llm_complete" and step_type in (
            "generate_image", "generate_3d", "generate_video", "generate_animation"
        ):
            # LLM output becomes the prompt for this generation step
            inputs["prompt"] = {"from": prev_id, "output": "content"}
        elif prev_type == "generate_image" and step_type in ("image_to_3d", "generate_3d"):
            # Image feeds 3D reconstruction — normalize text-to-3D into
            # image_to_3d so the image payload is consumed
            step_type = "image_to_3d"
            inputs["image_base64"] = {"from": prev_id, "output": "base64_data"}
            if prompt:
                inputs["prompt"] = prompt
        else:
            if step_type == "tts":
                inputs["text"] = prompt or "Hello from Trigen."
            elif step_type == "llm_complete":
                inputs["prompt"] = prompt or "Describe a vivid scene."
            else:
                inputs["prompt"] = prompt or "a 3D scene"

        nodes.append({"id": node_id, "type": step_type, "inputs": inputs})
        prev_id = node_id
        prev_type = step_type

    return ParsedIntent(
        tool_name="run_pipeline",
        arguments={"nodes": nodes},
        description=f"Pipeline: {' -> '.join(s[0] for s in steps)}",
    )
