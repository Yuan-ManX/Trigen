"""Image-to-3D reconstruction tool.

Converts a reference image into a scene of 3D primitives by orchestrating
a vision-language model to analyze the image, extract shapes/colors/spatial
layout, and emit structured object descriptors that the Trigen scene model
can ingest directly.

The pipeline:
  1. A vision LLM (GPT-4o, Claude, Qwen-VL, etc.) receives the image with a
     structured prompt asking for a JSON array of primitive descriptors,
     including PBR material properties (metalness, roughness, emissive).
  2. Each descriptor carries a geometry type, dimensions, color, material,
     and 3D position inferred from the image.
  3. The tool instantiates SceneObject instances from the descriptors and
     adds them to the scene, returning scene deltas for the frontend.
  4. Optionally, when ``refine_with_3d_model`` is true and a text-to-3D
     model (Meshy, Tripo) is configured, the tool generates a downloadable
     high-quality GLB asset for the most prominent detected object so the
     user gets both a lightweight primitive scene and a refined mesh.

When no vision LLM is configured, the tool falls back to a deterministic
three-object placeholder so the Agent can still demonstrate the flow.
"""

from __future__ import annotations

import base64
import json
import logging
from typing import Any, Dict, List, Optional

from trigen.config import AgentConfig, LLMConfig
from trigen.llm.client import LLMClient
from trigen.llm.router import Modality, router as model_router
from trigen.scene import (
    GEOMETRY_DEFAULTS,
    Geometry,
    Material,
    Scene,
    SceneObject,
    Transform,
)
from trigen.tools.base import SceneDelta, ToolBase, ToolRegistry, ToolResult

logger = logging.getLogger("trigen.tools.img2scene")


def _clamp_float(value: Any, lo: float, hi: float, default: float) -> float:
    """Coerce a value to a clamped float, falling back to ``default``."""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, f))


# Structured prompt asking the vision model to emit JSON primitives with
# full PBR material properties so the reconstructed scene matches the
# original appearance (shiny metal, matte wood, glowing lights, etc.).
_VISION_PROMPT = """You are a 3D scene analyzer. Examine the provided image and decompose every distinct visible object into simple 3D primitives.

Return ONLY a JSON array (no markdown, no explanation) where each element has this shape:
{
  "geometry_type": "box|sphere|cylinder|cone|torus|plane|capsule|ring",
  "name": "short object name",
  "color": "#rrggbb hex color sampled from the image",
  "metalness": 0.0 to 1.0 (how metallic the surface looks; 0=non-metal, 1=pure metal),
  "roughness": 0.0 to 1.0 (surface roughness; 0=mirror-smooth, 1=matte-diffuse),
  "emissive": "#rrggbb or #000000 if the object does not glow",
  "emissive_intensity": 0.0 to 5.0 (glow strength; 0=not emissive),
  "position": [x, y, z] in scene units (origin at center, y is up),
  "scale": [sx, sy, sz] relative size,
  "rotation": [rx, ry, rz] in radians if the object is tilted, else [0,0,0]
}

Guidelines:
- Use 3-12 primitives to represent the image contents.
- Estimate positions so objects do not overlap excessively.
- Pick geometry types that best approximate each object's silhouette.
- Sample real colors from the image; do not invent colors.
- Infer material properties from surface appearance: chrome/metal objects have high metalness and low roughness; wood/plastic have low metalness and mid-to-high roughness; lamps/screens/LEDs have non-black emissive.
- Keep the JSON valid and parseable.
"""


class ImageToSceneTool(ToolBase):
    """Agent tool that converts an image into a 3D primitive scene.

    When invoked with an image, it dispatches a vision-model request that
    returns structured primitive descriptors, then instantiates them as
    SceneObject instances. The tool is registered alongside the other
    editor tools and can be called by the Agent during a chat turn.
    """

    name = "image_to_3d"
    description = (
        "Reconstruct a 3D scene from a reference image. Provide an image_base64 "
        "data URL or a text prompt describing the desired scene. The tool uses a "
        "vision LLM to decompose the image into primitive 3D objects (boxes, "
        "spheres, cylinders, etc.) with inferred colors, positions, and scales, "
        "then adds them to the scene."
    )

    def __init__(
        self,
        config: Optional[LLMConfig] = None,
        registry: Optional[ToolRegistry] = None,
    ) -> None:
        self.llm_config = config or LLMConfig()
        self.registry = registry

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "image_base64": {
                    "type": "string",
                    "description": "Base64-encoded image data (without data: prefix). "
                    "If omitted, a text prompt is used to imagine a scene.",
                },
                "image_mime": {
                    "type": "string",
                    "description": "MIME type of the image, e.g. image/png",
                },
                "prompt": {
                    "type": "string",
                    "description": "Optional text prompt guiding the reconstruction. "
                    "Used alone when no image is provided.",
                },
                "model": {
                    "type": "string",
                    "description": "Optional vision model id to use for analysis. "
                    "Defaults to the first available vision-capable model.",
                },
                "clear_scene": {
                    "type": "boolean",
                    "description": "If true, clear existing scene objects before adding new ones.",
                },
                "refine_with_3d_model": {
                    "type": "boolean",
                    "description": "When true, after primitives are created, generate a "
                    "downloadable high-quality GLB asset for the most prominent "
                    "detected object using a text-to-3D model (Meshy/Tripo). "
                    "Ignored when no 3D-generation model is configured.",
                },
            },
            "required": [],
        }

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        image_b64 = arguments.get("image_base64", "")
        image_mime = arguments.get("image_mime", "image/png")
        prompt_text = arguments.get("prompt", "")
        model = arguments.get("model")
        clear = arguments.get("clear_scene", False)
        refine = bool(arguments.get("refine_with_3d_model", False))

        # Resolve a vision-capable model
        chosen_model = self._pick_vision_model(model)
        if not chosen_model:
            # No vision model available — use the deterministic fallback
            return await self._fallback_reconstruct(scene, prompt_text, clear)

        # Build the vision request
        raw = ""
        vision_failed = False
        try:
            from trigen.llm.client import LLMClient

            client = LLMClient(self.llm_config)
            if image_b64:
                # Strip optional data URL prefix
                if "," in image_b64 and image_b64.startswith("data:"):
                    image_b64 = image_b64.split(",", 1)[1]
                text = prompt_text or "Decompose this image into 3D primitives."
                chunks = []
                async for chunk in client.stream_vision(
                    text=text,
                    image_base64=image_b64,
                    image_mime=image_mime,
                    system=_VISION_PROMPT,
                    model=chosen_model,
                ):
                    if chunk.content:
                        chunks.append(chunk.content)
                raw = "".join(chunks)
            else:
                # Text-only imagination of a scene
                text = (
                    f"Imagine a 3D scene described as: {prompt_text}. "
                    "Decompose it into 3D primitives following the JSON schema."
                )
                messages = [{"role": "user", "content": text}]
                chunks = []
                async for chunk in client.stream(
                    messages=messages, system=_VISION_PROMPT, model=chosen_model
                ):
                    if chunk.content:
                        chunks.append(chunk.content)
                raw = "".join(chunks)
            # If the model returned an error marker, treat as failure
            if raw.startswith("[LLM call failed]") or raw.startswith("[Anthropic"):
                vision_failed = True
                logger.warning("Vision model %s returned an error: %s", chosen_model, raw[:120])
        except Exception as exc:
            logger.warning("Vision analysis failed, falling back: %s", exc)
            vision_failed = True

        if vision_failed or not raw.strip():
            return await self._fallback_reconstruct(scene, prompt_text, clear)

        descriptors = self._parse_descriptors(raw)
        if not descriptors:
            logger.warning("Vision model returned unparseable output; using fallback")
            return await self._fallback_reconstruct(scene, prompt_text, clear)

        # Optionally clear the scene
        if clear:
            scene.objects.clear()

        # Instantiate primitives
        created: List[SceneObject] = []
        for desc in descriptors:
            obj = self._descriptor_to_object(desc)
            if obj:
                scene.objects.append(obj)
                created.append(obj)

        deltas = [
            SceneDelta(action="create", target_id=obj.id, payload=obj.to_dict())
            for obj in created
        ]
        result_data: Dict[str, Any] = {
            "model_used": chosen_model,
            "object_count": len(created),
            "object_ids": [o.id for o in created],
        }
        message = f"Reconstructed {len(created)} primitives from the image."

        # Optional refine step: generate a downloadable GLB for the most
        # prominent detected object using a text-to-3D model (Meshy/Tripo).
        # The primitive stays in the scene as a lightweight placeholder; the
        # GLB is returned as a separate downloadable asset URL.
        if refine and created:
            refine_result = await self._refine_prominent(created)
            if refine_result is not None:
                result_data["refined_asset"] = refine_result
                message += f" Refined '{refine_result['name']}' via {refine_result['model']}."

        return ToolResult(
            success=True,
            message=message,
            deltas=deltas,
            data=result_data,
        )

    def _pick_vision_model(self, preferred: Optional[str]) -> Optional[str]:
        """Choose a vision-capable model that has an API key configured."""
        import os

        if preferred:
            entry = model_router.get_model(preferred)
            if entry and Modality.VISION in entry.modalities:
                resolved = model_router.resolve(preferred)
                if resolved.get("api_key"):
                    return preferred

        # Find the first available vision model
        for entry in model_router.list_by_modality(Modality.VISION):
            resolved = model_router.resolve(entry.id)
            if resolved.get("api_key"):
                return entry.id
        return None

    def _parse_descriptors(self, raw: str) -> List[Dict[str, Any]]:
        """Extract JSON array of primitive descriptors from LLM output."""
        # Tolerate markdown code fences
        text = raw.strip()
        if text.startswith("```"):
            # Remove the first fence line
            text = text.split("\n", 1)[1] if "\n" in text else text
            if text.endswith("```"):
                text = text.rsplit("```", 1)[0]
            text = text.strip()
        # Find the first JSON array
        start = text.find("[")
        end = text.rfind("]")
        if start < 0 or end < 0 or end <= start:
            return []
        try:
            parsed = json.loads(text[start : end + 1])
            if isinstance(parsed, list):
                return [p for p in parsed if isinstance(p, dict)]
        except json.JSONDecodeError:
            return []
        return []

    def _descriptor_to_object(self, desc: Dict[str, Any]) -> Optional[SceneObject]:
        """Convert a primitive descriptor into a SceneObject instance."""
        geo_type = desc.get("geometry_type", "box")
        if geo_type not in GEOMETRY_DEFAULTS:
            geo_type = "box"
        color = desc.get("color", "#cccccc")
        position = desc.get("position", [0, 0, 0])
        scale = desc.get("scale", [1, 1, 1])
        rotation = desc.get("rotation", [0, 0, 0])
        name = desc.get("name", geo_type.title())

        # Extract PBR material properties with safe clamping.
        metalness = _clamp_float(desc.get("metalness"), 0.0, 1.0, 0.0)
        roughness = _clamp_float(desc.get("roughness"), 0.0, 1.0, 0.5)
        emissive = desc.get("emissive") or "#000000"
        emissive_intensity = _clamp_float(desc.get("emissive_intensity"), 0.0, 5.0, 0.0)

        return SceneObject(
            name=name,
            geometry=Geometry(type=geo_type, params={}),
            material=Material(
                color=color,
                metalness=metalness,
                roughness=roughness,
                emissive=emissive,
                emissive_intensity=emissive_intensity,
            ),
            transform=Transform(
                position=[float(x) for x in position[:3]],
                rotation=[float(x) for x in rotation[:3]],
                scale=[float(x) for x in scale[:3]],
            ),
        )

    async def _refine_prominent(self, created: List[SceneObject]) -> Optional[Dict[str, Any]]:
        """Generate a downloadable GLB for the most prominent object.

        Picks the object with the largest bounding scale (a proxy for visual
        prominence) and calls ``generate_3d_asset`` with a text description
        derived from its geometry + color + material. Returns the asset URL
        descriptor on success, None on any failure (the primitive scene is
        already committed and remains useful without the refinement).
        """
        if not self.registry:
            return None
        gen_tool = self.registry.get("generate_3d_asset")
        if gen_tool is None:
            return None

        # Select the most prominent object by max scale dimension.
        def _volume(obj: SceneObject) -> float:
            s = obj.transform.scale
            return abs(s[0]) * abs(s[1]) * abs(s[2]) if len(s) >= 3 else 0.0

        prominent = max(created, key=_volume)
        prompt = self._build_refine_prompt(prominent)
        try:
            result = await gen_tool.execute(
                Scene(),  # empty scene — generate_3d_asset doesn't mutate it
                {"prompt": prompt, "output_format": "glb"},
            )
        except Exception:
            logger.exception("Refine step (generate_3d_asset) raised")
            return None
        if not result.success or not result.data.get("url"):
            return None
        return {
            "name": prominent.name,
            "prompt": prompt,
            "url": result.data.get("url"),
            "model": result.data.get("model"),
            "format": result.data.get("output_format", "glb"),
        }

    @staticmethod
    def _build_refine_prompt(obj: SceneObject) -> str:
        """Build a text-to-3D prompt from a scene object's descriptor."""
        geo = obj.geometry.type
        color = obj.material.color
        metal = obj.material.metalness
        rough = obj.material.roughness
        parts = [f"A detailed 3D model of a {geo.replace('torusKnot', 'torus knot')} shape"]
        if obj.name and obj.name.lower() != geo:
            parts[0] = f"A detailed 3D model of {obj.name}"
        parts.append(f"colored {color}")
        if metal > 0.5:
            parts.append("with a polished metallic finish")
        elif rough > 0.7:
            parts.append("with a matte rough surface")
        elif metal > 0.1:
            parts.append("with a semi-metallic finish")
        return ", ".join(parts) + "."

    async def _fallback_reconstruct(
        self, scene: Scene, prompt_text: str, clear: bool
    ) -> ToolResult:
        """Deterministic fallback when no vision LLM is available.

        Creates a small arrangement of primitives so the Agent can still
        demonstrate the image-to-3D flow without a configured model.
        """
        if clear:
            scene.objects.clear()
        # A simple three-object arrangement
        objs = [
            SceneObject(
                name="Base",
                geometry=Geometry(type="box", params={"width": 2, "height": 0.2, "depth": 2}),
                material=Material(color="#8a8a8a"),
                transform=Transform(position=[0, -0.5, 0]),
            ),
            SceneObject(
                name="Body",
                geometry=Geometry(type="cylinder", params={"radius": 0.6, "height": 1.4}),
                material=Material(color="#e84a4a"),
                transform=Transform(position=[0, 0.2, 0]),
            ),
            SceneObject(
                name="Top",
                geometry=Geometry(type="sphere", params={"radius": 0.5}),
                material=Material(color="#f2c14e"),
                transform=Transform(position=[0, 1.2, 0]),
            ),
        ]
        scene.objects.extend(objs)
        deltas = [
            SceneDelta(action="create", target_id=o.id, payload=o.to_dict()) for o in objs
        ]
        return ToolResult(
            success=True,
            message=(
                "Reconstructed 3 primitives using the offline fallback "
                "(no vision LLM configured)."
            ),
            deltas=deltas,
            data={"model_used": "offline-fallback", "object_count": len(objs)},
        )
