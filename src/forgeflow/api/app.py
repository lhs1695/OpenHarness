"""FastAPI application (spec §9)."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse

from forgeflow.api.schemas import ApprovalResolveRequest, CreateTaskRequest, TaskView
from forgeflow.application.task_service import CreateTaskInput, TaskNotFoundError, TaskService
from forgeflow.infrastructure.store import StoredTask


def build_app(service: TaskService) -> FastAPI:
    app = FastAPI(title="ForgeFlow", version="0.1.0")

    def _get(task_id: str) -> StoredTask:
        try:
            return service.get_task(task_id)
        except TaskNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/v1/tasks", response_model=TaskView)
    def create_task(request: CreateTaskRequest) -> TaskView:
        task = service.create_task(
            CreateTaskInput(
                repository=request.repository,
                title=request.title,
                description=request.description,
                task_type=request.task_type,
                priority=request.priority,
                acceptance_criteria=list(request.acceptance_criteria),
                risk_tags=list(request.risk_tags),
                requested_by=request.requested_by,
                initial_risk_score=request.initial_risk_score,
            )
        )
        return TaskView.from_stored(task)

    @app.get("/api/v1/tasks", response_model=list[TaskView])
    def list_tasks() -> list[TaskView]:
        return [TaskView.from_stored(task) for task in service.list_tasks()]

    @app.get("/api/v1/tasks/{task_id}", response_model=TaskView)
    def get_task(task_id: str) -> TaskView:
        return TaskView.from_stored(_get(task_id))

    @app.post("/api/v1/tasks/{task_id}/start", response_model=TaskView)
    async def start_task(task_id: str, command_id: str | None = None) -> TaskView:
        return TaskView.from_stored(service.start_task(task_id, command_id=command_id))

    @app.post("/api/v1/tasks/{task_id}/pause", response_model=TaskView)
    async def pause_task(task_id: str) -> TaskView:
        return TaskView.from_stored(service.pause_task(task_id))

    @app.post("/api/v1/tasks/{task_id}/resume", response_model=TaskView)
    async def resume_task(task_id: str) -> TaskView:
        return TaskView.from_stored(service.resume_task(task_id))

    @app.post("/api/v1/tasks/{task_id}/cancel", response_model=TaskView)
    async def cancel_task(task_id: str) -> TaskView:
        return TaskView.from_stored(service.cancel_task(task_id))

    @app.get("/api/v1/tasks/{task_id}/approvals")
    def list_approvals(task_id: str) -> list[dict[str, object]]:
        _get(task_id)
        return [
            {
                "id": approval.id,
                "task_id": approval.task_id,
                "approval_type": approval.approval_type,
                "status": approval.status,
                "requested_reason": approval.requested_reason,
            }
            for approval in service.approvals_for(task_id)
        ]

    @app.post("/api/v1/approvals/{approval_id}/approve")
    async def approve(approval_id: str, request: ApprovalResolveRequest) -> dict[str, object]:
        resolution = service.approve(
            approval_id,
            approved=request.approved,
            resolved_by=request.resolved_by,
            reason=request.reason,
        )
        return {
            "approval_id": resolution.approval_id,
            "approved": resolution.approved,
            "resolved_by": resolution.resolved_by,
            "resolved_at": resolution.resolved_at,
        }

    @app.post("/api/v1/approvals/{approval_id}/reject")
    async def reject(approval_id: str, request: ApprovalResolveRequest) -> dict[str, object]:
        return await approve(
            approval_id, ApprovalResolveRequest(approved=False, **request.model_dump(exclude={"approved"}))
        )

    @app.get("/api/v1/tasks/{task_id}/timeline")
    def task_timeline(task_id: str) -> list[dict[str, object]]:
        return service.trace_timeline(task_id)

    @app.get("/api/v1/tasks/{task_id}/trace")
    def task_trace(task_id: str) -> str:
        return service.export_trace_jsonl(task_id)

    @app.get("/api/v1/tasks/{task_id}/events")
    async def task_events(task_id: str) -> StreamingResponse:
        _get(task_id)
        queue = service.subscribe(task_id)

        async def event_stream() -> AsyncIterator[str]:
            try:
                while True:
                    try:
                        event = await asyncio.wait_for(queue.get(), timeout=15.0)
                    except TimeoutError:
                        yield "event: heartbeat\ndata: {}\n\n"
                        continue
                    data = json.dumps(
                        {
                            "task_id": event.task_id,
                            "type": event.event_type,
                            "occurred_at": event.occurred_at,
                            "payload": event.payload,
                        }
                    )
                    yield f"event: {event.event_type}\ndata: {data}\n\n"
            finally:
                service.unsubscribe(task_id, queue)

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    return app
