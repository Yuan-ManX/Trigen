"""Natural language intent parser for offline mode.

Parses user messages into structured tool-call intents, enabling the
offline rule engine to handle transforms, materials, lights, grouping,
deletion, duplication, focus, fog, and scene-level operations without
requiring an LLM API key.
"""

from __future__ import annotations

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
    "金属": "metal", "metal": "metal",
    "玻璃": "glass", "glass": "glass",
    "木头": "wood", "wood": "wood",
    "塑料": "plastic", "plastic": "plastic",
    "橡胶": "rubber", "rubber": "rubber",
    "陶瓷": "ceramic", "ceramic": "ceramic",
    "大理石": "marble", "marble": "marble",
    "霓虹": "neon", "neon": "neon",
    "发光": "emissive", "emissive": "emissive",
    "线框": "wireframe", "wireframe": "wireframe",
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
    ("plant", "l_system"),
    ("植物", "l_system"),
    ("tree", "l_system"),
    ("树", "l_system"),
    ("shatter", "voronoi_shatter"),
    ("碎裂", "voronoi_shatter"),
    ("碎块", "voronoi_shatter"),
    ("碎片", "voronoi_shatter"),
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
    # Check for type mentions (e.g., "the cube", "the sphere")
    for geo_type in GEO_MAP.values():
        if geo_type in msg_lower:
            # Find the first object of this type
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

    # 0. Creative skill invocation (checked first so multi-step recipes
    # take precedence over generic smart_compose templates like "crystal").
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

    # 0b-bis. Generative geometry tools (radial_symmetry / clone_with_jitter)
    # — require a target object. Defaults target to the most recently
    # created object when the user does not name one, and parses count /
    # radius / jitter magnitudes from the message.
    if not matched_any and scene_objects:
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

    # Object animation tools — require a target object to exist
    if not matched_any and scene_objects:
        for phrase, tool_name, kind in ANIMATION_TRIGGERS:
            if phrase in msg_lower:
                target_name = _find_target_name(msg_lower, scene_objects)
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
                    intents.append(ParsedIntent(
                        tool_name=tool_name,
                        arguments=args,
                        description=f"Attach {kind} animation to {target_name}",
                    ))
                    matched_any = True
                    break

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
    if any(kw in msg_lower for kw in list(GEO_MAP.keys())[:20]) and any(
        w in msg_lower for w in ["create", "add", "make", "生成", "创建", "添加", "做一个", "来一个"]
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

    # 3. Transform (move, rotate, scale)
    transform_verbs = ["move", "translate", "position", "rotate", "rotation", "scale", "resize", "移动", "旋转", "缩放", "调整"]
    if any(v in msg_lower for v in transform_verbs) and scene_objects:
        target_name = _find_target_name(msg_lower, scene_objects)
        if target_name:
            is_rotate = any(v in msg_lower for v in ["rotate", "rotation", "旋转"])
            is_scale = any(v in msg_lower for v in ["scale", "resize", "缩放"])
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

    # 4. Apply material
    if any(w in msg_lower for w in ["material", "color", "材质", "颜色", "涂"]) and scene_objects:
        target_name = _find_target_name(msg_lower, scene_objects)
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
    if any(w in msg_lower for w in ["duplicate", "copy", "复制", "副本"]) and scene_objects:
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

    # 12. Arrange layout
    if any(w in msg_lower for w in ["arrange", "layout", "排列", "排布", "布局"]):
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
    export_match = re.search(r'\b(export|glb|obj|stl|导出)\b', msg_lower)
    if export_match:
        fmt = "glb"
        if re.search(r'\bobj\b', msg_lower):
            fmt = "obj"
        elif re.search(r'\bstl\b', msg_lower):
            fmt = "stl"
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
            emit_tool_call=False,
        ))
        matched_any = True

    # 15. Scene info
    if any(k in msg_lower for k in ["scene info", "scene summary", "statistics", "inspect", "场景信息", "统计"]):
        intents.append(ParsedIntent(
            tool_name="scene_info",
            arguments={},
            description="Get scene info",
            emit_tool_call=False,
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
    if any(k in msg_lower for k in ["toggle grid", "grid on", "grid off", "show grid", "hide grid", "网格"]):
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
            emit_tool_call=False,
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

    # Select all / set selection
    if any(k in msg_lower for k in ["select all", "全选", "选择全部", "选择所有"]):
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
    if any(k in msg_lower for k in ["set camera position", "camera position", "设置相机位置", "相机位置"]):
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
    if any(k in msg_lower for k in ["clear scene", "reset scene", "清空", "重置"]):
        intents.append(ParsedIntent(
            tool_name="smart_compose",
            arguments={"template": "_clear"},
            description="Clear scene",
        ))
        matched_any = True

    # 19. Scene analysis
    if any(k in msg_lower for k in ["analyze", "describe scene", "what's in", "what is in", "scene analysis", "inspect", "分析场景", "描述场景", "场景里有什么", "看看场景"]):
        detail = "summary"
        if any(k in msg_lower for k in ["detailed", "detail", "full", "详细", "完整"]):
            detail = "detailed"
        if any(k in msg_lower for k in ["everything", "all details", "所有", "全部"]):
            detail = "full"
        intents.append(ParsedIntent(
            tool_name="analyze_scene",
            arguments={"detail_level": detail},
            description=f"Analyze scene ({detail})",
            emit_tool_call=False,
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

    if not matched_any:
        return [], ""

    return intents, ""


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
