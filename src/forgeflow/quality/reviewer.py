"""Independent read-only code reviewer (spec §4.4, §7.4).

The reviewer drives an injected engine whose tool registry contains only
read-only tools; combined with the review prompt this enforces that a review
never modifies the repository.  Unit tests inject a fake engine.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol

from forgeflow.domain.task import DevelopmentTask
from forgeflow.errors import AdapterError
from openharness.api.client import SupportsStreamingMessages
from openharness.config.settings import PermissionSettings
from openharness.engine.query_engine import QueryEngine
from openharness.engine.stream_events import AssistantTextDelta
from openharness.permissions.checker import PermissionChecker
from openharness.permissions.modes import PermissionMode
from openharness.tools import create_default_tool_registry
from openharness.tools.base import ToolRegistry

# Tools that are inherently read-only and safe for a reviewer.
_READ_ONLY_TOOL_NAMES = frozenset(
    {
        "read_file",
        "glob",
        "grep",
        "lsp",
        "image_to_text",
        "tool_search",
        "web_fetch",
        "web_search",
        "brief",
        "sleep",
        "cron_list",
        "task_get",
        "task_list",
        "task_output",
        "ask_user_question",
    }
)


class Severity(str, Enum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"


@dataclass(frozen=True)
class ReviewFinding:
    severity: Severity
    message: str
    file: str | None = None
    line: int | None = None


@dataclass(frozen=True)
class ReviewReport:
    verdict: str
    summary: str
    findings: list[ReviewFinding] = field(default_factory=list)

    @property
    def blockers(self) -> list[ReviewFinding]:
        return [finding for finding in self.findings if finding.severity in (Severity.P0, Severity.P1)]

    @property
    def approved(self) -> bool:
        return self.verdict == "approved" and not self.blockers


class ReviewEngineLike(Protocol):
    """Read-only engine surface consumed by the Reviewer."""

    def submit_message(self, prompt: str) -> AsyncIterator[object]: ...


def read_only_tool_registry() -> ToolRegistry:
    """A registry containing only read-only tools (Reviewer 默认只读)."""
    registry = ToolRegistry()
    for tool in create_default_tool_registry().list_tools():
        if tool.name in _READ_ONLY_TOOL_NAMES:
            registry.register(tool)
    return registry


def build_review_engine(
    api_client: SupportsStreamingMessages,
    *,
    cwd: str,
    model: str,
    system_prompt: str,
    max_turns: int = 6,
) -> QueryEngine:
    """Build a QueryEngine restricted to read-only tools and PLAN permission mode."""
    checker = PermissionChecker(PermissionSettings(mode=PermissionMode.PLAN))
    return QueryEngine(
        api_client=api_client,
        tool_registry=read_only_tool_registry(),
        permission_checker=checker,
        cwd=cwd,
        model=model,
        system_prompt=system_prompt,
        max_turns=max_turns,
    )


def build_review_prompt(task: DevelopmentTask, diff: str) -> str:
    return (
        "You are an independent senior code reviewer. You are READ-ONLY: do not modify any "
        "files and do not run any write or shell commands.\n\n"
        f"# Task\n"
        f"- Title: {task.title}\n"
        f"- Type: {task.task_type}\n"
        f"- Priority: {task.priority}\n"
        f"- Description: {task.description}\n"
        f"- Acceptance criteria: {', '.join(task.acceptance_criteria) or '(none)'}\n\n"
        "# Diff under review\n"
        f"```diff\n{diff or '(empty diff)'}\n```\n\n"
        "# Output format\n"
        "Verdict: approved | request_changes\n"
        "Summary: <one paragraph>\n"
        "## Findings\n"
        "- [P0|P1|P2|P3] <file>:<line> <message>\n"
        "  (omit the line number if unknown)"
    )


_FINDING_RE = re.compile(r"^\s*[-*]\s*\[?(P[0-3])\]?\s*(.*)$", re.IGNORECASE)


def _split_finding(rest: str) -> tuple[str | None, int | None, str]:
    location_match = re.match(r"^([^\s:]+)(?::(\d+))?\s+(.*)$", rest.strip())
    if location_match:
        file_name, line_text, message = location_match.groups()
        line = int(line_text) if line_text is not None else None
        return file_name, line, message
    return None, None, rest.strip()


def _extract_summary(text: str) -> str:
    match = re.search(r"^\s*summary\s*[:=]\s*(.*)$", text, re.IGNORECASE | re.MULTILINE)
    if match:
        return match.group(1).strip()
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return " ".join(lines[:3])[:300]


def parse_review(text: str) -> ReviewReport:
    findings: list[ReviewFinding] = []
    for line in text.splitlines():
        match = _FINDING_RE.match(line)
        if not match:
            continue
        severity = Severity(match.group(1).upper())
        file_name, line_number, message = _split_finding(match.group(2))
        findings.append(
            ReviewFinding(severity=severity, message=message, file=file_name, line=line_number)
        )
    verdict = (
        "approved"
        if re.search(r"verdict\s*[:=]\s*approved", text, re.IGNORECASE)
        else "request_changes"
    )
    if verdict == "approved" and any(
        finding.severity in (Severity.P0, Severity.P1) for finding in findings
    ):
        verdict = "request_changes"
    return ReviewReport(verdict=verdict, summary=_extract_summary(text), findings=findings)


class Reviewer:
    """Independent reviewer driving an injected read-only engine."""

    def __init__(self, engine: ReviewEngineLike) -> None:
        self._engine = engine

    async def review(self, task: DevelopmentTask, diff: str) -> ReviewReport:
        prompt = build_review_prompt(task, diff)
        text_parts: list[str] = []
        try:
            async for event in self._engine.submit_message(prompt):
                if isinstance(event, AssistantTextDelta):
                    text_parts.append(event.text)
        except Exception as exc:
            raise AdapterError(f"Reviewer 引擎失败：{exc}") from exc
        return parse_review("".join(text_parts))
