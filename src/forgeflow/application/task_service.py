"""Task service — lifecycle, idempotent commands, SSE wiring, persistence."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import uuid4

from forgeflow.application.event_bus import EventBus
from forgeflow.application.event_bus import TaskEvent as BusEvent
from forgeflow.application.task_orchestrator import TaskOrchestrator
from forgeflow.domain.approval import ApprovalManager, ApprovalResolution
from forgeflow.domain.policy import RepositoryPolicy
from forgeflow.domain.risk import RiskInputs, RiskScorer

# Tags that hint a change is schema/migration or public-API related (P0-3).
_SCHEMA_TAGS = frozenset({"migration", "schema", "ddl", "db", "database"})
_PUBLIC_API_TAGS = frozenset({"api", "public_api", "interface", "contract", "compat"})


def _risk_inputs_from_spec(spec: CreateTaskInput) -> RiskInputs:
    """Derive pre-execution risk facts from the task definition (P0-3).

    Without this, creation-time risk was always 0 because the rules only saw an
    empty ``RiskInputs`` — the approval/risk gating was effectively disabled.
    Execution-time facts (changed paths) still need the executor's feedback.
    """
    tags = {tag.strip().lower() for tag in spec.risk_tags}
    is_docs_or_tests = spec.task_type in ("docs", "test")
    criteria_text = " ".join(spec.acceptance_criteria).lower()
    has_test_hint = "test" in criteria_text or "pytest" in criteria_text or "测试" in criteria_text
    return RiskInputs(
        has_schema_or_migration_change=bool(tags & _SCHEMA_TAGS),
        has_public_api_change=bool(tags & _PUBLIC_API_TAGS),
        missing_tests=not is_docs_or_tests and spec.task_type != "verify" and not has_test_hint,
        is_docs_or_tests_only=is_docs_or_tests,
    )
from forgeflow.errors import ForgeFlowError
from forgeflow.infrastructure.store import StoredApproval, StoredTask, TaskStore, to_stored_approval
from forgeflow.orchestration.state_machine import TaskEvent, TaskState, TaskStateMachine
from forgeflow.trace.repository import TraceRepository


class TaskNotFoundError(ForgeFlowError):
    pass


def _utcnow() -> datetime:
    return datetime.now(UTC)


def reload_approvals_from_store(approvals: ApprovalManager, store: TaskStore) -> None:
    """Hydrate the in-memory ApprovalManager from persisted approvals (P0-2).

    Call after building the service so already-requested/approved approvals
    survive a restart; otherwise tasks waiting at an approval gate would be
    stranded because the manager starts empty.
    """
    from forgeflow.infrastructure.store import from_stored_approval

    approvals.reload([from_stored_approval(record) for record in store.list_all_approvals()])


@dataclass(frozen=True)
class CreateTaskInput:
    repository: str
    title: str
    description: str = ""
    task_type: str = "bugfix"
    priority: str = "P2"
    acceptance_criteria: list[str] = field(default_factory=list)
    risk_tags: list[str] = field(default_factory=list)
    requested_by: str = ""
    task_id: str | None = None
    initial_risk_score: int | None = None


class TaskService:
    """Creates, starts, queries, cancels tasks; idempotent command handling."""

    def __init__(
        self,
        *,
        store: TaskStore,
        event_bus: EventBus,
        orchestrator: TaskOrchestrator,
        approvals: ApprovalManager,
        policy_provider: PolicyProvider,
    ) -> None:
        self._store = store
        self._event_bus = event_bus
        self._orchestrator = orchestrator
        self._approvals = approvals
        self._policy_provider = policy_provider

    def create_task(self, spec: CreateTaskInput) -> StoredTask:
        policy = self._policy_provider.get(spec.repository)
        risk = (
            spec.initial_risk_score
            if spec.initial_risk_score is not None
            else RiskScorer().score(_risk_inputs_from_spec(spec), policy).score
        )
        task = StoredTask(
            id=spec.task_id or f"task_{uuid4().hex[:8]}",
            repository=spec.repository,
            title=spec.title,
            description=spec.description,
            task_type=spec.task_type,
            priority=spec.priority,
            acceptance_criteria=list(spec.acceptance_criteria),
            risk_tags=list(spec.risk_tags),
            status=TaskState.DRAFT.value,
            initial_risk_score=risk,
            final_risk_score=None,
            requested_by=spec.requested_by,
            created_at=_utcnow(),
            updated_at=_utcnow(),
        )
        self._store.create_task(task)
        self._store.append_event(
            task_id=task.id,
            run_id="",
            event_type="task_created",
            payload={"repository": task.repository, "risk": risk},
            event_id=uuid4().hex,
            occurred_at=task.created_at,
        )
        self._emit(task.id, "task_created", {"repository": task.repository, "risk": risk})
        return task

    def get_task(self, task_id: str) -> StoredTask:
        task = self._store.get_task(task_id)
        if task is None:
            raise TaskNotFoundError(task_id)
        return task

    def list_tasks(self, *, requested_by: str | None = None) -> list[StoredTask]:
        """List tasks, optionally filtered to one owner (PHASE3 B4)."""
        tasks = self._store.list_tasks()
        if requested_by:
            tasks = [task for task in tasks if task.requested_by == requested_by]
        return tasks

    def start_task(self, task_id: str, *, command_id: str | None = None) -> StoredTask:
        self.start_task_message(task_id, command_id=command_id)
        return self.get_task(task_id)

    def start_task_message(self, task_id: str, *, command_id: str | None = None) -> None:
        """Start a task. Idempotent under repeated command_id (Celery re-delivery).

        Dedup is persisted (P2-9) so a re-delivered command id after a restart is
        still a no-op.
        """
        self.get_task(task_id)
        if command_id:
            if self._store.is_processed(command_id):
                return  # idempotent no-op
            self._store.mark_processed(command_id)
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            self._orchestrator.run_sync(task_id)  # worker context: run on a fresh loop
        else:
            self._orchestrator.start(task_id)  # API context: schedule async

    def cancel_task(self, task_id: str, *, command_id: str | None = None) -> StoredTask:
        task = self.get_task(task_id)
        if command_id:
            if self._store.is_processed(command_id):
                return task
            self._store.mark_processed(command_id)
        self._orchestrator.cancel(task_id)
        return self.get_task(task_id)

    def pause_task(self, task_id: str) -> StoredTask:
        stored = self.get_task(task_id)
        machine = TaskStateMachine(TaskState(stored.status))
        self._apply_transition(stored, machine, TaskEvent.PAUSE)
        return self.get_task(task_id)

    def resume_task(self, task_id: str) -> StoredTask:
        stored = self.get_task(task_id)
        machine = TaskStateMachine(TaskState(stored.status))
        if machine.state is TaskState.PAUSED:
            # Restart semantics: the executor's worktree is cleaned up on pause,
            # so a resumed task re-runs the pipeline from READY (P1-4).
            self._apply_transition(stored, machine, TaskEvent.RESUME, resume_target=TaskState.READY)
            self._orchestrator.resume(task_id)
        return self.get_task(task_id)

    def approve(self, approval_id: str, *, approved: bool, resolved_by: str, reason: str | None = None) -> ApprovalResolution:
        approval = self._approvals.get(approval_id)
        task_id = approval.task_id
        resolution = self._approvals.resolve(
            approval_id, approved=approved, resolved_by=resolved_by, reason=reason
        )
        self._store.update_approval(to_stored_approval(self._approvals.get(approval_id)))
        self._event_bus.publish(
            task_id, "approval_resolved", {"approval_id": approval_id, "approved": approved}
        )
        if approved:
            self._orchestrator.resume(task_id)
        return resolution

    def approvals_for(self, task_id: str) -> list[StoredApproval]:
        return self._store.list_approvals(task_id)

    def subscribe(self, task_id: str) -> asyncio.Queue[BusEvent]:
        return self._event_bus.subscribe(task_id)

    def unsubscribe(self, task_id: str, queue: asyncio.Queue[BusEvent]) -> None:
        self._event_bus.unsubscribe(task_id, queue)

    def publish_event(self, task_id: str, event_type: str, payload: dict[str, object]) -> None:
        self._event_bus.publish(task_id, event_type, payload)

    def list_events(self, task_id: str) -> list[dict[str, object]]:
        return self._store.list_events(task_id)

    def trace_timeline(self, task_id: str) -> list[dict[str, object]]:
        self.get_task(task_id)
        return TraceRepository(self._store).timeline(task_id)

    def export_trace_jsonl(self, task_id: str) -> str:
        self.get_task(task_id)
        return TraceRepository(self._store).export_jsonl(task_id)

    def _apply_transition(
        self,
        stored: StoredTask,
        machine: TaskStateMachine,
        event: TaskEvent,
        *,
        resume_target: TaskState | None = None,
    ) -> None:
        previous = machine.state
        try:
            machine.apply(event, resume_target=resume_target)
        except ForgeFlowError:
            # Rejected user-driven transition is recorded, not silently ignored (P1-7).
            self._event_bus.publish(
                stored.id,
                "illegal_transition",
                {"from": previous.value, "event": event.value},
            )
            return
        self._event_bus.publish(
            stored.id,
            "task_state_changed",
            {"from": previous.value, "to": machine.state.value, "event": event.value},
        )
        self._store.update_task(stored.id, status=machine.state.value)

    def _emit(self, task_id: str, event_type: str, payload: dict[str, object]) -> None:
        self._event_bus.publish(task_id, event_type, payload)


class PolicyProvider:
    """Resolves a RepositoryPolicy for a repository (defaults to a blank policy)."""

    def __init__(self, policies: dict[str, RepositoryPolicy] | None = None) -> None:
        self._policies = dict(policies or {})

    def get(self, repository: str) -> RepositoryPolicy:
        return self._policies.get(repository, RepositoryPolicy(repository=repository))

    def for_repository(self, repository: str) -> RepositoryPolicy:
        """Alias of :meth:`get` (PHASE3 B3 naming)."""
        return self.get(repository)

    def repositories(self) -> list[str]:
        return list(self._policies)
