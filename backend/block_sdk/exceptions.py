"""Block exception hierarchy — structured errors for block authors.

All block-related errors inherit from BlockError, allowing the test runner
and pipeline executor to catch and display failures cleanly.

Hierarchy:
    BlockError
    ├── BlockConfigError      — invalid or missing configuration
    ├── BlockInputError       — missing or malformed input data
    ├── BlockOutputError      — failure to produce expected outputs
    ├── BlockExecutionError   — runtime failure during block execution
    ├── BlockDependencyError  — missing library or external dependency
    └── BlockTimeoutError     — block exceeded time limit
"""


class BlockError(Exception):
    """Base exception for all block-related errors."""

    def __init__(self, message: str, *, field: str = "", recoverable: bool = False):
        self.field = field
        self.recoverable = recoverable
        super().__init__(message)


class BlockConfigError(BlockError):
    """Raised when block configuration is invalid or missing required fields."""

    def __init__(self, message: str, *, field: str = "", recoverable: bool = False):
        super().__init__(message, field=field, recoverable=recoverable)


class BlockInputError(BlockError):
    """Raised when block input data is missing, malformed, or the wrong type."""

    def __init__(self, message: str, *, field: str = "", recoverable: bool = False):
        super().__init__(message, field=field, recoverable=recoverable)


class BlockOutputError(BlockError):
    """Raised when a block fails to produce its expected outputs."""

    def __init__(self, message: str, *, field: str = "", recoverable: bool = True):
        super().__init__(message, field=field, recoverable=recoverable)


class BlockExecutionError(BlockError):
    """Raised when a block fails during execution (runtime error)."""

    def __init__(self, message: str, *, field: str = "", recoverable: bool = False):
        super().__init__(message, field=field, recoverable=recoverable)


class BlockDependencyError(BlockError):
    """Raised when a required library or external service is unavailable."""

    def __init__(self, message: str, *, field: str = "", recoverable: bool = False):
        super().__init__(message, field=field, recoverable=recoverable)


class BlockTimeoutError(BlockError):
    """Raised when a block exceeds its allotted execution time."""

    def __init__(self, message: str, *, field: str = "", recoverable: bool = False):
        super().__init__(message, field=field, recoverable=recoverable)
