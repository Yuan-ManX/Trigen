"""Theme + undo history + render-preset editor-control tools.

Covers three editor-level surfaces the agent was previously unable to
drive from the chat side:

  * ``set_theme`` — flip between warm / studio / rainbow / moonlight color
    palettes. Maps to a frontend ThemeProvider toggle.
  * ``browse_history`` / ``restore_history_entry`` — the undo stack already
    exists in the orchestrator; these tools surface it so the agent can
    reason about *which* earlier state to jump to instead of only calling
    undo one step at a time.
  * ``apply_render_preset`` — load a curated combination of postfx +
    exposure + render quality into a single named look (e.g. "cinematic",
    "architectural", "sketch", "neon night").
  * ``set_workspace_layout`` — load pre-curated panel arrangements
    (modeler / animator / review / minimal) to match the current task.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from trigen.scene import Scene
from trigen.tools.base import ToolBase, ToolResult, SceneDelta


RENDER_PRESETS: Dict[str, Dict[str, Any]] = {
    "cinematic": {
        "description": "Filmic tone-mapping with warm color grading, mild bloom, and depth-of-field.",
        "postfx": {
            "tone_mapping": {"mode": "aces", "exposure": 1.1},
            "color_grading": {"saturation": 1.08, "contrast": 1.05, "temperature": 0.05, "tint": 0.02},
            "bloom": {"enabled": True, "intensity": 0.7, "threshold": 0.85, "radius": 0.6},
            "dof": {"enabled": True, "focus_distance": 6.0, "aperture": 0.02, "max_blur": 0.015},
            "vignette": {"enabled": True, "intensity": 0.35, "smoothness": 0.6},
            "film_grain": {"enabled": True, "intensity": 0.08, "size": 1.0},
        },
        "render_quality": "high",
        "exposure": 1.1,
    },
    "architectural": {
        "description": "Clean neutral lighting, sharp shadows, no film effects — for modeling and CAD reviews.",
        "postfx": {
            "tone_mapping": {"mode": "linear", "exposure": 1.0},
            "color_grading": {"saturation": 1.0, "contrast": 1.02, "temperature": 0.0, "tint": 0.0},
            "bloom": {"enabled": False},
            "dof": {"enabled": False},
            "vignette": {"enabled": False},
            "film_grain": {"enabled": False},
            "chromatic_aberration": {"enabled": False},
        },
        "render_quality": "ultra",
        "exposure": 1.0,
    },
    "sketch": {
        "description": "Hand-drawn feel: high film grain, cool blue tint, and pronounced edge lines.",
        "postfx": {
            "tone_mapping": {"mode": "reinhard", "exposure": 1.05},
            "color_grading": {"saturation": 0.7, "contrast": 1.08, "temperature": -0.05, "tint": 0.02},
            "film_grain": {"enabled": True, "intensity": 0.22, "size": 1.4},
            "vignette": {"enabled": True, "intensity": 0.5, "smoothness": 0.4},
        },
        "render_quality": "medium",
        "exposure": 1.05,
    },
    "neon_night": {
        "description": "Deep-black backdrop with strong bloom, chromatic aberration, and vivid color grading.",
        "postfx": {
            "tone_mapping": {"mode": "aces", "exposure": 1.2},
            "color_grading": {"saturation": 1.25, "contrast": 1.15, "temperature": -0.08, "tint": 0.05},
            "bloom": {"enabled": True, "intensity": 1.4, "threshold": 0.5, "radius": 0.9},
            "chromatic_aberration": {"enabled": True, "offset": 0.004},
            "film_grain": {"enabled": True, "intensity": 0.1, "size": 1.1},
        },
        "render_quality": "high",
        "exposure": 1.2,
    },
    "watercolor": {
        "description": "Desaturated, soft look with mild bloom and warm tint — resembles a watercolor wash.",
        "postfx": {
            "tone_mapping": {"mode": "reinhard", "exposure": 1.0},
            "color_grading": {"saturation": 0.75, "contrast": 0.9, "temperature": 0.08, "tint": -0.02},
            "bloom": {"enabled": True, "intensity": 0.4, "threshold": 0.7, "radius": 0.8},
            "vignette": {"enabled": True, "intensity": 0.3, "smoothness": 0.5},
        },
        "render_quality": "medium",
        "exposure": 1.0,
    },
    "studio_showcase": {
        "description": "Product studio look: bright key lighting, soft bloom, crisp tone mapping.",
        "postfx": {
            "tone_mapping": {"mode": "aces", "exposure": 1.15},
            "color_grading": {"saturation": 1.03, "contrast": 1.04, "temperature": 0.0, "tint": 0.0},
            "bloom": {"enabled": True, "intensity": 0.55, "threshold": 0.75, "radius": 0.5},
            "dof": {"enabled": False},
            "vignette": {"enabled": True, "intensity": 0.2, "smoothness": 0.55},
        },
        "render_quality": "high",
        "exposure": 1.15,
    },
}


THEMES: Dict[str, Dict[str, Any]] = {
    "warm": {
        "description": "Soft pink-purple warm palette — the default conversation-room look.",
        "palette": {"accent": "#ff7acc", "bg_warm": "#fde7f3", "bg_cool": "#efe8ff", "fg": "#2a1f2e"},
        "radius_scale": 1.0,
        "bounce_animations": True,
    },
    "studio": {
        "description": "Calm blue-gray professional palette for focused modeling work.",
        "palette": {"accent": "#4aa6ff", "bg_warm": "#e6eefb", "bg_cool": "#eef1f7", "fg": "#1c2330"},
        "radius_scale": 0.7,
        "bounce_animations": False,
    },
    "rainbow": {
        "description": "Rainbow nav accents with vivid gradient chips.",
        "palette": {"accent": "#9a3aff", "bg_warm": "#fff5e6", "bg_cool": "#e6faff", "fg": "#231a2e"},
        "radius_scale": 1.0,
        "bounce_animations": True,
    },
    "moonlight": {
        "description": "Dark-mode moonlight palette — cyan accents and deep indigo surfaces.",
        "palette": {"accent": "#5ee0ff", "bg_warm": "#131828", "bg_cool": "#0e111c", "fg": "#e5ecff"},
        "radius_scale": 0.85,
        "bounce_animations": True,
    },
}


WORKSPACE_LAYOUTS: Dict[str, Dict[str, Any]] = {
    "modeler": {
        "description": "Left outliner + right properties. Big canvas, chat tucked.",
        "panels": {"left": "open", "right": "open", "chat": "compact", "timeline": "hidden"},
        "viewport": {"shading": "solid", "grid": True, "minimap": True},
    },
    "animator": {
        "description": "Bottom timeline + left layers. Optimized for keyframe scrubbing.",
        "panels": {"left": "open", "right": "compact", "chat": "hidden", "timeline": "open"},
        "viewport": {"shading": "solid", "grid": True, "minimap": False},
    },
    "review": {
        "description": "Chat open + right critique / storyboard panels.",
        "panels": {"left": "hidden", "right": "open", "chat": "open", "timeline": "compact"},
        "viewport": {"shading": "rendered", "grid": False, "minimap": False},
    },
    "minimal": {
        "description": "Full-canvas immersive mode. Everything else hidden.",
        "panels": {"left": "hidden", "right": "hidden", "chat": "hidden", "timeline": "hidden"},
        "viewport": {"shading": "rendered", "grid": False, "minimap": False},
    },
}


class SetThemeTool(ToolBase):
    """Switch the frontend color/theme palette."""

    name = "set_theme"
    description = (
        "Change the editor visual theme. Available themes: warm (default pink-purple), "
        "studio (cool professional), rainbow (vivid accents), moonlight (dark cyan)."
    )
    category = "editor"

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "theme": {"type": "string", "description": "Theme name: warm | studio | rainbow | moonlight.", "default": "warm"},
            },
            "required": [],
        }

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        theme = str(arguments.get("theme", "warm") or "warm").lower()
        if theme not in THEMES:
            theme = "warm"
        scene.theme = {"name": theme, **THEMES[theme]}
        return ToolResult(
            success=True,
            message=f"Switched theme to '{theme}' — {THEMES[theme]['description']}",
            data={"theme": scene.theme, "editor_commands": [{"op": "set_theme", "theme": theme}]},
        )


class BrowseHistoryTool(ToolBase):
    """Inspect the session's undo stack summaries."""

    name = "browse_history"
    description = (
        "List the most recent scene history entries (undo stack) with their "
        "human-readable descriptions so the agent can reason about which "
        "earlier state to restore."
    )
    category = "editor"

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Maximum number of history entries to return (newest first).", "default": 20, "minimum": 1, "maximum": 100},
            },
            "required": [],
        }

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        limit = max(1, min(100, int(arguments.get("limit", 20))))
        history = list(getattr(scene, "_history_entries", None) or [])
        if not history:
            history = [
                {
                    "index": 0,
                    "label": f"Initial scene ({len(scene.objects)} objects)",
                    "object_count": len(scene.objects),
                }
            ]
        trimmed = list(reversed(history))[:limit]
        return ToolResult(
            success=True,
            message=f"Browsing {len(trimmed)} history entries (undo stack depth {len(history)}).",
            data={"entries": trimmed, "total": len(history)},
        )


class RestoreHistoryEntryTool(ToolBase):
    """Jump back to a specific history index by label substring or numeric index."""

    name = "restore_history_entry"
    description = (
        "Restore a specific history entry from the undo stack. Takes either "
        "a numeric index (as returned by browse_history) or a label keyword "
        "to fuzzy-match the closest entry. Undos are replayed on top so "
        "redo still works after the jump."
    )
    category = "editor"

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "index": {"type": "integer", "description": "Exact entry index as returned by browse_history."},
                "label_contains": {"type": "string", "description": "Keyword used to fuzzy-match history labels when index is omitted."},
            },
            "required": [],
        }

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        index = arguments.get("index")
        label_contains = str(arguments.get("label_contains", "") or "")
        history = list(getattr(scene, "_history_entries", None) or [])
        if not history:
            return ToolResult(
                success=False,
                message="No history entries are available to restore.",
            )
        target_idx: Optional[int] = None
        if index is not None:
            try:
                iv = int(index)
                if 0 <= iv < len(history):
                    target_idx = iv
            except (TypeError, ValueError):
                pass
        if target_idx is None and label_contains:
            needle = label_contains.lower()
            best_score = 0.0
            for i, entry in enumerate(history):
                label = str(entry.get("label", "")).lower()
                if not label:
                    continue
                score = 0.0
                if needle in label:
                    score = 1.0 - abs(len(label) - len(needle)) / max(len(label), 1)
                else:
                    a, b = set(needle), set(label)
                    if a and b:
                        score = len(a & b) / max(len(a | b), 1)
                if score > best_score:
                    best_score = score
                    target_idx = i
        if target_idx is None:
            return ToolResult(
                success=False,
                message="Could not identify a history entry to restore — pass an index or label_contains.",
            )
        entry = history[target_idx]
        return ToolResult(
            success=True,
            message=f"Restored history entry #{target_idx}: {entry.get('label', '')}",
            data={
                "restored_index": target_idx,
                "entry": entry,
                "editor_commands": [{"op": "restore_history", "index": target_idx}],
            },
        )


class ApplyRenderPresetTool(ToolBase):
    """Load a named combination of postfx + quality settings into the scene."""

    name = "apply_render_preset"
    description = (
        "Apply a curated render look to the current scene. Built-in presets: "
        "cinematic, architectural, sketch, neon_night, watercolor, studio_showcase."
    )
    category = "postfx"

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "preset": {"type": "string", "description": "Render preset name.", "default": "cinematic"},
                "exposure_override": {"type": "number", "description": "Optional exposure multiplier override. Omit to use the preset's default."},
            },
            "required": [],
        }

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        preset = str(arguments.get("preset", "cinematic") or "cinematic").lower()
        if preset not in RENDER_PRESETS:
            preset = "cinematic"
        spec = RENDER_PRESETS[preset]
        scene.post_processing = dict(spec["postfx"])
        scene.render_quality = str(spec.get("render_quality", "high"))
        scene.exposure = float(arguments.get("exposure_override", spec.get("exposure", 1.0)))
        return ToolResult(
            success=True,
            message=f"Applied render preset '{preset}' — {spec['description']}",
            data={
                "preset": preset,
                "render_quality": scene.render_quality,
                "exposure": scene.exposure,
                "postfx_keys": sorted(scene.post_processing.keys()),
            },
        )


class SetWorkspaceLayoutTool(ToolBase):
    """Load a named panel/viewport layout for the frontend editor shell."""

    name = "set_workspace_layout"
    description = (
        "Rearrange the editor workspace layout. Built-in layouts: modeler, "
        "animator, review, minimal."
    )
    category = "editor"

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "layout": {"type": "string", "description": "Layout name: modeler | animator | review | minimal.", "default": "modeler"},
            },
            "required": [],
        }

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        layout = str(arguments.get("layout", "modeler") or "modeler").lower()
        if layout not in WORKSPACE_LAYOUTS:
            layout = "modeler"
        spec = WORKSPACE_LAYOUTS[layout]
        scene.workspace_layout = {"name": layout, **spec}
        return ToolResult(
            success=True,
            message=f"Switched workspace layout to '{layout}' — {spec['description']}",
            data={
                "layout": scene.workspace_layout,
                "editor_commands": [{"op": "set_workspace_layout", "layout": layout, "spec": spec}],
            },
        )


class ListRenderPresetsTool(ToolBase):
    """Enumerate available render presets so the frontend gallery can render them."""

    name = "list_render_presets"
    description = "Return every render preset's name, description, and signature settings."
    category = "postfx"

    def schema(self) -> Dict[str, Any]:
        return {"type": "object", "properties": {}, "required": []}

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        presets = [
            {
                "name": name,
                "description": spec["description"],
                "render_quality": spec.get("render_quality", ""),
                "exposure": spec.get("exposure", 1.0),
            }
            for name, spec in RENDER_PRESETS.items()
        ]
        return ToolResult(
            success=True,
            message=f"Listed {len(presets)} render presets.",
            data={"presets": presets, "count": len(presets)},
        )


class ListThemesTool(ToolBase):
    """Enumerate available UI themes."""

    name = "list_themes"
    description = "Return every UI theme's name, description, and palette accent."
    category = "editor"

    def schema(self) -> Dict[str, Any]:
        return {"type": "object", "properties": {}, "required": []}

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        items = [
            {
                "name": name,
                "description": spec["description"],
                "accent": (spec.get("palette") or {}).get("accent", ""),
            }
            for name, spec in THEMES.items()
        ]
        return ToolResult(
            success=True,
            message=f"Listed {len(items)} UI themes.",
            data={"themes": items, "count": len(items)},
        )


class ListWorkspaceLayoutsTool(ToolBase):
    """Enumerate available workspace layouts."""

    name = "list_workspace_layouts"
    description = "Return every workspace layout's name and description."
    category = "editor"

    def schema(self) -> Dict[str, Any]:
        return {"type": "object", "properties": {}, "required": []}

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        items = [{"name": name, "description": spec["description"]} for name, spec in WORKSPACE_LAYOUTS.items()]
        return ToolResult(
            success=True,
            message=f"Listed {len(items)} workspace layouts.",
            data={"layouts": items, "count": len(items)},
        )
