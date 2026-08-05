"""B4 tests — API authentication and per-owner task filtering."""

from __future__ import annotations

from fastapi.testclient import TestClient

from forgeflow.api.app import build_app
from forgeflow.api.auth import ApiKeyAuthenticator


def _authed_app(make_service) -> TestClient:
    auth = ApiKeyAuthenticator({"secret-a": "alice", "secret-b": "bob"})
    return TestClient(build_app(make_service(), auth=auth))


def test_unauthenticated_request_is_rejected(make_service) -> None:
    client = _authed_app(make_service)
    assert client.get("/api/v1/tasks").status_code == 401
    assert (
        client.post("/api/v1/tasks", json={"repository": "r", "title": "t"}).status_code
        == 401
    )


def test_invalid_key_is_rejected(make_service) -> None:
    client = _authed_app(make_service)
    assert (
        client.get("/api/v1/tasks", headers={"X-API-Key": "wrong"}).status_code == 401
    )


def test_bearer_token_accepted(make_service) -> None:
    client = _authed_app(make_service)
    response = client.get("/api/v1/tasks", headers={"Authorization": "Bearer secret-a"})
    assert response.status_code == 200


def test_authenticated_create_uses_subject_as_owner(make_service) -> None:
    client = _authed_app(make_service)
    response = client.post(
        "/api/v1/tasks",
        json={"repository": "r", "title": "t", "requested_by": "spoofed"},
        headers={"X-API-Key": "secret-a"},
    )
    assert response.status_code == 200
    assert response.json()["requested_by"] == "alice"


def test_list_is_filtered_by_owner(make_service) -> None:
    client = _authed_app(make_service)
    client.post("/api/v1/tasks", json={"repository": "r", "title": "alice's"},
                headers={"X-API-Key": "secret-a"})
    client.post("/api/v1/tasks", json={"repository": "r", "title": "bob's"},
                headers={"X-API-Key": "secret-b"})

    alice_tasks = client.get("/api/v1/tasks", headers={"X-API-Key": "secret-a"}).json()
    bob_tasks = client.get("/api/v1/tasks", headers={"X-API-Key": "secret-b"}).json()
    assert [task["title"] for task in alice_tasks] == ["alice's"]
    assert [task["title"] for task in bob_tasks] == ["bob's"]


def test_open_mode_keeps_legacy_behavior(make_service) -> None:
    client = TestClient(build_app(make_service()))
    created = client.post(
        "/api/v1/tasks", json={"repository": "r", "title": "t", "requested_by": "tester"}
    )
    assert created.status_code == 200
    assert created.json()["requested_by"] == "tester"
    assert len(client.get("/api/v1/tasks").json()) == 1
