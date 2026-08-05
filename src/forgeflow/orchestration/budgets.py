"""Task execution budgets (spec §4.5)."""

from __future__ import annotations

from dataclasses import dataclass, field, replace


@dataclass(frozen=True)
class Budget:
    """Limits for one task run; None means unlimited for that dimension."""

    max_agent_steps: int | None = None
    max_model_calls: int | None = None
    max_tool_calls: int | None = None
    max_tokens: int | None = None
    max_execution_seconds: float | None = None


@dataclass(frozen=True)
class BudgetUsage:
    """Consumed amounts for one task run."""

    agent_steps: int = 0
    model_calls: int = 0
    tool_calls: int = 0
    tokens: int = 0
    elapsed_seconds: float = 0.0


@dataclass(frozen=True)
class BudgetCheck:
    ok: bool
    exceeded: list[str] = field(default_factory=list)


def check_budget(budget: Budget, usage: BudgetUsage) -> BudgetCheck:
    """Return which limits (if any) are exceeded."""
    exceeded: list[str] = []
    if budget.max_agent_steps is not None and usage.agent_steps > budget.max_agent_steps:
        exceeded.append("agent_steps")
    if budget.max_model_calls is not None and usage.model_calls > budget.max_model_calls:
        exceeded.append("model_calls")
    if budget.max_tool_calls is not None and usage.tool_calls > budget.max_tool_calls:
        exceeded.append("tool_calls")
    if budget.max_tokens is not None and usage.tokens > budget.max_tokens:
        exceeded.append("tokens")
    if (
        budget.max_execution_seconds is not None
        and usage.elapsed_seconds > budget.max_execution_seconds
    ):
        exceeded.append("execution_seconds")
    return BudgetCheck(ok=not exceeded, exceeded=exceeded)


class BudgetTracker:
    """Stateful budget usage tracker for one task run."""

    def __init__(self, budget: Budget) -> None:
        self._budget = budget
        self._usage = BudgetUsage()

    @property
    def usage(self) -> BudgetUsage:
        return self._usage

    def record_agent_step(self) -> None:
        self._usage = replace(self._usage, agent_steps=self._usage.agent_steps + 1)

    def record_model_call(self, tokens: int) -> None:
        self._usage = replace(
            self._usage,
            model_calls=self._usage.model_calls + 1,
            tokens=self._usage.tokens + tokens,
        )

    def record_tool_call(self) -> None:
        self._usage = replace(self._usage, tool_calls=self._usage.tool_calls + 1)

    def set_elapsed(self, seconds: float) -> None:
        self._usage = replace(self._usage, elapsed_seconds=seconds)

    def check(self) -> BudgetCheck:
        return check_budget(self._budget, self._usage)
