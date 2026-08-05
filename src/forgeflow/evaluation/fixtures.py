"""Fixture materialization — turn plain fixture files into temporary git repos.

The worktree backend requires a git repository; evaluation fixtures are stored
as plain files, so they are copied and git-initialized into a temp workspace
before a strategy runs.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def materialize_git_repo(source: Path, target_root: Path) -> Path:
    """Copy ``source`` (plain files) into ``target_root/<name>`` and git-init it."""
    repo = target_root / source.name
    if repo.exists():
        shutil.rmtree(repo)
    shutil.copytree(source, repo, ignore=shutil.ignore_patterns(".git"))
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=forgeflow",
            "-c",
            "user.email=forgeflow@local",
            "commit",
            "-qm",
            "fixture",
        ],
        cwd=repo,
        check=True,
    )
    return repo


def materialize_dataset_repos(fixture_root: Path, target_root: Path, repositories: list[str]) -> Path:
    """Materialize the given repositories into a git-repo workspace and return it."""
    target_root.mkdir(parents=True, exist_ok=True)
    for repository in repositories:
        materialize_git_repo(fixture_root / repository, target_root)
    return target_root
