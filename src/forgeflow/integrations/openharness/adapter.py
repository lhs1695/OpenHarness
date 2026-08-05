"""OpenHarness adapter — drive OpenHarness to plan a task.

The business layer only ever sees ForgeFlow types.  OpenHarness types are
confined to this integration package; the engine is injected so unit tests
can drive the adapter with a fake.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Protocol

from forgeflow.domain.task import DevelopmentTask
from forgeflow.errors import AdapterError, MaxTurnsExceededError
from forgeflow.integrations.openharness.event_mapper import TraceEvent, map_stream_event
from openharness.engine.query import MaxTurnsExceeded
from openharness.engine.stream_events import (
    AssistantTextDelta,
    StreamEvent,
    ToolExecutionCompleted,
    ToolExecutionStarted,
)


class EngineLike(Protocol):
    """Minimal engine surface consumed by ForgeFlow (satisfied by QueryEngine).

    Implementations are async generator functions; calling them returns the
    async iterator directly, so the protocol method is not ``async def``.
    """

    def submit_message(self, prompt: str) -> AsyncIterator[StreamEvent]: ...


@dataclass(frozen=True)
class TaskPlan:
    """Structured plan extracted from a planning run (M1)."""

    repository: str
    plan_text: str
    target_files: list[str] = field(default_factory=list)
    steps: list[str] = field(default_factory=list)
    risk_points: list[str] = field(default_factory=list)
    test_plan: list[str] = field(default_factory=list)
    token_usage: dict[str, int] = field(default_factory=dict)
    tool_call_count: int = 0
    tool_error_count: int = 0
    duration_ms: int = 0
    trace: list[TraceEvent] = field(default_factory=list)


SECTION_HEADERS = ("Target Files", "Steps", "Risk Points", "Test Plan")


def build_plan_prompt(task: DevelopmentTask) -> str:
    """Build the planning instruction sent to the model for a task."""
    criteria = "\n".join(f"- {item}" for item in task.acceptance_criteria) or "- (none)"
    tags = ", ".join(task.risk_tags) or "(none)"
    return (
        "You are a senior backend engineer planning a code change in repository "
        f"'{task.repository}'. DO NOT modify any files — analysis and planning only.\n\n"
        f"# Task\n"
        f"- Title: {task.title}\n"
        f"- Type: {task.task_type}\n"
        f"- Priority: {task.priority}\n"
        f"- Description: {task.description}\n"
        f"- Acceptance criteria:\n{criteria}\n"
        f"- Risk tags: {tags}\n\n"
        "# Output format (use exactly these section headers)\n"
        "## Target Files\n"
        "## Steps\n"
        "## Risk Points\n"
        "## Test Plan"
    )


def _clean_item(line: str) -> str:
    return line.strip().strip("-•*").strip()


def extract_plan(
    task: DevelopmentTask,
    *,
    text: str,
    events: list[TraceEvent],
    tool_call_count: int,
    tool_error_count: int,
    duration_ms: int,
) -> TaskPlan:
    """Assemble a structured TaskPlan from the collected text and events."""
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for raw in text.splitlines():
        line = raw.strip()
        header = next((h for h in SECTION_HEADERS if line.startswith(f"## {h}")), None)
        if header is not None:
            current = header
            sections.setdefault(current, [])
        elif current is not None and line:
            sections[current].append(_clean_item(line))

    tokens = {"input_tokens": 0, "output_tokens": 0}
    for event in events:
        if event.event_type == "model_turn_complete" and event.token_usage:
            tokens["input_tokens"] += event.token_usage.get("input_tokens", 0)
            tokens["output_tokens"] += event.token_usage.get("output_tokens", 0)

    return TaskPlan(
        repository=task.repository,
        plan_text=text.strip(),
        target_files=[_clean_item(item) for item in sections.get("Target Files", [])],
        steps=[_clean_item(item) for item in sections.get("Steps", [])],
        risk_points=[_clean_item(item) for item in sections.get("Risk Points", [])],
        test_plan=[_clean_item(item) for item in sections.get("Test Plan", [])],
        token_usage=tokens,
        tool_call_count=tool_call_count,
        tool_error_count=tool_error_count,
        duration_ms=duration_ms,
        trace=events,
    )


class OpenHarnessAdapter:
    """Plans a DevelopmentTask by driving an injected OpenHarness engine."""

    def __init__(self) -> None:
        self._prompt_builder = build_plan_prompt

    async def run_plan(self, task: DevelopmentTask, engine: EngineLike) -> TaskPlan:
        """Run a planning turn against ``engine`` and return a structured plan."""
        prompt = self._prompt_builder(task)
        started = time.monotonic()
        events: list[TraceEvent] = []
        text_parts: list[str] = []
        tool_calls = 0
        tool_errors = 0
        try:
            async for event in engine.submit_message(prompt):
                mapped = map_stream_event(event)
                if mapped is not None:
                    events.append(mapped)
                if isinstance(event, AssistantTextDelta):
                    text_parts.append(event.text)
                elif isinstance(event, ToolExecutionStarted):
                    tool_calls += 1
                elif isinstance(event, ToolExecutionCompleted) and event.is_error:
                    tool_errors += 1
        except MaxTurnsExceeded as exc:
            raise MaxTurnsExceededError(str(exc)) from exc
        except Exception as exc:
            raise AdapterError(f"OpenHarness engine failed while planning: {exc}") from exc
        duration_ms = int((time.monotonic() - started) * 1000)
        return extract_plan(
            task,
            text="".join(text_parts),
            events=events,
            tool_call_count=tool_calls,
            tool_error_count=tool_errors,
            duration_ms=duration_ms,
        )
