"""Feedback registry unit tests — versioning."""

import pytest

from forgeflow.evaluation.feedback import FeedbackDataset
from forgeflow.evaluation.registry import DatasetNotFoundError, FeedbackRegistry


def _dataset(version: str) -> FeedbackDataset:
    return FeedbackDataset(id="billing-feedback", version=version)


def test_register_get_and_list() -> None:
    registry = FeedbackRegistry()
    dataset = _dataset("2026-08-05")
    registry.register(dataset)
    assert registry.get("billing-feedback", "2026-08-05") is dataset
    assert registry.list() == [dataset]


def test_versioned_registration() -> None:
    registry = FeedbackRegistry()
    registry.register(_dataset("2026-08-05"))
    registry.register(_dataset("2026-08-06"))
    assert registry.get("billing-feedback", "2026-08-05").version == "2026-08-05"
    assert registry.latest("billing-feedback").version == "2026-08-06"


def test_unknown_dataset_raises() -> None:
    registry = FeedbackRegistry()
    with pytest.raises(DatasetNotFoundError):
        registry.get("nope", "1.0")
    with pytest.raises(DatasetNotFoundError):
        registry.latest("nope")
