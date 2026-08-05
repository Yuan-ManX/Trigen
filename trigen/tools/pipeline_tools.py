"""Pipeline authoring tools — let the Agent compose multimodal node-graphs.

These tools give the Agent a way to author and inspect multimodal pipeline
DAGs (the same shape consumed by the ``/api/models/pipeline`` endpoints and
rendered by the frontend ``NodeGraphView``) without executing them. The
Agent can propose a pipeline graph in chat; the frontend renders it and the
user triggers execution via the existing Run button.

Two tools live here:

  - ``compose_pipeline``: validates a node + edge definition against the
    pipeline schema and returns a structured graph payload (nodes + edges
    in the frontend's expected shape) ready for rendering.
  - ``list_pipeline_templates``: returns the built-in pipeline templates so
    the Agent can suggest a known recipe by name without the user having
    to leave the chat surface.

Neither tool mutates the 3D scene. Both are read-only / structuring tools.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from trigen.scene import Scene
from trigen.tools.base import ToolBase, ToolResult

logger = logging.getLogger("trigen.tools.pipeline")


_COMPOSE_PIPELINE_PARAMS = {
    "type": "object",
    "properties": {
        "name": {
            "type": "string",
            "description": "Pipeline name (human-readable).",
        },
        "nodes": {
            "type": "array",
            "description": (
                "Ordered list of pipeline nodes. Each node is an object with "
                "'id' (unique), 'type' (a registered node type such as "
                "'llm_complete', 'generate_image', 'generate_3d', "
                "'generate_video', 'tts', 'transcribe', 'image_to_3d', or "
                "'literal'), and 'inputs' (a dict mapping input port names "
                "to literal values or to {'from': <upstream_node_id>, "
                "'output': <upstream_output_port>} reference objects)."
            ),
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "type": {"type": "string"},
                    "inputs": {"type": "object", "additionalProperties": True},
                },
                "required": ["id", "type"],
            },
        },
    },
    "required": ["name", "nodes"],
}


_LIST_PIPELINE_TEMPLATES_PARAMS = {
    "type": "object",
    "properties": {},
    "required": [],
}


def _node_category(node_type: str) -> str:
    """Map a pipeline node type to a frontend-renderable category label."""
    return {
        "llm_complete": "llm",
        "llm_stream": "llm",
        "generate_image": "image",
        "generate_3d": "three_d",
        "generate_video": "video",
        "generate_animation": "video",
        "tts": "audio",
        "transcribe": "audio",
        "image_to_3d": "three_d",
        "literal": "utility",
    }.get(node_type, "utility")


def _derive_edges(nodes: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """Extract frontend-shaped edges from a pipeline node list.

    Each input value of the form ``{"from": X, "output": Y}`` becomes an
    edge ``{from: X, output: Y, to: <node_id>, input: <input_key>}`` matching
    the ``PipelineGraphEdge`` contract the frontend renders.
    """
    edges: List[Dict[str, str]] = []
    for node in nodes:
        node_id = node.get("id")
        if not isinstance(node_id, str):
            continue
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            continue
        for input_key, value in inputs.items():
            if (
                isinstance(value, dict)
                and "from" in value
                and "output" in value
            ):
                edges.append({
                    "from": str(value["from"]),
                    "output": str(value["output"]),
                    "to": node_id,
                    "input": str(input_key),
                })
    return edges


def _graph_payload(
    name: str, nodes: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Build the structured graph payload returned by ``compose_pipeline``.

    Returns a dict with ``name``, ``nodes`` (each enriched with a
    ``category`` label and an empty ``position`` placeholder so the
    frontend can lay it out), and ``edges`` (derived from input refs).
    """
    graph_nodes: List[Dict[str, Any]] = []
    for idx, node in enumerate(nodes):
        node_id = node.get("id", f"node_{idx}")
        node_type = node.get("type", "")
        graph_nodes.append({
            "id": str(node_id),
            "type": str(node_type),
            "category": _node_category(str(node_type)),
            "inputs": node.get("inputs", {}) or {},
            # Placeholder canvas position; the frontend assigns a real
            # layout when it mounts the graph. Stacking vertically with a
            # small horizontal offset keeps the initial render readable.
            "position": {"x": 80 + (idx % 4) * 260, "y": 80 + (idx // 4) * 180},
        })
    edges = _derive_edges(nodes)
    return {
        "name": name,
        "nodes": graph_nodes,
        "edges": edges,
    }


class ComposePipelineTool(ToolBase):
    """Author a multimodal pipeline DAG without executing it.

    Validates the supplied node + edge definition against the pipeline
    schema (via ``parse_pipeline``) and returns a structured graph payload
    the frontend ``NodeGraphView`` can render directly. The Agent uses
    this to propose a pipeline in chat; the user triggers execution via
    the existing Run button on the rendered graph.
    """

    name = "compose_pipeline"
    description = (
        "Compose (author) a multimodal pipeline node-graph from a node list "
        "without executing it. Validates the DAG structure and returns a "
        "graph payload the frontend renders in the node-graph editor. Use "
        "this when the user asks to design, draft, or preview a multimodal "
        "pipeline (e.g. 'text-to-image-to-3d'). The user runs the composed "
        "pipeline from the graph editor's Run button — this tool does not "
        "execute anything."
    )

    def schema(self) -> Dict[str, Any]:
        return _COMPOSE_PIPELINE_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        raw_name = str(arguments.get("name", "")).strip()
        if not raw_name:
            return ToolResult(success=False, message="Missing 'name' argument")
        raw_nodes = arguments.get("nodes")
        if not isinstance(raw_nodes, list) or not raw_nodes:
            return ToolResult(
                success=False,
                message="'nodes' must be a non-empty array of node objects",
            )

        # Validate the pipeline DAG via the shared parser. This catches
        # unknown node types, duplicate ids, forward references, missing
        # upstream outputs, and type mismatches — same checks the real
        # execution path enforces.
        try:
            from trigen.llm.pipeline import (
                PipelineValidationError,
                parse_pipeline,
            )
        except Exception as exc:
            logger.exception("pipeline module unavailable")
            return ToolResult(
                success=False,
                message=f"Pipeline module unavailable: {exc}",
            )
        definition = {"name": raw_name, "nodes": raw_nodes}
        try:
            pipeline = parse_pipeline(definition)
        except PipelineValidationError as exc:
            return ToolResult(
                success=False,
                message=f"Pipeline validation failed: {exc}",
                data={"name": raw_name, "validation_error": str(exc)},
            )

        payload = _graph_payload(pipeline.name, raw_nodes)
        edge_count = len(payload["edges"])
        summary = (
            f"Pipeline '{pipeline.name}' composed with {len(payload['nodes'])} "
            f"node(s) and {edge_count} edge(s). Render it in the node-graph "
            f"editor; the user can run it from there."
        )
        return ToolResult(
            success=True,
            message=summary,
            data={
                "name": pipeline.name,
                "graph": payload,
                "definition": definition,
                "node_count": len(payload["nodes"]),
                "edge_count": edge_count,
            },
        )


class ListPipelineTemplatesTool(ToolBase):
    """List the built-in multimodal pipeline templates.

    Returns the curated set of pre-built pipeline recipes (text→image→3D,
    LLM→image, text→speech, audio→text, etc.) so the Agent can suggest a
    known template by name in chat. The user can then load the template
    from the node-graph editor's palette. Read-only — never executes.
    """

    name = "list_pipeline_templates"
    description = (
        "List the built-in multimodal pipeline templates (e.g. text-to-image-"
        "to-3d, llm-then-image, text-to-speech). Use this to suggest a known "
        "recipe by name when the user asks for a multimodal workflow but has "
        "not specified exact nodes. Read-only; does not execute anything."
    )

    def schema(self) -> Dict[str, Any]:
        return _LIST_PIPELINE_TEMPLATES_PARAMS

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        try:
            from trigen.api.routers.models import PIPELINE_TEMPLATES
        except Exception as exc:
            logger.exception("pipeline templates module unavailable")
            return ToolResult(
                success=False,
                message=f"Pipeline templates unavailable: {exc}",
            )
        # Strip the heavy per-node inputs to keep the chat-facing summary
        # concise — the user only needs the id, name, description, and node
        # count to pick a template; full definition is loaded from the
        # editor palette.
        summaries: List[Dict[str, Any]] = []
        for tpl in PIPELINE_TEMPLATES:
            summaries.append({
                "id": tpl.get("id"),
                "name": tpl.get("name"),
                "description": tpl.get("description"),
                "node_count": len(tpl.get("nodes", [])),
            })
        return ToolResult(
            success=True,
            message=f"{len(summaries)} pipeline template(s) available.",
            data={"templates": summaries, "count": len(summaries)},
        )
