"""State machine tests — normal, approval, cancel, pause/resume, illegal, idempotent."""

import pytest

from forgeflow.errors import IllegalTransitionError
from forgeflow.orchestration.state_machine import TaskEvent, TaskState, TaskStateMachine, transition


def test_happy_path_full_sequence() -> None:
    machine = TaskStateMachine()
    for event, expected in (
        (TaskEvent.VALIDATED, TaskState.READY),
        (TaskEvent.PREPARE_ENVIRONMENT, TaskState.PREPARING_ENVIRONMENT),
        (TaskEvent.ENVIRONMENT_READY, TaskState.ANALYZING),
        (TaskEvent.PLAN_GENERATED, TaskState.PLANNED),
        (TaskEvent.START_EXECUTION, TaskState.EXECUTING),
        (TaskEvent.EXECUTION_FINISHED, TaskState.VERIFYING),
        (TaskEvent.VERIFICATION_FINISHED, TaskState.REVIEWING),
        (TaskEvent.REVIEW_FINISHED, TaskState.DELIVERING),
        (TaskEvent.DELIVERED, TaskState.COMPLETED),
    ):
        assert machine.apply(event) is expected


def test_plan_approval_branch() -> None:
    machine = TaskStateMachine()
    machine.apply(TaskEvent.VALIDATED)
    machine.apply(TaskEvent.PREPARE_ENVIRONMENT)
    machine.apply(TaskEvent.ENVIRONMENT_READY)
    machine.apply(TaskEvent.PLAN_GENERATED)
    machine.apply(TaskEvent.APPROVAL_NEEDED)
    assert machine.state is TaskState.WAITING_PLAN_APPROVAL
    machine.apply(TaskEvent.PLAN_APPROVED)
    assert machine.state is TaskState.EXECUTING


def test_plan_rejected_fails_task() -> None:
    machine = TaskStateMachine()
    for event in (
        TaskEvent.VALIDATED,
        TaskEvent.PREPARE_ENVIRONMENT,
        TaskEvent.ENVIRONMENT_READY,
        TaskEvent.PLAN_GENERATED,
        TaskEvent.APPROVAL_NEEDED,
        TaskEvent.PLAN_REJECTED,
    ):
        machine.apply(event)
    assert machine.state is TaskState.FAILED


def test_final_approval_branch() -> None:
    machine = TaskStateMachine()
    for event in (
        TaskEvent.VALIDATED,
        TaskEvent.PREPARE_ENVIRONMENT,
        TaskEvent.ENVIRONMENT_READY,
        TaskEvent.PLAN_GENERATED,
        TaskEvent.START_EXECUTION,
        TaskEvent.EXECUTION_FINISHED,
        TaskEvent.VERIFICATION_FINISHED,
        TaskEvent.APPROVAL_NEEDED,
    ):
        machine.apply(event)
    assert machine.state is TaskState.WAITING_FINAL_APPROVAL
    machine.apply(TaskEvent.FINAL_APPROVED)
    assert machine.state is TaskState.DELIVERING
    machine.apply(TaskEvent.DELIVERED)
    assert machine.state is TaskState.COMPLETED


def test_final_rejected_fails_task() -> None:
    machine = TaskStateMachine()
    for event in (
        TaskEvent.VALIDATED,
        TaskEvent.PREPARE_ENVIRONMENT,
        TaskEvent.ENVIRONMENT_READY,
        TaskEvent.PLAN_GENERATED,
        TaskEvent.START_EXECUTION,
        TaskEvent.EXECUTION_FINISHED,
        TaskEvent.VERIFICATION_FINISHED,
        TaskEvent.APPROVAL_NEEDED,
        TaskEvent.FINAL_REJECTED,
    ):
        machine.apply(event)
    assert machine.state is TaskState.FAILED


def test_cancel_from_executing() -> None:
    machine = TaskStateMachine()
    for event in (
        TaskEvent.VALIDATED,
        TaskEvent.PREPARE_ENVIRONMENT,
        TaskEvent.ENVIRONMENT_READY,
        TaskEvent.PLAN_GENERATED,
        TaskEvent.START_EXECUTION,
        TaskEvent.CANCEL,
    ):
        machine.apply(event)
    assert machine.state is TaskState.CANCEL_REQUESTED
    machine.apply(TaskEvent.CANCEL_CONFIRMED)
    assert machine.state is TaskState.CANCELLED


def test_pause_and_resume() -> None:
    machine = TaskStateMachine()
    for event in (
        TaskEvent.VALIDATED,
        TaskEvent.PREPARE_ENVIRONMENT,
        TaskEvent.ENVIRONMENT_READY,
        TaskEvent.PLAN_GENERATED,
        TaskEvent.START_EXECUTION,
        TaskEvent.PAUSE,
    ):
        machine.apply(event)
    assert machine.state is TaskState.PAUSED
    machine.apply(TaskEvent.RESUME, resume_target=TaskState.EXECUTING)
    assert machine.state is TaskState.EXECUTING


def test_budget_exceeded_from_executing() -> None:
    machine = TaskStateMachine()
    for event in (
        TaskEvent.VALIDATED,
        TaskEvent.PREPARE_ENVIRONMENT,
        TaskEvent.ENVIRONMENT_READY,
        TaskEvent.PLAN_GENERATED,
        TaskEvent.START_EXECUTION,
        TaskEvent.BUDGET_EXCEEDED,
    ):
        machine.apply(event)
    assert machine.state is TaskState.BUDGET_EXCEEDED


def test_fail_from_verifying() -> None:
    machine = TaskStateMachine()
    for event in (
        TaskEvent.VALIDATED,
        TaskEvent.PREPARE_ENVIRONMENT,
        TaskEvent.ENVIRONMENT_READY,
        TaskEvent.PLAN_GENERATED,
        TaskEvent.START_EXECUTION,
        TaskEvent.EXECUTION_FINISHED,
        TaskEvent.FAIL,
    ):
        machine.apply(event)
    assert machine.state is TaskState.FAILED


def test_illegal_transition_raises() -> None:
    with pytest.raises(IllegalTransitionError):
        transition(TaskState.DRAFT, TaskEvent.START_EXECUTION)


def test_illegal_transition_on_machine() -> None:
    machine = TaskStateMachine()
    machine.apply(TaskEvent.VALIDATED)
    with pytest.raises(IllegalTransitionError):
        machine.apply(TaskEvent.DELIVERED)


def test_resume_requires_paused_state() -> None:
    with pytest.raises(IllegalTransitionError):
        transition(TaskState.EXECUTING, TaskEvent.RESUME, resume_target=TaskState.EXECUTING)


def test_resume_requires_target() -> None:
    with pytest.raises(IllegalTransitionError):
        transition(TaskState.PAUSED, TaskEvent.RESUME)


def test_resume_target_must_be_executable() -> None:
    with pytest.raises(IllegalTransitionError):
        transition(TaskState.PAUSED, TaskEvent.RESUME, resume_target=TaskState.COMPLETED)


def test_repeated_event_is_idempotent_noop() -> None:
    machine = TaskStateMachine()
    for event in (
        TaskEvent.VALIDATED,
        TaskEvent.PREPARE_ENVIRONMENT,
        TaskEvent.ENVIRONMENT_READY,
        TaskEvent.PLAN_GENERATED,
        TaskEvent.START_EXECUTION,
        TaskEvent.EXECUTION_FINISHED,
    ):
        machine.apply(event)
    assert machine.state is TaskState.VERIFYING
    # Re-applying the same event must not advance the state.
    assert machine.apply(TaskEvent.EXECUTION_FINISHED) is TaskState.VERIFYING
    assert machine.state is TaskState.VERIFYING


def test_duplicate_approval_event_is_idempotent() -> None:
    machine = TaskStateMachine()
    for event in (
        TaskEvent.VALIDATED,
        TaskEvent.PREPARE_ENVIRONMENT,
        TaskEvent.ENVIRONMENT_READY,
        TaskEvent.PLAN_GENERATED,
        TaskEvent.APPROVAL_NEEDED,
        TaskEvent.PLAN_APPROVED,
    ):
        machine.apply(event)
    assert machine.state is TaskState.EXECUTING
    assert machine.apply(TaskEvent.PLAN_APPROVED) is TaskState.EXECUTING
    assert machine.state is TaskState.EXECUTING
