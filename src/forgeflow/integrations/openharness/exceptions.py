"""ForgeFlow error hierarchy.

All errors surfaced by the adapter are ForgeFlow types; OpenHarness
exceptions are wrapped so the business layer never depends on them.
"""


class ForgeFlowError(Exception):
    """Base error for all ForgeFlow failures."""


class AdapterError(ForgeFlowError):
    """Base error raised by the OpenHarness adapter."""


class MaxTurnsExceededError(AdapterError):
    """The agent exceeded its step/turn budget."""


class ProviderError(AdapterError):
    """A model provider failed during execution."""


class ExecutionTimeoutError(AdapterError):
    """Execution exceeded its time budget."""


class BudgetExceededError(AdapterError):
    """A task budget (tokens / tools / time) was exceeded."""


class UnsupportedOperationError(AdapterError):
    """ForgeFlow does not support the requested operation for this input."""
