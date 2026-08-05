"""Feedback pipeline unit tests — segmentation, classification, samples, pairs."""

from forgeflow.evaluation.feedback import (
    TraceSampleBuilder,
    build_preference_pairs,
    classify_segment,
    segment_trace,
)
from forgeflow.trace.events import SpanEvent

PROVENANCE = {
    "dataset_version": "2026-08-05",
    "case_id": "billing-001",
    "repository": "billing-service",
}


def _events() -> list[SpanEvent]:
    return [
        SpanEvent(event_id="e1", event_type="model_turn_started", span_id="s1", timestamp="t1"),
        SpanEvent(
            event_id="e2",
            event_type="tool_completed",
            span_id="s2",
            parent_event_id="s1",
            timestamp="t2",
            status="ok",
            metadata={"tool": "grep"},
        ),
        SpanEvent(
            event_id="e3",
            event_type="model_turn_completed",
            span_id="s1",
            timestamp="t3",
            token_usage={"input_tokens": 10, "output_tokens": 5},
        ),
        SpanEvent(
            event_id="e4",
            event_type="tool_completed",
            span_id="s3",
            timestamp="t4",
            status="error",
            metadata={"tool": "bash"},
        ),
        SpanEvent(event_id="e5", event_type="command_finished", span_id="s4", timestamp="t5", status="ok"),
    ]


def test_segment_trace_groups_turns() -> None:
    segments = segment_trace(_events())
    assert len(segments) == 3
    assert [event.event_type for event in segments[0]] == [
        "model_turn_started",
        "tool_completed",
        "model_turn_completed",
    ]
    assert segments[1][0].event_type == "tool_completed"  # standalone failure
    assert segments[2][0].event_type == "command_finished"


def test_classify_segment() -> None:
    segments = segment_trace(_events())
    assert classify_segment(segments[0]) == "success"
    assert classify_segment(segments[1]) == "failure"
    assert classify_segment(segments[2]) == "success"


def test_build_samples_with_provenance() -> None:
    builder = TraceSampleBuilder()
    dataset = builder.build(
        task_id="task_1", run_id="run_1", events=_events(), provenance=PROVENANCE
    )
    assert len(dataset.samples) == 3
    assert all(sample.provenance == PROVENANCE for sample in dataset.samples)
    assert all(sample.task_id == "task_1" for sample in dataset.samples)
    classifications = {sample.classification for sample in dataset.samples}
    assert classifications == {"success", "failure"}
    # turn sample is redacted JSON content
    turn_sample = next(sample for sample in dataset.samples if sample.source_type == "turn")
    assert '"event_type"' in turn_sample.content
    assert turn_sample.tags == ("tool:grep", "turn")


def test_preference_pairs_pair_failure_with_success() -> None:
    builder = TraceSampleBuilder()
    dataset = builder.build(
        task_id="task_1", run_id="run_1", events=_events(), provenance=PROVENANCE
    )
    assert len(dataset.preference_pairs) >= 1
    pair = dataset.preference_pairs[0]
    assert pair.chosen.classification == "success"
    assert pair.rejected.classification == "failure"
    assert pair.chosen.source_type == pair.rejected.source_type


def test_build_preference_pairs_empty_without_failures() -> None:
    from forgeflow.evaluation.feedback import ExperienceSample

    successes = [
        ExperienceSample(
            id="s1", task_id="t", run_id="r", source_type="turn", classification="success", content="x"
        )
    ]
    assert build_preference_pairs(successes) == []


def test_redaction_applied_to_sample_content() -> None:
    secret_event = SpanEvent(
        event_id="e6",
        event_type="tool_completed",
        span_id="s5",
        timestamp="t6",
        output_summary="TOKEN=sk-abcdef1234567890",
    )
    dataset = TraceSampleBuilder().build(
        task_id="task_1", run_id="run_1", events=[secret_event], provenance=PROVENANCE
    )
    assert "sk-abcdef1234567890" not in dataset.samples[0].content
