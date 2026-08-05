"""Quality report assembly and rendering (spec §7.4)."""

from __future__ import annotations

import shlex
from dataclasses import dataclass, field
from pathlib import Path

from forgeflow.domain.policy import RepositoryPolicy
from forgeflow.errors import PathEscapeError
from forgeflow.execution.base import ExecutionBackend, ExecutionResult, resolve_workspace_path
from forgeflow.quality.gates import (
    GateResult,
    GateStatus,
    GateType,
    diff_size_gate,
    forbidden_paths_gate,
    required_commands_gate,
    secret_scan_gate,
    test_masking_gate,
)


@dataclass(frozen=True)
class QualityReport:
    """Structured result of running a task's quality gates."""

    task_id: str
    changed_files: list[str]
    gates: list[GateResult]
    command_results: dict[str, ExecutionResult] = field(default_factory=dict)

    @property
    def hard_failures(self) -> list[GateResult]:
        return [
            gate
            for gate in self.gates
            if gate.gate_type is GateType.HARD and gate.status is GateStatus.FAILED
        ]

    @property
    def soft_failures(self) -> list[GateResult]:
        return [
            gate
            for gate in self.gates
            if gate.gate_type is GateType.SOFT and gate.status is GateStatus.FAILED
        ]

    @property
    def passed(self) -> bool:
        return not self.hard_failures

    def summarize(self) -> dict[str, object]:
        return {
            "task_id": self.task_id,
            "passed": self.passed,
            "changed_files": list(self.changed_files),
            "hard_failures": [gate.gate_name for gate in self.hard_failures],
            "soft_failures": [gate.gate_name for gate in self.soft_failures],
        }


class QualityGateRunner:
    """Run a repository's required commands and evaluate all deterministic gates."""

    def __init__(self, backend: ExecutionBackend, policy: RepositoryPolicy) -> None:
        self._backend = backend
        self._policy = policy

    async def evaluate(
        self,
        *,
        task_id: str,
        task_type: str,
        workspace: Path,
        changed_files: list[str] | None = None,
        command_timeout_seconds: int = 60,
    ) -> QualityReport:
        if changed_files is None:
            artifacts = await self._backend.collect_artifacts()
            changed_files = [
                artifact.path
                for artifact in artifacts
                if artifact.artifact_type == "changed_file"
            ]

        contents = self._read_changed_contents(changed_files, workspace)

        command_results = await self._run_required_commands(command_timeout_seconds)

        gates = [
            forbidden_paths_gate(changed_files, self._policy),
            diff_size_gate(changed_files, self._policy),
            test_masking_gate(changed_files, task_type=task_type),
            secret_scan_gate(contents),
            required_commands_gate(command_results),
        ]
        return QualityReport(
            task_id=task_id,
            changed_files=changed_files,
            gates=gates,
            command_results=command_results,
        )

    def _read_changed_contents(self, changed_files: list[str], workspace: Path) -> dict[str, str]:
        contents: dict[str, str] = {}
        for relative in changed_files:
            try:
                resolved = resolve_workspace_path(relative, workspace)
                # Agent-written files may be UTF-8; the platform default (e.g. GBK
                # on Chinese Windows) would raise UnicodeDecodeError. Read as UTF-8
                # with replacement so the secret scan never aborts on encoding.
                contents[relative] = resolved.read_text(encoding="utf-8", errors="replace")
            except (OSError, PathEscapeError):
                contents[relative] = ""
        return contents

    async def _run_required_commands(self, timeout_seconds: int) -> dict[str, ExecutionResult]:
        results: dict[str, ExecutionResult] = {}
        for command in self._policy.required_commands:
            args = shlex.split(command)
            results[command] = await self._backend.execute(args, timeout_seconds)
        return results


def render_report_markdown(report: QualityReport) -> str:
    """Render a compact markdown summary of a quality report."""
    lines = [
        f"## 质量门禁报告 — {report.task_id}",
        f"- 通过（硬门禁）：{'✅' if report.passed else '❌'}",
        f"- 改动文件：{', '.join(report.changed_files) or '(无)'}",
    ]
    if report.hard_failures:
        lines.append("- **硬门禁失败**：")
        lines.extend(f"  - {gate.gate_name}: {gate.details}" for gate in report.hard_failures)
    if report.soft_failures:
        lines.append("- 软门禁失败（需人工决定）：")
        lines.extend(f"  - {gate.gate_name}: {gate.details}" for gate in report.soft_failures)
    return "\n".join(lines)
