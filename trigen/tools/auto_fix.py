"""Scene auto-fix tool.

Gives the Agent a self-healing capability: it runs the prescriptive design
review (``critique_scene``) and then automatically applies the proposed
corrective tool calls for the highest-severity findings, in one step. This is
the Agent acting as its own editor — it can spot a dim scene and immediately
add a key light, or notice a floating object and drop it onto the ground plane.

The tool is fully deterministic and offline: the review runs on scene
geometry alone, and every proposed fix is resolved to a concrete registered
tool whose ``execute`` is called in place against the same scene. No LLM is
required, so it is easy to test and safe to expose via the direct-execution
endpoint (``POST /agent/run``).

Behavior:
  * Always runs the full review first (unbounded findings) so nothing is
    hidden by the default cap.
  * Applies fixes in severity order (high before medium before low) up to a
    bounded ``max_fixes`` so a single call never bulldozes the scene.
  * Resolves each proposed fix's ``tool`` through the shared registry; a fix
    whose tool is missing or whose execution fails is recorded in ``skipped``
    and does not abort the remaining fixes.
  * Returns a structured before/after report: what was applied, what was
    skipped and why, and which findings remain.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from trigen.scene import Scene
from trigen.tools.base import ToolBase, ToolRegistry, ToolResult
from trigen.tools.scene_critique import SceneCritiqueTool

_SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


class AutoFixSceneTool(ToolBase):
    """Review the scene and automatically apply the top corrective fixes."""

    name = "auto_fix_scene"
    description = (
        "Review the current scene for design problems and automatically apply "
        "the highest-severity corrective fixes in one call. Internally this "
        "runs the design review (critique_scene), then applies each proposed "
        "fix in severity order — e.g. adding a missing key light, setting a "
        "floating object down onto the ground plane, or separating overlapping "
        "objects — up to a bounded number of changes. Returns a before/after "
        "report of what was applied, what was skipped, and which issues remain. "
        "Use this when the user asks to 'fix the scene', 'clean up my scene', "
        "'make this look right', or 'auto-fix'. Mutates the scene."
    )
    category = "intelligence"

    def __init__(self, registry: Optional[ToolRegistry] = None) -> None:
        self.registry = registry

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "max_fixes": {
                    "type": "integer",
                    "description": "Maximum number of fixes to apply (default 4, capped at 10).",
                },
                "focus": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Optional list of review checks to limit fixes to, e.g. "
                        "['lighting', 'overlap', 'floating']. When omitted, all "
                        "checks run."
                    ),
                },
            },
            "required": [],
        }

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        try:
            max_fixes = int(arguments.get("max_fixes", 4))
        except (TypeError, ValueError):
            max_fixes = 4
        max_fixes = max(1, min(max_fixes, 10))

        # Run the full review unbounded so severity ordering is accurate.
        critique = SceneCritiqueTool()
        review = await critique.execute(scene, {"max_findings": 50, "focus": arguments.get("focus")})
        findings = (review.data or {}).get("findings", [])
        if not findings:
            return ToolResult(
                success=True,
                message=(
                    f"The scene passed the design review with {len(scene.objects)} object(s) "
                    "and no problems to fix. Nothing changed."
                ),
                data={
                    "applied": [],
                    "skipped": [],
                    "remaining": [],
                    "changed": False,
                    "object_count": len(scene.objects),
                },
            )

        # Apply fixes in severity order, respecting the cap.
        ordered = sorted(findings, key=lambda f: _SEVERITY_ORDER.get(f["severity"], 3))
        applied: List[Dict[str, Any]] = []
        skipped: List[Dict[str, Any]] = []
        remaining: List[Dict[str, Any]] = []

        for finding in ordered:
            if len(applied) >= max_fixes:
                remaining.append(finding)
                continue
            fix = finding.get("proposed_fix") or {}
            tool_name = fix.get("tool")
            fix_args = fix.get("arguments") or {}
            if not tool_name:
                skipped.append({"id": finding["id"], "reason": "no proposed tool"})
                continue
            if self.registry is None:
                skipped.append({
                    "id": finding["id"],
                    "tool": tool_name,
                    "reason": "no tool registry configured",
                })
                continue
            tool = self.registry.get(tool_name)
            if tool is None:
                skipped.append({
                    "id": finding["id"],
                    "tool": tool_name,
                    "reason": "unregistered tool",
                })
                continue
            try:
                result = await tool.execute(scene, dict(fix_args))
            except Exception as exc:  # noqa: BLE001 - a failing fix must not abort the rest
                skipped.append({
                    "id": finding["id"],
                    "tool": tool_name,
                    "reason": f"error: {exc}",
                })
                continue
            if result.success:
                applied.append({
                    "id": finding["id"],
                    "title": finding.get("title"),
                    "tool": tool_name,
                    "arguments": fix_args,
                    "message": result.message,
                })
            else:
                skipped.append({
                    "id": finding["id"],
                    "tool": tool_name,
                    "reason": result.message,
                })

        summary = (
            f"Applied {len(applied)} fix(es), {len(skipped)} skipped, "
            f"{len(remaining)} issue(s) left. "
        )
        if applied:
            summary += "Changes: " + "; ".join(
                f"{a['tool']} -> {a['title']}" for a in applied
            ) + ". "
        if skipped:
            summary += "Skipped: " + "; ".join(
                f"{s['tool']} ({s['reason']})" for s in skipped
            ) + ". "
        if remaining:
            summary += "Still open: " + ", ".join(
                f"[{r['severity']}] {r['id']}" for r in remaining
            ) + "."

        return ToolResult(
            success=True,
            message=summary,
            deltas=[],
            data={
                "applied": applied,
                "skipped": skipped,
                "remaining": remaining,
                "changed": bool(applied),
                "object_count": len(scene.objects),
            },
        )