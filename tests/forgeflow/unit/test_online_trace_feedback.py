"""A1 数据回流: online strategies forward StreamEvents -> TraceCollector -> FeedbackRegistry.

Runs the strategy orchestration with a fake runtime (no model calls) and asserts
a per-case FeedbackDataset lands in the registry with real provenance; also
covers the engine proxy and the runner-side merge/round-trip.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

from forgeflow.domain.policy import RepositoryPolicy
from forgeflow.evaluation.datasets import EvalCase
from forgeflow.evaluation.feedback import (
    FeedbackDataset,
    dataset_from_json,
    dataset_to_json,
    merge_datasets,
)
from forgeflow.evaluation.fixtures import materialize_git_repo
from forgeflow.evaluation.registry import FeedbackRegistry
from forgeflow.evaluation.strategies_online import (
    AgentEngine,
    RawAgentStrategy,
    _TraceForwardingEngine,
)
from forgeflow.trace.collector import TraceCollector
from openharness.api.usage import UsageSnapshot
from openharness.engine.messages import ConversationMessage
from openharness.engine.stream_events import (
    AssistantTextDelta,
    AssistantTurnComplete,
    StreamEvent,
    ToolExecutionCompleted,
    ToolExecutionStarted,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "repositories"

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
    return [record for record in _charges.values() if record.order_id == order_id]


def charge(order_id: str, amount: int) -> PaymentRecord:
    existing = charges_for(order_id)
    if existing:
        return existing[0]
    record = PaymentRecord(id=uuid.uuid4().hex, order_id=order_id, amount=amount)
    _charges[record.id] = record
    return record
'''

POLICY = RepositoryPolicy(repository="billing-service")


def _case(case_id: str = "billing-001") -> EvalCase:
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


class _Usage:
    input_tokens = 120
    output_tokens = 60


class _FixEngine:
    """Writes the working fix then completes a turn (plus a tool call)."""

    def __init__(self, workspace: Path, *, fix: bool = True) -> None:
        self._workspace = workspace
        self._fix = fix
        self.usage = _Usage()

    @property
    def model(self) -> str:
        return "fake-model"

    @property
    def total_usage(self) -> object:
        return self.usage

    async def submit_message(self, prompt: str) -> AsyncIterator[StreamEvent]:
        if self._fix:
            (self._workspace / "payment.py").write_text(FIXED_PAYMENT, encoding="utf-8")
        yield AssistantTextDelta(text="read files")
        yield ToolExecutionStarted(tool_name="read_file", tool_input={"path": "payment.py"})
        yield ToolExecutionCompleted(tool_name="read_file", output="source", is_error=False)
        yield AssistantTextDelta(text="implemented the change")
        yield AssistantTurnComplete(
            message=ConversationMessage(role="assistant"),
            usage=UsageSnapshot(input_tokens=120, output_tokens=60),
        )


class _RaisingEngine:
    """Yields one delta then fails, simulating a mid-turn provider error."""

    @property
    def model(self) -> str:
        return "fake-model"

    @property
    def total_usage(self) -> object:
        return _Usage()

    async def submit_message(self, prompt: str) -> AsyncIterator[StreamEvent]:
        yield AssistantTextDelta(text="started")
        raise RuntimeError("provider failure")


class _Session:
    def __init__(self, engine: AgentEngine) -> None:
        self.engine = engine
        self.api_client = object()
        self.closed = False

    async def close(self) -> None:
        self.closed = True


class _RuntimeFactory:
    def __init__(self, *, fix: bool = True, raising: bool = False) -> None:
        self._fix = fix
        self._raising = raising
        self.sessions: list[_Session] = []

    async def __call__(
        self,
        *,
        cwd: str,
        system_prompt: str,
        permission_mode: str,
        max_turns: int,
    ) -> _Session:
        if self._raising:
            session = _Session(_RaisingEngine())
        else:
            session = _Session(_FixEngine(Path(cwd), fix=self._fix))
        self.sessions.append(session)
        return session


def test_strategy_forwards_stream_events_and_registers_feedback(tmp_path: Path) -> None:
    registry = FeedbackRegistry()
    factory = _RuntimeFactory(fix=True)
    strategy = RawAgentStrategy(
        name="raw",
        policy=POLICY,
        runtime_factory=factory,
        feedback_registry=registry,
        dataset_version="2026-08-05",
    )

    result = asyncio.run(strategy.run(_case(), repo_path=_repo(tmp_path), strategy_name="raw"))

    assert result.status == "passed"
    datasets = registry.list()
    assert datasets, "no feedback dataset registered"
    dataset = datasets[0]
    assert dataset.samples, "expected at least one sample"
    sample = dataset.samples[0]
    assert sample.task_id == strategy._task_id(_case())
    assert sample.provenance["case_id"] == "billing-001"
    assert sample.provenance["repository"] == "billing-service"
    assert sample.provenance["strategy"] == "raw"
    # The turn content is JSON of the collected span events (redacted).
    assert '"model_turn_started"' in sample.content or '"model_turn_completed"' in sample.content
    assert sample.classification in ("success", "failure")


def test_trace_forwarding_engine_captures_tools_and_tokens(tmp_path: Path) -> None:
    collector = TraceCollector(task_id="case", run_id="run")
    engine = _TraceForwardingEngine(_FixEngine(tmp_path), collector)

    async def _drain() -> None:
        async for _event in engine.submit_message("go"):
            pass

    asyncio.run(_drain())

    types = [event.event_type for event in collector.events()]
    assert "model_turn_started" in types
    assert "tool_started" in types
    assert "tool_completed" in types
    assert "model_turn_completed" in types
    completed = next(
        event for event in collector.events() if event.event_type == "model_turn_completed"
    )
    assert (completed.token_usage or {}).get("input_tokens") == 120
    assert (completed.token_usage or {}).get("output_tokens") == 60


def test_strategy_attaches_real_diff_to_result(tmp_path: Path) -> None:
    """B1: the agent's real worktree diff lands on the EvalResult for delivery."""
    factory = _RuntimeFactory(fix=True)
    strategy = RawAgentStrategy(name="raw", policy=POLICY, runtime_factory=factory)
    result = asyncio.run(strategy.run(_case(), repo_path=_repo(tmp_path), strategy_name="raw"))
    assert "diff" in result.metadata
    assert "payment.py" in str(result.metadata["diff"])


def test_error_run_still_registers_partial_feedback(tmp_path: Path) -> None:
    registry = FeedbackRegistry()
    factory = _RuntimeFactory(raising=True)
    strategy = RawAgentStrategy(
        name="raw",
        policy=POLICY,
        runtime_factory=factory,
        feedback_registry=registry,
        dataset_version="2026-08-05",
    )

    result = asyncio.run(
        strategy.run(_case(), repo_path=_repo(tmp_path), strategy_name="raw")
    )

    assert result.status == "error"
    datasets = registry.list()
    assert datasets, "partial trace should still be registered on failure"
    assert datasets[0].samples


def test_merge_datasets_roundtrip() -> None:
    first = FeedbackDataset(
        id="feedback-a", version="v1", samples=(_sample("a1", "success"),)
    )
    second = FeedbackDataset(
        id="feedback-b", version="v2", samples=(_sample("b1", "failure"),)
    )

    merged = merge_datasets([first, second])
    assert len(merged.samples) == 2
    loaded = dataset_from_json(dataset_to_json(merged))
    assert len(loaded.samples) == 2
    assert {sample.id for sample in loaded.samples} == {"a1", "b1"}


def _sample(sample_id: str, classification: str):
    from forgeflow.evaluation.feedback import ExperienceSample

    return ExperienceSample(
        id=sample_id,
        task_id="t",
        run_id="r",
        source_type="turn",
        classification=classification,
        content="x",
    )
