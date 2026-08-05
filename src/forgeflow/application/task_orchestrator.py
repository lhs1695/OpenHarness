"""Task orchestrator — drives the state machine, persists transitions, emits events.

The actual step work is delegated to an injected ``TaskExecutor``.  The
pipeline is resumable: it always starts from the task's persisted state and
skips already-completed transitions (state machine idempotency).
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from forgeflow.application.event_bus import EventBus
from forgeflow.application.executors import (
    ExecutionOutcome,
    TaskExecutor,
    _changed_files_from_diff,
)
from forgeflow.domain.approval import (
    ApprovalManager,
    ApprovalRequiredError,
    ApprovalStatus,
    ApprovalType,
    approval_requirements,
)
from forgeflow.domain.policy import RepositoryPolicy
from forgeflow.domain.risk import RiskInputs, RiskLevel, RiskScorer, risk_level
from forgeflow.errors import IllegalTransitionError
from forgeflow.infrastructure.store import StoredTask, TaskStore, to_stored_approval
from forgeflow.orchestration.delivery import Patch, make_patch
from forgeflow.orchestration.state_machine import TaskEvent, TaskState, TaskStateMachine
from forgeflow.quality.gates import _is_test_file
from forgeflow.trace.collector import TraceCollector
from forgeflow.trace.repository import TraceRepository

if TYPE_CHECKING:
    from forgeflow.orchestration.delivery import DeliveryService

_DOC_SUFFIXES = (".md", ".rst", ".txt", ".ipynb")
_SQL_SUFFIX = ".sql"


def _is_doc_file(path: str) -> bool:
    normalized = path.replace("\\", "/")
    return normalized.endswith(_DOC_SUFFIXES) or normalized.startswith("docs/")


def _is_migration_file(path: str) -> bool:
    normalized = path.replace("\\", "/")
    if normalized.endswith(_SQL_SUFFIX):
        return True
    segments = normalized.split("/")
    return any(segment in ("migrations", "alembic", "schema", "migration") for segment in segments)


def _is_public_api_file(path: str) -> bool:
    segments = path.replace("\\", "/").split("/")
    return any(segment in ("api", "public", "contracts") for segment in segments)


def _risk_inputs_from_changes(
    changed_files: list[str],
    *,
    agent_failures: int = 0,
    reviewer_high_risk: int = 0,
) -> RiskInputs:
    """Derive post-execution risk facts from the actual changed files (收尾2).

    Heuristics: schema/migration paths (+25), public-API paths (+15),
    docs/tests-only (-10), code change without a test file (+15 missing tests),
    plus agent failures and reviewer blockers surfaced by the executor.
    """
    has_tests = any(_is_test_file(path) for path in changed_files)
    non_test_code = [
        path for path in changed_files if not _is_test_file(path) and not _is_doc_file(path)
    ]
    return RiskInputs(
        changed_paths=tuple(changed_files),
        has_schema_or_migration_change=any(_is_migration_file(path) for path in changed_files),
        has_public_api_change=any(_is_public_api_file(path) for path in changed_files),
        is_docs_or_tests_only=bool(changed_files) and not non_test_code,
        missing_tests=bool(non_test_code) and not has_tests,
        agent_failures=agent_failures,
        reviewer_high_risk_findings=reviewer_high_risk,
    )


class TaskOrchestrator:
    def __init__(
        self,
        *,
        store: TaskStore,
        event_bus: EventBus,
        executor: TaskExecutor,
        approvals: ApprovalManager,
        delivery: DeliveryService | None = None,
        policy_resolver: Callable[[str], RepositoryPolicy] | None = None,
    ) -> None:
        self._store = store
        self._event_bus = event_bus
        self._executor = executor
        self._approvals = approvals
        self._delivery = delivery
        self._policy_resolver = policy_resolver or (lambda name: RepositoryPolicy(repository=name))
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

        # Pipeline to PLANNED (idempotent skips let this resume from any point).
        self._advance(stored, machine, TaskEvent.VALIDATED)
        self._advance(stored, machine, TaskEvent.PREPARE_ENVIRONMENT)
        self._advance(stored, machine, TaskEvent.ENVIRONMENT_READY)
        self._advance(stored, machine, TaskEvent.PLAN_GENERATED)

        risk = risk_level(stored.initial_risk_score)
        required = approval_requirements(risk)

        # P0-1: SEVERE risk only produces a plan — never executes writes (§4.4).
        if risk is RiskLevel.SEVERE:
            self._event_bus.publish(
                stored.id,
                "severe_blocked",
                {"reason": "SEVERE 风险任务只允许生成方案，禁止执行写操作"},
            )
            self._advance(stored, machine, TaskEvent.FAIL)
            self._persist(stored, machine)
            self._persist_trace(task_id, run_id)
            return

        # Plan-approval gate (HIGH). Only PLAN is required here.
        if ApprovalType.PLAN in required:
            if not self._type_approved(stored, ApprovalType.PLAN):
                self._request_approvals(stored, [ApprovalType.PLAN])
                self._advance(stored, machine, TaskEvent.APPROVAL_NEEDED)
                self._persist(stored, machine)
                self._persist_trace(task_id, run_id)
                return  # waits at WAITING_PLAN_APPROVAL
            if machine.state is TaskState.WAITING_PLAN_APPROVAL:
                self._advance(stored, machine, TaskEvent.PLAN_APPROVED)

        # Execute exactly once — resume after final approval must not re-run it.
        if machine.state in (TaskState.PLANNED, TaskState.EXECUTING):
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
                self._persist(stored, machine)
                self._persist_trace(task_id, run_id)
                return
            if outcome.status == "budget_exceeded":
                self._advance(stored, machine, TaskEvent.BUDGET_EXCEEDED)
                self._persist(stored, machine)
                self._persist_trace(task_id, run_id)
                return
            self._record_final_risk(stored, outcome)
            self._advance(stored, machine, TaskEvent.EXECUTION_FINISHED)
            self._advance(stored, machine, TaskEvent.VERIFICATION_FINISHED)
            if outcome.patch is not None:
                self._persist_patch(task_id, run_id, outcome.patch)

        # Final-approval gate (MEDIUM/HIGH) after review (P1-5 两阶段).
        if ApprovalType.FINAL in required and machine.state in (
            TaskState.REVIEWING,
            TaskState.WAITING_FINAL_APPROVAL,
        ):
            if not self._type_approved(stored, ApprovalType.FINAL):
                self._request_approvals(stored, [ApprovalType.FINAL])
                self._advance(stored, machine, TaskEvent.APPROVAL_NEEDED)
                self._persist(stored, machine)
                self._persist_trace(task_id, run_id)
                return  # waits at WAITING_FINAL_APPROVAL
            if machine.state is TaskState.WAITING_FINAL_APPROVAL:
                self._advance(stored, machine, TaskEvent.FINAL_APPROVED)

        # Deliver.
        if machine.state in (TaskState.REVIEWING, TaskState.DELIVERING):
            self._advance(stored, machine, TaskEvent.REVIEW_FINISHED)
            self._advance(stored, machine, TaskEvent.DELIVERED)
            self._deliver(stored)
        self._persist(stored, machine)
        self._persist_trace(task_id, run_id)

    def _record_final_risk(self, stored: StoredTask, outcome: ExecutionOutcome) -> None:
        """Recompute risk from the actual changed files and persist it (收尾2)."""
        if not outcome.changed_files:
            return
        policy = self._policy_resolver(stored.repository)
        inputs = _risk_inputs_from_changes(
            outcome.changed_files,
            agent_failures=outcome.agent_failures,
            reviewer_high_risk=outcome.reviewer_high_risk_findings,
        )
        final = RiskScorer().score(inputs, policy)
        self._store.update_task(stored.id, final_risk_score=final.score)

    def _type_approved(self, stored: StoredTask, approval_type: ApprovalType) -> bool:
        candidates = [
            approval
            for approval in self._approvals.approvals_for(stored.id)
            if approval.approval_type is approval_type
        ]
        return bool(candidates) and all(
            approval.status is ApprovalStatus.APPROVED for approval in candidates
        )

    def _persist_patch(self, task_id: str, run_id: str, patch: Patch) -> None:
        """Persist the delivery diff so it survives the final-approval resume (P1-5)."""
        self._store.append_event(
            task_id=task_id,
            run_id=run_id,
            event_type="patch_ready",
            payload={"repository": patch.repository, "diff": patch.diff},
            event_id=uuid4().hex,
            occurred_at=datetime.now(UTC),
        )

    def _stored_diff(self, task_id: str) -> str:
        for item in self._store.list_events(task_id):
            if item["event_type"] == "patch_ready":
                payload = item.get("payload")
                diff = payload.get("diff") if isinstance(payload, dict) else None
                if isinstance(diff, str):
                    return diff
        return ""

    def _deliver(self, stored: StoredTask) -> None:
        """Submit a real Draft PR when a delivery service and a real diff exist (B1).

        Delivery failures are recorded as trace events, never crash the pipeline.
        """
        if self._delivery is None:
            return
        diff = self._stored_diff(stored.id)
        if not diff:
            return
        patch = make_patch(
            repository=stored.repository,
            diff=diff,
            changed_files=_changed_files_from_diff(diff),
        )
        try:
            pr = self._delivery.create_draft_pr(
                repository=stored.repository,
                patch=patch,
                head=f"forgeflow/{stored.id}",
            )
        except Exception as exc:  # noqa: BLE001 — delivery is best-effort
            if self._collector is not None:
                self._collector.on_task_event("delivery_failed", {"error": str(exc)})
            return
        if self._collector is not None:
            self._collector.on_task_event("draft_pr_created", {"url": pr.url or ""})

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
