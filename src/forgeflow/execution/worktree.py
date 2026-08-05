"""Local git-worktree execution backend (M3).

Adapts the upstream ``WorktreeManager`` (``openharness.swarm.worktree``) to
give each task an isolated git worktree of the source repository.  Commands
run with the worktree as cwd, are bounded by a timeout (killing the process
tree on expiry), and all file paths are validated to stay inside the
workspace.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from forgeflow.errors import ExecutionNotPreparedError
from forgeflow.execution.base import Artifact, ExecutionResult, resolve_workspace_path
from openharness.swarm.worktree import WorktreeInfo, WorktreeManager

_IGNORED_ARTIFACT_PREFIXES = (
    ".pytest_cache/",
    "__pycache__/",
    ".mypy_cache/",
    ".ruff_cache/",
)


class WorktreeExecutionBackend:
    """Isolated task workspace backed by a git worktree of a source repo."""

    def __init__(
        self,
        repo_path: str | Path,
        *,
        base_dir: str | Path | None = None,
    ) -> None:
        self._repo_path = Path(repo_path).resolve()
        self._manager = WorktreeManager(Path(base_dir) if base_dir is not None else None)
        self._info: WorktreeInfo | None = None
        self._process: asyncio.subprocess.Process | None = None

    @property
    def workspace(self) -> Path:
        if self._info is None:
            raise ExecutionNotPreparedError("prepare() 尚未调用")
        return self._info.path

    async def prepare(self, task_id: str, repository: str) -> str:
        slug = f"forgeflow-{task_id}"
        self._info = await self._manager.create_worktree(self._repo_path, slug)
        return str(self.workspace)

    def resolve_workspace_path(self, path: str | Path) -> Path:
        return resolve_workspace_path(path, self.workspace)

    async def execute(self, command: list[str], timeout_seconds: int) -> ExecutionResult:
        if not command:
            raise ValueError("command 不能为空")
        loop = asyncio.get_running_loop()
        started = loop.time()
        self._process = await asyncio.create_subprocess_exec(
            *command,
            cwd=str(self.workspace),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )
        timed_out = False
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                self._process.communicate(), timeout=timeout_seconds
            )
        except TimeoutError:
            timed_out = True
            await self._terminate(force=True)
            stdout_bytes, stderr_bytes = await self._process.communicate()
        except asyncio.CancelledError:
            await self._terminate(force=False)
            raise
        duration_ms = int((loop.time() - started) * 1000)
        result = ExecutionResult(
            command=command,
            returncode=self._process.returncode if self._process.returncode is not None else 0,
            stdout=stdout_bytes.decode(errors="replace"),
            stderr=stderr_bytes.decode(errors="replace"),
            duration_ms=duration_ms,
            timed_out=timed_out,
        )
        self._process = None
        return result

    async def cancel(self) -> None:
        if self._process is not None:
            await self._terminate(force=True)
            self._process = None

    async def collect_artifacts(self) -> list[Artifact]:
        tracked, _ = await self._run_git("diff", "HEAD", "--name-only")
        untracked, _ = await self._run_git("ls-files", "--others", "--exclude-standard")
        names = sorted(
            {
                line.strip()
                for line in (tracked + "\n" + untracked).splitlines()
                if line.strip()
            }
        )
        changed = [name for name in names if not name.startswith(_IGNORED_ARTIFACT_PREFIXES)]
        artifacts = [Artifact(artifact_type="changed_file", path=name) for name in changed]
        stat_stdout, _ = await self._run_git("diff", "HEAD", "--stat")
        artifacts.append(
            Artifact(
                artifact_type="diff_stat",
                path="",
                metadata={"stat": stat_stdout.strip()},
            )
        )
        return artifacts

    async def cleanup(self) -> None:
        if self._info is None:
            return
        if self._process is not None and self._process.returncode is None:
            await self._terminate(force=True)
            self._process = None
        await self._manager.remove_worktree(self._info.slug)
        self._info = None

    async def _run_git(self, *args: str) -> tuple[str, str]:
        proc = await asyncio.create_subprocess_exec(
            "git",
            *args,
            cwd=str(self.workspace),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        )
        stdout_bytes, stderr_bytes = await proc.communicate()
        return (
            stdout_bytes.decode(errors="replace"),
            stderr_bytes.decode(errors="replace"),
        )

    async def _terminate(self, *, force: bool) -> None:
        process = self._process
        if process is None or process.returncode is not None:
            return
        if force:
            await self._force_kill_tree(process)
            return
        try:
            process.terminate()
        except ProcessLookupError:
            return
        try:
            await asyncio.wait_for(process.wait(), timeout=2.0)
        except TimeoutError:
            await self._force_kill_tree(process)

    @staticmethod
    async def _force_kill_tree(process: asyncio.subprocess.Process) -> None:
        # On Windows, taskkill /T /F reaps the whole tree, after which asyncio
        # raises ProcessLookupError on the follow-up kill()/wait().
        if sys.platform == "win32" and process.pid:
            try:
                killer = await asyncio.create_subprocess_exec(
                    "taskkill",
                    "/PID",
                    str(process.pid),
                    "/T",
                    "/F",
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                await killer.wait()
            except OSError:
                pass
        try:
            process.kill()
        except ProcessLookupError:
            pass
        try:
            await process.wait()
        except ProcessLookupError:
            pass
