"""M5 integration — delivery artifacts from a real worktree change."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from forgeflow.execution.worktree import WorktreeExecutionBackend
from forgeflow.orchestration.delivery import (
    DeliveryService,
    DraftPrGuardError,
    make_patch,
)


def _git(*args: str, cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)


def _make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "calc.py").write_text("def add(a, b):\n    return a + b\n")
    _git("init", cwd=repo)
    _git("checkout", "-b", "main", cwd=repo)
    _git("add", ".", cwd=repo)
    _git("commit", "-m", "initial", cwd=repo)
    return repo


@pytest.mark.asyncio
async def test_generate_patch_and_draft_pr_for_test_repo(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    backend = WorktreeExecutionBackend(repo, base_dir=tmp_path / "worktrees")
    await backend.prepare("task_x", "billing-service")
    try:
        backend.resolve_workspace_path("calc.py").write_text("def add(a, b):\n    return a * b\n")
        artifacts = await backend.collect_artifacts()
        changed = [a.path for a in artifacts if a.artifact_type == "changed_file"]
        assert changed == ["calc.py"]
        stat = next(a for a in artifacts if a.artifact_type == "diff_stat")
        patch = make_patch(
            repository="billing-service",
            diff=str(stat.metadata["stat"]),
            changed_files=changed,
        )
        pr = DeliveryService(test_repositories=["billing-service"]).create_draft_pr(
            repository="billing-service", patch=patch
        )
        assert pr.repository == "billing-service"
        assert pr.changed_files == ["calc.py"]
    finally:
        await backend.cleanup()


@pytest.mark.asyncio
async def test_draft_pr_guard_blocks_non_test_repo(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    backend = WorktreeExecutionBackend(repo, base_dir=tmp_path / "worktrees")
    await backend.prepare("task_y", "billing-service")
    try:
        backend.resolve_workspace_path("calc.py").write_text("def add(a, b):\n    return a * b\n")
        artifacts = await backend.collect_artifacts()
        changed = [a.path for a in artifacts if a.artifact_type == "changed_file"]
        patch = make_patch(repository="prod-service", diff="+x", changed_files=changed)
        with pytest.raises(DraftPrGuardError):
            DeliveryService(test_repositories=["billing-service"]).create_draft_pr(
                repository="prod-service", patch=patch
            )
    finally:
        await backend.cleanup()
