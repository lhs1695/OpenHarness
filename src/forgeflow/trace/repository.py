"""Trace repository — persist spans, export JSONL, query timelines."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from typing import Any

from forgeflow.infrastructure.store import TaskStore
from forgeflow.trace.events import SpanEvent


class TraceRepository:
    """Persists SpanEvents via the task store and reconstructs them on read."""

    def __init__(self, store: TaskStore) -> None:
        self._store = store

    def save_events(self, *, task_id: str, run_id: str, events: list[SpanEvent]) -> None:
        records = []
        for event in events:
            records.append(
                {
                    "event_id": event.event_id,
                    "task_id": task_id,
                    "run_id": run_id,
                    "event_type": event.event_type,
                    "occurred_at": datetime.fromisoformat(event.timestamp),
                    "payload": asdict(event),
                }
            )
        self._store.bulk_append_events(records)

    def load_events(self, task_id: str) -> list[SpanEvent]:
        raw = self._store.list_events(task_id)
        events: list[SpanEvent] = []
        for item in raw:
            payload = item.get("payload")
            if isinstance(payload, dict) and "event_id" in payload:
                try:
                    events.append(SpanEvent(**payload))
                except (TypeError, ValueError):
                    continue
        return events

    def export_jsonl(self, task_id: str) -> str:
        return "\n".join(json.dumps(asdict(event), ensure_ascii=False) for event in self.load_events(task_id))

    def timeline(self, task_id: str) -> list[dict[str, Any]]:
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
            for event in self.load_events(task_id)
        ]
