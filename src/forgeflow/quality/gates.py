"""Deterministic quality gates (spec §7.4).

Hard-gate failures block delivery; soft-gate failures need a human decision.
Every gate is a pure function over the change and the repository policy, so
it can be unit-tested without an execution backend.
"""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass, field
from enum import Enum

from forgeflow.domain.policy import RepositoryPolicy
from forgeflow.execution.base import ExecutionResult


class GateType(str, Enum):
    HARD = "hard"
    SOFT = "soft"


class GateStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    NOT_APPLICABLE = "not_applicable"


@dataclass(frozen=True)
class GateResult:
    gate_name: str
    gate_type: GateType
    status: GateStatus
    details: dict[str, object] = field(default_factory=dict)


def _matches_any(path: str, patterns: list[str]) -> bool:
    normalized = path.replace("\\", "/")
    for pattern in patterns:
        pat = pattern.replace("\\", "/").rstrip("/")
        if fnmatch.fnmatch(normalized, pat):
            return True
        if fnmatch.fnmatch(normalized, pat + "/**"):
            return True
        if normalized.startswith(pat + "/"):
            return True
    return False


def forbidden_paths_gate(changed_files: list[str], policy: RepositoryPolicy) -> GateResult:
    """Hard: no change may touch a policy-forbidden path."""
    touched = [path for path in changed_files if _matches_any(path, policy.forbidden_paths)]
    if touched:
        return GateResult(
            "forbidden_paths",
            GateType.HARD,
            GateStatus.FAILED,
            details={"touched": touched},
        )
    return GateResult("forbidden_paths", GateType.HARD, GateStatus.PASSED)


def diff_size_gate(changed_files: list[str], policy: RepositoryPolicy) -> GateResult:
    """Soft: the diff should stay within policy.max_changed_files."""
    if len(changed_files) > policy.max_changed_files:
        return GateResult(
            "diff_size",
            GateType.SOFT,
            GateStatus.FAILED,
            details={"changed": len(changed_files), "max": policy.max_changed_files},
        )
    return GateResult("diff_size", GateType.SOFT, GateStatus.PASSED)


def _is_test_file(path: str) -> bool:
    normalized = path.replace("\\", "/")
    name = normalized.rsplit("/", 1)[-1]
    if normalized.startswith("tests/") or "/tests/" in normalized:
        return True
    return name.startswith("test_") or name.endswith("_test.py")


def test_masking_gate(changed_files: list[str], *, task_type: str) -> GateResult:
    """Soft: for a code-change task, changing only tests is suspicious."""
    if task_type in ("test", "docs"):
        return GateResult("test_masking", GateType.SOFT, GateStatus.NOT_APPLICABLE)
    if not changed_files:
        return GateResult("test_masking", GateType.SOFT, GateStatus.NOT_APPLICABLE)
    if all(_is_test_file(path) for path in changed_files):
        return GateResult(
            "test_masking",
            GateType.SOFT,
            GateStatus.FAILED,
            details={"test_only_files": list(changed_files)},
        )
    return GateResult("test_masking", GateType.SOFT, GateStatus.PASSED)


_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)\b(api[_-]?key|secret|token|password|passwd)\s*[:=]\s*['\"]?[\w\-]{12,}"),
    re.compile(r"(?i)\bsk-[A-Za-z0-9]{16,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
)


def secret_scan_gate(file_contents: dict[str, str]) -> GateResult:
    """Hard: no secret-like values may appear in changed files."""
    leaks: dict[str, list[str]] = {}
    for path, content in file_contents.items():
        for pattern in _SECRET_PATTERNS:
            if pattern.search(content):
                leaks.setdefault(path, []).append(pattern.pattern)
    if leaks:
        return GateResult(
            "secret_scan",
            GateType.HARD,
            GateStatus.FAILED,
            details={"leaks": leaks},
        )
    return GateResult("secret_scan", GateType.HARD, GateStatus.PASSED)


def required_commands_gate(command_results: dict[str, ExecutionResult]) -> GateResult:
    """Hard: every required command must exit with code 0."""
    failed = {
        name: result.returncode
        for name, result in command_results.items()
        if result.returncode != 0
    }
    if failed:
        return GateResult(
            "required_commands",
            GateType.HARD,
            GateStatus.FAILED,
            details={"failed": failed},
        )
    return GateResult("required_commands", GateType.HARD, GateStatus.PASSED)
