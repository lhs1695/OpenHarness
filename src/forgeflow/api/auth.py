"""API authentication (PHASE3 B4).

Simple API-key auth: a configured key map (key -> subject) gates the task
endpoints; the authenticated subject becomes the task's ``requested_by`` so task
lists can be filtered per owner.  ``build_app`` only enforces auth when an
authenticator is passed (or configured via env); without one the API stays open
for backwards compatibility.
"""

from __future__ import annotations

from fastapi import Header, HTTPException


class ApiKeyAuthenticator:
    """Validates ``Authorization: Bearer <key>`` / ``X-API-Key`` against key->subject."""

    def __init__(self, keys: dict[str, str]) -> None:
        if not keys:
            raise ValueError("ApiKeyAuthenticator requires at least one key")
        self._subjects = dict(keys)

    def subject_for(self, token: str | None) -> str | None:
        if not token:
            return None
        return self._subjects.get(token.strip())

    async def __call__(
        self,
        authorization: str | None = Header(default=None),
        x_api_key: str | None = Header(default=None),
    ) -> str:
        token = x_api_key
        if token is None and authorization:
            token = authorization.removeprefix("Bearer ").strip()
        subject = self.subject_for(token)
        if subject is None:
            raise HTTPException(status_code=401, detail="invalid or missing API key")
        return subject


async def _open_subject() -> str:
    """No-auth dependency: returns an empty subject so the caller's identity is kept."""
    return ""
