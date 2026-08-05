"""Approval flow (spec §4.4, §5) — idempotent, fully audited."""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum

from forgeflow.domain.risk import RiskLevel
from forgeflow.errors import ForgeFlowError


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ApprovalType(str, Enum):
    PLAN = "plan"
    HIGH_RISK_ACTION = "high_risk_action"
    FINAL = "final"


class ApprovalNotFoundError(ForgeFlowError):
    """No approval with the given id exists."""


class ApprovalRequiredError(ForgeFlowError):
    """A required approval is missing or not approved."""


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True)
class Approval:
    approval_id: str
    task_id: str
    run_id: str | None
    approval_type: ApprovalType
    status: ApprovalStatus
    requested_reason: str
    requested_at: str
    resolved_by: str | None = None
    resolved_at: str | None = None
    resolution_reason: str | None = None


@dataclass(frozen=True)
class ApprovalResolution:
    approval_id: str
    approved: bool
    resolved_by: str
    resolved_at: str
    reason: str | None = None


@dataclass(frozen=True)
class ApprovalAuditEntry:
    approval_id: str
    task_id: str
    action: str
    actor: str | None
    timestamp: str
    reason: str | None = None


def approval_requirements(risk_level: RiskLevel) -> list[ApprovalType]:
    """Required approvals for a risk level (spec §4.4).

    SEVERE tasks are only allowed to produce a plan and never execute write
    operations, so the requirements below apply to MEDIUM/HIGH.
    """
    if risk_level is RiskLevel.LOW:
        return []
    if risk_level is RiskLevel.MEDIUM:
        return [ApprovalType.FINAL]
    return [ApprovalType.PLAN, ApprovalType.FINAL]


class ApprovalManager:
    """In-memory approvals with idempotent resolution and an audit log."""

    def __init__(self) -> None:
        self._approvals: dict[str, Approval] = {}
        self._resolutions: dict[str, ApprovalResolution] = {}
        self._audit: list[ApprovalAuditEntry] = []

    def request(
        self,
        *,
        task_id: str,
        approval_type: ApprovalType,
        reason: str,
        run_id: str | None = None,
        actor: str | None = None,
        approval_id: str | None = None,
    ) -> Approval:
        approval_id = approval_id or f"approval-{len(self._approvals) + 1}"
        requested_at = _now_iso()
        approval = Approval(
            approval_id=approval_id,
            task_id=task_id,
            run_id=run_id,
            approval_type=approval_type,
            status=ApprovalStatus.PENDING,
            requested_reason=reason,
            requested_at=requested_at,
        )
        self._approvals[approval_id] = approval
        self._audit.append(
            ApprovalAuditEntry(
                approval_id=approval_id,
                task_id=task_id,
                action="requested",
                actor=actor,
                timestamp=requested_at,
                reason=reason,
            )
        )
        return approval

    def resolve(
        self,
        approval_id: str,
        *,
        approved: bool,
        resolved_by: str,
        reason: str | None = None,
        resolved_at: str | None = None,
    ) -> ApprovalResolution:
        """Resolve an approval. Re-resolving is an idempotent no-op."""
        approval = self._approvals.get(approval_id)
        if approval is None:
            raise ApprovalNotFoundError(approval_id)
        existing = self._resolutions.get(approval_id)
        if existing is not None:
            return existing
        timestamp = resolved_at or _now_iso()
        new_status = ApprovalStatus.APPROVED if approved else ApprovalStatus.REJECTED
        self._approvals[approval_id] = dataclasses.replace(
            approval,
            status=new_status,
            resolved_by=resolved_by,
            resolved_at=timestamp,
            resolution_reason=reason,
        )
        resolution = ApprovalResolution(
            approval_id=approval_id,
            approved=approved,
            resolved_by=resolved_by,
            resolved_at=timestamp,
            reason=reason,
        )
        self._resolutions[approval_id] = resolution
        self._audit.append(
            ApprovalAuditEntry(
                approval_id=approval_id,
                task_id=approval.task_id,
                action="approved" if approved else "rejected",
                actor=resolved_by,
                timestamp=timestamp,
                reason=reason,
            )
        )
        return resolution

    def get(self, approval_id: str) -> Approval:
        approval = self._approvals.get(approval_id)
        if approval is None:
            raise ApprovalNotFoundError(approval_id)
        return approval

    def approvals_for(self, task_id: str) -> list[Approval]:
        return [approval for approval in self._approvals.values() if approval.task_id == task_id]

    def audit_log(self) -> list[ApprovalAuditEntry]:
        return list(self._audit)

    def assert_approvals_complete(self, task_id: str, risk_level: RiskLevel) -> None:
        """未批准的高风险任务不能继续：要求的高危审批必须全部 APPROVED."""
        for approval_type in approval_requirements(risk_level):
            candidates = [
                approval
                for approval in self.approvals_for(task_id)
                if approval.approval_type is approval_type
            ]
            if not candidates or not all(
                approval.status is ApprovalStatus.APPROVED for approval in candidates
            ):
                raise ApprovalRequiredError(
                    f"任务 {task_id} 缺少已批准的 {approval_type.value} 审批（风险 {risk_level.value}）"
                )
