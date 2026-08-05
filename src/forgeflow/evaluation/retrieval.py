"""Historical experience retrieval (spec §13 M9 — before/after comparison; PHASE3 A4).

Keyword-overlap scoring over latin terms plus CJK n-grams (so Chinese case
descriptions match without a model).  When the optional ``sentence-transformers``
extra is installed, the top keyword candidates are re-ranked by embedding
similarity (hybrid — PHASE3 A4).
"""

from __future__ import annotations

import importlib.util
import re
from typing import Any

from forgeflow.evaluation.feedback import ExperienceSample, FeedbackDataset

_LATIN_RE = re.compile(r"[a-z0-9_]+")
_CJK_RE = re.compile(r"[一-鿿]")
_NGRAM_N = 2


def _cjk_ngrams(chars: list[str], n: int = _NGRAM_N) -> set[str]:
    if len(chars) < n:
        return {text for text in chars}
    return {"".join(chars[index : index + n]) for index in range(len(chars) - n + 1)}


def _tokenize(text: str) -> set[str]:
    """Latin terms + CJK bigrams, so Chinese content participates in scoring (A4)."""
    latin = set(_LATIN_RE.findall(text.lower()))
    cjk_chars = _CJK_RE.findall(text)
    return latin | _cjk_ngrams(cjk_chars)


def _keyword_score(query: str, sample: ExperienceSample) -> int:
    query_terms = _tokenize(query)
    content_terms = _tokenize(sample.content)
    tag_terms = set(sample.tags)
    return len(query_terms & (content_terms | tag_terms))


def _semantic_available() -> bool:
    return importlib.util.find_spec("sentence_transformers") is not None


_SEMANTIC_MODEL: Any | None = None
_SEMANTIC_FAILED = False


def _semantic_score(query: str, content: str) -> float:
    """Embedding cosine similarity; returns 0.0 if the model is unavailable."""
    global _SEMANTIC_MODEL, _SEMANTIC_FAILED
    if _SEMANTIC_FAILED:
        return 0.0
    if _SEMANTIC_MODEL is None:
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore[import-not-found]

            _SEMANTIC_MODEL = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
        except Exception:  # noqa: BLE001 — model load failure degrades to keyword scoring
            _SEMANTIC_FAILED = True
            return 0.0
    try:
        embeddings = _SEMANTIC_MODEL.encode([query, content], normalize_embeddings=True)
        return float((embeddings[0] * embeddings[1]).sum())
    except Exception:  # noqa: BLE001 — encoding failure degrades to keyword scoring
        return 0.0


def retrieve_experience(
    query: str,
    dataset: FeedbackDataset,
    *,
    top_k: int = 3,
    classification: str | None = None,
    semantic: bool = True,
) -> list[ExperienceSample]:
    """Return the most relevant samples for a query (keyword, optionally hybrid).

    Without the ``retrieval`` extra, keyword-overlap scoring over latin + CJK
    terms is used (A4 中文 n-gram).  With ``sentence-transformers`` installed the
    top keyword candidates are re-ranked by embedding similarity.
    """
    candidates = [
        sample
        for sample in dataset.samples
        if classification is None or sample.classification == classification
    ]
    keyword_ranked = sorted(
        candidates, key=lambda sample: _keyword_score(query, sample), reverse=True
    )
    if not semantic or not _semantic_available():
        return keyword_ranked[:top_k]
    shortlist = keyword_ranked[: max(top_k * 5, 10)]
    semantic_ranked = sorted(
        shortlist,
        key=lambda sample: _semantic_score(query, sample.content),
        reverse=True,
    )
    return semantic_ranked[:top_k]


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
