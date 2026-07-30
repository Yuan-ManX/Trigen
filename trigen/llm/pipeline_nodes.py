"""Pipeline node ABC and built-in node implementations.

A ``PipelineNodeBase`` is an atomic operation in a pipeline graph (LLM
call, image generation, 3D conversion, scene mutation). Each built-in
node type is a subclass; the pipeline orchestrator looks up a node
instance by ``node_type`` and calls ``execute(inputs, ctx)``.

The base class declares a ``cacheable`` flag. When true, the
orchestrator memoizes the node's result keyed by ``(node_id, inputs)``
so re-running a pipeline (or re-executing a shared sub-graph) reuses
results whose inputs have not changed, mirroring ComfyUI's per-node
caching model.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List

from trigen.config import LLMConfig
from trigen.llm.client import LLMClient
from trigen.llm.multimodal import dispatcher as multimodal_dispatcher

logger = logging.getLogger("trigen.pipeline.nodes")


@dataclass
class PipelineContext:
    """Runtime context handed to every node ``execute`` call.

    Carries the shared ``LLMConfig`` so node implementations don't each
    construct their own. Future extensions (workspace path, hook
    registry, progress reporter) can hang off this dataclass without
    breaking existing node signatures.
    """

    llm_config: LLMConfig


class PipelineNodeBase(ABC):
    """Base contract for every pipeline node type.

    Subclasses set ``node_type`` (the string used in pipeline JSON) and
    implement ``execute``. ``cacheable`` controls whether the
    orchestrator memoizes results for this node type.
    """

    node_type: str = ""
    cacheable: bool = True

    @abstractmethod
    async def execute(self, inputs: Dict[str, Any], ctx: PipelineContext) -> Dict[str, Any]:
        """Run the node and return its outputs dict.

        Raise to mark the node FAILED; the orchestrator captures the
        exception and records it on the ``NodeResult``.
        """
        ...


# ----------------------------------------------------------------------
# Built-in nodes
# ----------------------------------------------------------------------

class LLMCompleteNode(PipelineNodeBase):
    node_type = "llm_complete"
    # LLM output is non-deterministic at temperature > 0; skip caching so
    # re-runs always produce fresh text.
    cacheable = False

    async def execute(self, inputs: Dict[str, Any], ctx: PipelineContext) -> Dict[str, Any]:
        client = LLMClient(ctx.llm_config)
        messages = [{"role": "user", "content": inputs.get("prompt", "")}]
        system = inputs.get("system")
        model = inputs.get("model")
        resp = await client.complete(messages=messages, system=system, model=model)
        return {"content": resp.content, "finish_reason": resp.finish_reason}


class LLMStreamNode(PipelineNodeBase):
    node_type = "llm_stream"
    cacheable = False

    async def execute(self, inputs: Dict[str, Any], ctx: PipelineContext) -> Dict[str, Any]:
        client = LLMClient(ctx.llm_config)
        messages = [{"role": "user", "content": inputs.get("prompt", "")}]
        system = inputs.get("system")
        model = inputs.get("model")
        chunks: List[str] = []
        async for chunk in client.stream(messages=messages, system=system, model=model):
            if chunk.content:
                chunks.append(chunk.content)
        return {"content": "".join(chunks)}


class GenerateImageNode(PipelineNodeBase):
    node_type = "generate_image"

    async def execute(self, inputs: Dict[str, Any], ctx: PipelineContext) -> Dict[str, Any]:
        result = await multimodal_dispatcher.generate_image(
            model_id=inputs.get("model", "dall-e-3"),
            prompt=inputs.get("prompt", ""),
            size=inputs.get("size", "1024x1024"),
            n=int(inputs.get("n", 1)),
        )
        return {
            "success": result.success,
            "base64_data": result.base64_data,
            "url": result.url,
            "mime_type": result.mime_type,
            "error": result.error,
        }


class Generate3DNode(PipelineNodeBase):
    node_type = "generate_3d"

    async def execute(self, inputs: Dict[str, Any], ctx: PipelineContext) -> Dict[str, Any]:
        result = await multimodal_dispatcher.generate_3d(
            model_id=inputs.get("model", "meshy/text-to-3d"),
            prompt=inputs.get("prompt", ""),
            output_format=inputs.get("output_format", "glb"),
        )
        return {
            "success": result.success,
            "url": result.url,
            "error": result.error,
        }


class GenerateVideoNode(PipelineNodeBase):
    node_type = "generate_video"

    async def execute(self, inputs: Dict[str, Any], ctx: PipelineContext) -> Dict[str, Any]:
        try:
            duration = int(inputs.get("duration", 5))
        except (TypeError, ValueError):
            duration = 5
        result = await multimodal_dispatcher.generate_video(
            model_id=inputs.get("model", "runway/gen3-alpha"),
            prompt=inputs.get("prompt", ""),
            duration=duration,
        )
        return {
            "success": result.success,
            "url": result.url,
            "mime_type": result.mime_type,
            "error": result.error,
        }


class GenerateAnimationNode(PipelineNodeBase):
    node_type = "generate_animation"

    async def execute(self, inputs: Dict[str, Any], ctx: PipelineContext) -> Dict[str, Any]:
        try:
            frames = int(inputs.get("frames", 24))
        except (TypeError, ValueError):
            frames = 24
        result = await multimodal_dispatcher.generate_animation(
            model_id=inputs.get("model", ""),
            prompt=inputs.get("prompt", ""),
            frames=frames,
        )
        return {
            "success": result.success,
            "base64_data": result.base64_data,
            "url": result.url,
            "mime_type": result.mime_type,
            "error": result.error,
        }


class TTSNode(PipelineNodeBase):
    node_type = "tts"

    async def execute(self, inputs: Dict[str, Any], ctx: PipelineContext) -> Dict[str, Any]:
        result = await multimodal_dispatcher.synthesize_speech(
            model_id=inputs.get("model", "tts-1"),
            text=inputs.get("text", ""),
            voice=inputs.get("voice", "alloy"),
        )
        return {
            "success": result.success,
            "base64_data": result.base64_data,
            "mime_type": result.mime_type,
            "error": result.error,
        }


class TranscribeNode(PipelineNodeBase):
    node_type = "transcribe"

    async def execute(self, inputs: Dict[str, Any], ctx: PipelineContext) -> Dict[str, Any]:
        result = await multimodal_dispatcher.transcribe_audio(
            model_id=inputs.get("model", "whisper-1"),
            audio_base64=inputs.get("audio_base64", ""),
            mime_type=inputs.get("mime_type", "audio/wav"),
        )
        return {
            "success": result.success,
            "text": result.raw.get("text", ""),
            "error": result.error,
        }


class ImageTo3DNode(PipelineNodeBase):
    node_type = "image_to_3d"

    async def execute(self, inputs: Dict[str, Any], ctx: PipelineContext) -> Dict[str, Any]:
        from trigen.tools.img2threejs_tool import ImageToThreeJSTool
        from trigen.scene import Scene

        tool = ImageToThreeJSTool(ctx.llm_config)
        scene = Scene()
        result = await tool.execute(
            scene,
            {
                "image_base64": inputs.get("image_base64", ""),
                "image_mime": inputs.get("image_mime", "image/png"),
                "prompt": inputs.get("prompt", ""),
                "model": inputs.get("model"),
                "clear_scene": True,
            },
        )
        return {
            "success": result.success,
            "object_count": result.data.get("object_count", 0),
            "scene": scene.to_dict(),
            "message": result.message,
        }


class LiteralNode(PipelineNodeBase):
    node_type = "literal"
    # Echoes inputs; caching is pointless and would mask intent changes.
    cacheable = False

    async def execute(self, inputs: Dict[str, Any], ctx: PipelineContext) -> Dict[str, Any]:
        return dict(inputs)


class _CallableNode(PipelineNodeBase):
    """Adapter wrapping a legacy callable registered via ``register_handler``.

    Callables can't be safely introspected for cacheability, so they are
    treated as non-cacheable to preserve the prior execute-every-time
    behaviour.
    """

    cacheable = False

    def __init__(self, node_type: str, handler: Any) -> None:
        self.node_type = node_type
        self._handler = handler

    async def execute(self, inputs: Dict[str, Any], ctx: PipelineContext) -> Dict[str, Any]:
        result = self._handler(inputs)
        # Support both sync and async handlers transparently.
        if hasattr(result, "__await__"):
            result = await result
        return result


def builtin_nodes() -> List[PipelineNodeBase]:
    """Return fresh instances of every built-in node type."""
    return [
        LLMCompleteNode(),
        LLMStreamNode(),
        GenerateImageNode(),
        Generate3DNode(),
        GenerateVideoNode(),
        GenerateAnimationNode(),
        TTSNode(),
        TranscribeNode(),
        ImageTo3DNode(),
        LiteralNode(),
    ]
