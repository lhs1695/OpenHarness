"""ForgeFlow error hierarchy (business layer).

All ForgeFlow layers raise these types; OpenHarness exceptions are wrapped
into them by the adapter so business code never depends on upstream types.
"""


class ForgeFlowError(Exception):
    """Base error for all ForgeFlow failures."""


class AdapterError(ForgeFlowError):
    """Base error raised by the OpenHarness adapter."""


class MaxTurnsExceededError(AdapterError):
    """The agent exceeded its step/turn budget."""


class ProviderError(AdapterError):
    """A model provider failed during execution."""


class ExecutionTimeoutError(ForgeFlowError):
    """Execution exceeded its time budget."""


class BudgetExceededError(ForgeFlowError):
    """A task budget (tokens / tools / time) was exceeded."""


class UnsupportedOperationError(ForgeFlowError):
    """ForgeFlow does not support the requested operation for this input."""


class IllegalTransitionError(ForgeFlowError):
    """A state-machine transition is not allowed from the current state."""


class TaskAlreadyExistsError(ForgeFlowError):
    """A task with the same id already exists."""


class PathEscapeError(ForgeFlowError):
    """A resolved path is outside the task workspace."""


class ExecutionNotPreparedError(ForgeFlowError):
    """The execution backend has not been prepared yet."""
