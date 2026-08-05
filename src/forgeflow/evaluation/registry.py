"""Versioned feedback dataset registry (spec §8.9)."""

from __future__ import annotations

from forgeflow.evaluation.feedback import FeedbackDataset


class DatasetNotFoundError(KeyError):
    pass


class FeedbackRegistry:
    """Register and retrieve versioned feedback datasets."""

    def __init__(self) -> None:
        self._datasets: dict[tuple[str, str], FeedbackDataset] = {}

    def register(self, dataset: FeedbackDataset) -> None:
        self._datasets[(dataset.id, dataset.version)] = dataset

    def get(self, dataset_id: str, version: str) -> FeedbackDataset:
        key = (dataset_id, version)
        if key not in self._datasets:
            raise DatasetNotFoundError(f"dataset {dataset_id} v{version} not found")
        return self._datasets[key]

    def latest(self, dataset_id: str) -> FeedbackDataset:
        versions = [version for (did, version) in self._datasets if did == dataset_id]
        if not versions:
            raise DatasetNotFoundError(f"no datasets for {dataset_id}")
        return self._datasets[(dataset_id, max(versions))]

    def list(self) -> list[FeedbackDataset]:
        return list(self._datasets.values())
