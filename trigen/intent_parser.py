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

    # 1. Smart compose (check first to allow scene replacement)
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

    # 18. Reset / clear scene
    if any(k in msg_lower for k in ["clear scene", "reset scene", "清空", "重置"]):
        intents.append(ParsedIntent(
            tool_name="smart_compose",
            arguments={"template": "_clear"},
            description="Clear scene",
        ))
        matched_any = True

    # 19. Image-to-3D reconstruction
    # Triggered by keywords like "reconstruct", "image to 3d", "重建", "图像转3D"
    img2threejs_triggers = [
        "reconstruct", "image to 3d", "image-to-3d", "img2threejs",
        "from image", "convert image", "image to mesh", "photo to 3d",
        "重建", "图像转3d", "图像转3D", "图片转3d", "图片转3D",
        "从图片", "图片生成", "图像生成",
    ]
    if any(k in msg_lower for k in img2threejs_triggers):
        # Extract a prompt description from the message by removing trigger words
        prompt_text = msg
        for trig in img2threejs_triggers:
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

    if not matched_any:
        return [], ""

    return intents, ""
