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

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from trigen.config import LLMConfig

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
    cached: bool = False  # True when served from the result cache


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


# Typed schema for every built-in node type. ``inputs`` maps an input key to
# a type label ("str", "int", "bool", "dict", "any"); ``outputs`` does the
# same for the keys a handler returns. The literal node is special-cased:
# both its inputs and outputs are "any" because it just echoes its inputs.
NODE_SCHEMAS: Dict[str, Dict[str, Dict[str, str]]] = {
    "llm_complete": {
        "inputs": {"prompt": "str", "system": "str", "model": "str"},
        "outputs": {"content": "str", "finish_reason": "str"},
    },
    "llm_stream": {
        "inputs": {"prompt": "str", "system": "str", "model": "str"},
        "outputs": {"content": "str"},
    },
    "generate_image": {
        "inputs": {
            "model": "str",
            "prompt": "str",
            "size": "str",
            "n": "int",
        },
        "outputs": {
            "success": "bool",
            "base64_data": "str",
            "url": "str",
            "mime_type": "str",
            "error": "str",
        },
    },
    "generate_3d": {
        "inputs": {"model": "str", "prompt": "str", "output_format": "str"},
        "outputs": {"success": "bool", "url": "str", "error": "str"},
    },
    "generate_video": {
        "inputs": {"model": "str", "prompt": "str", "duration": "int"},
        "outputs": {"success": "bool", "url": "str", "mime_type": "str", "error": "str"},
    },
    "generate_animation": {
        "inputs": {"model": "str", "prompt": "str", "frames": "int"},
        "outputs": {
            "success": "bool",
            "base64_data": "str",
            "url": "str",
            "mime_type": "str",
            "error": "str",
        },
    },
    "tts": {
        "inputs": {"model": "str", "text": "str", "voice": "str"},
        "outputs": {"success": "bool", "base64_data": "str", "mime_type": "str", "error": "str"},
    },
    "transcribe": {
        "inputs": {"model": "str", "audio_base64": "str", "mime_type": "str"},
        "outputs": {"success": "bool", "text": "str", "error": "str"},
    },
    "image_to_3d": {
        "inputs": {
            "image_base64": "str",
            "image_mime": "str",
            "prompt": "str",
            "model": "str",
        },
        "outputs": {
            "success": "bool",
            "object_count": "int",
            "scene": "dict",
            "message": "str",
        },
    },
    "literal": {
        "inputs": {},
        "outputs": {},
    },
}


class PipelineValidationError(ValueError):
    """Raised when a pipeline definition fails structural validation."""


def _is_type_compatible(output_type: str, input_type: str) -> bool:
    """Return True if an output type can feed an input type.

    ``any`` is compatible with everything. Matching types are compatible.
    Otherwise the pair is incompatible (e.g. feeding an ``int`` output into a
    ``dict`` input is a type mismatch).
    """
    if output_type == "any" or input_type == "any":
        return True
    return output_type == input_type


class PipelineOrchestrator:
    """Executes a pipeline DAG by topologically sorting and running nodes.

    Each node type is backed by a ``PipelineNodeBase`` instance held in the
    node registry. Outputs from upstream nodes are injected into downstream
    nodes via the {"from": "<node_id>", "output": "<key>"} reference syntax.

    Per-node result caching (ComfyUI-style): when a node's ``cacheable``
    flag is true, the orchestrator memoizes its SUCCESS result keyed by
    ``(node_id, inputs)``. Re-running a pipeline (or re-executing a shared
    sub-graph) reuses results whose inputs have not changed, avoiding
    redundant LLM / image-generation calls. Non-cacheable nodes (LLM
    completions, literals, ad-hoc callables) always re-execute.
    """

    def __init__(self, llm_config: Optional[LLMConfig] = None) -> None:
        from trigen.llm.pipeline_nodes import (
            PipelineContext,
            PipelineNodeBase,
            _CallableNode,
            builtin_nodes,
        )

        self.llm_config = llm_config or LLMConfig()
        self._ctx = PipelineContext(llm_config=self.llm_config)
        self._node_registry: Dict[str, "PipelineNodeBase"] = {}
        for node in builtin_nodes():
            self._node_registry[node.node_type] = node
        # Result cache: (node_id, inputs_hash) -> NodeResult
        self._cache: Dict[str, NodeResult] = {}

    def register_handler(self, node_type: str, handler: Any) -> None:
        """Register a custom node handler callable at runtime.

        Supports both sync and async callables. Wrapped as a
        ``_CallableNode`` (non-cacheable) so legacy registrations keep the
        prior execute-every-time behaviour.
        """
        from trigen.llm.pipeline_nodes import _CallableNode

        self._node_registry[node_type] = _CallableNode(node_type, handler)

    def register_node(self, node: Any) -> None:
        """Register a ``PipelineNodeBase`` instance by its ``node_type``."""
        self._node_registry[node.node_type] = node

    def clear_cache(self) -> int:
        """Drop all cached node results. Returns the number cleared."""
        n = len(self._cache)
        self._cache.clear()
        return n

    async def execute(self, pipeline: Pipeline) -> List[NodeResult]:
        """Execute the pipeline and return per-node results.

        Nodes whose upstream dependencies failed or were skipped are
        themselves marked SKIPPED rather than executed with empty inputs,
        so a single upstream failure does not cascade into confusing
        downstream errors.
        """
        results: Dict[str, NodeResult] = {}
        # Topological order is implied by node list order in the pipeline
        # definition; cycles are the author's responsibility.
        for node in pipeline.nodes:
            result = await self._run_node_with_deps(node, results)
            results[node.id] = result
        return list(results.values())

    async def execute_stream(
        self, pipeline: Pipeline
    ) -> Any:
        """Execute the pipeline, yielding each NodeResult as it completes.

        Yields dicts with: event ("start" | "result" | "done"), node_id,
        status, outputs, error, elapsed_ms, cached. Allows the frontend to
        show real-time progress as each node finishes.
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
            result = await self._run_node_with_deps(node, results)
            results[node.id] = result
            yield {
                "event": "result",
                "node_id": result.node_id,
                "status": result.status.value,
                "outputs": result.outputs,
                "error": result.error,
                "elapsed_ms": result.elapsed_ms,
                "cached": result.cached,
                "index": idx,
                "total": total,
            }

        total_elapsed = int((time.time() - total_start) * 1000)
        succeeded = sum(1 for r in results.values() if r.status == NodeStatus.SUCCESS)
        failed = sum(1 for r in results.values() if r.status == NodeStatus.FAILED)
        cached = sum(1 for r in results.values() if r.cached)
        yield {
            "event": "done",
            "name": pipeline.name,
            "total_elapsed_ms": total_elapsed,
            "node_count": total,
            "succeeded": succeeded,
            "failed": failed,
            "cached": cached,
        }

    async def _run_node_with_deps(
        self, node: PipelineNode, results: Dict[str, NodeResult]
    ) -> NodeResult:
        """Run a node, skipping it if any upstream dependency did not succeed.

        If an upstream node failed, was skipped, or is missing entirely, the
        downstream node is marked SKIPPED with a descriptive error instead of
        being executed with empty string inputs. This surfaces the real root
        cause (the upstream failure) rather than a confusing downstream error.
        """
        # Check every upstream dependency before running
        for value in node.inputs.values():
            if isinstance(value, dict) and "from" in value and "output" in value:
                upstream_id = value["from"]
                upstream = results.get(upstream_id)
                if upstream is None:
                    return NodeResult(
                        node_id=node.id,
                        status=NodeStatus.SKIPPED,
                        error=f"Upstream node '{upstream_id}' not found",
                    )
                if upstream.status != NodeStatus.SUCCESS:
                    return NodeResult(
                        node_id=node.id,
                        status=NodeStatus.SKIPPED,
                        error=(
                            f"Upstream node '{upstream_id}' did not succeed "
                            f"(status={upstream.status.value})"
                        ),
                    )
        resolved_inputs = self._resolve_inputs(node, results)
        return await self._run_node(node, resolved_inputs)

    def _resolve_inputs(
        self, node: PipelineNode, results: Dict[str, NodeResult]
    ) -> Dict[str, Any]:
        """Resolve input references that point to upstream node outputs.

        At this point upstream viability has already been checked by
        ``_run_node_with_deps``, so we only need to pull the value. A missing
        output key resolves to an empty string to preserve backward
        compatibility with handlers that tolerate it.
        """
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

    @staticmethod
    def _cache_key(node: PipelineNode, inputs: Dict[str, Any]) -> str:
        """Stable cache key for ``(node.id, canonical inputs)``.

        Uses sha1 over a sorted-key JSON dump so dict insertion order does
        not defeat the cache. Inputs containing non-JSON-serializable
        values fall back to their ``repr``.
        """
        import hashlib
        import json

        try:
            blob = json.dumps(inputs, sort_keys=True, ensure_ascii=False)
        except (TypeError, ValueError):
            blob = repr(sorted(inputs.items()))
        digest = hashlib.sha1(blob.encode("utf-8")).hexdigest()
        return f"{node.id}:{node.type}:{digest}"

    async def _run_node(
        self, node: PipelineNode, inputs: Dict[str, Any]
    ) -> NodeResult:
        """Run a single node, consulting the cache for cacheable types."""
        import time

        impl = self._node_registry.get(node.type)
        if impl is None:
            return NodeResult(
                node_id=node.id,
                status=NodeStatus.FAILED,
                error=f"Unknown node type: {node.type}",
            )

        # Cache lookup (only SUCCESS results are cached, and only for
        # cacheable node types).
        if getattr(impl, "cacheable", False):
            key = self._cache_key(node, inputs)
            hit = self._cache.get(key)
            if hit is not None and hit.status == NodeStatus.SUCCESS:
                return NodeResult(
                    node_id=hit.node_id,
                    status=NodeStatus.SUCCESS,
                    outputs=dict(hit.outputs),
                    elapsed_ms=0,
                    cached=True,
                )

        start = time.time()
        try:
            outputs = await impl.execute(inputs, self._ctx)
            elapsed = int((time.time() - start) * 1000)
            result = NodeResult(
                node_id=node.id,
                status=NodeStatus.SUCCESS,
                outputs=outputs,
                elapsed_ms=elapsed,
            )
            if getattr(impl, "cacheable", False):
                self._cache[key] = result
            return result
        except Exception as exc:
            elapsed = int((time.time() - start) * 1000)
            logger.exception("Pipeline node %s failed", node.id)
            return NodeResult(
                node_id=node.id,
                status=NodeStatus.FAILED,
                error=str(exc),
                elapsed_ms=elapsed,
            )


# Global orchestrator instance
orchestrator = PipelineOrchestrator()


def _node_output_schema(node_type: str) -> Dict[str, str]:
    """Return the output schema for a node type, falling back to empty."""
    schema = NODE_SCHEMAS.get(node_type, {})
    return dict(schema.get("outputs", {}))


def parse_pipeline(definition: Dict[str, Any]) -> Pipeline:
    """Parse and structurally validate a pipeline definition dict.

    Validation checks (raise PipelineValidationError on failure):
      1. Every node has an ``id`` and ``type``.
      2. Node ids are unique within the pipeline.
      3. Every node ``type`` is a registered handler (or appears in
         NODE_SCHEMAS for built-ins).
      4. Every edge ``{"from": X, "output": Y}`` references an upstream
         node X that appears earlier in the node list (DAG ordering).
      5. The referenced output key Y exists in the upstream node's
         output schema.
      6. The output type is compatible with the downstream input type
         when both are concrete (non-``any``).

    Custom handler types registered via ``register_handler`` but absent
    from NODE_SCHEMAS skip edge-output and type checks (treated as ``any``).
    """
    raw_nodes = definition.get("nodes", [])
    if not isinstance(raw_nodes, list):
        raise PipelineValidationError("'nodes' must be a list")

    seen_ids: set[str] = set()
    # First pass: build PipelineNode list and validate ids/types
    nodes: List[PipelineNode] = []
    for idx, n in enumerate(raw_nodes):
        if not isinstance(n, dict):
            raise PipelineValidationError(f"Node #{idx} is not an object")
        node_id = n.get("id")
        node_type = n.get("type")
        if not node_id:
            raise PipelineValidationError(f"Node #{idx} is missing 'id'")
        if not node_type:
            raise PipelineValidationError(f"Node '{node_id}' is missing 'type'")
        if node_id in seen_ids:
            raise PipelineValidationError(f"Duplicate node id: '{node_id}'")
        # Accept both built-in schema types and runtime-registered nodes
        known = node_type in NODE_SCHEMAS or node_type in orchestrator._node_registry
        if not known:
            raise PipelineValidationError(
                f"Node '{node_id}' has unknown type '{node_type}'"
            )
        seen_ids.add(node_id)
        nodes.append(
            PipelineNode(id=node_id, type=node_type, inputs=n.get("inputs", {}))
        )

    # Second pass: validate edges and type compatibility
    # Map node id -> index so we can enforce DAG ordering (forward refs forbidden)
    id_to_index = {n.id: i for i, n in enumerate(nodes)}
    for idx, node in enumerate(nodes):
        node_input_schema = NODE_SCHEMAS.get(node.type, {}).get("inputs", {})
        for input_key, value in node.inputs.items():
            if not (isinstance(value, dict) and "from" in value and "output" in value):
                continue
            upstream_id = value["from"]
            output_key = value["output"]
            if upstream_id not in id_to_index:
                raise PipelineValidationError(
                    f"Node '{node.id}' input '{input_key}' references "
                    f"unknown upstream node '{upstream_id}'"
                )
            if id_to_index[upstream_id] >= idx:
                raise PipelineValidationError(
                    f"Node '{node.id}' input '{input_key}' references "
                    f"upstream node '{upstream_id}' that appears later in the "
                    f"pipeline (forward references are not allowed)"
                )
            upstream_outputs = _node_output_schema(nodes[id_to_index[upstream_id]].type)
            if upstream_outputs and output_key not in upstream_outputs:
                raise PipelineValidationError(
                    f"Node '{node.id}' input '{input_key}' references output "
                    f"'{output_key}' which is not produced by upstream node "
                    f"'{upstream_id}' (available: {sorted(upstream_outputs)})"
                )
            # Type compatibility check (skip when either side is unknown/any)
            if upstream_outputs and node_input_schema:
                out_type = upstream_outputs.get(output_key, "any")
                in_type = node_input_schema.get(input_key, "any")
                if not _is_type_compatible(out_type, in_type):
                    raise PipelineValidationError(
                        f"Node '{node.id}' input '{input_key}' expects type "
                        f"'{in_type}' but upstream output '{output_key}' of "
                        f"'{upstream_id}' is type '{out_type}'"
                    )

    return Pipeline(nodes=nodes, name=definition.get("name", "untitled"))
