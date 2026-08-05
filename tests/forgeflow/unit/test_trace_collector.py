"""Trace collector unit tests — spans, parallel tools, errors, JSONL, summary."""

from __future__ import annotations

import json

from forgeflow.trace.collector import TraceCollector
from openharness.api.usage import UsageSnapshot
from openharness.engine.messages import ConversationMessage, TextBlock
from openharness.engine.stream_events import (
    AssistantTextDelta,
    AssistantTurnComplete,
    ErrorEvent,
    ToolExecutionCompleted,
    ToolExecutionStarted,
)


def _turn_message(text: str) -> ConversationMessage:
    return ConversationMessage(role="assistant", content=[TextBlock(text=text)])


def test_turn_and_tool_spans_with_parent_child() -> None:
    collector = TraceCollector(task_id="t1", run_id="r1")
    collector.on_stream_event(AssistantTextDelta(text="let me check"))
    collector.on_stream_event(ToolExecutionStarted(tool_name="grep", tool_input={"pattern": "x"}))
    collector.on_stream_event(ToolExecutionCompleted(tool_name="grep", output="hit", is_error=False))
    collector.on_stream_event(
        AssistantTurnComplete(
            message=_turn_message("done"),
            usage=UsageSnapshot(input_tokens=10, output_tokens=5),
        )
    )
    events = collector.events()
    types = [event.event_type for event in events]
    assert "model_turn_started" in types
    assert "tool_started" in types
    assert "tool_completed" in types
    assert "model_turn_completed" in types

    turn = next(e for e in events if e.event_type == "model_turn_started")
    tool = next(e for e in events if e.event_type == "tool_completed")
    assert tool.parent_event_id == turn.span_id  # tool is a child of the turn


def test_parallel_tools_share_parent_span() -> None:
    collector = TraceCollector(task_id="t1", run_id="r1")
    collector.on_stream_event(AssistantTextDelta(text="run parallel"))
    collector.on_stream_event(ToolExecutionStarted(tool_name="grep", tool_input={"a": 1}))
    collector.on_stream_event(ToolExecutionStarted(tool_name="bash", tool_input={"b": 2}))
    collector.on_stream_event(ToolExecutionCompleted(tool_name="grep", output="g", is_error=False))
    collector.on_stream_event(ToolExecutionCompleted(tool_name="bash", output="b", is_error=True))
    collector.on_stream_event(
        AssistantTurnComplete(message=_turn_message("ok"), usage=UsageSnapshot())
    )
    tool_events = [e for e in collector.events() if e.event_type == "tool_completed"]
    assert len(tool_events) == 2
    parents = {e.parent_event_id for e in tool_events}
    assert len(parents) == 1  # both tools under the same turn span
    assert {e.status for e in tool_events} == {"ok", "error"}


def test_turn_completed_tracks_tokens_and_cost() -> None:
    collector = TraceCollector(task_id="t1", run_id="r1")
    collector.on_stream_event(AssistantTextDelta(text="x"))
    collector.on_stream_event(
        AssistantTurnComplete(
            message=_turn_message("done"),
            usage=UsageSnapshot(input_tokens=1000, output_tokens=2000),
        )
    )
    turn = next(e for e in collector.events() if e.event_type == "model_turn_completed")
    assert turn.token_usage == {"input_tokens": 1000, "output_tokens": 2000}
    assert turn.estimated_cost is not None and turn.estimated_cost > 0


def test_error_event_recorded() -> None:
    collector = TraceCollector(task_id="t1", run_id="r1")
    collector.on_stream_event(ErrorEvent(message="boom", recoverable=False))
    error = next(e for e in collector.events() if e.event_type == "error")
    assert error.status == "error"
    assert error.error_message == "boom"


def test_command_span() -> None:
    collector = TraceCollector(task_id="t1", run_id="r1")
    collector.on_command(command=["pytest", "-q"], returncode=1, duration_ms=120, output="FAILED")
    cmd = next(e for e in collector.events() if e.event_type == "command_finished")
    assert cmd.status == "error"
    assert cmd.latency_ms == 120
    assert cmd.metadata["returncode"] == 1


def test_redaction_applied_to_summaries() -> None:
    collector = TraceCollector(task_id="t1", run_id="r1", redact=True)
    collector.on_command(
        command=["env"], returncode=0, duration_ms=1, output="TOKEN=sk-abcdef1234567890"
    )
    cmd = collector.events()[0]
    assert "sk-abcdef1234567890" not in cmd.output_summary


def test_to_jsonl_and_summary() -> None:
    collector = TraceCollector(task_id="t1", run_id="r1")
    collector.on_stream_event(AssistantTextDelta(text="x"))
    collector.on_stream_event(
        AssistantTurnComplete(
            message=_turn_message("done"),
            usage=UsageSnapshot(input_tokens=100, output_tokens=50),
        )
    )
    lines = collector.to_jsonl().splitlines()
    assert len(lines) == 2  # turn_started + turn_completed
    for line in lines:
        parsed = json.loads(line)
        assert "event_type" in parsed
        assert "span_id" in parsed
    summary = collector.summary()
    assert summary["turn_count"] == 1
    assert summary["total_tokens"] == 150
    assert summary["tool_call_count"] == 0
