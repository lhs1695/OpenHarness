"""Transparent, explainable risk scoring (spec §4.3).

Scoring is pure and rule-driven: every rule returns a signed delta plus a
reason, so a RiskScore always carries why it reached that value.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol

from forgeflow.domain.policy import RepositoryPolicy, path_matches


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    SEVERE = "SEVERE"


def risk_level(score: int) -> RiskLevel:
    if score >= 80:
        return RiskLevel.SEVERE
    if score >= 60:
        return RiskLevel.HIGH
    if score >= 30:
        return RiskLevel.MEDIUM
    return RiskLevel.LOW


@dataclass(frozen=True)
class RiskInputs:
    """Facts about a change that risk rules reason over."""

    changed_paths: tuple[str, ...] = ()
    has_schema_or_migration_change: bool = False
    has_public_api_change: bool = False
    is_docs_or_tests_only: bool = False
    missing_tests: bool = False
    agent_failures: int = 0
    reviewer_high_risk_findings: int = 0


@dataclass(frozen=True)
class RiskRuleResult:
    score_delta: int
    reason: str


class RiskRule(Protocol):
    name: str

    def evaluate(self, inputs: RiskInputs, policy: RepositoryPolicy | None) -> RiskRuleResult: ...


class SensitiveModuleRule:
    """+20 when the change touches a repository sensitive path."""

    name = "sensitive_module"

    def evaluate(self, inputs: RiskInputs, policy: RepositoryPolicy | None) -> RiskRuleResult:
        if policy is None or not inputs.changed_paths or not policy.sensitive_paths:
            return RiskRuleResult(0, "")
        touched = [
            path for path in inputs.changed_paths if path_matches(path, policy.sensitive_paths)
        ]
        if touched:
            return RiskRuleResult(
                +20, f"修改敏感模块：{', '.join(sorted(touched))}"
            )
        return RiskRuleResult(0, "")


class MigrationRule:
    """+25 when the change touches schema or migration files."""

    name = "schema_migration"

    def evaluate(self, inputs: RiskInputs, policy: RepositoryPolicy | None) -> RiskRuleResult:
        if inputs.has_schema_or_migration_change:
            return RiskRuleResult(+25, "修改数据库 Schema 或 Migration")
        return RiskRuleResult(0, "")


class PublicApiRule:
    """+15 when the change touches a public API."""

    name = "public_api"

    def evaluate(self, inputs: RiskInputs, policy: RepositoryPolicy | None) -> RiskRuleResult:
        if inputs.has_public_api_change:
            return RiskRuleResult(+15, "修改公共 API")
        return RiskRuleResult(0, "")


class ManyFilesRule:
    """+10 when the change touches more than 10 files."""

    name = "many_files"

    def evaluate(self, inputs: RiskInputs, policy: RepositoryPolicy | None) -> RiskRuleResult:
        if len(inputs.changed_paths) > 10:
            return RiskRuleResult(+10, f"修改文件超过 10 个（{len(inputs.changed_paths)}）")
        return RiskRuleResult(0, "")


class MissingTestsRule:
    """+15 when the change lacks corresponding tests."""

    name = "missing_tests"

    def evaluate(self, inputs: RiskInputs, policy: RepositoryPolicy | None) -> RiskRuleResult:
        if inputs.missing_tests:
            return RiskRuleResult(+15, "缺少对应测试")
        return RiskRuleResult(0, "")


class AgentFailureRule:
    """+10 when the agent failed or fell back multiple times."""

    name = "agent_failures"

    def evaluate(self, inputs: RiskInputs, policy: RepositoryPolicy | None) -> RiskRuleResult:
        if inputs.agent_failures >= 2:
            return RiskRuleResult(+10, f"Agent 多次失败或回退（{inputs.agent_failures} 次）")
        return RiskRuleResult(0, "")


class ReviewerRule:
    """+20 when the reviewer found high-risk issues."""

    name = "reviewer_high_risk"

    def evaluate(self, inputs: RiskInputs, policy: RepositoryPolicy | None) -> RiskRuleResult:
        if inputs.reviewer_high_risk_findings >= 1:
            return RiskRuleResult(
                +20, f"Reviewer 发现高风险问题（{inputs.reviewer_high_risk_findings}）"
            )
        return RiskRuleResult(0, "")


class DocsTestsOnlyRule:
    """-10 for documentation- or test-only changes."""

    name = "docs_tests_only"

    def evaluate(self, inputs: RiskInputs, policy: RepositoryPolicy | None) -> RiskRuleResult:
        if inputs.is_docs_or_tests_only:
            return RiskRuleResult(-10, "仅文档或测试文件")
        return RiskRuleResult(0, "")


DEFAULT_RISK_RULES: tuple[RiskRule, ...] = (
    SensitiveModuleRule(),
    MigrationRule(),
    PublicApiRule(),
    ManyFilesRule(),
    MissingTestsRule(),
    AgentFailureRule(),
    ReviewerRule(),
    DocsTestsOnlyRule(),
)


@dataclass(frozen=True)
class RiskScore:
    """A 0-100 risk score with an explicit, explainable reason list."""

    score: int
    level: RiskLevel
    reasons: list[str] = field(default_factory=list)


class RiskScorer:
    """Applies the configured risk rules and aggregates a RiskScore."""

    def __init__(self, rules: Sequence[RiskRule] | None = None) -> None:
        self._rules = tuple(rules) if rules is not None else DEFAULT_RISK_RULES

    def score(
        self, inputs: RiskInputs, policy: RepositoryPolicy | None = None
    ) -> RiskScore:
        total = 0
        reasons: list[str] = []
        for rule in self._rules:
            result = rule.evaluate(inputs, policy)
            if result.score_delta:
                total += result.score_delta
                reasons.append(f"{result.reason}（{result.score_delta:+d}）")
        total = max(0, min(100, total))
        return RiskScore(score=total, level=risk_level(total), reasons=reasons)
