"""GitHub integration — real Draft PR creation + branch publishing (PHASE3 B1/收尾).

Thin wrappers over ``gh`` / ``git`` so ``DeliveryService`` can publish a branch
built from a persisted diff and open a real Draft PR when a token is configured.
The subprocess runner is injectable so unit tests exercise the clients with fakes
or a local bare repo.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from forgeflow.errors import ForgeFlowError


class GitHubError(ForgeFlowError):
    """The gh CLI failed (missing binary, bad auth, non-zero exit)."""


Runner = Callable[[list[str], dict[str, str], str | None], subprocess.CompletedProcess[str]]


def _default_runner(
    args: list[str], env: dict[str, str], cwd: str | None = None
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(args, capture_output=True, text=True, env=env, cwd=cwd, check=False)
    except FileNotFoundError as exc:
        raise GitHubError("gh CLI is not installed; install GitHub CLI or pass a fake runner") from exc


@dataclass(frozen=True)
class GitHubPrInfo:
    """Identity of a PR created against the remote."""

    url: str
    number: str


def _number_from_url(url: str) -> str:
    return url.rstrip("/").rsplit("/", 1)[-1] if url else ""


class GitHubPrClient:
    """Creates Draft PRs against a remote via the gh CLI (GH_TOKEN auth)."""

    def __init__(
        self,
        *,
        token: str | None = None,
        runner: Runner | None = None,
    ) -> None:
        self._token = token
        self._runner = runner or _default_runner

    @property
    def has_token(self) -> bool:
        return bool(self._token)

    def _env(self) -> dict[str, str]:
        env = dict(os.environ)
        if self._token:
            env["GH_TOKEN"] = self._token
        return env

    def _gh(self, args: list[str]) -> subprocess.CompletedProcess[str]:
        completed = self._runner(["gh", *args], self._env(), None)
        if completed.returncode != 0:
            error = (completed.stderr or completed.stdout or "gh command failed").strip()
            subcommand = " ".join(args[:2]) if len(args) >= 2 else args[0]
            raise GitHubError(f"gh {subcommand} failed: {error}")
        return completed

    def current_repository(self) -> str:
        """Resolve the repository's ``owner/name`` via ``gh repo view``."""
        completed = self._gh(["repo", "view", "--json", "nameWithOwner"])
        raw = (completed.stdout or "").strip()
        if not raw:
            raise GitHubError("gh repo view returned no repository name")
        name = json.loads(raw).get("nameWithOwner")
        if not name:
            raise GitHubError("gh repo view returned no nameWithOwner")
        return str(name)

    def create_draft_pr(
        self,
        *,
        title: str,
        body: str,
        base: str,
        head: str,
        repository: str | None = None,
    ) -> GitHubPrInfo:
        """Run ``gh pr create --draft`` and return the created PR's identity."""
        args = [
            "pr",
            "create",
            "--draft",
            "--base",
            base,
            "--head",
            head,
            "--title",
            title,
            "--body",
            body,
        ]
        if repository:
            args += ["--repo", repository]
        completed = self._gh(args)
        url = (completed.stdout or "").strip()
        return GitHubPrInfo(url=url, number=_number_from_url(url))


def owner_repo_from_url(url: str) -> str:
    """Extract ``owner/repo`` from an https or ssh clone URL (PHASE3 收尾)."""
    url = url.rstrip("/")
    url = url.removesuffix(".git")
    if ":" in url and not url.startswith(("http://", "https://")):
        _, _, url = url.partition(":")  # strip scp-like user@host: prefix
    parts = [part for part in url.split("/") if part]
    if len(parts) < 2:
        raise GitHubError(f"cannot derive owner/repo from URL: {url}")
    return f"{parts[-2]}/{parts[-1]}"


class GitHubPublisher:
    """Publishes a branch built from a persisted diff to a remote (PHASE3 收尾).

    Clones the target repository, applies the diff, commits and pushes the branch
    with ``GH_TOKEN`` auth — so delivery works even after the evaluation worktree
    was cleaned up.  The git runner is injectable for tests.
    """

    def __init__(self, *, token: str, runner: Runner | None = None) -> None:
        if not token:
            raise GitHubError("GitHubPublisher requires a token")
        self._token = token
        self._runner = runner or _default_runner

    def _env(self) -> dict[str, str]:
        env = dict(os.environ)
        env["GH_TOKEN"] = self._token
        env["GIT_TERMINAL_PROMPT"] = "0"
        env["GIT_AUTHOR_NAME"] = "ForgeFlow"
        env["GIT_AUTHOR_EMAIL"] = "forgeflow@localhost"
        env["GIT_COMMITTER_NAME"] = "ForgeFlow"
        env["GIT_COMMITTER_EMAIL"] = "forgeflow@localhost"
        return env

    def _run_git(self, args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        completed = self._runner(["git", *args], self._env(), str(cwd))
        if completed.returncode != 0:
            error = (completed.stderr or completed.stdout or "git command failed").strip()
            raise GitHubError(f"git {args[0]} failed: {error}")
        return completed

    def publish(
        self,
        *,
        repository_url: str,
        base_branch: str,
        branch_name: str,
        diff: str,
        message: str,
        work_dir: Path,
    ) -> str:
        """Clone, apply ``diff``, commit and push ``branch_name``; returns the branch."""
        if work_dir.exists():
            shutil.rmtree(work_dir)
        work_dir.mkdir(parents=True)
        self._run_git(
            [
                "clone",
                "-c",
                "core.autocrlf=false",
                "--branch",
                base_branch,
                "--depth",
                "1",
                repository_url,
                str(work_dir),
            ],
            cwd=work_dir.parent,
        )
        patch_path = work_dir / ".forgeflow.patch"
        patch_path.write_bytes(diff.encode("utf-8"))  # bytes: keep LF (Windows text write would add CRLF)
        self._run_git(["apply", "--index", ".forgeflow.patch"], cwd=work_dir)
        self._run_git(["add", "-A"], cwd=work_dir)
        self._run_git(["commit", "-m", message], cwd=work_dir)
        self._run_git(["push", "origin", f"HEAD:{branch_name}"], cwd=work_dir)
        return branch_name
