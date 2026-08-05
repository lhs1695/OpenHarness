"""Sensitive-data redaction for trace payloads (spec §7.5, §11)."""

from __future__ import annotations

import re
from typing import Any

_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)\bsk-[A-Za-z0-9]{16,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"(?i)\b(api[_-]?key|secret|token|password|passwd)\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{8,}"),
    re.compile(r"(?i)\b[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}\b"),
)

REDACTED = "<redacted>"


def redact(text: str) -> str:
    """Replace secret-like substrings in ``text`` with <redacted>."""
    result = text
    for pattern in _PATTERNS:
        result = pattern.sub(REDACTED, result)
    return result


def redact_payload(value: Any) -> Any:
    """Recursively redact strings inside a JSON-like payload."""
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, dict):
        return {key: redact_payload(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_payload(item) for item in value]
    return value
