"""Block SDK exception hierarchy.

Blocks raise these exceptions to communicate specific failure types.
The executor catches them and surfaces clean, actionable error messages
to the frontend via SSE events.
"""


class BlockError(Exception):
    """Base exception for all block errors. Includes a user-facing message."""

    def __init__(self, message: str, details: str = "", recoverable: bool = False):
        self.message = message
        self.details = details
        self.recoverable = recoverable
        super().__init__(message)


class BlockInputError(BlockError):
    """Raised when block receives invalid or missing input data."""
    pass


class BlockConfigError(BlockError):
    """Raised when block configuration is invalid."""

    def __init__(self, field: str, message: str, **kwargs):
        self.field = field
        super().__init__(f"Config '{field}': {message}", **kwargs)


class BlockTimeoutError(BlockError):
    """Raised when block exceeds its timeout limit."""

    def __init__(self, timeout_seconds: float, message: str = ""):
        self.timeout_seconds = timeout_seconds
        msg = message or f"Block timed out after {timeout_seconds}s"
        super().__init__(msg, recoverable=True)


class BlockMemoryError(BlockError):
    """Raised when block exceeds memory limits or system runs out of memory."""

    def __init__(self, message: str = "Insufficient memory to complete operation"):
        super().__init__(message, recoverable=False)


class BlockDependencyError(BlockError):
    """Raised when a required library or external service is unavailable."""

    def __init__(self, dependency: str, message: str = "", install_hint: str = ""):
        self.dependency = dependency
        self.install_hint = install_hint
        msg = message or f"Required dependency '{dependency}' is not available"
        if install_hint:
            msg += f". Install with: {install_hint}"
        super().__init__(msg, recoverable=False)


class BlockDataError(BlockError):
    """Raised when input data is valid structurally but contains bad content."""
    pass
