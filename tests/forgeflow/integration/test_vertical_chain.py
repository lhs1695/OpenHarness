"""Vertical chain: DevelopmentTask -> Adapter -> OpenHarness engine -> structured plan.

Online marker: requires a real model API. Skipped by default (`pytest` adds
`-m "not online"`); run with `pytest -m online` and credentials configured.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from forgeflow.domain.task import DevelopmentTask
from forgeflow.integrations.openharness.adapter import OpenHarnessAdapter

pytestmark = pytest.mark.online

FIXTURE_REPO = (
    Path(__file__).resolve().parents[2] / "fixtures" / "repositories" / "billing-service"
)


def _has_api_credentials() -> bool:
    from openharness.config.settings import load_settings

    try:
        load_settings().resolve_auth()
        return True
    except Exception:  # noqa: BLE001 — capability probe: any failure means no creds
        return False


@pytest.mark.asyncio
async def test_vertical_chain_plans_fixture_repo() -> None:
    if not _has_api_credentials():
        pytest.skip("no API credentials available")

    from openharness.ui.runtime import build_runtime, close_runtime

    runtime = await build_runtime(
        cwd=str(FIXTURE_REPO),
        system_prompt=(
            "You are ForgeFlow, a planning agent. You only read and analyze code; "
            "you never modify files."
        ),
        permission_mode="full_auto",
        max_turns=20,  # DeepSeek's planner explores beyond 6 turns on this fixture
        model=os.environ.get("OPENHARNESS_MODEL"),
    )
    task = DevelopmentTask(
        repository="billing-service",
        task_type="bugfix",
        priority="P2",
        title="Fix duplicate charge on client retry",
        description=(
            "The payment endpoint may create a second charge when the client "
            "retries after a timeout."
        ),
        acceptance_criteria=[
            "the same idempotency key produces only one payment record",
            "add a concurrency and retry test",
        ],
        risk_tags=["payment", "idempotency"],
    )
    try:
        plan = await OpenHarnessAdapter().run_plan(task, runtime.engine)
    finally:
        await close_runtime(runtime)

    assert plan.repository == "billing-service"
    assert plan.plan_text
    assert plan.duration_ms >= 0
    assert plan.token_usage is not None
