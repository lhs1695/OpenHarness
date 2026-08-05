"""Online (model-driven) evaluation strategies (spec §13 M8 online phase).

Each strategy drives a real OpenHarness agent inside an isolated git worktree
of the fixture repository to repair the case's bug, then verifies with the
repository test command and/or the deterministic quality gates:

- ``raw``: agent repairs the bug directly, then the repository tests must pass;
- ``plan_gates``: adapter-produced plan → agent repair → required commands + gates;
- ``plan_gates_reviewer``: ``plan_gates`` plus an independent read-only reviewer
  that must approve the resulting diff.

These strategies require real API credentials and are exercised through the
runner CLI's ``--online`` flag; their tests carry the ``online`` marker so the
default (offline) suite skips them.  The model-facing surfaces (runtime builder,
reviewer builder) are injectable so unit tests can drive the orchestration with
fakes.
"""

from __future__ import annotations

import asyncio
import os
import shlex
import sys
import time
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Protocol, cast
from uuid import uuid4

from forgeflow.domain.policy import RepositoryPolicy
from forgeflow.domain.task import DevelopmentTask
from forgeflow.evaluation.datasets import EvalCase, EvalResult
from forgeflow.evaluation.feedback import TraceSampleBuilder
from forgeflow.evaluation.registry import FeedbackRegistry
from forgeflow.evaluation.strategies import (
    _BASE_POLICY,
    EvalStrategy,
    _policy_for_case,
    _resolved_test_command,
)
from forgeflow.execution.base import ExecutionResult
from forgeflow.execution.worktree import WorktreeExecutionBackend
from forgeflow.integrations.openharness.adapter import OpenHarnessAdapter
from forgeflow.quality.reports import QualityGateRunner
from forgeflow.quality.reviewer import (
    ReviewEngineLike,
    Reviewer,
    ReviewReport,
    build_review_engine,
)
from forgeflow.trace.collector import TraceCollector
from forgeflow.trace.events import estimate_cost
from openharness.engine.stream_events import (
    AssistantTextDelta,
    StreamEvent,
    ToolExecutionCompleted,
    ToolExecutionStarted,
)


class ReviewerLike(Protocol):
    """A reviewer surface returning a structured ReviewReport."""

    async def review(self, task: DevelopmentTask, diff: str) -> ReviewReport: ...

AGENT_SYSTEM_PROMPT = (
    "You are an expert software engineer working inside an isolated repository. "
    "Make the requested change, run the repository's test command, and iterate "
    "until the whole suite passes. Follow existing conventions; do not modify "
    "unrelated files and do not add new dependencies."
)

PLANNER_SYSTEM_PROMPT = (
    "You are a senior backend engineer producing an implementation plan. "
    "You are READ-ONLY: never modify files and never run commands. "
    "Read the code, understand the failure, and output a structured plan."
)

REVIEWER_SYSTEM_PROMPT = (
    "You are an independent senior code reviewer. Review the diff against the "
    "task's acceptance criteria and report blockers."
)

_PLAN_MAX_TURNS = 25
_IMPL_MAX_TURNS = 40
_REVIEW_MAX_TURNS = 8
_TEST_TIMEOUT_SECONDS = 180
# Wall-clock budgets per model phase.  Turn limits alone are not enough: a
# stalled provider request would otherwise hang an eval run forever.
_PLAN_TIMEOUT_SECONDS = 600
_IMPL_TIMEOUT_SECONDS = 900
_REVIEW_TIMEOUT_SECONDS = 300


class AgentEngine(Protocol):
    """Engine surface consumed by the online strategies (satisfied by QueryEngine)."""

    def submit_message(self, prompt: str) -> AsyncIterator[StreamEvent]: ...

    @property
    def total_usage(self) -> object: ...

    @property
    def model(self) -> str: ...


class RuntimeSession(Protocol):
    """One runtime + its close handle (wraps an OpenHarness RuntimeBundle)."""

    @property
    def engine(self) -> AgentEngine: ...

    @property
    def api_client(self) -> object | None: ...

    async def close(self) -> None: ...


class RuntimeFactory(Protocol):
    async def __call__(
        self,
        *,
        cwd: str,
        system_prompt: str,
        permission_mode: str,
        max_turns: int,
    ) -> RuntimeSession: ...


class _BuildRuntimeSession:
    def __init__(self, bundle: Any) -> None:
        self._bundle = bundle

    @property
    def engine(self) -> AgentEngine:
        engine = getattr(self._bundle, "engine", None)
        if engine is None:
            raise RuntimeError("runtime bundle has no engine")
        return cast(AgentEngine, engine)

    @property
    def api_client(self) -> object | None:
        return getattr(self._bundle, "api_client", None)

    async def close(self) -> None:
        from openharness.ui.runtime import close_runtime

        await close_runtime(self._bundle)


async def default_runtime_factory(
    *,
    cwd: str,
    system_prompt: str,
    permission_mode: str,
    max_turns: int,
) -> RuntimeSession:
    """Build an OpenHarness runtime (full tool registry) for the given workspace."""
    from openharness.ui.runtime import build_runtime

    bundle = await build_runtime(
        cwd=cwd,
        system_prompt=system_prompt,
        permission_mode=permission_mode,
        max_turns=max_turns,
    )
    return _BuildRuntimeSession(bundle)


class _TraceForwardingEngine:
    """Engine proxy that forwards every StreamEvent to a TraceCollector.

    Each strategy wraps the plan / fix / review engines with this proxy so one
    per-case collector accumulates the whole trace without the adapter or the
    reviewer knowing about tracing (A1 数据回流).
    """

    def __init__(self, engine: AgentEngine, collector: TraceCollector) -> None:
        self._engine = engine
        self._collector = collector

    def submit_message(self, prompt: str) -> AsyncIterator[StreamEvent]:
        async def _forward() -> AsyncIterator[StreamEvent]:
            async for event in self._engine.submit_message(prompt):
                self._collector.on_stream_event(event)
                yield event

        return _forward()

    @property
    def total_usage(self) -> object:
        return self._engine.total_usage

    @property
    def model(self) -> str:
        return self._engine.model


ReviewerFactory = Callable[..., ReviewerLike]


def _default_reviewer_factory(
    session: RuntimeSession,
    *,
    workspace: str,
    model: str,
    collector: TraceCollector | None = None,
) -> ReviewerLike:
    from openharness.api.client import SupportsStreamingMessages

    api_client = session.api_client
    if api_client is None:
        raise RuntimeError("runtime session has no streaming API client for review")
    review_engine: ReviewEngineLike = build_review_engine(
        cast(SupportsStreamingMessages, api_client),
        cwd=workspace,
        model=model,
        system_prompt=REVIEWER_SYSTEM_PROMPT,
        max_turns=_REVIEW_MAX_TURNS,
    )
    if collector is not None:
        review_engine = _TraceForwardingEngine(cast(AgentEngine, review_engine), collector)
    return Reviewer(review_engine)


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def case_to_task(case: EvalCase) -> DevelopmentTask:
    """Convert an EvalCase into the DevelopmentTask the adapters/reviewer expect."""
    return DevelopmentTask(
        repository=case.repository,
        task_type=case.task_type,
        priority=case.priority,
        title=case.title,
        description=case.description,
        acceptance_criteria=list(case.acceptance_rules),
        risk_tags=list(case.tags),
    )


def build_fix_prompt(case: EvalCase, *, plan_text: str = "", context: str = "") -> str:
    """Build the agent prompt that repairs a case inside its worktree."""
    rules = "\n".join(f"- {item}" for item in case.acceptance_rules) or "- (none)"
    tags = ", ".join(case.tags) or "(none)"
    if case.task_type == "verify":
        instructions = [
            "1. Read the relevant source files.",
            f"2. Run the repository test command with this interpreter: `{sys.executable} -m pytest -q`",
            "3. If any test fails, fix the code and re-run until the suite passes.",
            "4. Otherwise do NOT modify any code — the task is to verify existing behavior.",
        ]
    else:
        instructions = [
            "1. Read the relevant source files.",
            "2. Implement the change so that every acceptance criterion holds.",
            f"3. Run the repository test command with this interpreter: `{sys.executable} -m pytest -q`",
            "4. If any test fails, fix the code and re-run until the suite passes.",
        ]
    lines = [
        "# Task",
        f"- Title: {case.title}",
        f"- Type: {case.task_type}",
        f"- Priority: {case.priority}",
        f"- Description: {case.description}",
        f"- Acceptance criteria:\n{rules}",
        f"- Risk tags: {tags}",
        "",
        "# Instructions",
        *instructions,
    ]
    if plan_text.strip():
        lines += [
            "",
            "# Implementation plan (produced earlier — use it as a guide)",
            plan_text.strip(),
        ]
    if context.strip():
        lines += [
            "",
            "# Historical experience retrieved from past runs (use it to inform your fix)",
            context.strip(),
        ]
    return "\n".join(lines)


def _tokens(input_tokens: int, output_tokens: int) -> dict[str, int]:
    return {"input_tokens": input_tokens, "output_tokens": output_tokens}


def _add_tokens(*snapshots: dict[str, int]) -> dict[str, int]:
    result = {"input_tokens": 0, "output_tokens": 0}
    for snapshot in snapshots:
        result["input_tokens"] += snapshot.get("input_tokens", 0)
        result["output_tokens"] += snapshot.get("output_tokens", 0)
    return result


def _usage_to_tokens(usage: object) -> dict[str, int]:
    return _tokens(
        getattr(usage, "input_tokens", 0) or 0,
        getattr(usage, "output_tokens", 0) or 0,
    )


def _describe_test_failure(result: object) -> str:
    returncode = getattr(result, "returncode", None)
    timed_out = bool(getattr(result, "timed_out", False))
    stdout = getattr(result, "stdout", "") or ""
    stderr = getattr(result, "stderr", "") or ""
    if timed_out:
        return "test command timed out"
    tail = "\n".join((stdout + "\n" + stderr).strip().splitlines()[-8:])
    return f"test command exited {returncode}:\n{tail}"


async def _git_diff(workspace: Path) -> str:
    proc = await asyncio.create_subprocess_exec(
        "git",
        "diff",
        "HEAD",
        cwd=str(workspace),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
    )
    stdout, _ = await proc.communicate()
    return stdout.decode(errors="replace")


# ---------------------------------------------------------------------------
# Agent turn runner
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _AgentStats:
    text: str
    input_tokens: int
    output_tokens: int
    tool_calls: int
    tool_errors: int


async def _collect_stream(engine: AgentEngine, prompt: str) -> tuple[list[str], int, int]:
    text_parts: list[str] = []
    tool_calls = 0
    tool_errors = 0
    async for event in engine.submit_message(prompt):
        if isinstance(event, AssistantTextDelta):
            text_parts.append(event.text)
        elif isinstance(event, ToolExecutionStarted):
            tool_calls += 1
        elif isinstance(event, ToolExecutionCompleted) and event.is_error:
            tool_errors += 1
    return text_parts, tool_calls, tool_errors


async def _run_agent_turn(
    engine: AgentEngine,
    prompt: str,
    *,
    timeout_seconds: int = _IMPL_TIMEOUT_SECONDS,
) -> _AgentStats:
    try:
        text_parts, tool_calls, tool_errors = await asyncio.wait_for(
            _collect_stream(engine, prompt), timeout=timeout_seconds
        )
    except TimeoutError as exc:
        raise _AgentPhaseTimeout(f"agent turn exceeded {timeout_seconds}s wall-clock budget") from exc
    tokens = _usage_to_tokens(engine.total_usage)
    return _AgentStats(
        text="".join(text_parts),
        input_tokens=tokens["input_tokens"],
        output_tokens=tokens["output_tokens"],
        tool_calls=tool_calls,
        tool_errors=tool_errors,
    )


class _AgentPhaseTimeout(Exception):
    """Raised when a model phase exceeds its wall-clock budget."""


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------


class _BaseOnlineStrategy:
    """Shared online strategy plumbing: worktree prep, result assembly."""

    def __init__(
        self,
        *,
        name: str,
        policy: RepositoryPolicy,
        runtime_factory: RuntimeFactory = default_runtime_factory,
        reviewer_factory: ReviewerFactory | None = None,
        run_token: str = "",
        feedback_registry: FeedbackRegistry | None = None,
        dataset_version: str = "",
    ) -> None:
        self._name = name
        self._policy = policy
        self._runtime_factory = runtime_factory
        self._reviewer_factory = reviewer_factory or _default_reviewer_factory
        self._run_token = run_token or uuid4().hex[:8]
        self._feedback_registry = feedback_registry
        self._dataset_version = dataset_version
        self._collector: TraceCollector | None = None

    @property
    def name(self) -> str:
        return self._name

    def _task_id(self, case: EvalCase) -> str:
        # Unique per (case, strategy, run) so strategies never share a worktree
        # and a crashed prior run cannot be fast-resumed with stale changes.
        return f"{case.case_id}-{self._name}-{self._run_token}"

    def _new_collector(self, case: EvalCase) -> TraceCollector:
        collector = TraceCollector(
            task_id=self._task_id(case), run_id=f"run_{case.case_id}"
        )
        self._collector = collector
        return collector

    def _wrapped(self, engine: AgentEngine) -> AgentEngine:
        """Wrap ``engine`` so every StreamEvent also lands in the per-case collector."""
        if self._collector is None:
            return engine
        return _TraceForwardingEngine(engine, self._collector)

    def _record_command(self, result: ExecutionResult) -> None:
        if self._collector is None:
            return
        self._collector.on_command(
            command=list(result.command),
            returncode=result.returncode,
            duration_ms=result.duration_ms,
            output=f"{result.stdout}\n{result.stderr}",
        )

    def _register_feedback(self, case: EvalCase) -> None:
        """Build a FeedbackDataset from the collected trace and register it (A1)."""
        registry = self._feedback_registry
        collector = self._collector
        if registry is None or collector is None:
            return
        events = collector.events()
        if not events:
            return
        dataset = TraceSampleBuilder().build(
            task_id=self._task_id(case),
            run_id=f"run_{case.case_id}",
            events=events,
            provenance={
                "dataset_version": self._dataset_version,
                "case_id": case.case_id,
                "repository": case.repository,
                "strategy": self._name,
            },
        )
        registry.register(dataset)

    async def _attach_diff(self, result: EvalResult, workspace: Path) -> EvalResult:
        """Attach the agent's real worktree diff to the result (B1 delivery needs it)."""
        if "diff" in result.metadata:
            return result
        diff = await _git_diff(workspace)
        if diff:
            return replace(result, metadata={**result.metadata, "diff": diff})
        return result

    async def _run_plan(self, task: DevelopmentTask, workspace: Path) -> tuple[str, dict[str, int]]:
        session = await self._runtime_factory(
            cwd=str(workspace),
            system_prompt=PLANNER_SYSTEM_PROMPT,
            permission_mode="plan",
            max_turns=_PLAN_MAX_TURNS,
        )
        try:
            try:
                plan = await asyncio.wait_for(
                    OpenHarnessAdapter().run_plan(task, self._wrapped(session.engine)),
                    timeout=_PLAN_TIMEOUT_SECONDS,
                )
            except TimeoutError as exc:
                raise _AgentPhaseTimeout(
                    f"planning exceeded {_PLAN_TIMEOUT_SECONDS}s wall-clock budget"
                ) from exc
            return plan.plan_text, dict(plan.token_usage)
        finally:
            await session.close()

    async def _run_fix_agent(
        self,
        case: EvalCase,
        workspace: Path,
        *,
        plan_text: str = "",
        context: str = "",
    ) -> _AgentStats:
        session = await self._runtime_factory(
            cwd=str(workspace),
            system_prompt=AGENT_SYSTEM_PROMPT,
            permission_mode="full_auto",
            max_turns=_IMPL_MAX_TURNS,
        )
        try:
            return await _run_agent_turn(
                self._wrapped(session.engine),
                build_fix_prompt(case, plan_text=plan_text, context=context),
            )
        finally:
            await session.close()

    def _error_result(self, case: EvalCase, strategy_name: str, started: float, exc: Exception) -> EvalResult:
        return EvalResult(
            case_id=case.case_id,
            strategy=strategy_name,
            status="error",
            failure_class="error",
            error=f"{type(exc).__name__}: {exc}",
            duration_ms=int((time.monotonic() - started) * 1000),
        )


class RawAgentStrategy(_BaseOnlineStrategy):
    """``raw``: agent repairs the bug directly; repository tests must then pass."""

    async def run(
        self,
        case: EvalCase,
        *,
        repo_path: Path,
        strategy_name: str,
        context: str = "",
    ) -> EvalResult:
        started = time.monotonic()
        backend = WorktreeExecutionBackend(repo_path)
        self._new_collector(case)
        result: EvalResult
        workspace: Path | None = None
        try:
            workspace = Path(await backend.prepare(self._task_id(case), case.repository))
            stats = await self._run_fix_agent(case, workspace, context=context)
            test_command = _resolved_test_command(case.test_command)
            test_result = await backend.execute(shlex.split(test_command), _TEST_TIMEOUT_SECONDS)
            self._record_command(test_result)
            tests_passed = test_result.returncode == 0 and not test_result.timed_out
            tokens = _tokens(stats.input_tokens, stats.output_tokens)
            duration_ms = int((time.monotonic() - started) * 1000)
            result = EvalResult(
                case_id=case.case_id,
                strategy=strategy_name,
                status="passed" if tests_passed else "failed",
                failure_class="pass" if tests_passed else "agent_failed",
                tests_passed=tests_passed,
                token_usage=tokens["input_tokens"] + tokens["output_tokens"],
                cost=estimate_cost(tokens),
                duration_ms=duration_ms,
                error=None if tests_passed else _describe_test_failure(test_result),
                metadata={
                    "tool_calls": stats.tool_calls,
                    "tool_failures": stats.tool_errors,
                    "agent_text_len": len(stats.text),
                },
            )
            if workspace is not None:
                result = await self._attach_diff(result, workspace)
        except Exception as exc:  # noqa: BLE001 — any strategy failure becomes an error result
            result = self._error_result(case, strategy_name, started, exc)
        finally:
            await backend.cleanup()
        self._register_feedback(case)
        return result


class PlanGatesStrategy(_BaseOnlineStrategy):
    """``plan_gates``: adapter plan → agent repair → required commands + gates."""

    async def run(
        self,
        case: EvalCase,
        *,
        repo_path: Path,
        strategy_name: str,
        context: str = "",
    ) -> EvalResult:
        started = time.monotonic()
        backend = WorktreeExecutionBackend(repo_path)
        self._new_collector(case)
        result: EvalResult
        workspace: Path | None = None
        try:
            workspace = Path(await backend.prepare(self._task_id(case), case.repository))
            task = case_to_task(case)
            plan_text, plan_tokens = await self._run_plan(task, workspace)
            stats = await self._run_fix_agent(case, workspace, plan_text=plan_text, context=context)
            runner = QualityGateRunner(backend, _policy_for_case(self._policy, case))
            report = await runner.evaluate(
                task_id=case.case_id,
                task_type=case.task_type,
                workspace=workspace,
            )
            result = self._gates_result(
                case,
                strategy_name,
                started,
                report,
                tokens=_add_tokens(plan_tokens, _tokens(stats.input_tokens, stats.output_tokens)),
                stats=stats,
                plan_text=plan_text,
            )
            if workspace is not None:
                result = await self._attach_diff(result, workspace)
        except Exception as exc:  # noqa: BLE001 — any strategy failure becomes an error result
            result = self._error_result(case, strategy_name, started, exc)
        finally:
            await backend.cleanup()
        self._register_feedback(case)
        return result

    def _gates_result(
        self,
        case: EvalCase,
        strategy_name: str,
        started: float,
        report: object,
        *,
        tokens: dict[str, int],
        stats: _AgentStats,
        plan_text: str = "",
        review: ReviewReport | None = None,
        require_review: bool = False,
    ) -> EvalResult:
        hard_failed = [
            gate.gate_name
            for gate in getattr(report, "hard_failures", [])
        ]
        gates_passed = bool(getattr(report, "passed", False))
        if require_review:
            reviewer_approved = review is not None and review.approved
        else:
            reviewer_approved = True
        passed = gates_passed and reviewer_approved
        if passed:
            error = None
        elif not gates_passed:
            error = f"hard gates failed: {hard_failed}"
        elif review is None:
            error = "reviewer did not run"
        else:
            error = (
                f"reviewer not approved "
                f"(verdict={review.verdict}, blockers={len(review.blockers)})"
            )
        return EvalResult(
            case_id=case.case_id,
            strategy=strategy_name,
            status="passed" if passed else "failed",
            failure_class="pass" if passed else "agent_failed",
            tests_passed="required_commands" not in hard_failed,
            hard_gates_passed=gates_passed,
            forbidden_paths_touched="forbidden_paths" in hard_failed,
            token_usage=tokens["input_tokens"] + tokens["output_tokens"],
            cost=estimate_cost(tokens),
            duration_ms=int((time.monotonic() - started) * 1000),
            error=error,
            metadata={
                "tool_calls": stats.tool_calls,
                "tool_failures": stats.tool_errors,
                "plan_chars": len(plan_text),
                "reviewer_verdict": review.verdict if review else "not-run",
                "reviewer_blockers": len(review.blockers) if review else 0,
            },
        )


class PlanGatesReviewerStrategy(PlanGatesStrategy):
    """``plan_gates_reviewer``: plan_gates plus an independent read-only reviewer."""

    async def run(
        self,
        case: EvalCase,
        *,
        repo_path: Path,
        strategy_name: str,
        context: str = "",
    ) -> EvalResult:
        started = time.monotonic()
        backend = WorktreeExecutionBackend(repo_path)
        self._new_collector(case)
        result: EvalResult
        workspace: Path | None = None
        try:
            workspace = Path(await backend.prepare(self._task_id(case), case.repository))
            task = case_to_task(case)
            plan_text, plan_tokens = await self._run_plan(task, workspace)
            session = await self._runtime_factory(
                cwd=str(workspace),
                system_prompt=AGENT_SYSTEM_PROMPT,
                permission_mode="full_auto",
                max_turns=_IMPL_MAX_TURNS,
            )
            try:
                stats = await _run_agent_turn(
                    self._wrapped(session.engine),
                    build_fix_prompt(case, plan_text=plan_text, context=context),
                )
                runner = QualityGateRunner(backend, _policy_for_case(self._policy, case))
                report = await runner.evaluate(
                    task_id=case.case_id,
                    task_type=case.task_type,
                    workspace=workspace,
                )
                review: ReviewReport | None = None
                if getattr(report, "passed", False):
                    diff = await _git_diff(workspace)
                    reviewer = self._reviewer_factory(
                        session,
                        workspace=str(workspace),
                        model=session.engine.model,
                        collector=self._collector,
                    )
                    try:
                        review = await asyncio.wait_for(
                            reviewer.review(task, diff), timeout=_REVIEW_TIMEOUT_SECONDS
                        )
                    except TimeoutError as exc:
                        raise _AgentPhaseTimeout(
                            f"review exceeded {_REVIEW_TIMEOUT_SECONDS}s wall-clock budget"
                        ) from exc
            finally:
                await session.close()
            result = self._gates_result(
                case,
                strategy_name,
                started,
                report,
                tokens=_add_tokens(plan_tokens, _tokens(stats.input_tokens, stats.output_tokens)),
                stats=stats,
                plan_text=plan_text,
                review=review,
                require_review=True,
            )
            if workspace is not None:
                result = await self._attach_diff(result, workspace)
        except Exception as exc:  # noqa: BLE001 — any strategy failure becomes an error result
            result = self._error_result(case, strategy_name, started, exc)
        finally:
            await backend.cleanup()
        self._register_feedback(case)
        return result


def online_strategies(
    feedback_registry: FeedbackRegistry | None = None,
    dataset_version: str = "",
) -> dict[str, EvalStrategy]:
    """The online strategy set: raw / plan_gates / plan_gates_reviewer.

    When ``feedback_registry`` is given, each strategy forwards its per-case
    stream events into a TraceCollector and registers the resulting
    FeedbackDataset (A1 数据回流).
    """
    strategies: dict[str, EvalStrategy] = {}
    for name in ("raw", "plan_gates", "plan_gates_reviewer"):
        if name == "raw":
            strategies[name] = RawAgentStrategy(
                name=name,
                policy=_BASE_POLICY,
                feedback_registry=feedback_registry,
                dataset_version=dataset_version,
            )
        elif name == "plan_gates":
            strategies[name] = PlanGatesStrategy(
                name=name,
                policy=_BASE_POLICY,
                feedback_registry=feedback_registry,
                dataset_version=dataset_version,
            )
        else:
            strategies[name] = PlanGatesReviewerStrategy(
                name=name,
                policy=_BASE_POLICY,
                feedback_registry=feedback_registry,
                dataset_version=dataset_version,
            )
    return strategies
