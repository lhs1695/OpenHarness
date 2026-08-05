"""Unified trace event model (spec §7.5)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4


def new_event_id() -> str:
    return uuid4().hex


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True)
class SpanEvent:
    """A span in the execution trace, linkable into a parent/child tree."""

    event_id: str
    event_type: str
    span_id: str
    timestamp: str
    status: str = "ok"
    parent_event_id: str | None = None
    agent_id: str | None = None
    input_summary: str | None = None
    output_summary: str | None = None
    latency_ms: int | None = None
    token_usage: dict[str, int] | None = None
    estimated_cost: float | None = None
    error_type: str | None = None
    error_message: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


# Nominal per-1M-token prices used for a rough cost estimate (configurable).
DEFAULT_COST_PER_M_INPUT = 3.0
DEFAULT_COST_PER_M_OUTPUT = 15.0


def estimate_cost(
    tokens: dict[str, int],
    *,
    per_m_input: float = DEFAULT_COST_PER_M_INPUT,
    per_m_output: float = DEFAULT_COST_PER_M_OUTPUT,
) -> float:
    """Rough USD cost estimate from token usage (best-effort)."""
    input_tokens = tokens.get("input_tokens", 0)
    output_tokens = tokens.get("output_tokens", 0)
    return (input_tokens / 1_000_000) * per_m_input + (output_tokens / 1_000_000) * per_m_output
