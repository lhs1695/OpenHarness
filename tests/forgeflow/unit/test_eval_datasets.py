"""Evaluation dataset unit tests."""

from forgeflow.evaluation.datasets import (
    billing_smoke_dataset,
    cart_smoke_dataset,
    default_dataset,
    get_dataset,
)


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
