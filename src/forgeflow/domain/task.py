"""Development task model (M1 minimal; expanded by M2)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class DevelopmentTask(BaseModel):
    """A research task ForgeFlow plans and executes.

    This is a pure ForgeFlow type: no OpenHarness types are imported here.
    """

    repository: str
    task_type: str = "bugfix"
    priority: str = "P2"
    title: str
    description: str = ""
    acceptance_criteria: list[str] = Field(default_factory=list)
    risk_tags: list[str] = Field(default_factory=list)
    requested_by: str = ""
