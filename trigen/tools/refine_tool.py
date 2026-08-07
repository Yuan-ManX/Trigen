"""Goal-driven scene refinement tool — multi-iteration critique+autofix loop.

Distinct from ``auto_fix_scene`` (single-pass healing): ``refine_scene``
runs a bounded iteration loop. Each iteration:

  1. Calls ``critique_scene`` to find what's still wrong.
  2. Calls ``auto_fix_scene`` to apply the top corrective fixes.
  3. Stops early when critique returns 0 findings or no fix was applied.

The ``goal`` string anchors the loop's user-facing message so the Agent
can describe *why* it iterated (e.g. "make the scene presentation-ready"),
giving the user a single audit trail of how each iteration improved the
scene. The full iteration trace (per-iter findings + applied + skipped)
is returned in ``data`` so the frontend can render a timeline.

Like ``auto_fix_scene``, this tool requires the shared ToolRegistry so
it can resolve critique-proposed fixes to registered tools. The
orchestrator passes it in at construction time.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from trigen.scene import Scene
from trigen.tools.base import ToolBase, ToolRegistry, ToolResult
from trigen.tools.scene_critique import SceneCritiqueTool
from trigen.tools.auto_fix import AutoFixSceneTool


class RefineSceneTool(ToolBase):
    """Goal-anchored multi-iteration critique + auto-fix loop."""

    name = "refine_scene"
    description = (
        "Iteratively refine the current scene toward a stated goal. Each "
        "iteration runs the design review (critique_scene), then applies the "
        "top corrective fixes (auto_fix_scene), until the review finds zero "
        "issues, no fix could be applied, or the iteration cap is hit. Use "
        "this for higher-stakes cleanup passes like 'make the scene "
        "presentation-ready', 'clean up for a hero shot', or 'tighten the "
        "composition'. Returns a per-iteration trace (findings + applied + "
        "skipped) so you can audit how the scene evolved."
    )
    category = "intelligence"

    def __init__(self, registry: Optional[ToolRegistry] = None) -> None:
        self.registry = registry

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "goal": {
                    "type": "string",
                    "description": (
                        "A short description of what the refinement should "
                        "achieve (e.g. 'presentation-ready', 'hero shot'). "
                        "Used to anchor the user-facing summary; the engine "
                        "itself is deterministic."
                    ),
                },
                "max_iterations": {
                    "type": "integer",
                    "description": "Maximum iteration count (default 3, capped at 6).",
                },
                "max_fixes_per_iter": {
                    "type": "integer",
                    "description": "Max fixes applied per iteration (default 3, capped at 8).",
                },
            },
            "required": [],
        }

    async def execute(self, scene: Scene, arguments: Dict[str, Any]) -> ToolResult:
        goal = str(arguments.get("goal", "") or "").strip() or "refine the scene"
        try:
            max_iter = int(arguments.get("max_iterations", 3))
        except (TypeError, ValueError):
            max_iter = 3
        max_iter = max(1, min(max_iter, 6))
        try:
            max_fixes = int(arguments.get("max_fixes_per_iter", 3))
        except (TypeError, ValueError):
            max_fixes = 3
        max_fixes = max(1, min(max_fixes, 8))

        if self.registry is None:
            return ToolResult(
                success=False,
                message="refine_scene requires a tool registry; none was configured.",
                data={"iterations": [], "goal": goal},
            )

        critique = SceneCritiqueTool()
        autofix = AutoFixSceneTool(registry=self.registry)

        iterations: List[Dict[str, Any]] = []
        total_applied = 0
        total_skipped = 0
        final_findings_count = 0
        stopped_reason = "max_iterations"

        for i in range(1, max_iter + 1):
            # Step 1 — critique
            try:
                review = await critique.execute(scene, {"max_findings": 30})
            except Exception as exc:  # noqa: BLE001 - critique must not abort the loop
                iterations.append({
                    "iteration": i,
                    "error": f"critique failed: {exc}",
                })
                stopped_reason = "critique_error"
                break

            findings = (review.data or {}).get("findings", [])
            if not findings:
                iterations.append({
                    "iteration": i,
                    "findings_count": 0,
                    "applied": [],
                    "skipped": [],
                    "verdict": "clean",
                })
                final_findings_count = 0
                stopped_reason = "no_findings"
                break

            # Step 2 — auto-fix
            try:
                fix_result = await autofix.execute(
                    scene,
                    {"max_fixes": max_fixes},
                )
            except Exception as exc:  # noqa: BLE001 - autofix must not abort the loop
                iterations.append({
                    "iteration": i,
                    "findings_count": len(findings),
                    "error": f"autofix failed: {exc}",
                })
                stopped_reason = "autofix_error"
                break

            applied = (fix_result.data or {}).get("applied", [])
            skipped = (fix_result.data or {}).get("skipped", [])
            remaining = (fix_result.data or {}).get("remaining", [])
            iterations.append({
                "iteration": i,
                "findings_count": len(findings),
                "applied": applied,
                "skipped": skipped,
                "remaining_after": len(remaining),
                "applied_count": len(applied),
                "skipped_count": len(skipped),
            })
            total_applied += len(applied)
            total_skipped += len(skipped)
            final_findings_count = len(remaining)

            # Step 3 — stop if nothing was applied (no progress)
            if not applied:
                stopped_reason = "no_progress"
                break

        # Build a goal-anchored summary.
        summary_lines: List[str] = [
            f"Refinement goal: '{goal}'.",
            f"Ran {len(iterations)} iteration(s); applied {total_applied} fix(es), "
            f"skipped {total_skipped}; stopped because: {stopped_reason}.",
        ]
        if final_findings_count > 0:
            summary_lines.append(f"{final_findings_count} issue(s) still open after refinement.")
        else:
            summary_lines.append("Scene reached a clean review state.")

        return ToolResult(
            success=True,
            message=" ".join(summary_lines),
            data={
                "goal": goal,
                "iterations": iterations,
                "iteration_count": len(iterations),
                "total_applied": total_applied,
                "total_skipped": total_skipped,
                "remaining_findings": final_findings_count,
                "stopped_reason": stopped_reason,
            },
        )
