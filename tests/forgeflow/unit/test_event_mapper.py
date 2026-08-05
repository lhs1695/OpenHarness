"""Event mapper unit tests."""

from forgeflow.integrations.openharness.event_mapper import map_stream_event
from forgeflow.trace.events import SpanEvent
from openharness.api.usage import UsageSnapshot
from openharness.engine.messages import ConversationMessage, TextBlock
from openharness.engine.stream_events import (
    AssistantTextDelta,
    AssistantTurnComplete,
    ErrorEvent,
    StatusEvent,
    ToolExecutionCompleted,
    ToolExecutionStarted,
)


def test_maps_text_delta() -> None:
    event = map_stream_event(AssistantTextDelta(text="hello"))
    assert event is not None
    assert event.event_type == "model_text_delta"
    assert event.status == "ok"
    assert event.output_summary == "hello"


def test_maps_turn_complete_usage() -> None:
    message = ConversationMessage(role="assistant", content=[TextBlock(text="plan")])
    event = map_stream_event(
        AssistantTurnComplete(
            message=message,
            usage=UsageSnapshot(input_tokens=10, output_tokens=5),
        )
    )
    assert event is not None
    assert event.event_type == "model_turn_completed"
    assert event.token_usage == {"input_tokens": 10, "output_tokens": 5}


def test_maps_tool_started() -> None:
    event = map_stream_event(
        ToolExecutionStarted(tool_name="file_read", tool_input={"path": "payment.py"})
    )
    assert event is not None
    assert event.event_type == "tool_started"
    assert event.metadata == {"tool": "file_read"}
    assert event.input_summary is not None


def test_maps_tool_completed_with_error_status() -> None:
    ok_event = map_stream_event(
        ToolExecutionCompleted(tool_name="bash", output="ok", is_error=False)
    )
    err_event = map_stream_event(
        ToolExecutionCompleted(tool_name="bash", output="boom", is_error=True)
    )
    assert ok_event is not None and ok_event.status == "ok"
    assert err_event is not None and err_event.status == "error"


def test_maps_error_event() -> None:
    event = map_stream_event(ErrorEvent(message="boom", recoverable=False))
    assert event is not None
    assert event.event_type == "error"
    assert event.status == "error"
    assert event.error_message == "boom"


def test_maps_status_event() -> None:
    event = map_stream_event(StatusEvent(message="working"))
    assert event is not None
    assert event.event_type == "status"
    assert event.output_summary == "working"


def test_ignores_untracked_events() -> None:
    assert map_stream_event("not-a-stream-event") is None  # type: ignore[arg-type]


def test_now_is_overridable() -> None:
    event = map_stream_event(StatusEvent(message="x"), now="2026-08-05T00:00:00+00:00")
    assert event is not None
    assert event.timestamp == "2026-08-05T00:00:00+00:00"


def test_trace_event_is_dataclass() -> None:
    event = SpanEvent(event_id="e1", event_type="status", span_id="s1", timestamp="t")
    assert event.status == "ok"
    assert event.token_usage is None
