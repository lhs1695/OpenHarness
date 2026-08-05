"""M3 integration tests — fixed tasks on a temp git repo worktree backend.

These run locally (git + subprocess, no model calls), so they are not marked
``online`` and run in the default suite.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from forgeflow.errors import PathEscapeError
from forgeflow.execution.worktree import WorktreeExecutionBackend


def _git(*args: str, cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)


def _make_git_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "calc.py").write_text("def add(a, b):\n    return a + b\n")
    (repo / "test_calc.py").write_text(
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


@pytest.mark.asyncio
async def test_task_run_repo_tests_in_worktree(tmp_path: Path) -> None:
    """Task 1: run the repo's test suite inside an isolated worktree."""
    backend, repo = _make_backend(tmp_path)
    await backend.prepare("task_1", "calc-repo")
    try:
        result = await backend.execute([sys.executable, "-m", "pytest", "-q"], timeout_seconds=60)
        assert result.returncode == 0, result.stderr
        assert "passed" in result.stdout
        assert not (repo / ".pytest_cache").exists()  # original repo untouched
    finally:
        await backend.cleanup()


@pytest.mark.asyncio
async def test_task_change_isolated_from_original(tmp_path: Path) -> None:
    """Task 2: a code change in the worktree does not touch the original repo."""
    backend, repo = _make_backend(tmp_path)
    await backend.prepare("task_2", "calc-repo")
    try:
        target = backend.resolve_workspace_path("calc.py")
        target.write_text("def add(a, b):\n    return a * b\n")
        artifacts = await backend.collect_artifacts()
        assert any(artifact.path == "calc.py" for artifact in artifacts)
        assert (repo / "calc.py").read_text() == "def add(a, b):\n    return a + b\n"
    finally:
        await backend.cleanup()


@pytest.mark.asyncio
async def test_task_safety_path_escape_and_timeout(tmp_path: Path) -> None:
    """Task 3: path escapes are rejected and runaway commands are killed."""
    backend, _ = _make_backend(tmp_path)
    workspace = await backend.prepare("task_3", "calc-repo")
    try:
        with pytest.raises(PathEscapeError):
            backend.resolve_workspace_path("../outside.txt")
        with pytest.raises(PathEscapeError):
            backend.resolve_workspace_path(str(tmp_path / "outside.txt"))

        outside = tmp_path / "secret.txt"
        outside.write_text("secret")
        link = Path(workspace) / "leak.txt"
        symlink_ok = True
        try:
            link.symlink_to(outside)
        except OSError:
            symlink_ok = False
        if symlink_ok:
            with pytest.raises(PathEscapeError):
                backend.resolve_workspace_path("leak.txt")

        result = await backend.execute(
            [sys.executable, "-c", "import time; time.sleep(30)"], timeout_seconds=2
        )
        assert result.timed_out
    finally:
        await backend.cleanup()


@pytest.mark.asyncio
async def test_cleanup_removes_worktree(tmp_path: Path) -> None:
    backend, _ = _make_backend(tmp_path)
    await backend.prepare("task_4", "calc-repo")
    worktree_dir = backend.workspace
    assert worktree_dir.exists()
    await backend.cleanup()
    assert not worktree_dir.exists()
