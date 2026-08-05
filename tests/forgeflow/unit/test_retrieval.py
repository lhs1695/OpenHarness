"""Historical experience retrieval unit tests."""

from forgeflow.evaluation.feedback import ExperienceSample, FeedbackDataset
from forgeflow.evaluation.retrieval import (
    _tokenize,
    build_retrieval_context,
    retrieval_comparison,
    retrieve_experience,
)


def _sample(id_: str, content: str, tags: tuple[str, ...] = ()) -> ExperienceSample:
    return ExperienceSample(
        id=id_,
        task_id="t",
        run_id="r",
        source_type="event",
        classification="success",
        content=content,
        tags=tags,
    )


def _dataset() -> FeedbackDataset:
    return FeedbackDataset(
        id="d",
        version="1.0",
        samples=(
            _sample("s1", "add idempotency key check to payment charge"),
            _sample("s2", "configure docker compose for postgres and redis"),
            _sample("s3", "refactor checkout discount calculation"),
        ),
    )


def test_retrieve_returns_relevant_samples() -> None:
    dataset = _dataset()
    results = retrieve_experience("idempotency payment", dataset, top_k=2)
    assert results
    assert results[0].id == "s1"  # most relevant to idempotency payment


def test_retrieve_respects_top_k_and_classification() -> None:
    dataset = _dataset()
    assert len(retrieve_experience("docker", dataset, top_k=5)) == 3
    # classification filter: all samples are 'success'; 'failure' returns none
    assert retrieve_experience("docker", dataset, classification="failure") == []


def test_build_retrieval_context() -> None:
    dataset = _dataset()
    context = build_retrieval_context("idempotency", dataset, top_k=1)
    assert "历史经验参考" in context
    assert "idempotency key" in context


def test_build_retrieval_context_empty_when_no_match() -> None:
    empty = FeedbackDataset(id="d", version="1.0", samples=())
    assert build_retrieval_context("anything", empty) == ""


def test_retrieval_comparison_summary() -> None:
    dataset = _dataset()
    summary = retrieval_comparison("payment", dataset, top_k=2)
    assert summary["retrieved_count"] == 2
    assert summary["retrieved_ids"]
    assert summary["sources"][0]["task_id"] == "t"


def test_tokenize_includes_cjk_bigrams() -> None:
    terms = _tokenize("客户端超时重试 payment 幂等")
    assert "payment" in terms
    assert "客户" in terms  # bigram of 客户端
    assert "户端" in terms
    assert "幂等" in terms


def test_chinese_query_matches_chinese_content() -> None:
    dataset = FeedbackDataset(
        id="d",
        version="1.0",
        samples=(
            _sample("cn", "charge 在已存在幂等记录时直接返回，不新增记录"),
            _sample("en", "add idempotency key check to payment charge"),
        ),
    )
    results = retrieve_experience("重复扣款 幂等键", dataset, top_k=1)
    assert results[0].id == "cn", "CJK n-gram scoring should surface the Chinese sample"


def test_retrieve_falls_back_without_semantic_extra() -> None:
    """Without sentence-transformers the keyword path must still work (no crash)."""
    dataset = _dataset()
    results = retrieve_experience("idempotency", dataset, top_k=1, semantic=True)
    assert results[0].id == "s1"
