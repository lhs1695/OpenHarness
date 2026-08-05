"""Reviewer unit tests — read-only guarantee, parsing, engine."""

from collections.abc import AsyncIterator

import pytest

from forgeflow.domain.task import DevelopmentTask
from forgeflow.errors import AdapterError
from forgeflow.quality.gates import GateStatus, GateType, reviewer_gate
from forgeflow.quality.reviewer import (
    Reviewer,
    ReviewFinding,
    ReviewReport,
    Severity,
    build_review_engine,
    build_review_prompt,
    parse_review,
    read_only_tool_registry,
)
from openharness.engine.stream_events import AssistantTextDelta


def make_task() -> DevelopmentTask:
    return DevelopmentTask(
        repository="billing-service",
        title="fix duplicate charge",
        description="retries create a second charge",
        task_type="bugfix",
    )


class FakeReviewEngine:
    def __init__(self, text: str) -> None:
        self._text = text

    async def submit_message(self, prompt: str) -> AsyncIterator[object]:
        yield AssistantTextDelta(text=self._text)


def test_review_prompt_forbids_writes() -> None:
    prompt = build_review_prompt(make_task(), "--- a.py\n+++ b.py\n")
    assert "READ-ONLY" in prompt
    assert "do not modify" in prompt.lower()
    assert "```diff" in prompt
    assert "payment" not in prompt  # not needed


def test_parse_review_findings() -> None:
    text = (
        "Verdict: request_changes\n"
        "Summary: The fix breaks idempotency.\n"
        "## Findings\n"
        "- [P1] payment.py:12 missing idempotency key check\n"
        "- [P2] payment.py:20 style nit\n"
    )
    report = parse_review(text)
    assert report.verdict == "request_changes"
    assert report.summary == "The fix breaks idempotency."
    assert len(report.findings) == 2
    assert report.findings[0].severity is Severity.P1
    assert report.findings[0].file == "payment.py"
    assert report.findings[0].line == 12
    assert [finding.severity for finding in report.blockers] == [Severity.P1]


def test_parse_review_approved_without_blockers() -> None:
    text = "Verdict: approved\nSummary: Looks good.\n## Findings\n- [P3] comment typo\n"
    report = parse_review(text)
    assert report.approved


def test_parse_review_downgrades_when_blocker_found() -> None:
    text = "Verdict: approved\nSummary: ok\n## Findings\n- [P1] security issue\n"
    report = parse_review(text)
    assert not report.approved
    assert report.verdict == "request_changes"


@pytest.mark.asyncio
async def test_reviewer_returns_report() -> None:
    engine = FakeReviewEngine("Verdict: approved\nSummary: Looks fine.\n## Findings\n")
    report = await Reviewer(engine).review(make_task(), "diff")
    assert report.approved
    assert report.summary == "Looks fine."


@pytest.mark.asyncio
async def test_reviewer_wraps_engine_errors() -> None:
    class Boom:
        async def submit_message(self, prompt: str) -> AsyncIterator[object]:
            raise RuntimeError("boom")
            yield  # pragma: no cover

    with pytest.raises(AdapterError):
        await Reviewer(Boom()).review(make_task(), "diff")


def test_read_only_tool_registry_contains_only_read_tools() -> None:
    registry = read_only_tool_registry()
    names = {tool.name for tool in registry.list_tools()}
    assert "read_file" in names
    assert "glob" in names
    assert "grep" in names
    assert "bash" not in names
    assert "write_file" not in names
    assert "edit_file" not in names


def test_build_review_engine_uses_read_only_registry() -> None:
    engine = build_review_engine(
        object(), cwd=".", model="test-model", system_prompt="reviewer"
    )
    names = {tool.name for tool in engine._tool_registry.list_tools()}
    assert "bash" not in names
    assert "read_file" in names


def test_reviewer_gate_hard_fails_on_blockers() -> None:
    report = ReviewReport(
        verdict="request_changes",
        summary="bad",
        findings=[ReviewFinding(severity=Severity.P1, message="security")],
    )
    result = reviewer_gate(report)
    assert result.status is GateStatus.FAILED
    assert result.gate_type is GateType.HARD


def test_reviewer_gate_passes_without_blockers() -> None:
    report = ReviewReport(
        verdict="approved",
        summary="ok",
        findings=[ReviewFinding(severity=Severity.P3, message="nit")],
    )
    assert reviewer_gate(report).status is GateStatus.PASSED
