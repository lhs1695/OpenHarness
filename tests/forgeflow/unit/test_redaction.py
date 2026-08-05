"""Redaction unit tests (spec §7.5, §11)."""

from forgeflow.trace.redaction import REDACTED, redact, redact_payload


def test_redacts_sk_token() -> None:
    assert "sk-abcdef1234567890" not in redact("key = 'sk-abcdef1234567890'")
    assert REDACTED in redact("key = 'sk-abcdef1234567890'")


def test_redacts_aws_key() -> None:
    assert REDACTED in redact("AKIAIOSFODNN7EXAMPLE")


def test_redacts_assignment() -> None:
    assert "api_key" not in redact("api_key = 'supersecretvalue123'").split(REDACTED)[1]


def test_redacts_email() -> None:
    assert "user@example.com" not in redact("contact user@example.com")
    assert REDACTED in redact("contact user@example.com")


def test_redact_leaves_plain_text() -> None:
    assert redact("def add(a, b):\n    return a + b\n") == "def add(a, b):\n    return a + b\n"


def test_redact_payload_recursive() -> None:
    payload = {
        "text": "token='sk-abcdef1234567890'",
        "nested": {"email": "a@b.com"},
        "items": ["sk-abcdef1234567890"],
        "count": 3,
    }
    result = redact_payload(payload)
    assert REDACTED in result["text"]
    assert REDACTED in result["nested"]["email"]
    assert REDACTED in result["items"][0]
    assert result["count"] == 3
