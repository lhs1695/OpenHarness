"""Historical experience retrieval (spec §13 M9 — before/after comparison)."""

from __future__ import annotations

import re
from typing import Any

from forgeflow.evaluation.feedback import ExperienceSample, FeedbackDataset


def _term_set(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9_]+", text.lower()))


def _score(query: str, sample: ExperienceSample) -> int:
    query_terms = _term_set(query)
    content_terms = _term_set(sample.content)
    tag_terms = set(sample.tags)
    return len(query_terms & (content_terms | tag_terms))


def retrieve_experience(
    query: str,
    dataset: FeedbackDataset,
    *,
    top_k: int = 3,
    classification: str | None = None,
) -> list[ExperienceSample]:
    """Return the most relevant samples for a query (keyword-overlap scoring)."""
    candidates = [
        sample
        for sample in dataset.samples
        if classification is None or sample.classification == classification
    ]
    ranked = sorted(candidates, key=lambda sample: _score(query, sample), reverse=True)
    return ranked[:top_k]


def build_retrieval_context(
    query: str, dataset: FeedbackDataset, *, top_k: int = 3
) -> str:
    """Render retrieved successful samples as injectable strategy context."""
    samples = retrieve_experience(query, dataset, top_k=top_k, classification="success")
    if not samples:
        return ""
    lines = ["# 历史经验参考（检索自反馈数据集）", ""]
    for index, sample in enumerate(samples, 1):
        lines.append(f"## 经验 {index}（{sample.source_type} / 成功）")
        lines.append(f"- 来源：task {sample.task_id} · run {sample.run_id}")
        lines.append(sample.content)
    return "\n".join(lines)


def retrieval_comparison(
    query: str, dataset: FeedbackDataset, *, top_k: int = 3
) -> dict[str, Any]:
    """Summarize what retrieval would inject (for the before/after comparison)."""
    retrieved = retrieve_experience(query, dataset, top_k=top_k)
    return {
        "query": query,
        "retrieved_count": len(retrieved),
        "retrieved_ids": [sample.id for sample in retrieved],
        "sources": [{"task_id": s.task_id, "run_id": s.run_id} for s in retrieved],
    }
