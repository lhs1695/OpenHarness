"""API request/response schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field

from forgeflow.infrastructure.store import StoredTask


class CreateTaskRequest(BaseModel):
    repository: str
    title: str
    description: str = ""
    task_type: str = "bugfix"
    priority: str = "P2"
    acceptance_criteria: list[str] = Field(default_factory=list)
    risk_tags: list[str] = Field(default_factory=list)
    requested_by: str = ""
    initial_risk_score: int | None = None


class TaskView(BaseModel):
    id: str
    repository: str
    title: str
    description: str
    task_type: str
    priority: str
    status: str
    initial_risk_score: int
    final_risk_score: int | None
    requested_by: str
    created_at: str
    updated_at: str

    @classmethod
    def from_stored(cls, task: StoredTask) -> TaskView:
        return cls(
            id=task.id,
            repository=task.repository,
            title=task.title,
            description=task.description,
            task_type=task.task_type,
            priority=task.priority,
            status=task.status,
            initial_risk_score=task.initial_risk_score,
            final_risk_score=task.final_risk_score,
            requested_by=task.requested_by,
            created_at=task.created_at.isoformat(),
            updated_at=task.updated_at.isoformat(),
        )


class ApprovalResolveRequest(BaseModel):
    approved: bool
    resolved_by: str
    reason: str | None = None
