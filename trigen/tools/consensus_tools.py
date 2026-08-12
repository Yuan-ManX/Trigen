"""Consensus and self-evaluation tools.

Provides multi-model consensus voting — dispatches a prompt to several
LLM models in parallel and synthesises a single best answer by majority
agreement. Also provides an agent self-evaluation tool that scores the
quality of the current scene against a user goal and proposes corrective
actions. Both tools operate without side-effects on the scene when used
in read-only mode, making them safe for plan-preview flows.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Dict, List, Optional

from trigen.config import LLMConfig
from trigen.llm.client import LLMClient
from trigen.scene import Scene
from trigen.tools.base import SceneDelta, ToolBase, ToolResult

logger = logging.getLogger("trigen.tools.consensus")


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

_CONSENSUS_PARAMS = {
    "type": "object",
    "properties": {
        "prompt": {
            "type": "string",
            "description": "The question or task to dispatch to multiple models.",
        },
        "models": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Model identifiers to query (default: top 3 from router).",
        },
        "strategy": {
            "type": "string",
            "enum": ["majority", "best_of_3", "first_success"],
            "description": "Voting strategy (default majority).",
        },
        "max_models": {
            "type": "integer",
            "description": "Max models to query (default 3, max 5).",
            "minimum": 2,
            "maximum": 5,
        },
    },
    "required": ["prompt"],
}

_SELF_EVAL_PARAMS = {
    "type": "object",
    "properties": {
        "goal": {
            "type": "string",
            "description": "The user's creative goal or success criteria.",
        },
        "criteria": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Specific quality dimensions to score (default: composition, lighting, color, complexity).",
        },
        "auto_fix": {
            "type": "boolean",
            "description": "If true, propose corrective tool calls (default false).",
        },
    },
    "required": ["goal"],
}


# ---------------------------------------------------------------------------
# Multi-model consensus voting
# ---------------------------------------------------------------------------

class ConsensusVoteTool(ToolBase):
    """Dispatch a prompt to multiple LLM models and synthesise a consensus answer.

    Queries up to ``max_models`` models in parallel, collects their text
    responses, and applies a voting strategy:

    - ``majority``: pick the response that most models agree on (by
      structural similarity of the first 200 chars).
    - ``best_of_3``: pick the longest substantive response.
    - ``first_success``: return the first non-empty response.

    Returns the winning response, per-model responses, and agreement score.
    When no LLM is configured (offline mode), returns a structured offline
    fallback that surfaces the intent for the intent parser to handle.
    """

    name = "consensus_vote"
    description = (
        "Query multiple LLM models in parallel and return a consensus answer "
        "with agreement scoring. Useful for high-stakes creative decisions "
        "where a single model may hallucinate."
    )
    category = "intelligence"

    def __init__(self, llm_config: Optional[LLMConfig] = None) -> None:
        self._llm_config = llm_config

    def schema(self) -> Dict[str, Any]:
        return _CONSENSUS_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        prompt = str(arguments.get("prompt", "")).strip()
        if not prompt:
            return ToolResult(success=False, message="Prompt is required.")

        strategy = str(arguments.get("strategy", "majority"))
        max_models = min(5, max(2, int(arguments.get("max_models", 3))))
        requested_models = arguments.get("models", [])

        # Gather candidate models from the router
        from trigen.llm.router import router as model_router
        available = model_router.list_models()
        if not available:
            return ToolResult(
                success=False,
                message="No models available. Configure LLM API keys to use consensus voting.",
                data={"offline": True},
            )

        # Select models: user-specified first, then fill from router
        candidates: List[str] = []
        if requested_models:
            for m in requested_models[:max_models]:
                if m in available:
                    candidates.append(m)
        if len(candidates) < max_models:
            for m in available:
                if m not in candidates:
                    candidates.append(m)
                    if len(candidates) >= max_models:
                        break

        if len(candidates) < 2:
            return ToolResult(
                success=False,
                message="At least 2 models are required for consensus voting.",
                data={"available_models": len(candidates)},
            )

        # Query models in parallel
        client = LLMClient(self._llm_config) if self._llm_config else LLMClient()
        responses: Dict[str, str] = {}

        async def _query(model_id: str) -> tuple:
            try:
                resp = await client.complete(
                    prompt=prompt,
                    model=model_id,
                    system="You are a 3D creation assistant. Answer concisely.",
                    temperature=0.7,
                    max_tokens=512,
                )
                return model_id, resp.text or ""
            except Exception as exc:
                logger.warning("Consensus query failed for %s: %s", model_id, str(exc)[:80])
                return model_id, ""

        results = await asyncio.gather(*[_query(m) for m in candidates])
        for model_id, text in results:
            if text:
                responses[model_id] = text

        if not responses:
            return ToolResult(
                success=False,
                message="All model queries failed. Check API keys and network.",
                data={"queried": candidates},
            )

        # Apply voting strategy
        winner, agreement = self._vote(responses, strategy)

        return ToolResult(
            success=True,
            message=f"Consensus reached with {agreement:.0%} agreement across {len(responses)} models.",
            data={
                "winning_response": winner,
                "agreement_score": round(agreement, 3),
                "strategy": strategy,
                "models_queried": candidates,
                "models_responded": list(responses.keys()),
                "all_responses": responses,
            },
        )

    @staticmethod
    def _vote(responses: Dict[str, str], strategy: str) -> tuple:
        """Apply the voting strategy and return (winner_text, agreement_score)."""
        if strategy == "first_success":
            winner = next(iter(responses.values()))
            return winner, 1.0

        if strategy == "best_of_3":
            # Pick the longest substantive response
            winner = max(responses.values(), key=len)
            return winner, 1.0 / max(len(responses), 1)

        # majority: cluster by first-200-char structural similarity
        fingerprints: Dict[str, List[str]] = {}
        for model, text in responses.items():
            # Structural fingerprint: first 200 chars lowercased, stripped of whitespace
            fp = "".join(text[:200].lower().split())
            fingerprints.setdefault(fp, []).append(model)

        # Find the largest cluster
        best_cluster = max(fingerprints.values(), key=len)
        agreement = len(best_cluster) / len(responses)
        # Return the response from the first model in the winning cluster
        winner_model = best_cluster[0]
        return responses[winner_model], agreement


# ---------------------------------------------------------------------------
# Agent self-evaluation
# ---------------------------------------------------------------------------

class SelfEvaluateTool(ToolBase):
    """Evaluate the current scene against a user goal and score it.

    Performs a structured quality assessment across multiple dimensions
    (composition, lighting, color harmony, complexity, goal alignment)
    and returns numeric scores plus actionable suggestions. When
    ``auto_fix`` is true, the returned suggestions are formatted as
    tool-call proposals that the orchestrator can execute directly.
    """

    name = "self_evaluate"
    description = (
        "Score the current scene against a user goal across multiple quality "
        "dimensions and propose corrective actions. Returns per-dimension "
        "scores, an overall quality rating, and actionable next-step suggestions."
    )
    category = "intelligence"

    def schema(self) -> Dict[str, Any]:
        return _SELF_EVAL_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        goal = str(arguments.get("goal", "")).strip()
        if not goal:
            return ToolResult(success=False, message="A goal is required for evaluation.")

        criteria = arguments.get("criteria", [])
        if not criteria:
            criteria = ["composition", "lighting", "color_harmony", "complexity", "goal_alignment"]

        auto_fix = bool(arguments.get("auto_fix", False))

        # Gather scene statistics for heuristic evaluation
        obj_count = len(scene.objects)
        light_count = len(scene.lights)
        has_materials = any(o.material.color != "#cccccc" for o in scene.objects)
        has_animation = any(o.animation is not None for o in scene.objects)
        visible_count = sum(1 for o in scene.objects if o.visible)

        # Heuristic scoring (0.0 - 1.0 per dimension)
        scores: Dict[str, float] = {}

        # Composition: prefers 3-30 visible objects (not empty, not cluttered)
        if visible_count == 0:
            scores["composition"] = 0.1
        elif visible_count <= 2:
            scores["composition"] = 0.4
        elif visible_count <= 30:
            scores["composition"] = 0.8
        elif visible_count <= 100:
            scores["composition"] = 0.6
        else:
            scores["composition"] = 0.3

        # Lighting: prefers 2-5 lights with at least one directional
        directional = sum(1 for l in scene.lights if l.type == "directional")
        ambient = sum(1 for l in scene.lights if l.type == "ambient")
        if light_count == 0:
            scores["lighting"] = 0.1
        elif light_count >= 2 and directional >= 1:
            scores["lighting"] = 0.85
        elif light_count >= 1:
            scores["lighting"] = 0.5
        else:
            scores["lighting"] = 0.3

        # Color harmony: checks if colors are varied but not random
        colors = set(o.material.color for o in scene.objects)
        if not colors:
            scores["color_harmony"] = 0.3
        elif len(colors) <= 5:
            scores["color_harmony"] = 0.8
        elif len(colors) <= 10:
            scores["color_harmony"] = 0.6
        else:
            scores["color_harmony"] = 0.4

        # Complexity: rewards animation and material variety
        complexity = 0.3
        if has_materials:
            complexity += 0.2
        if has_animation:
            complexity += 0.2
        if obj_count >= 5:
            complexity += 0.15
        if light_count >= 3:
            complexity += 0.15
        scores["complexity"] = min(complexity, 1.0)

        # Goal alignment: heuristic based on keyword matching
        goal_lower = goal.lower()
        alignment = 0.5  # neutral baseline
        goal_keywords = {
            "forest": ["green", "tree", "plant", "nature"],
            "city": ["building", "tower", "road", "block"],
            "character": ["humanoid", "figure", "body", "rig"],
            "interior": ["room", "wall", "floor", "furniture"],
            "abstract": ["fractal", "crystal", "geometric", "spiral"],
            "landscape": ["terrain", "mountain", "water", "sky"],
        }
        for keyword, tags in goal_keywords.items():
            if keyword in goal_lower:
                matching = sum(1 for o in scene.objects if any(t in o.name.lower() for t in tags))
                if matching > 0:
                    alignment = min(0.5 + matching * 0.15, 1.0)
                break
        scores["goal_alignment"] = alignment

        overall = sum(scores.values()) / len(scores) if scores else 0.0

        # Generate suggestions
        suggestions: List[Dict[str, Any]] = []
        if scores["composition"] < 0.6:
            if visible_count == 0:
                suggestions.append({
                    "dimension": "composition",
                    "issue": "Scene is empty.",
                    "fix": "create_object",
                    "arguments": {"geometry_type": "box", "name": "Starter"},
                })
            elif visible_count > 100:
                suggestions.append({
                    "dimension": "composition",
                    "issue": "Scene is cluttered.",
                    "fix": "describe_scene",
                    "arguments": {},
                })

        if scores["lighting"] < 0.6:
            suggestions.append({
                "dimension": "lighting",
                "issue": "Insufficient lighting setup.",
                "fix": "create_lighting_rig",
                "arguments": {"preset": "three_point"},
            })

        if scores["color_harmony"] < 0.6:
            suggestions.append({
                "dimension": "color_harmony",
                "issue": "Color palette is inconsistent.",
                "fix": "randomize_palette",
                "arguments": {"harmony": "analogous"},
            })

        if scores["complexity"] < 0.5:
            if not has_animation:
                suggestions.append({
                    "dimension": "complexity",
                    "issue": "No animation in scene.",
                    "fix": "orbit_animation",
                    "arguments": {"target": scene.objects[0].name if scene.objects else ""},
                })

        if scores["goal_alignment"] < 0.6:
            suggestions.append({
                "dimension": "goal_alignment",
                "issue": f"Scene does not strongly match goal: {goal}",
                "fix": "smart_compose",
                "arguments": {"template": "auto"},
            })

        # Determine quality rating
        if overall >= 0.8:
            rating = "excellent"
        elif overall >= 0.6:
            rating = "good"
        elif overall >= 0.4:
            rating = "fair"
        else:
            rating = "needs_work"

        data: Dict[str, Any] = {
            "overall_score": round(overall, 3),
            "quality_rating": rating,
            "per_dimension": {k: round(v, 3) for k, v in scores.items()},
            "scene_stats": {
                "objects": obj_count,
                "visible": visible_count,
                "lights": light_count,
                "has_animation": has_animation,
                "color_variety": len(colors),
            },
            "suggestions": suggestions,
        }

        if auto_fix:
            data["proposed_tool_calls"] = [
                {"tool": s["fix"], "arguments": s["arguments"]}
                for s in suggestions
            ]

        return ToolResult(
            success=True,
            message=f"Scene quality: {rating} ({overall:.0%}). {len(suggestions)} suggestion(s).",
            data=data,
        )
