"""Persistence for tasks, runs, trace events, and approvals."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from forgeflow.domain.approval import Approval
from forgeflow.infrastructure.models import (
    ApprovalRecord,
    RunRecord,
    TaskRecord,
    TraceEventRecord,
)


@dataclass(frozen=True)
class StoredTask:
    id: str
    repository: str
    title: str
    description: str
    task_type: str
    priority: str
    acceptance_criteria: list[str]
    risk_tags: list[str]
    status: str
    initial_risk_score: int
    final_risk_score: int | None
    requested_by: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class StoredApproval:
    id: str
    task_id: str
    run_id: str
    approval_type: str
    status: str
    requested_reason: str
    requested_at: datetime
    resolved_by: str | None
    resolved_at: datetime | None
    resolution_reason: str | None


def _dump(value: object) -> str:
    return json.dumps(value, ensure_ascii=False)


def _load(text: str) -> Any:
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        return []


def _load_list(text: str) -> list[str]:
    value = _load(text)
    return [str(item) for item in value] if isinstance(value, list) else []


def to_stored_approval(approval: Approval) -> StoredApproval:
    """Convert a domain Approval to a StoredApproval (for persistence)."""
    return StoredApproval(
        id=approval.approval_id,
        task_id=approval.task_id,
        run_id=approval.run_id or "",
        approval_type=approval.approval_type.value,
        status=approval.status.value,
        requested_reason=approval.requested_reason,
        requested_at=datetime.fromisoformat(approval.requested_at),
        resolved_by=approval.resolved_by,
        resolved_at=(
            datetime.fromisoformat(approval.resolved_at) if approval.resolved_at else None
        ),
        resolution_reason=approval.resolution_reason,
    )


def _to_stored(record: TaskRecord) -> StoredTask:
    return StoredTask(
        id=record.id,
        repository=record.repository,
        title=record.title,
        description=record.description,
        task_type=record.task_type,
        priority=record.priority,
        acceptance_criteria=_load_list(record.acceptance_criteria),
        risk_tags=_load_list(record.risk_tags),
        status=record.status,
        initial_risk_score=record.initial_risk_score,
        final_risk_score=record.final_risk_score,
        requested_by=record.requested_by,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


class TaskStore:
    """Persistence for task state, runs, trace events, and approvals."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def create_task(self, task: StoredTask) -> StoredTask:
        self._session.add(
            TaskRecord(
                id=task.id,
                repository=task.repository,
                title=task.title,
                description=task.description,
                task_type=task.task_type,
                priority=task.priority,
                acceptance_criteria=_dump(task.acceptance_criteria),
                risk_tags=_dump(task.risk_tags),
                status=task.status,
                initial_risk_score=task.initial_risk_score,
                final_risk_score=task.final_risk_score,
                requested_by=task.requested_by,
                created_at=task.created_at,
                updated_at=task.updated_at,
            )
        )
        self._session.commit()
        return task

    def get_task(self, task_id: str) -> StoredTask | None:
        record = self._session.get(TaskRecord, task_id)
        return _to_stored(record) if record is not None else None

    def list_tasks(self) -> list[StoredTask]:
        records = self._session.scalars(select(TaskRecord).order_by(TaskRecord.created_at)).all()
        return [_to_stored(record) for record in records]

    def update_task(
        self,
        task_id: str,
        *,
        status: str | None = None,
        final_risk_score: int | None = None,
    ) -> StoredTask | None:
        record = self._session.get(TaskRecord, task_id)
        if record is None:
            return None
        if status is not None:
            record.status = status
        if final_risk_score is not None:
            record.final_risk_score = final_risk_score
        self._session.commit()
        return _to_stored(record)

    def append_event(
        self,
        *,
        task_id: str,
        run_id: str,
        event_type: str,
        payload: dict[str, Any],
        event_id: str,
        occurred_at: datetime,
    ) -> None:
        self._session.add(
            TraceEventRecord(
                id=event_id,
                task_id=task_id,
                run_id=run_id,
                event_type=event_type,
                occurred_at=occurred_at,
                payload=_dump(payload),
            )
        )
        self._session.commit()

    def list_events(self, task_id: str) -> list[dict[str, Any]]:
        records = self._session.scalars(
            select(TraceEventRecord)
            .where(TraceEventRecord.task_id == task_id)
            .order_by(TraceEventRecord.occurred_at)
        ).all()
        return [
            {
                "id": record.id,
                "task_id": record.task_id,
                "run_id": record.run_id,
                "event_type": record.event_type,
                "occurred_at": record.occurred_at.isoformat(),
                "payload": _load(record.payload),
            }
            for record in records
        ]

    def create_run(self, run_id: str, task_id: str, strategy_name: str) -> None:
        self._session.add(
            RunRecord(id=run_id, task_id=task_id, strategy_name=strategy_name, status="running")
        )
        self._session.commit()

    def finish_run(
        self, run_id: str, *, status: str, finished_at: datetime, token_usage: dict[str, Any]
    ) -> None:
        record = self._session.get(RunRecord, run_id)
        if record is None:
            return
        record.status = status
        record.finished_at = finished_at
        record.token_usage = _dump(token_usage)
        self._session.commit()

    def create_approval(self, approval: StoredApproval) -> StoredApproval:
        self._session.add(
            ApprovalRecord(
                id=approval.id,
                task_id=approval.task_id,
                run_id=approval.run_id,
                approval_type=approval.approval_type,
                status=approval.status,
                requested_reason=approval.requested_reason,
                requested_at=approval.requested_at,
                resolved_by=approval.resolved_by,
                resolved_at=approval.resolved_at,
                resolution_reason=approval.resolution_reason,
            )
        )
        self._session.commit()
        return approval

    def update_approval(self, approval: StoredApproval) -> StoredApproval:
        record = self._session.get(ApprovalRecord, approval.id)
        if record is not None:
            record.status = approval.status
            record.resolved_by = approval.resolved_by
            record.resolved_at = approval.resolved_at
            record.resolution_reason = approval.resolution_reason
            self._session.commit()
        return approval

    def list_approvals(self, task_id: str) -> list[StoredApproval]:
        records = self._session.scalars(
            select(ApprovalRecord).where(ApprovalRecord.task_id == task_id)
        ).all()
        return [
            StoredApproval(
                id=record.id,
                task_id=record.task_id,
                run_id=record.run_id,
                approval_type=record.approval_type,
                status=record.status,
                requested_reason=record.requested_reason,
                requested_at=record.requested_at,
                resolved_by=record.resolved_by,
                resolved_at=record.resolved_at,
                resolution_reason=record.resolution_reason,
            )
            for record in records
        ]
