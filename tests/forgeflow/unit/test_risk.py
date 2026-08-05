"""Risk scoring tests — every rule must produce an explainable reason."""

from forgeflow.domain.policy import RepositoryPolicy
from forgeflow.domain.risk import (
    RiskInputs,
    RiskLevel,
    RiskScorer,
    risk_level,
)

SENSITIVE = RepositoryPolicy(
    repository="billing-service",
    sensitive_paths=["src/payment/**", "src/auth/**", "migrations/**"],
)


def test_risk_level_boundaries() -> None:
    assert risk_level(0) is RiskLevel.LOW
    assert risk_level(29) is RiskLevel.LOW
    assert risk_level(30) is RiskLevel.MEDIUM
    assert risk_level(59) is RiskLevel.MEDIUM
    assert risk_level(60) is RiskLevel.HIGH
    assert risk_level(79) is RiskLevel.HIGH
    assert risk_level(80) is RiskLevel.SEVERE
    assert risk_level(100) is RiskLevel.SEVERE


def test_clean_change_scores_zero_low() -> None:
    score = RiskScorer().score(RiskInputs(changed_paths=("README.md",)))
    assert score.score == 0
    assert score.level is RiskLevel.LOW
    assert score.reasons == []


def test_sensitive_module_rule() -> None:
    score = RiskScorer().score(
        RiskInputs(changed_paths=("src/payment/charge.py", "README.md")),
        SENSITIVE,
    )
    assert score.score == 20
    assert score.level is RiskLevel.LOW
    assert any("敏感模块" in reason for reason in score.reasons)


def test_migration_and_api_rules() -> None:
    score = RiskScorer().score(
        RiskInputs(
            changed_paths=("migrations/0002_x.py",),
            has_schema_or_migration_change=True,
            has_public_api_change=True,
        )
    )
    assert score.score == 25 + 15
    assert score.level is RiskLevel.MEDIUM


def test_many_files_rule() -> None:
    paths = tuple(f"src/mod{i}.py" for i in range(11))
    score = RiskScorer().score(RiskInputs(changed_paths=paths))
    assert score.score == 10
    assert any("超过 10 个" in reason for reason in score.reasons)


def test_missing_tests_rule() -> None:
    score = RiskScorer().score(RiskInputs(changed_paths=("x.py",), missing_tests=True))
    assert score.score == 15


def test_agent_failure_rule_threshold() -> None:
    assert RiskScorer().score(RiskInputs(agent_failures=1)).score == 0
    assert RiskScorer().score(RiskInputs(agent_failures=2)).score == 10
    assert RiskScorer().score(RiskInputs(agent_failures=3)).score == 10


def test_reviewer_rule() -> None:
    score = RiskScorer().score(RiskInputs(reviewer_high_risk_findings=2))
    assert score.score == 20


def test_docs_tests_only_reduces_score() -> None:
    score = RiskScorer().score(
        RiskInputs(changed_paths=("tests/test_x.py",), is_docs_or_tests_only=True)
    )
    assert score.score == 0  # -10 clamped to 0 by RiskScorer
    assert any("仅文档或测试文件" in reason for reason in score.reasons)


def test_score_clamped_to_range() -> None:
    low = RiskScorer().score(RiskInputs(is_docs_or_tests_only=True))
    assert low.score == 0
    high = RiskScorer().score(
        RiskInputs(
            changed_paths=("src/payment/a.py",),
            has_schema_or_migration_change=True,
            has_public_api_change=True,
            missing_tests=True,
            agent_failures=3,
            reviewer_high_risk_findings=1,
        ),
        SENSITIVE,
    )
    assert high.score == 100
    assert high.level is RiskLevel.SEVERE


def test_combined_score_with_reasons() -> None:
    score = RiskScorer().score(
        RiskInputs(
            changed_paths=("src/payment/charge.py",),
            has_schema_or_migration_change=True,
            missing_tests=True,
            agent_failures=2,
        ),
        SENSITIVE,
    )
    assert score.score == 20 + 25 + 15 + 10
    assert len(score.reasons) == 4
    assert all("（+" in reason or "（-" in reason for reason in score.reasons)
    assert any("Schema 或 Migration" in reason for reason in score.reasons)


def test_path_matching_directory_and_glob() -> None:
    scorer = RiskScorer()
    inputs = RiskInputs(changed_paths=("src/payment/sub/charge.py",))
    score = scorer.score(inputs, SENSITIVE)
    assert score.score == 20  # "src/payment/**" matches nested path


def test_sensitive_path_uses_forward_slash_normalization() -> None:
    scorer = RiskScorer()
    inputs = RiskInputs(changed_paths=(r"src\payment\charge.py",))
    score = scorer.score(inputs, SENSITIVE)
    assert score.score == 20


def test_empty_policy_never_triggers_sensitive_rule() -> None:
    score = RiskScorer().score(RiskInputs(changed_paths=("src/payment/charge.py",)))
    assert score.score == 0
