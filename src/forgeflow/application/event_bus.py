"""In-process async event bus — live source for SSE (spec §9.1)."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True)
class TaskEvent:
    task_id: str
    event_type: str
    occurred_at: str
    payload: dict[str, Any] = field(default_factory=dict)


class EventBus:
    """Fans task events out to per-task asyncio queues."""

    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue[TaskEvent]]] = {}

    def subscribe(self, task_id: str) -> asyncio.Queue[TaskEvent]:
        queue: asyncio.Queue[TaskEvent] = asyncio.Queue()
        self._subscribers.setdefault(task_id, set()).add(queue)
        return queue

    def unsubscribe(self, task_id: str, queue: asyncio.Queue[TaskEvent]) -> None:
        subscribers = self._subscribers.get(task_id)
        if subscribers is None:
            return
        subscribers.discard(queue)
        if not subscribers:
            self._subscribers.pop(task_id, None)

    def publish(self, task_id: str, event_type: str, payload: dict[str, Any] | None = None) -> TaskEvent:
        event = TaskEvent(
            task_id=task_id,
            event_type=event_type,
            occurred_at=_now_iso(),
            payload=payload or {},
        )
        for queue in list(self._subscribers.get(task_id, ())):
            queue.put_nowait(event)
        return event
