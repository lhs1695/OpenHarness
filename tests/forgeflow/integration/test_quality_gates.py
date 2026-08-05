"""M4 integration tests — fixed tasks exercising quality gates on a temp repo.

Each task prepares a worktree backend, makes a change, and asserts the
deterministic gate outcomes.  Runs locally (git + subprocess, no model calls).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from forgeflow.domain.policy import RepositoryPolicy
from forgeflow.execution.worktree import WorktreeExecutionBackend
from forgeflow.quality.reports import QualityGateRunner


def _git(*args: str, cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)


def _make_git_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "calc.py").write_text("def add(a, b):\n    return a + b\n")
    (repo / "tests").mkdir()
    (repo / "tests" / "test_calc.py").write_text(
        "from calc import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n"
    )
    _git("init", cwd=repo)
    _git("checkout", "-b", "main", cwd=repo)
    _git("add", ".", cwd=repo)
    _git("commit", "-m", "initial", cwd=repo)
    return repo


def _make_backend(tmp_path: Path) -> tuple[WorktreeExecutionBackend, Path]:
    repo = _make_git_repo(tmp_path)
    backend = WorktreeExecutionBackend(repo, base_dir=tmp_path / "worktrees")
    return backend, repo


def _policy(**overrides: object) -> RepositoryPolicy:
    fields: dict[str, object] = {
        "repository": "billing-service",
        "forbidden_paths": ["src/auth/**", "migrations/**"],
        "max_changed_files": 2,
        "required_commands": [],
    }
    fields.update(overrides)
    return RepositoryPolicy(**fields)


def _python_exit_command(code: int) -> str:
    return f'"{sys.executable}" -c "import sys; sys.exit({code})"'


@pytest.mark.asyncio
async def test_task_clean_change_passes_hard_gates(tmp_path: Path) -> None:
    backend, _ = _make_backend(tmp_path)
    await backend.prepare("task_a", "billing-service")
    try:
        backend.resolve_workspace_path("calc.py").write_text("def add(a, b):\n    return a + b + 1\n")
        report = await QualityGateRunner(backend, _policy()).evaluate(
            task_id="task_a",
            task_type="bugfix",
            workspace=backend.workspace,
        )
        assert report.passed
        assert report.hard_failures == []
        assert report.soft_failures == []
    finally:
        await backend.cleanup()


@pytest.mark.asyncio
async def test_task_forbidden_path_fails_hard(tmp_path: Path) -> None:
    backend, _ = _make_backend(tmp_path)
    await backend.prepare("task_b", "billing-service")
    try:
        target = backend.resolve_workspace_path("src/auth/cred.py")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("SECRET = 'x'\n")
        report = await QualityGateRunner(backend, _policy()).evaluate(
            task_id="task_b",
            task_type="bugfix",
            workspace=backend.workspace,
        )
        assert not report.passed
        assert any(gate.gate_name == "forbidden_paths" for gate in report.hard_failures)
    finally:
        await backend.cleanup()


@pytest.mark.asyncio
async def test_task_diff_size_soft_fails(tmp_path: Path) -> None:
    backend, _ = _make_backend(tmp_path)
    await backend.prepare("task_c", "billing-service")
    try:
        for name in ("calc.py", "calc2.py", "calc3.py"):
            backend.resolve_workspace_path(name).write_text("x = 1\n")
        report = await QualityGateRunner(backend, _policy(max_changed_files=2)).evaluate(
            task_id="task_c",
            task_type="bugfix",
            workspace=backend.workspace,
        )
        assert report.passed  # hard gates still pass
        assert any(gate.gate_name == "diff_size" for gate in report.soft_failures)
    finally:
        await backend.cleanup()


@pytest.mark.asyncio
async def test_task_test_only_change_flags_masking(tmp_path: Path) -> None:
    backend, _ = _make_backend(tmp_path)
    await backend.prepare("task_d", "billing-service")
    try:
        backend.resolve_workspace_path("tests/test_calc.py").write_text(
            "from calc import add\n\n\ndef test_add():\n    assert add(2, 3) == 5\n"
        )
        report = await QualityGateRunner(backend, _policy()).evaluate(
            task_id="task_d",
            task_type="bugfix",
            workspace=backend.workspace,
        )
        assert report.passed
        assert any(gate.gate_name == "test_masking" for gate in report.soft_failures)
    finally:
        await backend.cleanup()


@pytest.mark.asyncio
async def test_task_secret_leak_fails_hard(tmp_path: Path) -> None:
    backend, _ = _make_backend(tmp_path)
    await backend.prepare("task_e", "billing-service")
    try:
        backend.resolve_workspace_path("config.py").write_text(
            "api_key = 'sk-abcdef1234567890abcdefxyz'\n"
        )
        report = await QualityGateRunner(backend, _policy()).evaluate(
            task_id="task_e",
            task_type="bugfix",
            workspace=backend.workspace,
        )
        assert not report.passed
        assert any(gate.gate_name == "secret_scan" for gate in report.hard_failures)
    finally:
        await backend.cleanup()


@pytest.mark.asyncio
async def test_task_failing_required_command_fails_hard(tmp_path: Path) -> None:
    backend, _ = _make_backend(tmp_path)
    await backend.prepare("task_f", "billing-service")
    try:
        backend.resolve_workspace_path("calc.py").write_text("def add(a, b):\n    return a + b\n")
        policy = _policy(required_commands=[_python_exit_command(1)])
        report = await QualityGateRunner(backend, policy).evaluate(
            task_id="task_f",
            task_type="bugfix",
            workspace=backend.workspace,
        )
        assert not report.passed
        assert any(gate.gate_name == "required_commands" for gate in report.hard_failures)
    finally:
        await backend.cleanup()


@pytest.mark.asyncio
async def test_report_summarize_and_markdown(tmp_path: Path) -> None:
    backend, _ = _make_backend(tmp_path)
    await backend.prepare("task_g", "billing-service")
    try:
        target = backend.resolve_workspace_path("src/auth/cred.py")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("x = 1\n")
        report = await QualityGateRunner(backend, _policy()).evaluate(
            task_id="task_g",
            task_type="bugfix",
            workspace=backend.workspace,
        )
        summary = report.summarize()
        assert summary["passed"] is False
        assert "forbidden_paths" in summary["hard_failures"]
        from forgeflow.quality.reports import render_report_markdown

        assert "质量门禁报告" in render_report_markdown(report)
    finally:
        await backend.cleanup()
