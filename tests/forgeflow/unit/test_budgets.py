"""Budget checks — limits, tracking, and over-budget detection."""

from forgeflow.orchestration.budgets import Budget, BudgetTracker, BudgetUsage, check_budget


def test_check_within_limits() -> None:
    check = check_budget(
        Budget(max_agent_steps=10, max_tokens=1000, max_execution_seconds=60.0),
        BudgetUsage(agent_steps=5, tokens=500, elapsed_seconds=30.0),
    )
    assert check.ok
    assert check.exceeded == []


def test_check_flags_each_exceeded_limit() -> None:
    check = check_budget(
        Budget(
            max_agent_steps=1,
            max_model_calls=1,
            max_tool_calls=1,
            max_tokens=100,
            max_execution_seconds=1.0,
        ),
        BudgetUsage(agent_steps=2, model_calls=2, tool_calls=2, tokens=200, elapsed_seconds=2.0),
    )
    assert not check.ok
    assert set(check.exceeded) == {
        "agent_steps",
        "model_calls",
        "tool_calls",
        "tokens",
        "execution_seconds",
    }


def test_none_limits_never_exceeded() -> None:
    check = check_budget(Budget(), BudgetUsage(agent_steps=10_000, tokens=10_000))
    assert check.ok
    assert check.exceeded == []


def test_boundary_equal_is_within_limit() -> None:
    check = check_budget(
        Budget(max_agent_steps=10),
        BudgetUsage(agent_steps=10),
    )
    assert check.ok


def test_tracker_detects_over_budget() -> None:
    tracker = BudgetTracker(Budget(max_agent_steps=2, max_tokens=100, max_tool_calls=3))
    assert tracker.check().ok
    tracker.record_agent_step()
    tracker.record_agent_step()
    assert tracker.check().ok
    tracker.record_agent_step()
    assert not tracker.check().ok
    assert "agent_steps" in tracker.check().exceeded


def test_tracker_accumulates_model_calls_and_tokens() -> None:
    tracker = BudgetTracker(Budget(max_model_calls=2, max_tokens=150))
    tracker.record_model_call(100)
    tracker.record_model_call(60)
    usage = tracker.usage
    assert usage.model_calls == 2
    assert usage.tokens == 160
    assert not tracker.check().ok
    assert "tokens" in tracker.check().exceeded


def test_tracker_records_tools_and_elapsed() -> None:
    tracker = BudgetTracker(Budget(max_tool_calls=1, max_execution_seconds=10.0))
    tracker.record_tool_call()
    tracker.set_elapsed(12.0)
    assert tracker.check().exceeded == ["execution_seconds"]
    tracker.record_tool_call()
    assert set(tracker.check().exceeded) == {"tool_calls", "execution_seconds"}
