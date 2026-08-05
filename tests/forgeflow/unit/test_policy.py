"""RepositoryPolicy model tests."""

from forgeflow.domain.policy import RepositoryPolicy


def test_policy_defaults() -> None:
    policy = RepositoryPolicy(repository="billing-service")
    assert policy.sensitive_paths == []
    assert policy.max_changed_files == 12
    assert policy.max_execution_minutes == 45
    assert policy.max_agent_steps == 40
    assert policy.approval_rules == {}
    assert policy.model_strategy == "default"


def test_policy_custom_values() -> None:
    policy = RepositoryPolicy(
        repository="billing-service",
        sensitive_paths=["src/payment/**", "migrations/**"],
        forbidden_commands=["git push --force", "rm -rf"],
        required_commands=["pytest -q", "ruff check ."],
        max_changed_files=5,
        approval_rules={"payment_change": ["backend_owner", "qa"]},
    )
    assert "src/payment/**" in policy.sensitive_paths
    assert policy.max_changed_files == 5
    assert policy.approval_rules["payment_change"] == ["backend_owner", "qa"]
