"""GitHub integration — real Draft PR creation via the gh CLI (PHASE3 B1).

Thin wrapper over ``gh`` so ``DeliveryService`` can submit real Draft PRs when a
token is configured.  The subprocess runner is injectable so unit tests exercise
the client with a fake ``gh``.
"""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Callable
from dataclasses import dataclass

from forgeflow.errors import ForgeFlowError


class GitHubError(ForgeFlowError):
    """The gh CLI failed (missing binary, bad auth, non-zero exit)."""


Runner = Callable[[list[str], dict[str, str]], subprocess.CompletedProcess[str]]


def _default_runner(args: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(args, capture_output=True, text=True, env=env, check=False)
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
        completed = self._runner(["gh", *args], self._env())
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
