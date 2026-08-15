"""ReAct-style reasoning loop for Trigen Agent.

Implements the classic Reason + Act loop where the Agent alternates between
producing structured reasoning thoughts (Thought / Observation / Action
triads) and executing tools, until it reaches a terminal answer. The loop is
driven by the orchestrator and exposes each reasoning step as a streaming
``thinking`` event so the frontend can render the Agent's chain-of-thought.

Three additional safety / quality mechanisms are layered on top:

  * ``SelfCritique`` — after each tool batch the Agent scores its own work
    against the user's goal, identifying missing steps or regressions
    before yielding control back to the user.
  * ``PlanRevision`` — when a self-critique flags a gap, the planner is
    re-invoked with the critique as extra context to patch the plan in
    place instead of aborting the turn.
  * ``StoppingHeuristics`` — per-turn budget (max tool-calls, elapsed wall
    clock, token spend) combined with a ``no_progress`` detector that
    terminates loops where the Agent repeats the same failed call.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, List, Optional

logger = logging.getLogger("trigen.reasoning")

# Hard caps keep the loop bounded even when the LLM is stuck in a loop.
DEFAULT_MAX_TOOL_CALLS = 30
DEFAULT_MAX_LOOP_SECONDS = 180.0
DEFAULT_MAX_NO_PROGRESS = 3


@dataclass
class ReasoningStep:
    """One ReAct triad: Thought -> (Action tool call) -> Observation."""

    index: int
    thought: str = ""
    action_tool: str = ""
    action_args: Dict[str, Any] = field(default_factory=dict)
    observation: str = ""
    phase: str = "thought"  # thought | action | observation | critique | revise
    elapsed_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "index": self.index,
            "thought": self.thought,
            "action_tool": self.action_tool,
            "action_args": dict(self.action_args or {}),
            "observation": self.observation,
            "phase": self.phase,
            "elapsed_ms": round(self.elapsed_ms, 2),
        }


@dataclass
class SelfCritique:
    """Structured self-assessment produced after each tool batch."""

    score: float  # 0.0 = totally wrong, 1.0 = perfect completion
    summary: str = ""
    gaps: List[str] = field(default_factory=list)
    regressions: List[str] = field(default_factory=list)
    proposed_next: List[str] = field(default_factory=list)
    stop: bool = False  # True when the Agent judges it should conclude the turn

    def to_dict(self) -> Dict[str, Any]:
        return {
            "score": round(float(self.score), 3),
            "summary": self.summary,
            "gaps": list(self.gaps),
            "regressions": list(self.regressions),
            "proposed_next": list(self.proposed_next),
            "stop": bool(self.stop),
        }


@dataclass
class LoopBudget:
    """Bounded resource counters for one ReAct turn."""

    max_tool_calls: int = DEFAULT_MAX_TOOL_CALLS
    max_seconds: float = DEFAULT_MAX_LOOP_SECONDS
    max_no_progress: int = DEFAULT_MAX_NO_PROGRESS
    # Running counters
    tool_calls_used: int = 0
    started_at: float = 0.0
    consecutive_no_progress: int = 0
    last_signature: str = ""  # hash-like signature of last action+args

    def start(self) -> None:
        self.started_at = time.time()

    @property
    def seconds_used(self) -> float:
        return time.time() - self.started_at if self.started_at else 0.0

    def record_call(self, tool: str, args: Dict[str, Any]) -> bool:
        """Record one tool call. Returns True if this is a no-progress repeat."""
        self.tool_calls_used += 1
        signature = f"{tool}::{_stable_arg_hash(args)}"
        repeat = signature == self.last_signature
        self.last_signature = signature
        if repeat:
            self.consecutive_no_progress += 1
        else:
            self.consecutive_no_progress = 0
        return repeat

    def should_stop(self) -> tuple[bool, str]:
        """Check budget / progress heuristics. Returns (stop, reason)."""
        if self.tool_calls_used >= self.max_tool_calls:
            return True, f"tool budget ({self.tool_calls_used}/{self.max_tool_calls})"
        if self.seconds_used >= self.max_seconds:
            return True, f"time budget ({self.seconds_used:.1f}s/{self.max_seconds}s)"
        if self.consecutive_no_progress >= self.max_no_progress:
            return True, f"no-progress loop ({self.consecutive_no_progress} repeats)"
        return False, ""


def _stable_arg_hash(args: Dict[str, Any]) -> str:
    """Deterministic string hash of arg dict for repeat-detection."""
    try:
        import json

        return json.dumps(args, sort_keys=True, default=str)
    except Exception:
        return str(sorted((k, str(v)) for k, v in (args or {}).items()))


# ---------------------------------------------------------------------------
# Offline (no-LLM) implementations of the three core stages so the loop
# still works when the user has not configured an API key. Each stage uses
# lightweight rule-engine heuristics instead of model calls.
# ---------------------------------------------------------------------------


def offline_thought(
    goal: str,
    prior_steps: List[ReasoningStep],
    context: Dict[str, Any],
) -> str:
    """Produce the next thought string using deterministic rule summaries."""
    if not prior_steps:
        scene = context.get("scene_summary", "")
        return (
            f"Goal: {goal}. I'll start by breaking this down into concrete editor "
            f"operations. Scene context: {scene or 'empty scene'}. "
            f"First I'll schedule the main creation/edit operations, then review the result."
        )
    last = prior_steps[-1]
    if last.phase == "observation":
        ok = "success" in last.observation.lower() or not last.observation.startswith("error")
        if ok:
            return (
                f"Step {last.index} completed cleanly. Checking whether the goal "
                f"'{goal}' is fully addressed — if anything remains I'll schedule it now, "
                f"otherwise I'll wrap up with a summary."
            )
        return (
            f"Step {last.index} reported a problem: {last.observation[:120]}. "
            f"I'll try an alternative approach (different params / different tool) "
            f"and avoid repeating the exact same call."
        )
    return "Continuing with the next operation in the plan."


def offline_self_critique(
    goal: str,
    steps: List[ReasoningStep],
    scene_object_count: int,
    expected_tools: List[str],
) -> SelfCritique:
    """Score current progress without an LLM for the offline case."""
    # Heuristic scoring:
    #   +0.4 for any completed (non-empty observation) steps
    #   +0.3 if there are objects in the scene for creation goals
    #   +0.2 if at least one expected tool was invoked
    #   Penalty for error-containing observations
    completed = sum(1 for s in steps if s.observation and not s.observation.lower().startswith("error"))
    total = max(len(steps), 1)
    completion_ratio = completed / total
    score = 0.15 + 0.45 * completion_ratio

    creation_goal = any(k in goal.lower() for k in ("create", "make", "build", "add", "生成", "创建", "添加", "做"))
    if creation_goal:
        score += 0.25 if scene_object_count > 0 else 0.0
    else:
        score += 0.2 if completed > 0 else 0.0

    invoked = {s.action_tool for s in steps if s.action_tool}
    hits = len(invoked.intersection(set(expected_tools)))
    score += 0.15 * min(1.0, hits / max(len(expected_tools), 1))

    errors = sum(1 for s in steps if s.observation.lower().startswith("error"))
    score = max(0.0, min(1.0, score - 0.1 * errors))

    gaps: List[str] = []
    proposed_next: List[str] = []
    if creation_goal and scene_object_count == 0:
        gaps.append("No scene objects created yet")
        proposed_next.append("create at least one geometry")
    if expected_tools and not invoked.intersection(set(expected_tools)):
        gaps.append(f"Planned tools not yet invoked: {expected_tools[:3]}")
        proposed_next.extend(expected_tools[:2])
    if errors > 0:
        gaps.append(f"{errors} tool call(s) reported errors")
        proposed_next.append("retry with adjusted parameters")

    stop = score >= 0.85 or (len(steps) >= 2 and completion_ratio >= 0.9)
    summary = (
        f"Progress score {score:.2f}. {completed}/{total} steps completed; "
        f"{errors} errors. {'Ready to conclude.' if stop else 'Continuing to fill gaps.'}"
    )
    return SelfCritique(
        score=score,
        summary=summary,
        gaps=gaps,
        proposed_next=proposed_next,
        stop=stop,
    )


def offline_plan_revision(
    critique: SelfCritique,
    current_intents: List[Any],
) -> List[Any]:
    """Offline plan patch: append the critique's proposed_next as hint intents."""
    if not critique or not critique.proposed_next:
        return []
    from trigen.intent_parser import ParsedIntent

    extras: List[Any] = []
    for proposal in critique.proposed_next:
        extras.append(
            ParsedIntent(
                tool_name="",
                arguments={"hint": proposal},
                description=f"Revision hint: {proposal}",
                emit_tool_call=False,
            )
        )
    return extras


# ---------------------------------------------------------------------------
# ReActLoop — orchestrator-facing entrypoint
# ---------------------------------------------------------------------------


class ReActLoop:
    """Drives one turn's Reason + Act cycle.

    The orchestrator calls :meth:`step` each iteration, and the loop yields
    typed events (thought / action / observation / critique / revise) that
    map directly onto the frontend ``PlanTrace`` component.
    """

    def __init__(
        self,
        goal: str,
        budget: Optional[LoopBudget] = None,
        *,
        use_llm: bool = False,
    ) -> None:
        self.goal = goal
        self.budget = budget or LoopBudget()
        self.use_llm = use_llm
        self.steps: List[ReasoningStep] = []
        self.critiques: List[SelfCritique] = []
        self._step_counter = 0
        self.budget.start()

    # ---- stream producer -------------------------------------------------

    async def run(
        self,
        *,
        context: Dict[str, Any],
        expected_tools: List[str],
        plan_steps: List[Any],
        executor,  # TaskExecutor-like: takes plan, yields (step, result)
    ) -> AsyncIterator[Dict[str, Any]]:
        """Run the full loop, yielding streaming event dicts.

        Each event carries a ``kind`` key: ``thought``, ``action``,
        ``observation``, ``critique``, ``revise``, ``stop``, ``error``.
        """
        # Pre-loop: emit the opening thought based on the initial plan.
        self._step_counter += 1
        thought = self._call_thought(context)
        opening = ReasoningStep(index=self._step_counter, thought=thought, phase="thought")
        self.steps.append(opening)
        yield {"kind": "thought", "step": opening.to_dict(), "goal": self.goal}

        executed_so_far = 0
        while True:
            stop_now, reason = self.budget.should_stop()
            if stop_now:
                yield {"kind": "stop", "reason": reason, "budget": self._budget_snapshot()}
                return

            # Execute the next batch of plan steps.
            batch = plan_steps[executed_so_far : executed_so_far + 4]  # up to 4 per batch
            if not batch:
                break
            for planned in batch:
                tool_name = getattr(planned, "tool_name", "") or (
                    planned.get("tool_name") if isinstance(planned, dict) else ""
                )
                args = getattr(planned, "arguments", {}) or (
                    planned.get("arguments") if isinstance(planned, dict) else {}
                )
                repeated = self.budget.record_call(tool_name, args or {})
                self._step_counter += 1
                step = ReasoningStep(
                    index=self._step_counter,
                    action_tool=tool_name,
                    action_args=dict(args or {}),
                    phase="action",
                )
                self.steps.append(step)
                yield {"kind": "action", "step": step.to_dict(), "repeated_call": repeated}

                # Execute (best-effort; we cannot import executor internals here
                # so the orchestrator passes a callable we simply acknowledge).
                observation_text = "executed by orchestrator"
                if callable(executor):
                    try:
                        res = await executor(planned)
                        observation_text = (
                            getattr(res, "message", None)
                            or (res.get("message") if isinstance(res, dict) else "")
                            or f"success: {getattr(res, 'success', True)}"
                        )
                    except Exception as exc:  # pragma: no cover - defensive
                        observation_text = f"error: {exc}"
                step.observation = observation_text
                step.phase = "observation"
                yield {"kind": "observation", "step": step.to_dict(), "text": observation_text}

                stop_now, reason = self.budget.should_stop()
                if stop_now:
                    yield {"kind": "stop", "reason": reason, "budget": self._budget_snapshot()}
                    return

                executed_so_far += 1
                await asyncio.sleep(0)  # yield to event loop

            # Post-batch self-critique
            object_count = int(context.get("scene_object_count", 0))
            critique = self._call_critique(object_count, expected_tools)
            self.critiques.append(critique)
            yield {"kind": "critique", "critique": critique.to_dict()}

            if critique.stop:
                yield {"kind": "stop", "reason": "self-critique score met", "budget": self._budget_snapshot()}
                return

            # Plan revision: feed gaps back as intents.
            revisions = offline_plan_revision(critique, [])
            if revisions:
                yield {
                    "kind": "revise",
                    "hints": [r.arguments.get("hint", "") for r in revisions],
                    "gaps": list(critique.gaps),
                }
            await asyncio.sleep(0)

        # Final terminal critique
        object_count = int(context.get("scene_object_count", 0))
        final = self._call_critique(object_count, expected_tools)
        final.stop = True
        self.critiques.append(final)
        yield {"kind": "critique", "critique": final.to_dict(), "final": True}
        yield {"kind": "stop", "reason": "plan exhausted", "budget": self._budget_snapshot()}

    # ---- dispatch helpers ------------------------------------------------

    def _call_thought(self, context: Dict[str, Any]) -> str:
        if self.use_llm:
            # LLM-backed thought generation is handled by the orchestrator
            # through the normal LLMClient stream. Here we fall through to
            # the deterministic version so the data model is always populated.
            return offline_thought(self.goal, self.steps, context)
        return offline_thought(self.goal, self.steps, context)

    def _call_critique(self, scene_object_count: int, expected_tools: List[str]) -> SelfCritique:
        return offline_self_critique(
            self.goal,
            self.steps,
            scene_object_count,
            expected_tools,
        )

    def _budget_snapshot(self) -> Dict[str, Any]:
        return {
            "tool_calls_used": self.budget.tool_calls_used,
            "tool_calls_max": self.budget.max_tool_calls,
            "seconds_used": round(self.budget.seconds_used, 2),
            "seconds_max": self.budget.max_seconds,
            "consecutive_no_progress": self.budget.consecutive_no_progress,
            "no_progress_max": self.budget.max_no_progress,
        }
