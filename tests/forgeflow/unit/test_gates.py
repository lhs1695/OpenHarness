"""Quality gate unit tests — pure, no backend needed."""

from forgeflow.domain.policy import RepositoryPolicy
from forgeflow.execution.base import ExecutionResult
from forgeflow.quality.gates import (
    GateStatus,
    GateType,
    diff_size_gate,
    forbidden_paths_gate,
    required_commands_gate,
    secret_scan_gate,
)
from forgeflow.quality.gates import (
    test_masking_gate as masking_gate,
)

POLICY = RepositoryPolicy(
    repository="billing-service",
    forbidden_paths=["migrations/**", "src/auth/**"],
    max_changed_files=2,
)


def _result(returncode: int) -> ExecutionResult:
    return ExecutionResult(
        command=["cmd"],
        returncode=returncode,
        stdout="",
        stderr="",
        duration_ms=1,
    )


def test_forbidden_paths_gate_fails_on_touch() -> None:
    result = forbidden_paths_gate(["src/auth/cred.py", "calc.py"], POLICY)
    assert result.status is GateStatus.FAILED
    assert result.gate_type is GateType.HARD
    assert result.details["touched"] == ["src/auth/cred.py"]


def test_forbidden_paths_gate_passes_clean() -> None:
    result = forbidden_paths_gate(["calc.py"], POLICY)
    assert result.status is GateStatus.PASSED


def test_diff_size_gate_soft_fails_over_limit() -> None:
    result = diff_size_gate(["a.py", "b.py", "c.py"], POLICY)
    assert result.status is GateStatus.FAILED
    assert result.gate_type is GateType.SOFT
    assert result.details == {"changed": 3, "max": 2}


def test_diff_size_gate_passes_within_limit() -> None:
    assert diff_size_gate(["a.py", "b.py"], POLICY).status is GateStatus.PASSED


def test_test_masking_flags_test_only_change() -> None:
    result = masking_gate(["tests/test_calc.py"], task_type="bugfix")
    assert result.status is GateStatus.FAILED
    assert result.gate_type is GateType.SOFT


def test_test_masking_passes_with_source_change() -> None:
    result = masking_gate(["calc.py", "tests/test_calc.py"], task_type="bugfix")
    assert result.status is GateStatus.PASSED


def test_test_masking_not_applicable_for_test_task() -> None:
    result = masking_gate(["tests/test_calc.py"], task_type="test")
    assert result.status is GateStatus.NOT_APPLICABLE


def test_secret_scan_flags_apikey() -> None:
    result = secret_scan_gate({"config.py": "api_key = 'sk-abcdef1234567890abcdefxyz'\n"})
    assert result.status is GateStatus.FAILED
    assert "config.py" in result.details["leaks"]


def test_secret_scan_passes_clean_content() -> None:
    result = secret_scan_gate({"config.py": "def f():\n    return 1\n"})
    assert result.status is GateStatus.PASSED


def test_secret_scan_ignores_short_words() -> None:
    result = secret_scan_gate({"config.py": "SECRET = 'x'\n"})
    assert result.status is GateStatus.PASSED


def test_required_commands_fails_on_nonzero() -> None:
    result = required_commands_gate({"ok": _result(0), "bad": _result(1)})
    assert result.status is GateStatus.FAILED
    assert result.gate_type is GateType.HARD
    assert result.details["failed"] == {"bad": 1}


def test_required_commands_passes_all_zero() -> None:
    assert required_commands_gate({"ok": _result(0)}).status is GateStatus.PASSED


def test_required_commands_passes_empty() -> None:
    assert required_commands_gate({}).status is GateStatus.PASSED
