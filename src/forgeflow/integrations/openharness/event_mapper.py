"""Map OpenHarness StreamEvents to ForgeFlow TraceEvents.

TraceEvent is a ForgeFlow type (no OpenHarness imports in its definition);
the adapter layer is the only place that touches ``openharness.*``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from openharness.engine.stream_events import (
    AssistantTextDelta,
    AssistantTurnComplete,
    ErrorEvent,
    StatusEvent,
    StreamEvent,
    ToolExecutionCompleted,
    ToolExecutionStarted,
)


@dataclass(frozen=True)
class TraceEvent:
    """A ForgeFlow trace event (M1 subset of the spec §7.5 model)."""

    event_id: str
    event_type: str
    timestamp: str
    status: str = "ok"
    agent_id: str | None = None
    parent_event_id: str | None = None
    input_summary: str | None = None
    output_summary: str | None = None
    latency_ms: int | None = None
    token_usage: dict[str, int] | None = None
    error_type: str | None = None
    error_message: str | None = None
    metadata: dict[str, Any] | None = None


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _summarize(value: Any) -> str:
    return str(value)[:300]


def map_stream_event(event: StreamEvent, *, now: str | None = None) -> TraceEvent | None:
    """Map one OpenHarness StreamEvent to a ForgeFlow TraceEvent.

    Returns None for events ForgeFlow does not track.
    """
    timestamp = now or _now_iso()
    if isinstance(event, AssistantTextDelta):
        return TraceEvent(
            event_id=uuid4().hex,
            event_type="model_text_delta",
            timestamp=timestamp,
            output_summary=event.text,
        )
    if isinstance(event, AssistantTurnComplete):
        return TraceEvent(
            event_id=uuid4().hex,
            event_type="model_turn_complete",
            timestamp=timestamp,
            token_usage={
                "input_tokens": event.usage.input_tokens,
                "output_tokens": event.usage.output_tokens,
            },
            output_summary=_summarize(event.message.text),
        )
    if isinstance(event, ToolExecutionStarted):
        return TraceEvent(
            event_id=uuid4().hex,
            event_type="tool_started",
            timestamp=timestamp,
            input_summary=_summarize(event.tool_input),
            metadata={"tool": event.tool_name},
        )
    if isinstance(event, ToolExecutionCompleted):
        return TraceEvent(
            event_id=uuid4().hex,
            event_type="tool_completed",
            timestamp=timestamp,
            status="error" if event.is_error else "ok",
            output_summary=_summarize(event.output),
            metadata={"tool": event.tool_name},
        )
    if isinstance(event, ErrorEvent):
        return TraceEvent(
            event_id=uuid4().hex,
            event_type="error",
            timestamp=timestamp,
            status="error",
            error_message=event.message,
            metadata={"recoverable": event.recoverable},
        )
    if isinstance(event, StatusEvent):
        return TraceEvent(
            event_id=uuid4().hex,
            event_type="status",
            timestamp=timestamp,
            output_summary=event.message,
        )
    return None
