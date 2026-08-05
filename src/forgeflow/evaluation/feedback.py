"""Data feedback loop: Trace -> segment -> classify -> samples & preference pairs.

Spec §13 M9.  No claim of model post-training is made here — samples are
produced with provenance so they can be inspected and reused later.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

from forgeflow.trace.events import SpanEvent, new_event_id, now_iso
from forgeflow.trace.redaction import redact


@dataclass(frozen=True)
class ExperienceSample:
    id: str
    task_id: str
    run_id: str
    source_type: str  # "turn" | "event"
    classification: str  # "success" | "failure"
    content: str  # redacted
    tags: tuple[str, ...] = ()
    provenance: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class PreferencePair:
    chosen: ExperienceSample
    rejected: ExperienceSample
    rationale: str = ""


@dataclass(frozen=True)
class FeedbackDataset:
    id: str
    version: str
    samples: tuple[ExperienceSample, ...] = ()
    preference_pairs: tuple[PreferencePair, ...] = ()


def _sample_from_dict(data: dict[str, Any]) -> ExperienceSample:
    return ExperienceSample(
        id=str(data["id"]),
        task_id=str(data["task_id"]),
        run_id=str(data["run_id"]),
        source_type=str(data["source_type"]),
        classification=str(data["classification"]),
        content=str(data["content"]),
        tags=tuple(str(item) for item in data.get("tags", [])),
        provenance={str(k): str(v) for k, v in dict(data.get("provenance", {})).items()},
    )


def dataset_to_json(dataset: FeedbackDataset) -> str:
    """Serialize a FeedbackDataset to JSON (for archiving/seeding)."""
    return json.dumps(asdict(dataset), ensure_ascii=False, indent=2)


def dataset_from_json(text: str) -> FeedbackDataset:
    """Load a FeedbackDataset from JSON produced by ``dataset_to_json``."""
    data = json.loads(text)
    return FeedbackDataset(
        id=str(data["id"]),
        version=str(data["version"]),
        samples=tuple(_sample_from_dict(item) for item in data.get("samples", [])),
        preference_pairs=tuple(
            PreferencePair(
                chosen=_sample_from_dict(item["chosen"]),
                rejected=_sample_from_dict(item["rejected"]),
                rationale=str(item.get("rationale", "")),
            )
            for item in data.get("preference_pairs", [])
        ),
    )


def merge_datasets(datasets: list[FeedbackDataset]) -> FeedbackDataset:
    """Merge multiple datasets into one (archiving keeps them reusable by retrieval)."""
    samples = tuple(sample for dataset in datasets for sample in dataset.samples)
    pairs = tuple(pair for dataset in datasets for pair in dataset.preference_pairs)
    first = datasets[0] if datasets else None
    return FeedbackDataset(
        id=f"{first.id}-merged" if first is not None else "feedback-empty",
        version=now_iso(),
        samples=samples,
        preference_pairs=pairs,
    )


def segment_trace(events: list[SpanEvent]) -> list[list[SpanEvent]]:
    """Group events into segments: each model turn is one segment; others standalone."""
    segments: list[list[SpanEvent]] = []
    current: list[SpanEvent] = []
    in_turn = False
    for event in events:
        if event.event_type == "model_turn_started":
            current = [event]
            in_turn = True
            continue
        if in_turn:
            current.append(event)
            if event.event_type == "model_turn_completed":
                segments.append(current)
                current = []
                in_turn = False
            continue
        segments.append([event])
    if in_turn and current:
        segments.append(current)
    return segments


def classify_segment(segment: list[SpanEvent]) -> str:
    for event in segment:
        if event.status == "error" or event.error_type is not None:
            return "failure"
    return "success"


def _is_turn(segment: list[SpanEvent]) -> bool:
    return any(event.event_type in ("model_turn_started", "model_turn_completed") for event in segment)


def _extract_tags(segment: list[SpanEvent]) -> tuple[str, ...]:
    tags: list[str] = []
    for event in segment:
        tool = event.metadata.get("tool")
        if tool:
            tags.append(f"tool:{tool}")
    if _is_turn(segment):
        tags.append("turn")
    return tuple(sorted(set(tags)))


def build_preference_pairs(samples: list[ExperienceSample]) -> list[PreferencePair]:
    """Pair each failure with a same-source-type success (deterministic)."""
    successes = [sample for sample in samples if sample.classification == "success"]
    failures = [sample for sample in samples if sample.classification == "failure"]
    pairs: list[PreferencePair] = []
    for failure in failures:
        match = next(
            (
                sample
                for sample in successes
                if sample.source_type == failure.source_type
                and (set(sample.tags) & set(failure.tags))
            ),
            None,
        )
        if match is None:
            match = next(
                (sample for sample in successes if sample.source_type == failure.source_type), None
            )
        if match is not None:
            pairs.append(
                PreferencePair(
                    chosen=match,
                    rejected=failure,
                    rationale=f"{failure.source_type} 成功 vs 失败样本配对",
                )
            )
    return pairs


class TraceSampleBuilder:
    """Build a FeedbackDataset (samples + preference pairs) from a task trace."""

    def build(
        self,
        *,
        task_id: str,
        run_id: str,
        events: list[SpanEvent],
        provenance: dict[str, str],
    ) -> FeedbackDataset:
        samples: list[ExperienceSample] = []
        for segment in segment_trace(events):
            content = redact(json.dumps([asdict(event) for event in segment], ensure_ascii=False))
            samples.append(
                ExperienceSample(
                    id=new_event_id(),
                    task_id=task_id,
                    run_id=run_id,
                    source_type="turn" if _is_turn(segment) else "event",
                    classification=classify_segment(segment),
                    content=content,
                    tags=_extract_tags(segment),
                    provenance=dict(provenance),
                )
            )
        pairs = build_preference_pairs(samples)
        return FeedbackDataset(
            id=f"feedback-{task_id}",
            version=now_iso(),
            samples=tuple(samples),
            preference_pairs=tuple(pairs),
        )
