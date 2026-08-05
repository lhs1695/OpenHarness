"""Map OpenHarness StreamEvents to the unified ForgeFlow SpanEvent (P2-8).

Previously a parallel ``TraceEvent`` model existed here; everything now uses
``forgeflow.trace.events.SpanEvent`` so plan, execution and feedback traces share
one model.  The adapter layer is the only place that touches ``openharness.*``.
"""

from __future__ import annotations

from typing import Any

from forgeflow.trace.events import SpanEvent, new_event_id, now_iso
from openharness.engine.stream_events import (
    AssistantTextDelta,
    AssistantTurnComplete,
    ErrorEvent,
    StatusEvent,
    StreamEvent,
    ToolExecutionCompleted,
    ToolExecutionStarted,
)


def _summarize(value: Any) -> str:
    return str(value)[:300]


def map_stream_event(event: StreamEvent, *, now: str | None = None) -> SpanEvent | None:
    """Map one OpenHarness StreamEvent to a ForgeFlow SpanEvent.

    Returns None for events ForgeFlow does not track.
    """
    timestamp = now or now_iso()
    if isinstance(event, AssistantTextDelta):
        return SpanEvent(
            event_id=new_event_id(),
            event_type="model_text_delta",
            span_id=new_event_id(),
            timestamp=timestamp,
            output_summary=event.text,
        )
    if isinstance(event, AssistantTurnComplete):
        return SpanEvent(
            event_id=new_event_id(),
            event_type="model_turn_completed",
            span_id=new_event_id(),
            timestamp=timestamp,
            token_usage={
                "input_tokens": event.usage.input_tokens,
                "output_tokens": event.usage.output_tokens,
            },
            output_summary=_summarize(event.message.text),
        )
    if isinstance(event, ToolExecutionStarted):
        return SpanEvent(
            event_id=new_event_id(),
            event_type="tool_started",
            span_id=new_event_id(),
            timestamp=timestamp,
            input_summary=_summarize(event.tool_input),
            metadata={"tool": event.tool_name},
        )
    if isinstance(event, ToolExecutionCompleted):
        return SpanEvent(
            event_id=new_event_id(),
            event_type="tool_completed",
            span_id=new_event_id(),
            timestamp=timestamp,
            status="error" if event.is_error else "ok",
            output_summary=_summarize(event.output),
            metadata={"tool": event.tool_name},
        )
    if isinstance(event, ErrorEvent):
        return SpanEvent(
            event_id=new_event_id(),
            event_type="error",
            span_id=new_event_id(),
            timestamp=timestamp,
            status="error",
            error_message=event.message,
            metadata={"recoverable": event.recoverable},
        )
    if isinstance(event, StatusEvent):
        return SpanEvent(
            event_id=new_event_id(),
            event_type="status",
            span_id=new_event_id(),
            timestamp=timestamp,
            output_summary=event.message,
        )
    return None
