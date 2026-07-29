"""Scene analysis tool.

Lets the Agent inspect the current 3D scene and produce a structured
description that can be fed back into the LLM context. This gives the
Agent situational awareness — it can answer questions like "what objects
are in the scene?", "what colors are used?", and "is the layout balanced?"

The tool produces a rich scene description including:
  - Object inventory with geometry, material, and transform details
  - Color palette extracted from all materials
  - Spatial distribution analysis (bounding box, density)
  - Lighting summary
  - Composition assessment (symmetry, balance, focal point)
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from trigen.scene import Scene
from trigen.tools.base import SceneDelta, ToolBase, ToolResult

logger = logging.getLogger("trigen.tools.scene_analyzer")


class SceneAnalyzerTool(ToolBase):
    """Agent tool that analyzes the current scene and returns a description.

    When the Agent needs to understand what's currently in the scene — for
    example, to answer "what do you see?" or to plan the next operation —
    it calls this tool. The output is a structured description that the
    LLM can reason about.
    """

    name = "analyze_scene"
    description = (
        "Analyze the current 3D scene and return a structured description. "
        "Includes object inventory, color palette, spatial distribution, "
        "lighting summary, and composition assessment. Use this when the "
        "user asks what's in the scene or when planning complex operations."
    )

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "detail_level": {
                    "type": "string",
                    "enum": ["summary", "detailed", "full"],
                    "description": "Level of detail in the analysis. 'summary' gives a brief overview, "
                    "'detailed' adds color palette and spatial info, 'full' includes every object's complete data.",
                },
            },
            "required": [],
        }

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        detail = arguments.get("detail_level", "detailed")
        scene_dict = scene.to_dict()
        objects = scene_dict.get("objects", [])
        lights = scene_dict.get("lights", [])
        groups = scene_dict.get("groups", [])

        # Build the analysis
        analysis: Dict[str, Any] = {
            "object_count": len(objects),
            "light_count": len(lights),
            "group_count": len(groups),
        }

        if detail in ("summary", "detailed", "full"):
            analysis["objects"] = self._summarize_objects(objects, detail)
            analysis["lights"] = self._summarize_lights(lights)

        if detail in ("detailed", "full"):
            analysis["color_palette"] = self._extract_colors(objects)
            analysis["spatial"] = self._analyze_spatial(objects)
            analysis["composition"] = self._assess_composition(objects)

        if detail == "full":
            analysis["raw_objects"] = objects
            analysis["raw_lights"] = lights

        # Build a natural-language description
        description = self._build_description(analysis, detail)

        return ToolResult(
            success=True,
            message=description,
            data=analysis,
        )

    def _summarize_objects(self, objects: List[Dict], detail: str) -> List[Dict[str, Any]]:
        """Summarize each object in the scene."""
        summary: List[Dict[str, Any]] = []
        for obj in objects:
            entry: Dict[str, Any] = {
                "name": obj.get("name", ""),
                "geometry": obj.get("geometry", {}).get("type", ""),
            }
            if detail in ("detailed", "full"):
                material = obj.get("material", {})
                entry["color"] = material.get("color", "")
                entry["metalness"] = material.get("metalness", 0)
                entry["roughness"] = material.get("roughness", 1)
                transform = obj.get("transform", {})
                entry["position"] = transform.get("position", [0, 0, 0])
                entry["scale"] = transform.get("scale", [1, 1, 1])
            if detail == "full":
                entry["geometry_params"] = obj.get("geometry", {}).get("params", {})
                entry["rotation"] = obj.get("transform", {}).get("rotation", [0, 0, 0])
                entry["material"] = obj.get("material", {})
            summary.append(entry)
        return summary

    def _summarize_lights(self, lights: List[Dict]) -> List[Dict[str, Any]]:
        """Summarize each light in the scene."""
        return [
            {
                "name": l.get("name", ""),
                "type": l.get("type", ""),
                "intensity": l.get("intensity", 1.0),
                "color": l.get("color", "#ffffff"),
            }
            for l in lights
        ]

    def _extract_colors(self, objects: List[Dict]) -> List[str]:
        """Extract the unique color palette from all materials."""
        colors: List[str] = []
        for obj in objects:
            color = obj.get("material", {}).get("color", "")
            if color and color not in colors:
                colors.append(color)
        return colors

    def _analyze_spatial(self, objects: List[Dict]) -> Dict[str, Any]:
        """Analyze the spatial distribution of objects."""
        if not objects:
            return {"density": "empty", "bounding_box": None}

        positions = [obj.get("transform", {}).get("position", [0, 0, 0]) for obj in objects]
        xs = [p[0] for p in positions if len(p) >= 3]
        ys = [p[1] for p in positions if len(p) >= 3]
        zs = [p[2] for p in positions if len(p) >= 3]

        if not xs:
            return {"density": "unknown", "bounding_box": None}

        bbox = {
            "min": [min(xs), min(ys), min(zs)],
            "max": [max(xs), max(ys), max(zs)],
            "size": [max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs)],
        }

        # Estimate density
        volume = max(bbox["size"][0] * bbox["size"][1] * bbox["size"][2], 0.01)
        density = len(objects) / volume

        return {
            "density": "sparse" if density < 0.1 else ("moderate" if density < 1.0 else "dense"),
            "bounding_box": bbox,
            "center": [
                (min(xs) + max(xs)) / 2,
                (min(ys) + max(ys)) / 2,
                (min(zs) + max(zs)) / 2,
            ],
        }

    def _assess_composition(self, objects: List[Dict]) -> Dict[str, Any]:
        """Assess the composition quality of the scene."""
        if len(objects) < 2:
            return {"assessment": "insufficient objects for composition analysis"}

        positions = [obj.get("transform", {}).get("position", [0, 0, 0]) for obj in objects]
        xs = [p[0] for p in positions if len(p) >= 3]
        if not xs:
            return {"assessment": "unable to assess"}

        # Check symmetry around the center
        center_x = sum(xs) / len(xs)
        left = sum(1 for x in xs if x < center_x)
        right = sum(1 for x in xs if x > center_x)
        symmetry = "balanced" if abs(left - right) <= 1 else "asymmetric"

        # Check spread
        spread = max(xs) - min(xs) if xs else 0
        spread_assessment = "compact" if spread < 3 else ("spread" if spread < 8 else "wide")

        return {
            "symmetry": symmetry,
            "spread": spread_assessment,
            "focal_point": [center_x, 0, 0],
        }

    def _build_description(self, analysis: Dict[str, Any], detail: str) -> str:
        """Build a natural-language description of the scene."""
        parts: List[str] = []
        parts.append(
            f"Scene contains {analysis['object_count']} objects, "
            f"{analysis['light_count']} lights, and {analysis['group_count']} groups."
        )

        if detail in ("detailed", "full"):
            palette = analysis.get("color_palette", [])
            if palette:
                parts.append(f"Color palette: {', '.join(palette)}")

            spatial = analysis.get("spatial", {})
            if spatial.get("density"):
                parts.append(f"Spatial density: {spatial['density']}")

            comp = analysis.get("composition", {})
            if comp.get("symmetry"):
                parts.append(f"Composition: {comp.get('symmetry', 'unknown')} and {comp.get('spread', 'unknown')}")

        # Object list
        obj_summary = analysis.get("objects", [])
        if obj_summary:
            names = [o.get("name", o.get("geometry", "?")) for o in obj_summary[:8]]
            parts.append(f"Objects: {', '.join(names)}")
            if len(obj_summary) > 8:
                parts.append(f"... and {len(obj_summary) - 8} more")

        return " ".join(parts)
