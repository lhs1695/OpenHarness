"""Trace collector — builds parent/child spans from StreamEvents, commands, task events."""

from __future__ import annotations

import json
import time
from typing import Any

from forgeflow.trace.events import SpanEvent, estimate_cost, new_event_id, now_iso
from forgeflow.trace.redaction import redact_payload
from openharness.engine.stream_events import (
    AssistantTextDelta,
    AssistantTurnComplete,
    ErrorEvent,
    StatusEvent,
    StreamEvent,
    ToolExecutionCompleted,
    ToolExecutionStarted,
)


class TraceCollector:
    """Consumes runtime events and assembles an ordered span tree.

    Tool executions are child spans of the enclosing model turn; parallel tool
    calls share the same parent and are correlated by (tool_name, order).
    """

    def __init__(self, *, task_id: str, run_id: str = "", redact: bool = True) -> None:
        self._task_id = task_id
        self._run_id = run_id
        self._redact = redact
        self._events: list[SpanEvent] = []
        self._turn_span: str | None = None
        self._turn_started: float | None = None
        self._tool_spans: list[tuple[str, str]] = []  # (span_id, tool_name)
        self._tool_started: dict[str, float] = {}

    # ------------------------------------------------------------------ input

    def on_stream_event(self, event: StreamEvent) -> None:
        if isinstance(event, AssistantTextDelta):
            if self._turn_span is None:
                self._open_turn()
            return
        if isinstance(event, AssistantTurnComplete):
            self._close_turn(event)
            return
        if isinstance(event, ToolExecutionStarted):
            self._open_tool(event)
            return
        if isinstance(event, ToolExecutionCompleted):
            self._close_tool(event)
            return
        if isinstance(event, ErrorEvent):
            self._add(
                "error",
                status="error",
                error_type="error",
                error_message=event.message,
                metadata={"recoverable": event.recoverable},
            )
            return
        if isinstance(event, StatusEvent):
            self._add("status", output_summary=event.message)

    def on_command(
        self, *, command: list[str], returncode: int, duration_ms: int, output: str = ""
    ) -> None:
        self._add(
            "command_finished",
            status="ok" if returncode == 0 else "error",
            input_summary=" ".join(command),
            output_summary=output,
            latency_ms=duration_ms,
            metadata={"returncode": returncode},
        )

    def on_task_event(self, event_type: str, payload: dict[str, Any]) -> None:
        self._add(event_type, metadata=payload)

    # ------------------------------------------------------------------ spans

    def _open_turn(self) -> None:
        span_id = new_event_id()
        self._turn_span = span_id
        self._turn_started = time.monotonic()
        self._add("model_turn_started", span_id=span_id)

    def _close_turn(self, event: AssistantTurnComplete) -> None:
        latency = (
            int((time.monotonic() - self._turn_started) * 1000)
            if self._turn_started is not None
            else None
        )
        tokens = {
            "input_tokens": event.usage.input_tokens,
            "output_tokens": event.usage.output_tokens,
        }
        self._add(
            "model_turn_completed",
            span_id=self._turn_span or new_event_id(),
            token_usage=tokens,
            estimated_cost=estimate_cost(tokens),
            latency_ms=latency,
            output_summary=event.message.text,
        )
        self._turn_span = None
        self._turn_started = None

    def _open_tool(self, event: ToolExecutionStarted) -> None:
        span_id = new_event_id()
        self._tool_spans.append((span_id, event.tool_name))
        self._tool_started[span_id] = time.monotonic()
        self._add(
            "tool_started",
            span_id=span_id,
            parent_event_id=self._turn_span,
            input_summary=str(event.tool_input),
            metadata={"tool": event.tool_name},
        )

    def _close_tool(self, event: ToolExecutionCompleted) -> None:
        match_index = next(
            (index for index, (_, name) in enumerate(self._tool_spans) if name == event.tool_name),
            None,
        )
        if match_index is None:
            if not self._tool_spans:
                return
            match_index = 0
        span_id, _ = self._tool_spans.pop(match_index)
        started = self._tool_started.pop(span_id, None)
        latency = int((time.monotonic() - started) * 1000) if started is not None else None
        self._add(
            "tool_completed",
            span_id=span_id,
            parent_event_id=self._turn_span,
            status="error" if event.is_error else "ok",
            output_summary=event.output,
            latency_ms=latency,
            metadata={"tool": event.tool_name},
        )

    # ------------------------------------------------------------------ emit

    def _add(
        self,
        event_type: str,
        *,
        span_id: str | None = None,
        parent_event_id: str | None = None,
        status: str = "ok",
        input_summary: str | None = None,
        output_summary: str | None = None,
        latency_ms: int | None = None,
        token_usage: dict[str, int] | None = None,
        estimated_cost: float | None = None,
        error_type: str | None = None,
        error_message: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if self._redact:
            input_summary = _redact_text(input_summary)
            output_summary = _redact_text(output_summary)
            error_message = _redact_text(error_message)
            metadata = redact_payload(metadata or {})
        self._events.append(
            SpanEvent(
                event_id=new_event_id(),
                event_type=event_type,
                span_id=span_id or new_event_id(),
                timestamp=now_iso(),
                status=status,
                parent_event_id=parent_event_id,
                input_summary=input_summary,
                output_summary=output_summary,
                latency_ms=latency_ms,
                token_usage=token_usage,
                estimated_cost=estimated_cost,
                error_type=error_type,
                error_message=error_message,
                metadata=metadata or {},
            )
        )

    # ------------------------------------------------------------------ out

    def events(self) -> list[SpanEvent]:
        return list(self._events)

    def to_jsonl(self) -> str:
        return "\n".join(json.dumps(_event_to_dict(event), ensure_ascii=False) for event in self._events)

    def timeline(self) -> list[dict[str, Any]]:
        return [
            {
                "timestamp": event.timestamp,
                "event_type": event.event_type,
                "span_id": event.span_id,
                "parent_event_id": event.parent_event_id,
                "status": event.status,
                "summary": event.output_summary or event.input_summary,
                "latency_ms": event.latency_ms,
            }
            for event in self._events
        ]

    def summary(self) -> dict[str, Any]:
        turns = [event for event in self._events if event.event_type == "model_turn_completed"]
        tools = [event for event in self._events if event.event_type == "tool_completed"]
        errors = [event for event in self._events if event.status == "error"]
        total_input = sum((event.token_usage or {}).get("input_tokens", 0) for event in turns)
        total_output = sum((event.token_usage or {}).get("output_tokens", 0) for event in turns)
        total_cost = sum(event.estimated_cost or 0 for event in turns)
        return {
            "task_id": self._task_id,
            "run_id": self._run_id,
            "event_count": len(self._events),
            "turn_count": len(turns),
            "total_tokens": total_input + total_output,
            "estimated_cost_usd": round(total_cost, 6),
            "tool_call_count": len(tools),
            "tool_error_count": sum(1 for event in tools if event.status == "error"),
            "error_count": len(errors),
        }


def _redact_text(value: str | None) -> str | None:
    if value is None:
        return None
    from forgeflow.trace.redaction import redact

    return redact(value)


def _event_to_dict(event: SpanEvent) -> dict[str, Any]:
    return {
        "event_id": event.event_id,
        "event_type": event.event_type,
        "span_id": event.span_id,
        "parent_event_id": event.parent_event_id,
        "timestamp": event.timestamp,
        "status": event.status,
        "agent_id": event.agent_id,
        "input_summary": event.input_summary,
        "output_summary": event.output_summary,
        "latency_ms": event.latency_ms,
        "token_usage": event.token_usage,
        "estimated_cost": event.estimated_cost,
        "error_type": event.error_type,
        "error_message": event.error_message,
        "metadata": event.metadata,
    }
