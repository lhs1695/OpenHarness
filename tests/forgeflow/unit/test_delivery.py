"""Delivery unit tests — patch + Draft PR guard."""

import pytest

from forgeflow.orchestration.delivery import (
    DeliveryService,
    DraftPrGuardError,
    make_patch,
)


def test_make_patch() -> None:
    patch = make_patch(
        repository="billing-service",
        diff="--- a\n+++ b\n",
        changed_files=["a.py"],
    )
    assert patch.repository == "billing-service"
    assert patch.changed_files == ["a.py"]
    assert patch.generated_at


def test_draft_pr_allowed_for_test_repo() -> None:
    service = DeliveryService(test_repositories=["billing-service"])
    patch = make_patch(repository="billing-service", diff="+x", changed_files=["a.py"])
    pr = service.create_draft_pr(repository="billing-service", patch=patch)
    assert pr.repository == "billing-service"
    assert "a.py" in pr.title
    assert "+x" in pr.body


def test_draft_pr_rejected_for_non_test_repo() -> None:
    service = DeliveryService(test_repositories=["billing-service"])
    patch = make_patch(repository="prod-service", diff="+x", changed_files=["a.py"])
    with pytest.raises(DraftPrGuardError):
        service.create_draft_pr(repository="prod-service", patch=patch)


def test_draft_pr_rejected_without_any_test_repo() -> None:
    service = DeliveryService(test_repositories=[])
    patch = make_patch(repository="anything", diff="", changed_files=[])
    with pytest.raises(DraftPrGuardError):
        service.create_draft_pr(repository="anything", patch=patch)
