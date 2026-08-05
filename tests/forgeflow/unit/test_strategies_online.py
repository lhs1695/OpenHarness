"""Offline tests for the online strategies — orchestration with fake runtimes.

The strategies drive a real OpenHarness runtime in production; here we inject a
fake runtime factory (and a fake reviewer) so the worktree-prep → agent-turn →
test/gate/review pipeline is exercised deterministically without any model
calls.  The fake implementation agent writes a working idempotency fix into the
worktree when ``fix=True``, mirroring what a real model would do.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from forgeflow.domain.policy import RepositoryPolicy
from forgeflow.evaluation.datasets import EvalCase
from forgeflow.evaluation.fixtures import materialize_git_repo
from forgeflow.evaluation.strategies_online import (
    PlanGatesReviewerStrategy,
    PlanGatesStrategy,
    RawAgentStrategy,
    build_fix_prompt,
)
from forgeflow.quality.reviewer import ReviewFinding, ReviewReport, Severity
from openharness.engine.stream_events import AssistantTextDelta, StreamEvent

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "repositories"

# A payment.charge with an idempotency guard (makes tests/test_payment.py pass).
FIXED_PAYMENT = '''\
"""Payment processing with an idempotency guard."""

import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class PaymentRecord:
    id: str
    order_id: str
    amount: int


_charges: dict[str, PaymentRecord] = {}


def charges_for(order_id: str) -> list[PaymentRecord]:
    """Return all recorded charges for an order."""
    return [record for record in _charges.values() if record.order_id == order_id]


def charge(order_id: str, amount: int) -> PaymentRecord:
    """Charge an order exactly once per order."""
    existing = charges_for(order_id)
    if existing:
        return existing[0]
    record = PaymentRecord(id=uuid.uuid4().hex, order_id=order_id, amount=amount)
    _charges[record.id] = record
    return record
'''

PLAN_TEXT = (
    "## Target Files\n"
    "- payment.py\n"
    "## Steps\n"
    "- add an idempotency guard in charge()\n"
    "## Risk Points\n"
    "- none\n"
    "## Test Plan\n"
    "- run pytest"
)


class _FakeUsage:
    input_tokens = 120
    output_tokens = 60


class FakeEngine:
    """Yields a plan or fixes payment.py, mimicking a model turn."""

    def __init__(self, workspace: Path, *, kind: str, fix: bool) -> None:
        self._workspace = workspace
        self._kind = kind
        self._fix = fix
        self.usage = _FakeUsage()
        self.last_prompt = ""

    @property
    def model(self) -> str:
        return "fake-model"

    @property
    def total_usage(self) -> object:
        return self.usage

    async def submit_message(self, prompt: str) -> AsyncIterator[StreamEvent]:
        self.last_prompt = prompt
        if self._kind == "plan":
            yield AssistantTextDelta(text=PLAN_TEXT)
            return
        if self._fix:
            (self._workspace / "payment.py").write_text(FIXED_PAYMENT, encoding="utf-8")
        yield AssistantTextDelta(text="implemented the change")


class FakeRuntimeSession:
    def __init__(self, workspace: Path, *, kind: str, fix: bool) -> None:
        self.engine = FakeEngine(workspace, kind=kind, fix=fix)
        self.api_client = object()
        self.closed = False

    async def close(self) -> None:
        self.closed = True


class FakeRuntimeFactory:
    def __init__(self, *, fix: bool) -> None:
        self._fix = fix
        self.calls: list[dict[str, object]] = []
        self.sessions: list[FakeRuntimeSession] = []

    async def __call__(
        self,
        *,
        cwd: str,
        system_prompt: str,
        permission_mode: str,
        max_turns: int,
    ) -> FakeRuntimeSession:
        self.calls.append(
            {
                "cwd": cwd,
                "permission_mode": permission_mode,
                "max_turns": max_turns,
            }
        )
        session = FakeRuntimeSession(
            Path(cwd),
            kind="plan" if permission_mode == "plan" else "impl",
            fix=self._fix,
        )
        self.sessions.append(session)
        return session


class FakeReviewer:
    def __init__(self, verdict: str, blockers: int, diffs: list[str]) -> None:
        self._verdict = verdict
        self._blockers = blockers
        self.diffs = diffs

    async def review(self, task: object, diff: str) -> ReviewReport:
        self.diffs.append(diff)
        findings = (
            [ReviewFinding(severity=Severity.P1, message="fix must not regress")]
            if self._blockers
            else []
        )
        return ReviewReport(verdict=self._verdict, summary="looks good", findings=findings)


class FakeReviewerFactory:
    def __init__(self, verdict: str, blockers: int = 0) -> None:
        self._verdict = verdict
        self._blockers = blockers
        self.diffs: list[str] = []

    def __call__(self, session: object, *, workspace: str, model: str) -> FakeReviewer:
        return FakeReviewer(self._verdict, self._blockers, self.diffs)


POLICY = RepositoryPolicy(repository="billing-service")


def _billing_case(case_id: str = "billing-001") -> EvalCase:
    return EvalCase(
        case_id=case_id,
        repository="billing-service",
        title="修复重复扣款",
        description="客户端超时重试时可能产生第二笔扣款",
        acceptance_rules=("相同幂等键只产生一笔支付记录",),
        tags=("payment", "idempotency"),
    )


def _repo(tmp_path: Path) -> Path:
    return materialize_git_repo(FIXTURES / "billing-service", tmp_path)


def test_fix_prompt_includes_acceptance_and_interpreter() -> None:
    prompt = build_fix_prompt(_billing_case())
    assert "客户端超时重试时可能产生第二笔扣款" in prompt
    assert "相同幂等键只产生一笔支付记录" in prompt
    assert "-m pytest -q" in prompt
    assert "python.exe" in prompt


class _HangingEngine:
    @property
    def model(self) -> str:
        return "fake"

    @property
    def total_usage(self) -> object:
        return _FakeUsage()

    async def submit_message(self, prompt: str) -> AsyncIterator[StreamEvent]:
        yield AssistantTextDelta(text="started")
        await asyncio.sleep(30)  # simulate a stalled provider request


def test_agent_turn_times_out_instead_of_hanging() -> None:
    from forgeflow.evaluation.strategies_online import _AgentPhaseTimeout, _run_agent_turn

    with pytest.raises(_AgentPhaseTimeout):
        asyncio.run(_run_agent_turn(_HangingEngine(), "go", timeout_seconds=1))


def test_fix_prompt_verify_type_forbids_changes() -> None:
    case = EvalCase(
        case_id="cart-001",
        repository="cart-service",
        title="验证购物车加价计算",
        description="现有测试应通过（基线冒烟）",
        task_type="verify",
        acceptance_rules=("现有测试通过",),
    )
    prompt = build_fix_prompt(case)
    assert "do NOT modify any code" in prompt


@pytest.mark.asyncio
async def test_raw_agent_fix_flips_case_to_pass(tmp_path: Path) -> None:
    factory = FakeRuntimeFactory(fix=True)
    strategy = RawAgentStrategy(name="raw", policy=POLICY, runtime_factory=factory)
    result = await strategy.run(
        _billing_case(), repo_path=_repo(tmp_path), strategy_name="raw"
    )
    assert result.status == "passed"
    assert result.failure_class == "pass"
    assert result.tests_passed
    assert result.token_usage > 0
    assert result.cost > 0


@pytest.mark.asyncio
async def test_raw_agent_that_does_not_fix_marks_agent_failed(tmp_path: Path) -> None:
    factory = FakeRuntimeFactory(fix=False)
    strategy = RawAgentStrategy(name="raw", policy=POLICY, runtime_factory=factory)
    result = await strategy.run(
        _billing_case(), repo_path=_repo(tmp_path), strategy_name="raw"
    )
    assert result.status == "failed"
    assert result.failure_class == "agent_failed"
    assert not result.tests_passed
    assert "test command exited" in (result.error or "")


@pytest.mark.asyncio
async def test_plan_gates_runs_plan_then_fix_then_gates(tmp_path: Path) -> None:
    factory = FakeRuntimeFactory(fix=True)
    strategy = PlanGatesStrategy(name="plan_gates", policy=POLICY, runtime_factory=factory)
    result = await strategy.run(
        _billing_case(), repo_path=_repo(tmp_path), strategy_name="plan_gates"
    )
    assert result.status == "passed"
    assert result.failure_class == "pass"
    assert result.hard_gates_passed
    assert len(factory.sessions) == 2  # planning + implementation
    assert factory.sessions[0].closed
    assert factory.sessions[1].closed
    impl_prompt = factory.sessions[1].engine.last_prompt
    assert "Implementation plan" in impl_prompt
    assert result.metadata["plan_chars"] > 0


@pytest.mark.asyncio
async def test_plan_gates_fails_when_agent_does_not_fix(tmp_path: Path) -> None:
    factory = FakeRuntimeFactory(fix=False)
    strategy = PlanGatesStrategy(name="plan_gates", policy=POLICY, runtime_factory=factory)
    result = await strategy.run(
        _billing_case(), repo_path=_repo(tmp_path), strategy_name="plan_gates"
    )
    assert result.status == "failed"
    assert result.failure_class == "agent_failed"
    assert not result.tests_passed


@pytest.mark.asyncio
async def test_plan_gates_reviewer_approved_passes(tmp_path: Path) -> None:
    factory = FakeRuntimeFactory(fix=True)
    reviewer_factory = FakeReviewerFactory(verdict="approved")
    strategy = PlanGatesReviewerStrategy(
        name="plan_gates_reviewer",
        policy=POLICY,
        runtime_factory=factory,
        reviewer_factory=reviewer_factory,
    )
    result = await strategy.run(
        _billing_case(), repo_path=_repo(tmp_path), strategy_name="plan_gates_reviewer"
    )
    assert result.status == "passed"
    assert result.failure_class == "pass"
    assert result.metadata["reviewer_verdict"] == "approved"
    assert reviewer_factory.diffs  # reviewer saw a real diff


@pytest.mark.asyncio
async def test_plan_gates_reviewer_rejected_fails(tmp_path: Path) -> None:
    factory = FakeRuntimeFactory(fix=True)
    reviewer_factory = FakeReviewerFactory(verdict="request_changes", blockers=1)
    strategy = PlanGatesReviewerStrategy(
        name="plan_gates_reviewer",
        policy=POLICY,
        runtime_factory=factory,
        reviewer_factory=reviewer_factory,
    )
    result = await strategy.run(
        _billing_case(), repo_path=_repo(tmp_path), strategy_name="plan_gates_reviewer"
    )
    assert result.status == "failed"
    assert result.failure_class == "agent_failed"
    assert result.metadata["reviewer_verdict"] == "request_changes"
    assert result.metadata["reviewer_blockers"] == 1
    assert "reviewer not approved" in (result.error or "")


@pytest.mark.asyncio
async def test_plan_gates_reviewer_skips_review_when_gates_fail(tmp_path: Path) -> None:
    factory = FakeRuntimeFactory(fix=False)
    reviewer_factory = FakeReviewerFactory(verdict="approved")
    strategy = PlanGatesReviewerStrategy(
        name="plan_gates_reviewer",
        policy=POLICY,
        runtime_factory=factory,
        reviewer_factory=reviewer_factory,
    )
    result = await strategy.run(
        _billing_case(), repo_path=_repo(tmp_path), strategy_name="plan_gates_reviewer"
    )
    assert result.status == "failed"
    assert result.metadata["reviewer_verdict"] == "not-run"
    assert not reviewer_factory.diffs
