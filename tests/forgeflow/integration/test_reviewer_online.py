"""Online reviewer integration — real read-only review (skipped by default).

Run with ``pytest -m online`` and API credentials configured.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from forgeflow.domain.task import DevelopmentTask
from forgeflow.quality.reviewer import Reviewer, build_review_engine

pytestmark = pytest.mark.online

FIXTURE_REPO = (
    Path(__file__).resolve().parents[2] / "fixtures" / "repositories" / "billing-service"
)

SAMPLE_DIFF = """--- a/payment.py
+++ b/payment.py
@@ -1,3 +1,4 @@
 def charge(order_id: str, amount: int) -> PaymentRecord:
+    # no idempotency guard
     record = PaymentRecord(id=uuid4().hex, order_id=order_id, amount=amount)
     _charges[record.id] = record
     return record
"""


def _has_api_credentials() -> bool:
    from openharness.config.settings import load_settings

    try:
        load_settings().resolve_auth()
        return True
    except Exception:  # noqa: BLE001 — capability probe: any failure means no creds
        return False


@pytest.mark.asyncio
async def test_reviewer_online_read_only() -> None:
    if not _has_api_credentials():
        pytest.skip("no API credentials available")

    from openharness.ui.runtime import build_runtime, close_runtime

    runtime = await build_runtime(
        cwd=str(FIXTURE_REPO),
        system_prompt="You are a code reviewer.",
        permission_mode="full_auto",
        max_turns=4,
        model=os.environ.get("OPENHARNESS_MODEL"),
    )
    task = DevelopmentTask(
        repository="billing-service",
        task_type="bugfix",
        title="Fix duplicate charge",
        description="retries create a second charge",
        risk_tags=["payment"],
    )
    try:
        engine = build_review_engine(
            runtime.api_client,
            cwd=str(FIXTURE_REPO),
            model=runtime.engine.model,
            system_prompt="You are an independent senior code reviewer.",
            max_turns=4,
        )
        report = await Reviewer(engine).review(task, SAMPLE_DIFF)
    finally:
        await close_runtime(runtime)

    assert report.summary
    assert report.verdict in ("approved", "request_changes")
