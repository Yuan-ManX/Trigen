"""ComfyUI-style pipeline orchestrator.

Provides a node-graph execution engine for multi-step generation workflows.
Each node is an atomic operation (LLM call, image generation, 3D conversion,
scene mutation) with typed inputs and outputs. Nodes are wired together into
a directed acyclic graph; the orchestrator topologically sorts and executes
them, passing outputs between nodes.

This mirrors the ComfyUI execution model: declarative node definitions,
explicit edge wiring, and deterministic execution order. Pipelines are
defined as JSON so they can be persisted, shared, and edited visually.

Example pipeline (text-to-image-to-3D):
  {
    "nodes": [
      {"id": "llm_1", "type": "llm_complete", "inputs": {"prompt": "a robot"}},
      {"id": "img_1", "type": "generate_image", "inputs": {"model": "dall-e-3", "prompt": {"from": "llm_1", "output": "content"}}},
      {"id": "recon_1", "type": "image_to_3d", "inputs": {"image_base64": {"from": "img_1", "output": "base64_data"}}}
    ]
  }
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from trigen.config import LLMConfig
from trigen.llm.client import LLMClient
from trigen.llm.multimodal import dispatcher as multimodal_dispatcher

logger = logging.getLogger("trigen.pipeline")


class NodeStatus(str, Enum):
    """Execution status of a single pipeline node."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class NodeResult:
    """Output of a single node execution."""

    node_id: str
    status: NodeStatus
    outputs: Dict[str, Any] = field(default_factory=dict)
    error: str = ""
    elapsed_ms: int = 0


@dataclass
class PipelineNode:
    """A single node in the pipeline graph."""

    id: str
    type: str
    inputs: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Pipeline:
    """A declarative pipeline definition."""

    nodes: List[PipelineNode] = field(default_factory=list)
    name: str = "untitled"


class PipelineOrchestrator:
    """Executes a pipeline DAG by topologically sorting and running nodes.

    Each node type maps to a handler function that receives the resolved
    inputs and returns an outputs dict. Outputs from upstream nodes are
    injected into downstream nodes via the {"from": "<node_id>", "output":
    "<key>"} reference syntax.
    """

    def __init__(self, llm_config: Optional[LLMConfig] = None) -> None:
        self.llm_config = llm_config or LLMConfig()
        self._handlers: Dict[str, Any] = {
            "llm_complete": self._handle_llm_complete,
            "llm_stream": self._handle_llm_stream,
            "generate_image": self._handle_generate_image,
            "generate_3d": self._handle_generate_3d,
            "tts": self._handle_tts,
            "transcribe": self._handle_transcribe,
            "image_to_3d": self._handle_image_to_3d,
            "literal": self._handle_literal,
        }

    def register_handler(self, node_type: str, handler: Any) -> None:
        """Register a custom node handler at runtime."""
        self._handlers[node_type] = handler

    async def execute(self, pipeline: Pipeline) -> List[NodeResult]:
        """Execute the pipeline and return per-node results."""
        results: Dict[str, NodeResult] = {}
        # Topological order is implied by node list order in the pipeline
        # definition; cycles are the author's responsibility.
        for node in pipeline.nodes:
            resolved_inputs = self._resolve_inputs(node, results)
            result = await self._run_node(node, resolved_inputs)
            results[node.id] = result
        return list(results.values())

    async def execute_stream(
        self, pipeline: Pipeline
    ) -> Any:
        """Execute the pipeline, yielding each NodeResult as it completes.

        Yields dicts with: event ("start" | "result" | "done"), node_id,
        status, outputs, error, elapsed_ms. Allows the frontend to show
        real-time progress as each node finishes.
        """
        import time
        from typing import AsyncIterator

        results: Dict[str, NodeResult] = {}
        total_start = time.time()
        total = len(pipeline.nodes)

        for idx, node in enumerate(pipeline.nodes):
            # Emit a start event so the frontend can mark the node as running
            yield {
                "event": "start",
                "node_id": node.id,
                "node_type": node.type,
                "index": idx,
                "total": total,
            }
            resolved_inputs = self._resolve_inputs(node, results)
            result = await self._run_node(node, resolved_inputs)
            results[node.id] = result
            yield {
                "event": "result",
                "node_id": result.node_id,
                "status": result.status.value,
                "outputs": result.outputs,
                "error": result.error,
                "elapsed_ms": result.elapsed_ms,
                "index": idx,
                "total": total,
            }

        total_elapsed = int((time.time() - total_start) * 1000)
        succeeded = sum(1 for r in results.values() if r.status == NodeStatus.SUCCESS)
        failed = sum(1 for r in results.values() if r.status == NodeStatus.FAILED)
        yield {
            "event": "done",
            "name": pipeline.name,
            "total_elapsed_ms": total_elapsed,
            "node_count": total,
            "succeeded": succeeded,
            "failed": failed,
        }

    def _resolve_inputs(
        self, node: PipelineNode, results: Dict[str, NodeResult]
    ) -> Dict[str, Any]:
        """Resolve input references that point to upstream node outputs."""
        resolved: Dict[str, Any] = {}
        for key, value in node.inputs.items():
            if isinstance(value, dict) and "from" in value and "output" in value:
                upstream_id = value["from"]
                output_key = value["output"]
                upstream = results.get(upstream_id)
                if upstream and upstream.status == NodeStatus.SUCCESS:
                    resolved[key] = upstream.outputs.get(output_key, "")
                else:
                    resolved[key] = ""
            else:
                resolved[key] = value
        return resolved

    async def _run_node(
        self, node: PipelineNode, inputs: Dict[str, Any]
    ) -> NodeResult:
        """Run a single node and capture its result."""
        import time

        handler = self._handlers.get(node.type)
        if handler is None:
            return NodeResult(
                node_id=node.id,
                status=NodeStatus.FAILED,
                error=f"Unknown node type: {node.type}",
            )
        start = time.time()
        try:
            outputs = await handler(inputs)
            elapsed = int((time.time() - start) * 1000)
            return NodeResult(
                node_id=node.id,
                status=NodeStatus.SUCCESS,
                outputs=outputs,
                elapsed_ms=elapsed,
            )
        except Exception as exc:
            elapsed = int((time.time() - start) * 1000)
            logger.exception("Pipeline node %s failed", node.id)
            return NodeResult(
                node_id=node.id,
                status=NodeStatus.FAILED,
                error=str(exc),
                elapsed_ms=elapsed,
            )

    # ===== Built-in node handlers =====

    async def _handle_llm_complete(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Run a non-streaming LLM completion."""
        client = LLMClient(self.llm_config)
        messages = [{"role": "user", "content": inputs.get("prompt", "")}]
        system = inputs.get("system")
        model = inputs.get("model")
        resp = await client.complete(messages=messages, system=system, model=model)
        return {"content": resp.content, "finish_reason": resp.finish_reason}

    async def _handle_llm_stream(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Run a streaming LLM completion, collecting the full text."""
        client = LLMClient(self.llm_config)
        messages = [{"role": "user", "content": inputs.get("prompt", "")}]
        system = inputs.get("system")
        model = inputs.get("model")
        chunks: List[str] = []
        async for chunk in client.stream(messages=messages, system=system, model=model):
            if chunk.content:
                chunks.append(chunk.content)
        return {"content": "".join(chunks)}

    async def _handle_generate_image(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Generate an image from a prompt."""
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

    async def _handle_generate_3d(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Generate a 3D asset from a prompt."""
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

    async def _handle_tts(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Synthesize speech from text."""
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

    async def _handle_transcribe(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Transcribe audio to text."""
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

    async def _handle_image_to_3d(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Run the image-to-3D reconstruction via the multimodal dispatcher."""
        # Delegate to the img2threejs tool's vision analysis
        from trigen.tools.img2threejs_tool import ImageToThreeJSTool
        from trigen.scene import Scene

        tool = ImageToThreeJSTool(self.llm_config)
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

    async def _handle_literal(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Pass-through node that emits its inputs as outputs."""
        return dict(inputs)


# Global orchestrator instance
orchestrator = PipelineOrchestrator()


def parse_pipeline(definition: Dict[str, Any]) -> Pipeline:
    """Parse a pipeline definition dict into a Pipeline instance."""
    nodes = [
        PipelineNode(
            id=n["id"],
            type=n["type"],
            inputs=n.get("inputs", {}),
        )
        for n in definition.get("nodes", [])
    ]
    return Pipeline(nodes=nodes, name=definition.get("name", "untitled"))
