"""SQLAlchemy ORM models for ForgeFlow persistence (restart recovery)."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from forgeflow.infrastructure.database import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class TaskRecord(Base):
    __tablename__ = "forgeflow_tasks"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    repository: Mapped[str] = mapped_column(String(255))
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    task_type: Mapped[str] = mapped_column(String(32), default="bugfix")
    priority: Mapped[str] = mapped_column(String(8), default="P2")
    acceptance_criteria: Mapped[str] = mapped_column(Text, default="[]")
    risk_tags: Mapped[str] = mapped_column(Text, default="[]")
    status: Mapped[str] = mapped_column(String(32), default="DRAFT")
    initial_risk_score: Mapped[int] = mapped_column(Integer, default=0)
    final_risk_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    requested_by: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)


class RunRecord(Base):
    __tablename__ = "forgeflow_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    task_id: Mapped[str] = mapped_column(String(64), index=True)
    strategy_name: Mapped[str] = mapped_column(String(128), default="default")
    status: Mapped[str] = mapped_column(String(32), default="running")
    started_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    token_usage: Mapped[str] = mapped_column(Text, default="{}")


class TraceEventRecord(Base):
    __tablename__ = "forgeflow_trace_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    task_id: Mapped[str] = mapped_column(String(64), index=True)
    run_id: Mapped[str] = mapped_column(String(64), default="")
    event_type: Mapped[str] = mapped_column(String(64))
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    payload: Mapped[str] = mapped_column(Text, default="{}")


class ApprovalRecord(Base):
    __tablename__ = "forgeflow_approvals"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    task_id: Mapped[str] = mapped_column(String(64), index=True)
    run_id: Mapped[str] = mapped_column(String(64), default="")
    approval_type: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), default="pending")
    requested_reason: Mapped[str] = mapped_column(Text, default="")
    requested_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    resolved_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    resolution_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
