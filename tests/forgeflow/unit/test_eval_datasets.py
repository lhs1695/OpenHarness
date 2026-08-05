"""Evaluation dataset unit tests."""

from forgeflow.evaluation.datasets import (
    EvalCase,
    billing_smoke_dataset,
    cart_smoke_dataset,
    default_dataset,
    get_dataset,
)


def test_eval_case_metadata_provenance_roundtrip() -> None:
    case = EvalCase(
        case_id="billing-001",
        repository="billing-service",
        title="修复重复扣款",
        metadata={"issue_url": "https://github.com/acme/billing/issues/1", "author": "tester"},
    )
    assert case.metadata["issue_url"].endswith("/issues/1")
    assert case.metadata["author"] == "tester"


def test_eval_case_metadata_defaults_empty() -> None:
    case = EvalCase(case_id="x", repository="r", title="t")
    assert case.metadata == {}


def test_billing_dataset_is_versioned() -> None:
    dataset = billing_smoke_dataset()
    assert dataset.version == "2026-08-05"
    assert len(dataset.cases) >= 5
    assert all(case.repository == "billing-service" for case in dataset.cases)


def test_cart_dataset_has_clean_cases() -> None:
    dataset = cart_smoke_dataset()
    assert len(dataset.cases) >= 1
    assert all(case.task_type == "verify" for case in dataset.cases)


def test_default_dataset_combines_both() -> None:
    dataset = default_dataset()
    assert len(dataset.cases) == len(billing_smoke_dataset().cases) + len(cart_smoke_dataset().cases)
    repositories = {case.repository for case in dataset.cases}
    assert {"billing-service", "cart-service"} <= repositories


def test_get_dataset_known_and_unknown() -> None:
    assert get_dataset("default").id == "default"
    try:
        get_dataset("nope")
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


def test_issues_attrs_dataset_has_real_provenance() -> None:
    dataset = get_dataset("issues-attrs")
    assert len(dataset.cases) >= 20
    for case in dataset.cases:
        assert case.metadata["issue_url"].startswith(
            f"https://github.com/{case.repository}/issues/"
        )
        assert case.metadata["issue_id"]
        assert case.metadata["author"]
        assert case.acceptance_rules
        assert case.tags
        assert case.title


def test_issues_attrs_cases_have_distinct_real_issues() -> None:
    dataset = get_dataset("issues-attrs")
    issue_ids = {case.metadata["issue_id"] for case in dataset.cases}
    assert len(issue_ids) == len(dataset.cases), "each case must reference a distinct issue"
    urls = {case.metadata["issue_url"] for case in dataset.cases}
    assert len(urls) == len(dataset.cases)
