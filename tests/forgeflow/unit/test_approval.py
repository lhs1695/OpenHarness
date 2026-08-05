"""Approval unit tests — idempotency, requirements, audit."""

import pytest

from forgeflow.domain.approval import (
    ApprovalManager,
    ApprovalNotFoundError,
    ApprovalRequiredError,
    ApprovalStatus,
    ApprovalType,
    approval_requirements,
)
from forgeflow.domain.risk import RiskLevel


def test_approval_requirements_by_risk() -> None:
    assert approval_requirements(RiskLevel.LOW) == []
    assert approval_requirements(RiskLevel.MEDIUM) == [ApprovalType.FINAL]
    assert approval_requirements(RiskLevel.HIGH) == [ApprovalType.PLAN, ApprovalType.FINAL]
    assert approval_requirements(RiskLevel.SEVERE) == [ApprovalType.PLAN, ApprovalType.FINAL]


def test_request_and_approve() -> None:
    manager = ApprovalManager()
    approval = manager.request(task_id="t1", approval_type=ApprovalType.PLAN, reason="high risk")
    assert approval.status is ApprovalStatus.PENDING
    resolution = manager.resolve(
        approval.approval_id, approved=True, resolved_by="owner", reason="ok"
    )
    assert resolution.approved
    assert manager.get(approval.approval_id).status is ApprovalStatus.APPROVED


def test_resolve_is_idempotent() -> None:
    manager = ApprovalManager()
    approval = manager.request(task_id="t1", approval_type=ApprovalType.FINAL, reason="r")
    first = manager.resolve(approval.approval_id, approved=True, resolved_by="a")
    second = manager.resolve(approval.approval_id, approved=True, resolved_by="a")
    assert first is second  # same resolution object returned
    # conflicting re-resolve is a no-op; the first resolution wins
    third = manager.resolve(approval.approval_id, approved=False, resolved_by="b")
    assert third is first
    assert manager.get(approval.approval_id).status is ApprovalStatus.APPROVED


def test_reject_sets_status() -> None:
    manager = ApprovalManager()
    approval = manager.request(task_id="t1", approval_type=ApprovalType.PLAN, reason="r")
    manager.resolve(approval.approval_id, approved=False, resolved_by="owner", reason="no")
    assert manager.get(approval.approval_id).status is ApprovalStatus.REJECTED


def test_unknown_approval_raises() -> None:
    manager = ApprovalManager()
    with pytest.raises(ApprovalNotFoundError):
        manager.resolve("nope", approved=True, resolved_by="a")


def test_assert_approvals_complete_passes_when_approved() -> None:
    manager = ApprovalManager()
    plan = manager.request(task_id="t1", approval_type=ApprovalType.PLAN, reason="r")
    final = manager.request(task_id="t1", approval_type=ApprovalType.FINAL, reason="r")
    manager.resolve(plan.approval_id, approved=True, resolved_by="a")
    manager.resolve(final.approval_id, approved=True, resolved_by="a")
    manager.assert_approvals_complete("t1", RiskLevel.HIGH)  # must not raise


def test_assert_approvals_complete_blocks_pending() -> None:
    manager = ApprovalManager()
    plan = manager.request(task_id="t1", approval_type=ApprovalType.PLAN, reason="r")
    with pytest.raises(ApprovalRequiredError):
        manager.assert_approvals_complete("t1", RiskLevel.HIGH)
    manager.resolve(plan.approval_id, approved=True, resolved_by="a")
    with pytest.raises(ApprovalRequiredError):  # FINAL still missing
        manager.assert_approvals_complete("t1", RiskLevel.HIGH)


def test_low_risk_needs_no_approval() -> None:
    manager = ApprovalManager()
    manager.assert_approvals_complete("t1", RiskLevel.LOW)  # must not raise


def test_audit_log_records_actions_without_duplicates() -> None:
    manager = ApprovalManager()
    approval = manager.request(
        task_id="t1", approval_type=ApprovalType.PLAN, reason="r", actor="requester"
    )
    manager.resolve(approval.approval_id, approved=True, resolved_by="owner", reason="ok")
    assert [entry.action for entry in manager.audit_log()] == ["requested", "approved"]
    manager.resolve(approval.approval_id, approved=True, resolved_by="owner", reason="ok")
    assert len(manager.audit_log()) == 2  # idempotent re-resolve is not re-audited
