"""API integration tests — CRUD via TestClient, start + SSE via a live uvicorn server."""

from __future__ import annotations

import threading
import time

import httpx
import pytest
import uvicorn
from fastapi.testclient import TestClient

from forgeflow.api.app import build_app


@pytest.fixture
def client(make_service) -> TestClient:
    return TestClient(build_app(make_service()))


def test_create_and_get_task(client: TestClient) -> None:
    response = client.post(
        "/api/v1/tasks", json={"repository": "billing-service", "title": "fix dup"}
    )
    assert response.status_code == 200
    task_id = response.json()["id"]
    got = client.get(f"/api/v1/tasks/{task_id}")
    assert got.status_code == 200
    assert got.json()["repository"] == "billing-service"
    assert got.json()["status"] == "DRAFT"


def test_list_tasks(client: TestClient) -> None:
    client.post("/api/v1/tasks", json={"repository": "r", "title": "one"})
    client.post("/api/v1/tasks", json={"repository": "r", "title": "two"})
    assert len(client.get("/api/v1/tasks").json()) == 2


def test_get_missing_task_returns_404(client: TestClient) -> None:
    assert client.get("/api/v1/tasks/nope").status_code == 404


def test_index_serves_management_ui(client: TestClient) -> None:
    """PHASE3 收尾4: the root route serves the simple management UI."""
    response = client.get("/")
    assert response.status_code == 200
    assert "ForgeFlow 管理台" in response.text
    assert "/api/v1" in response.text


def test_cancel_returns_200(client: TestClient) -> None:
    task_id = client.post("/api/v1/tasks", json={"repository": "r", "title": "t"}).json()["id"]
    response = client.post(f"/api/v1/tasks/{task_id}/cancel")
    assert response.status_code == 200


class _Server:
    def __init__(self, app) -> None:
        self._config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="error")
        self._server = uvicorn.Server(self._config)
        self._thread = threading.Thread(target=self._server.run, daemon=True)
        self.url = ""

    def start(self) -> None:
        self._thread.start()
        for _ in range(200):
            if self._server.started:
                break
            time.sleep(0.05)
        if not self._server.started:
            raise RuntimeError("uvicorn failed to start")
        _, port = self._server.servers[0].sockets[0].getsockname()
        self.url = f"http://127.0.0.1:{port}"

    def stop(self) -> None:
        self._server.should_exit = True
        self._thread.join(timeout=5)


@pytest.fixture
def live(make_service):
    server = _Server(build_app(make_service()))
    server.start()
    yield server.url
    server.stop()


def test_start_task_and_sse(live: str) -> None:
    with httpx.Client(timeout=30) as client:
        task_id = client.post(
            f"{live}/api/v1/tasks", json={"repository": "r", "title": "t"}
        ).json()["id"]

        with client.stream("GET", f"{live}/api/v1/tasks/{task_id}/events") as response:
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/event-stream")
            time.sleep(0.2)  # let the server-side subscription register
            client.post(f"{live}/api/v1/tasks/{task_id}/start")
            seen_state_change = False
            for line in response.iter_lines():
                if "task_state_changed" in line:
                    seen_state_change = True
                    break
            assert seen_state_change

        status = ""
        for _ in range(50):
            status = client.get(f"{live}/api/v1/tasks/{task_id}").json()["status"]
            if status == "COMPLETED":
                break
            time.sleep(0.05)
        assert status == "COMPLETED"


def test_approval_flow_via_api(live: str) -> None:
    with httpx.Client(timeout=30) as client:
        task_id = client.post(
            f"{live}/api/v1/tasks",
            json={"repository": "r", "title": "high-risk", "initial_risk_score": 70},
        ).json()["id"]
        client.post(f"{live}/api/v1/tasks/{task_id}/start")

        # Two-stage flow (P1-5): PLAN approval first, then FINAL after review.
        for _ in range(50):
            status = client.get(f"{live}/api/v1/tasks/{task_id}").json()["status"]
            if status == "WAITING_PLAN_APPROVAL":
                break
            time.sleep(0.05)
        assert status == "WAITING_PLAN_APPROVAL"

        plan_approvals = client.get(f"{live}/api/v1/tasks/{task_id}/approvals").json()
        assert len(plan_approvals) == 1  # PLAN only at this gate
        response = client.post(
            f"{live}/api/v1/approvals/{plan_approvals[0]['id']}/approve",
            json={"approved": True, "resolved_by": "owner", "reason": "ok"},
        )
        assert response.status_code == 200

        # Execution + review happen, then the task waits for FINAL approval.
        for _ in range(50):
            status = client.get(f"{live}/api/v1/tasks/{task_id}").json()["status"]
            if status == "WAITING_FINAL_APPROVAL":
                break
            time.sleep(0.05)
        assert status == "WAITING_FINAL_APPROVAL"

        final_approvals = client.get(f"{live}/api/v1/tasks/{task_id}/approvals").json()
        assert len(final_approvals) == 2  # approved PLAN + pending FINAL
        pending_final = next(
            approval for approval in final_approvals if approval["approval_type"] == "final"
        )
        response = client.post(
            f"{live}/api/v1/approvals/{pending_final['id']}/approve",
            json={"approved": True, "resolved_by": "owner", "reason": "ok"},
        )
        assert response.status_code == 200

        for _ in range(50):
            status = client.get(f"{live}/api/v1/tasks/{task_id}").json()["status"]
            if status == "COMPLETED":
                break
            time.sleep(0.05)
        assert status == "COMPLETED"


def test_timeline_and_trace_endpoints(live: str) -> None:
    with httpx.Client(timeout=30) as client:
        task_id = client.post(
            f"{live}/api/v1/tasks", json={"repository": "r", "title": "t"}
        ).json()["id"]
        client.post(f"{live}/api/v1/tasks/{task_id}/start")
        for _ in range(50):
            if client.get(f"{live}/api/v1/tasks/{task_id}").json()["status"] == "COMPLETED":
                break
            time.sleep(0.05)

        timeline = client.get(f"{live}/api/v1/tasks/{task_id}/timeline").json()
        assert timeline
        assert any(item["event_type"] == "task_state_changed" for item in timeline)

        trace = client.get(f"{live}/api/v1/tasks/{task_id}/trace").text
        assert "task_state_changed" in trace
