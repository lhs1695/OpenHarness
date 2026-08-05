"""Adapter unit tests — drive the adapter with a fake engine (no model calls)."""

from collections.abc import AsyncIterator

import pytest

from forgeflow.domain.task import DevelopmentTask
from forgeflow.errors import AdapterError, MaxTurnsExceededError
from forgeflow.integrations.openharness.adapter import OpenHarnessAdapter
from openharness.api.usage import UsageSnapshot
from openharness.engine.messages import ConversationMessage, TextBlock
from openharness.engine.query import MaxTurnsExceeded
from openharness.engine.stream_events import (
    AssistantTextDelta,
    AssistantTurnComplete,
    StreamEvent,
    ToolExecutionCompleted,
    ToolExecutionStarted,
)

PLAN_DELTAS = (
    AssistantTextDelta(
        text=(
            "## Target Files\n"
            "- payment.py\n"
            "## Steps\n"
            "1. add idempotency key\n"
            "2. write retry test\n"
            "## Risk Points\n"
            "- concurrency\n"
            "## Test Plan\n"
            "- pytest -q"
        )
    ),
)


class FakeEngine:
    """Yields a scripted sequence of StreamEvents."""

    def __init__(self, events: list[StreamEvent]) -> None:
        self._events = events

    async def submit_message(self, prompt: str) -> AsyncIterator[StreamEvent]:
        for event in self._events:
            yield event


class ThrowingEngine:
    """Raises immediately on submit."""

    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    async def submit_message(self, prompt: str) -> AsyncIterator[StreamEvent]:
        raise self._exc
        yield  # pragma: no cover


def make_task() -> DevelopmentTask:
    return DevelopmentTask(
        repository="billing-service",
        task_type="bugfix",
        priority="P2",
        title="Fix duplicate charge on retry",
        description="Retries may create a second charge.",
        acceptance_criteria=["same idempotency key creates one record"],
        risk_tags=["payment"],
    )


async def _happy_events() -> list[StreamEvent]:
    message = ConversationMessage(role="assistant", content=[TextBlock(text="plan done")])
    return [
        *PLAN_DELTAS,
        ToolExecutionStarted(tool_name="file_read", tool_input={"path": "payment.py"}),
        ToolExecutionCompleted(tool_name="file_read", output="...", is_error=False),
        ToolExecutionCompleted(tool_name="bash", output="fail", is_error=True),
        AssistantTurnComplete(
            message=message,
            usage=UsageSnapshot(input_tokens=100, output_tokens=50),
        ),
    ]


@pytest.mark.asyncio
async def test_run_plan_builds_structured_plan() -> None:
    plan = await OpenHarnessAdapter().run_plan(make_task(), FakeEngine(await _happy_events()))
    assert plan.repository == "billing-service"
    assert plan.target_files == ["payment.py"]
    assert plan.steps == ["1. add idempotency key", "2. write retry test"]
    assert plan.risk_points == ["concurrency"]
    assert plan.test_plan == ["pytest -q"]
    assert plan.token_usage == {"input_tokens": 100, "output_tokens": 50}
    assert plan.tool_call_count == 1
    assert plan.tool_error_count == 1
    assert plan.duration_ms >= 0
    assert len(plan.trace) == 5
    assert "## Target Files" in plan.plan_text


@pytest.mark.asyncio
async def test_run_plan_maps_max_turns_to_typed_error() -> None:
    engine = ThrowingEngine(MaxTurnsExceeded("exceeded max turns"))
    with pytest.raises(MaxTurnsExceededError):
        await OpenHarnessAdapter().run_plan(make_task(), engine)


@pytest.mark.asyncio
async def test_run_plan_wraps_unexpected_errors() -> None:
    engine = ThrowingEngine(RuntimeError("provider exploded"))
    with pytest.raises(AdapterError):
        await OpenHarnessAdapter().run_plan(make_task(), engine)


def test_build_plan_prompt_contains_task_fields() -> None:
    prompt = OpenHarnessAdapter()._prompt_builder(make_task())
    assert "billing-service" in prompt
    assert "Fix duplicate charge on retry" in prompt
    assert "## Target Files" in prompt
