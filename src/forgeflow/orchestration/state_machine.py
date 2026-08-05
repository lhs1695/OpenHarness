"""ForgeFlow task state machine (docs/STATE_MACHINE.md).

Pure transition logic plus an idempotent stateful holder.  Transitions are
table-driven and never perform I/O; callers run side effects.
"""

from __future__ import annotations

from enum import Enum

from forgeflow.errors import IllegalTransitionError


class TaskState(str, Enum):
    DRAFT = "DRAFT"
    READY = "READY"
    PREPARING_ENVIRONMENT = "PREPARING_ENVIRONMENT"
    ANALYZING = "ANALYZING"
    PLANNED = "PLANNED"
    WAITING_PLAN_APPROVAL = "WAITING_PLAN_APPROVAL"
    EXECUTING = "EXECUTING"
    VERIFYING = "VERIFYING"
    REVIEWING = "REVIEWING"
    WAITING_FINAL_APPROVAL = "WAITING_FINAL_APPROVAL"
    DELIVERING = "DELIVERING"
    COMPLETED = "COMPLETED"
    PAUSED = "PAUSED"
    FAILED = "FAILED"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    CANCELLED = "CANCELLED"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"


class TaskEvent(str, Enum):
    VALIDATED = "VALIDATED"
    PREPARE_ENVIRONMENT = "PREPARE_ENVIRONMENT"
    ENVIRONMENT_READY = "ENVIRONMENT_READY"
    PLAN_GENERATED = "PLAN_GENERATED"
    APPROVAL_NEEDED = "APPROVAL_NEEDED"
    PLAN_APPROVED = "PLAN_APPROVED"
    PLAN_REJECTED = "PLAN_REJECTED"
    START_EXECUTION = "START_EXECUTION"
    EXECUTION_FINISHED = "EXECUTION_FINISHED"
    VERIFICATION_FINISHED = "VERIFICATION_FINISHED"
    REVIEW_FINISHED = "REVIEW_FINISHED"
    FINAL_APPROVED = "FINAL_APPROVED"
    FINAL_REJECTED = "FINAL_REJECTED"
    DELIVERED = "DELIVERED"
    PAUSE = "PAUSE"
    RESUME = "RESUME"
    CANCEL = "CANCEL"
    CANCEL_CONFIRMED = "CANCEL_CONFIRMED"
    FAIL = "FAIL"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"


# States that may be interrupted by PAUSE / CANCEL / FAIL / BUDGET_EXCEEDED.
_EXECUTABLE = frozenset(
    {
        TaskState.PREPARING_ENVIRONMENT,
        TaskState.ANALYZING,
        TaskState.PLANNED,
        TaskState.WAITING_PLAN_APPROVAL,
        TaskState.EXECUTING,
        TaskState.VERIFYING,
        TaskState.REVIEWING,
        TaskState.WAITING_FINAL_APPROVAL,
        TaskState.DELIVERING,
    }
)

_TRANSITIONS: dict[tuple[TaskState, TaskEvent], TaskState] = {
    (TaskState.DRAFT, TaskEvent.VALIDATED): TaskState.READY,
    (TaskState.READY, TaskEvent.PREPARE_ENVIRONMENT): TaskState.PREPARING_ENVIRONMENT,
    (TaskState.PREPARING_ENVIRONMENT, TaskEvent.ENVIRONMENT_READY): TaskState.ANALYZING,
    (TaskState.ANALYZING, TaskEvent.PLAN_GENERATED): TaskState.PLANNED,
    (TaskState.PLANNED, TaskEvent.APPROVAL_NEEDED): TaskState.WAITING_PLAN_APPROVAL,
    (TaskState.PLANNED, TaskEvent.START_EXECUTION): TaskState.EXECUTING,
    (TaskState.WAITING_PLAN_APPROVAL, TaskEvent.PLAN_APPROVED): TaskState.EXECUTING,
    (TaskState.WAITING_PLAN_APPROVAL, TaskEvent.PLAN_REJECTED): TaskState.FAILED,
    (TaskState.EXECUTING, TaskEvent.EXECUTION_FINISHED): TaskState.VERIFYING,
    (TaskState.VERIFYING, TaskEvent.VERIFICATION_FINISHED): TaskState.REVIEWING,
    (TaskState.REVIEWING, TaskEvent.APPROVAL_NEEDED): TaskState.WAITING_FINAL_APPROVAL,
    (TaskState.REVIEWING, TaskEvent.REVIEW_FINISHED): TaskState.DELIVERING,
    (TaskState.WAITING_FINAL_APPROVAL, TaskEvent.FINAL_APPROVED): TaskState.DELIVERING,
    (TaskState.WAITING_FINAL_APPROVAL, TaskEvent.FINAL_REJECTED): TaskState.FAILED,
    (TaskState.DELIVERING, TaskEvent.DELIVERED): TaskState.COMPLETED,
    (TaskState.CANCEL_REQUESTED, TaskEvent.CANCEL_CONFIRMED): TaskState.CANCELLED,
}

_INTERRUPT_RESULTS: dict[TaskEvent, TaskState] = {
    TaskEvent.PAUSE: TaskState.PAUSED,
    TaskEvent.CANCEL: TaskState.CANCEL_REQUESTED,
    TaskEvent.FAIL: TaskState.FAILED,
    TaskEvent.BUDGET_EXCEEDED: TaskState.BUDGET_EXCEEDED,
}


def transition(
    state: TaskState,
    event: TaskEvent,
    *,
    resume_target: TaskState | None = None,
) -> TaskState:
    """Return the next state for a legal transition; raise otherwise."""
    if event == TaskEvent.RESUME:
        if state != TaskState.PAUSED:
            raise IllegalTransitionError(
                f"{state.value} --RESUME--> ?（只能从 PAUSED 恢复）"
            )
        if resume_target is None:
            raise IllegalTransitionError("恢复需要指定 resume_target")
        if resume_target not in _EXECUTABLE:
            raise IllegalTransitionError(
                f"resume_target={resume_target.value} 不是可执行状态"
            )
        return resume_target
    key = (state, event)
    if key in _TRANSITIONS:
        return _TRANSITIONS[key]
    if state in _EXECUTABLE and event in _INTERRUPT_RESULTS:
        return _INTERRUPT_RESULTS[event]
    raise IllegalTransitionError(f"非法转移：{state.value} --{event.value}--> ?")


class TaskStateMachine:
    """Stateful task state machine with idempotent event application."""

    def __init__(self, initial: TaskState = TaskState.DRAFT) -> None:
        self._state = initial
        self._last: tuple[TaskState, TaskEvent, TaskState] | None = None

    @property
    def state(self) -> TaskState:
        return self._state

    def apply(
        self, event: TaskEvent, *, resume_target: TaskState | None = None
    ) -> TaskState:
        """Apply an event; a repeated identical event is an idempotent no-op."""
        previous = self._state
        if (
            self._last is not None
            and self._last[1] == event
            and self._last[2] == previous
        ):
            return previous
        next_state = transition(previous, event, resume_target=resume_target)
        self._state = next_state
        self._last = (previous, event, next_state)
        return next_state
