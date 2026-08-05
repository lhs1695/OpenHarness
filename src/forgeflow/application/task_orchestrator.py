"""Task orchestrator — drives the state machine, persists transitions, emits events.

The actual step work is delegated to an injected ``TaskExecutor``.  The
pipeline is resumable: it always starts from the task's persisted state and
skips already-completed transitions (state machine idempotency).
"""

from __future__ import annotations

import asyncio

from forgeflow.application.event_bus import EventBus
from forgeflow.application.executors import ExecutionOutcome, TaskExecutor
from forgeflow.domain.approval import (
    ApprovalManager,
    ApprovalRequiredError,
    ApprovalType,
    approval_requirements,
)
from forgeflow.domain.risk import RiskLevel, risk_level
from forgeflow.errors import IllegalTransitionError
from forgeflow.infrastructure.store import StoredTask, TaskStore, to_stored_approval
from forgeflow.orchestration.state_machine import TaskEvent, TaskState, TaskStateMachine
from forgeflow.trace.collector import TraceCollector
from forgeflow.trace.repository import TraceRepository


class TaskOrchestrator:
    def __init__(
        self,
        *,
        store: TaskStore,
        event_bus: EventBus,
        executor: TaskExecutor,
        approvals: ApprovalManager,
    ) -> None:
        self._store = store
        self._event_bus = event_bus
        self._executor = executor
        self._approvals = approvals
        self._running: dict[str, asyncio.Task[None]] = {}
        self._collector: TraceCollector | None = None

    def start(self, task_id: str) -> None:
        task = asyncio.create_task(self._run(task_id))
        self._running[task_id] = task
        task.add_done_callback(lambda _: self._running.pop(task_id, None))

    def resume(self, task_id: str) -> None:
        self.start(task_id)

    def run_sync(self, task_id: str) -> None:
        """Run the pipeline to completion on a fresh loop (Celery worker context)."""
        asyncio.run(self._run(task_id))

    def cancel(self, task_id: str) -> None:
        stored = self._store.get_task(task_id)
        if stored is None:
            return
        running = self._running.get(task_id)
        machine = TaskStateMachine(TaskState(stored.status))
        if running is not None and not running.done():
            running.cancel()
            self._advance(stored, machine, TaskEvent.CANCEL)
            self._persist(stored, machine)
            return
        self._advance(stored, machine, TaskEvent.CANCEL)
        self._advance(stored, machine, TaskEvent.CANCEL_CONFIRMED)
        self._persist(stored, machine)

    async def _run(self, task_id: str) -> None:
        stored = self._store.get_task(task_id)
        if stored is None:
            return
        run_id = f"run_{task_id}"
        self._collector = TraceCollector(task_id=task_id, run_id=run_id)
        machine = TaskStateMachine(TaskState(stored.status))
        self._advance(stored, machine, TaskEvent.VALIDATED)
        self._advance(stored, machine, TaskEvent.PREPARE_ENVIRONMENT)
        self._advance(stored, machine, TaskEvent.ENVIRONMENT_READY)
        self._advance(stored, machine, TaskEvent.PLAN_GENERATED)

        risk = risk_level(stored.initial_risk_score)
        if approval_requirements(risk):
            if not self._approvals_complete(stored, risk):
                self._request_approvals(stored, approval_requirements(risk))
                self._advance(stored, machine, TaskEvent.APPROVAL_NEEDED)
                self._persist(stored, machine)
                self._persist_trace(task_id, run_id)
                return  # paused at WAITING_PLAN_APPROVAL until approvals resolve
            if machine.state is TaskState.WAITING_PLAN_APPROVAL:
                self._advance(stored, machine, TaskEvent.PLAN_APPROVED)
        self._advance(stored, machine, TaskEvent.START_EXECUTION)

        try:
            outcome = await self._executor.execute(stored)
        except asyncio.CancelledError:
            self._advance(stored, machine, TaskEvent.CANCEL)
            self._advance(stored, machine, TaskEvent.CANCEL_CONFIRMED)
            self._persist(stored, machine)
            self._persist_trace(task_id, run_id)
            raise
        self._record_commands(outcome)
        if outcome.status == "failed":
            self._advance(stored, machine, TaskEvent.FAIL)
        elif outcome.status == "budget_exceeded":
            self._advance(stored, machine, TaskEvent.BUDGET_EXCEEDED)
        else:
            self._advance(stored, machine, TaskEvent.EXECUTION_FINISHED)
            self._advance(stored, machine, TaskEvent.VERIFICATION_FINISHED)
            self._advance(stored, machine, TaskEvent.REVIEW_FINISHED)
            self._advance(stored, machine, TaskEvent.DELIVERED)
        self._persist(stored, machine)
        self._persist_trace(task_id, run_id)

    def _advance(self, stored: StoredTask, machine: TaskStateMachine, event: TaskEvent) -> None:
        previous = machine.state
        try:
            machine.apply(event)
        except IllegalTransitionError:
            return  # already past this transition (resumable pipeline)
        payload = {"from": previous.value, "to": machine.state.value, "event": event.value}
        self._event_bus.publish(stored.id, "task_state_changed", payload)
        self._store.update_task(stored.id, status=machine.state.value)
        if self._collector is not None:
            self._collector.on_task_event("task_state_changed", payload)

    def _record_commands(self, outcome: ExecutionOutcome) -> None:
        if self._collector is None:
            return
        for result in outcome.command_results.values():
            self._collector.on_command(
                command=result.command,
                returncode=result.returncode,
                duration_ms=result.duration_ms,
                output=result.stdout,
            )

    def _persist_trace(self, task_id: str, run_id: str) -> None:
        if self._collector is None:
            return
        TraceRepository(self._store).save_events(
            task_id=task_id, run_id=run_id, events=self._collector.events()
        )
        self._collector = None

    def _persist(self, stored: StoredTask, machine: TaskStateMachine) -> None:
        self._store.update_task(stored.id, status=machine.state.value)

    def _approvals_complete(self, stored: StoredTask, risk: RiskLevel) -> bool:
        try:
            self._approvals.assert_approvals_complete(stored.id, risk)
            return True
        except ApprovalRequiredError:
            return False

    def _request_approvals(self, stored: StoredTask, required: list[ApprovalType]) -> None:
        existing = self._approvals.approvals_for(stored.id)
        for approval_type in required:
            if not any(a.approval_type is approval_type for a in existing):
                approval = self._approvals.request(
                    task_id=stored.id,
                    approval_type=approval_type,
                    reason=f"{approval_type.value} approval for task {stored.id}",
                )
                self._store.create_approval(to_stored_approval(approval))
