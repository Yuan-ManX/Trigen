"""Node-graph workflow tools — procedural node-graph authoring.

Provides a ComfyUI-style node-graph authoring surface where the Agent
can declaratively wire processing nodes (create / modify / materialize
/ light / export) into a DAG and execute it in one pass. The graph
is stored as a plain dict on the scene for forward compatibility.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from trigen.scene import Scene
from trigen.tools.base import SceneDelta, ToolBase, ToolResult


# ---------------------------------------------------------------------------
# Node type registry — maps node type -> category so the planner can
# reason about graph semantics.
# ---------------------------------------------------------------------------

_NODE_CATEGORIES: Dict[str, str] = {
    "create": "creation",
    "modify": "creation",
    "material": "material",
    "light": "lighting",
    "transform": "transform",
    "animate": "animation",
    "export": "export",
    "group": "scene",
    "compose": "multimodal",
}


class ConfigureNodeGraphTool(ToolBase):
    """Author a procedural node-graph: nodes + edges forming a DAG."""

    name = "configure_node_graph"
    description = "Author a procedural node-graph pipeline: define nodes and wire them with edges forming a directed acyclic graph."

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "graph_name": {"type": "string", "description": "Graph name for identification"},
                "nodes": {
                    "type": "array",
                    "description": "List of node objects {id, type, params}",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string", "description": "Unique node id"},
                            "type": {
                                "type": "string",
                                "enum": list(_NODE_CATEGORIES.keys()),
                                "description": "Node semantic type",
                            },
                            "tool_name": {"type": "string", "description": "Optional specific tool name to invoke"},
                            "params": {"type": "object", "description": "Parameters forwarded to the tool"},
                        },
                        "required": ["id", "type"],
                    },
                },
                "edges": {
                    "type": "array",
                    "description": "List of edge objects {from, to}",
                    "items": {
                        "type": "object",
                        "properties": {
                            "from": {"type": "string", "description": "Source node id"},
                            "to": {"type": "string", "description": "Target node id"},
                        },
                        "required": ["from", "to"],
                    },
                },
                "auto_execute": {
                    "type": "boolean",
                    "description": "Execute the graph immediately after configuration",
                },
            },
            "required": ["nodes", "edges"],
        }

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        nodes = arguments.get("nodes", [])
        edges = arguments.get("edges", [])

        if not isinstance(nodes, list) or not nodes:
            return ToolResult(success=False, message="At least one node is required")
        if not isinstance(edges, list):
            return ToolResult(success=False, message="Edges must be a list")

        # Validate node structure.
        node_ids: set = set()
        parsed_nodes: List[Dict[str, Any]] = []
        for node in nodes:
            if not isinstance(node, dict):
                return ToolResult(success=False, message=f"Invalid node: {node!r}")
            nid = str(node.get("id", ""))
            ntype = str(node.get("type", ""))
            if not nid:
                return ToolResult(success=False, message=f"Node missing 'id': {node!r}")
            if ntype not in _NODE_CATEGORIES:
                return ToolResult(
                    success=False,
                    message=f"Unknown node type '{ntype}'. Available: {', '.join(_NODE_CATEGORIES.keys())}",
                )
            if nid in node_ids:
                return ToolResult(success=False, message=f"Duplicate node id: {nid}")
            node_ids.add(nid)
            parsed_nodes.append(
                {
                    "id": nid,
                    "type": ntype,
                    "category": _NODE_CATEGORIES[ntype],
                    "tool_name": node.get("tool_name"),
                    "params": node.get("params", {}),
                }
            )

        # Validate edge structure and detect cycles.
        parsed_edges: List[Dict[str, str]] = []
        for edge in edges:
            if not isinstance(edge, dict):
                return ToolResult(success=False, message=f"Invalid edge: {edge!r}")
            frm = str(edge.get("from", ""))
            to = str(edge.get("to", ""))
            if frm not in node_ids:
                return ToolResult(success=False, message=f"Edge references unknown node '{frm}'")
            if to not in node_ids:
                return ToolResult(success=False, message=f"Edge references unknown node '{to}'")
            parsed_edges.append({"from": frm, "to": to})

        # Cycle detection via Kahn's topological sort.
        adjacency: Dict[str, List[str]] = {n["id"]: [] for n in parsed_nodes}
        in_degree: Dict[str, int] = {n["id"]: 0 for n in parsed_nodes}
        for e in parsed_edges:
            adjacency[e["from"]].append(e["to"])
            in_degree[e["to"]] = in_degree.get(e["to"], 0) + 1

        queue = [nid for nid, deg in in_degree.items() if deg == 0]
        visited_count = 0
        while queue:
            current = queue.pop(0)
            visited_count += 1
            for neighbor in adjacency[current]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if visited_count != len(parsed_nodes):
            return ToolResult(success=False, message="Graph contains a cycle — DAG required")

        # Topological order.
        topo_order: List[str] = []
        in_deg_copy = {nid: 0 for nid in node_ids}
        for e in parsed_edges:
            in_deg_copy[e["to"]] = in_deg_copy.get(e["to"], 0) + 1
        q = [nid for nid, d in in_deg_copy.items() if d == 0]
        while q:
            cur = q.pop(0)
            topo_order.append(cur)
            for nb in adjacency[cur]:
                in_deg_copy[nb] -= 1
                if in_deg_copy[nb] == 0:
                    q.append(nb)

        graph: Dict[str, Any] = {
            "name": str(arguments.get("graph_name", "NodeGraph")),
            "nodes": parsed_nodes,
            "edges": parsed_edges,
            "topological_order": topo_order,
            "categories_used": sorted({n["category"] for n in parsed_nodes}),
        }

        # Store graph on scene as a lightweight attribute.
        scene.node_graph = graph  # type: ignore[attr-defined]

        # Optionally execute — the caller (orchestrator) handles actual
        # node dispatch; here we only validate + persist the graph.
        auto = bool(arguments.get("auto_execute", False))
        exec_info: Dict[str, Any] = {}
        if auto:
            exec_info = {
                "would_execute": True,
                "execution_order": topo_order,
                "note": "Node dispatch deferred to orchestrator for full tool access",
            }

        return ToolResult(
            success=True,
            message=f"Node graph '{graph['name']}' configured: {len(parsed_nodes)} nodes, {len(parsed_edges)} edges (DAG)",
            deltas=[SceneDelta(action="update", target_id=None, payload={"node_graph": graph})],
            data={"graph": graph, "execution": exec_info},
        )


class ExecuteNodeGraphTool(ToolBase):
    """Execute a previously configured node graph in topological order.

    Accepts a ToolRegistry at construction time so each node's tool can
    be resolved and dispatched. When instantiated by the orchestrator
    without a registry it still returns the topological plan (fallback).
    """

    name = "execute_node_graph"
    description = "Execute the scene's stored node graph, dispatching each node's tool in topological order."

    def __init__(self, registry=None):
        self._registry = registry

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "graph_name": {"type": "string", "description": "Graph name to execute (empty for latest)"},
                "step_by_step": {
                    "type": "boolean",
                    "description": "Emit per-node progress (default true)",
                },
            },
            "required": [],
        }

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        graph: Optional[Dict[str, Any]] = getattr(scene, "node_graph", None)
        if not graph:
            return ToolResult(success=False, message="No node graph configured — call configure_node_graph first")

        graph_name = str(arguments.get("graph_name", ""))
        if graph_name and graph.get("name") != graph_name:
            return ToolResult(success=False, message=f"Graph '{graph_name}' not found")

        topo_order = graph.get("topological_order", [])
        nodes_by_id = {n["id"]: n for n in graph.get("nodes", [])}

        # Resolve tool names from node types if not explicitly set.
        _TYPE_TO_TOOL: Dict[str, str] = {
            "create": "create_object",
            "modify": "modify_geometry",
            "material": "apply_material",
            "light": "add_light",
            "transform": "transform_object",
            "animate": "keyframe_animation",
            "export": "export_scene",
            "group": "group_objects",
            "compose": "compose_pipeline",
        }

        plan: List[Dict[str, Any]] = []
        all_deltas: List[SceneDelta] = []
        executed = 0
        failed_nodes: List[str] = []
        # Track which object IDs each node produced so downstream nodes
        # can reference upstream nodes by their node-id alias.
        node_output_ids: Dict[str, str] = {}

        def _resolve_refs(raw_params: Dict[str, Any]) -> Dict[str, Any]:
            """Substitute node-id references with produced object IDs."""
            resolved: Dict[str, Any] = {}
            for key, value in raw_params.items():
                if key in ("target", "target_id") and isinstance(value, str) and value in node_output_ids:
                    resolved[key] = node_output_ids[value]
                else:
                    resolved[key] = value
            return resolved

        for nid in topo_order:
            node = nodes_by_id.get(nid)
            if not node:
                continue
            tool_name = node.get("tool_name") or _TYPE_TO_TOOL.get(node["type"], node["type"])
            raw_params = node.get("params", {})
            resolved_params = _resolve_refs(raw_params)

            plan.append(
                {
                    "node_id": nid,
                    "type": node["type"],
                    "tool_name": tool_name,
                    "category": node["category"],
                    "params": resolved_params,
                }
            )

            # Dispatch the node's tool if registry is available.
            if self._registry is not None:
                tool = self._registry.get(tool_name)
                if tool is None:
                    failed_nodes.append(f"{nid}({tool_name}:not_found)")
                    continue
                result = await tool.execute(scene, resolved_params)
                all_deltas.extend(result.deltas)

                if result.success:
                    executed += 1
                    # Extract created object/light/camera IDs for downstream ref mapping.
                    result_data = getattr(result, "data", None) or {}
                    if isinstance(result_data, dict):
                        for key in ("object", "light", "camera"):
                            val = result_data.get(key)
                            if isinstance(val, dict):
                                ref_id = val.get("id", "")
                                if ref_id:
                                    node_output_ids[nid] = ref_id
                                    break
                    # Fallback: check deltas for target_id.
                    if nid not in node_output_ids:
                        for delta in result.deltas:
                            tid = getattr(delta, "target_id", None)
                            if tid and isinstance(tid, str):
                                node_output_ids[nid] = tid
                                break
                else:
                    failed_nodes.append(f"{nid}({tool_name}:{result.message})")

        message = (
            f"Node graph '{graph['name']} executed: {len(plan)} nodes in topological order"
            if self._registry is not None
            else f"Node graph '{graph['name']} execution plan ready ({len(plan)} nodes — dispatch via registry)"
        )
        if executed and self._registry is not None:
            message += f", {executed} succeeded"
        if failed_nodes:
            message += f", {len(failed_nodes)} failed: {', '.join(failed_nodes[:5])}"

        return ToolResult(
            success=True,
            message=message,
            deltas=all_deltas,
            data={
                "graph_name": graph.get("name"),
                "execution_plan": plan,
                "node_count": len(plan),
                "executed": executed,
                "failed": failed_nodes,
                "node_output_map": node_output_ids,
                "note": (
                    "Full tool dispatch complete with ID mapping"
                    if self._registry is not None
                    else "Registry not available — plan returned only"
                ),
            },
        )


class ListNodeGraphsTool(ToolBase):
    """List all stored node graphs on the scene."""

    name = "list_node_graphs"
    description = "List all configured node graphs on the scene."

    def schema(self) -> Dict[str, Any]:
        return {"type": "object", "properties": {}, "required": []}

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        graph: Optional[Dict[str, Any]] = getattr(scene, "node_graph", None)
        graphs: List[Dict[str, Any]] = []
        if graph:
            graphs.append(
                {
                    "name": graph.get("name", "NodeGraph"),
                    "nodes": len(graph.get("nodes", [])),
                    "edges": len(graph.get("edges", [])),
                    "categories": graph.get("categories_used", []),
                }
            )

        return ToolResult(
            success=True,
            message=f"{len(graphs)} node graph(s) found",
            deltas=[],
            data={"graphs": graphs},
        )


class DeleteNodeGraphTool(ToolBase):
    """Delete a stored node graph."""

    name = "delete_node_graph"
    description = "Remove a stored node graph from the scene."

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "graph_name": {"type": "string", "description": "Graph name to delete"},
            },
            "required": ["graph_name"],
        }

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        graph: Optional[Dict[str, Any]] = getattr(scene, "node_graph", None)
        name = str(arguments.get("graph_name", ""))
        if not graph or graph.get("name") != name:
            return ToolResult(success=False, message=f"Graph '{name}' not found")

        scene.node_graph = None  # type: ignore[attr-defined]
        return ToolResult(
            success=True,
            message=f"Deleted node graph '{name}'",
            deltas=[SceneDelta(action="update", target_id=None, payload={"node_graph": None})],
            data={"deleted": name},
        )
