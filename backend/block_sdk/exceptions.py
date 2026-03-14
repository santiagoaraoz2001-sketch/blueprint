"""Block SDK exception hierarchy.

Blocks raise these exceptions to communicate specific failure types.
The executor catches them and surfaces clean, actionable error messages
to the frontend via SSE events.

Hierarchy:
    BlockError
    ├── BlockConfigError      — invalid or missing configuration
    ├── BlockInputError       — missing or malformed input data
    ├── BlockOutputError      — failure to produce expected outputs
    ├── BlockExecutionError   — runtime failure during block execution
    ├── BlockDependencyError  — missing library or external dependency
    ├── BlockTimeoutError     — block exceeded time limit
    ├── BlockMemoryError      — out of memory
    └── BlockDataError        — structurally valid but bad content
"""


class BlockError(Exception):
    """Base exception for all block errors. Includes a user-facing message."""

    def __init__(self, message: str, *, details: str = "", recoverable: bool = False):
        self.message = message
        self.details = details
        self.recoverable = recoverable
        super().__init__(message)

    def to_dict(self) -> dict:
        return {
            "error_type": type(self).__name__,
            "message": self.message,
            "details": self.details,
            "recoverable": self.recoverable,
        }


class BlockInputError(BlockError):
    """Raised when block receives invalid or missing input data."""

    def __init__(self, message: str, *, details: str = "", recoverable: bool = False):
        super().__init__(message, details=details, recoverable=recoverable)


class BlockConfigError(BlockError):
    """Raised when block configuration is invalid."""

    def __init__(self, field: str, message: str, *, details: str = "", recoverable: bool = True):
        self.field = field
        super().__init__(message, details=details, recoverable=recoverable)

    def to_dict(self) -> dict:
        d = super().to_dict()
        d["field"] = self.field
        return d


class BlockOutputError(BlockError):
    """Raised when a block fails to produce its expected outputs."""

    def __init__(self, message: str, *, details: str = "", recoverable: bool = True):
        super().__init__(message, details=details, recoverable=recoverable)


class BlockExecutionError(BlockError):
    """Raised when a block fails during execution (runtime error)."""

    def __init__(self, message: str, *, details: str = "", recoverable: bool = False):
        super().__init__(message, details=details, recoverable=recoverable)


class BlockTimeoutError(BlockError):
    """Raised when block exceeds its timeout limit."""

    def __init__(self, timeout_seconds: int | float, message: str = ""):
        self.timeout_seconds = timeout_seconds
        if not message:
            message = f"Block execution exceeded {timeout_seconds}s timeout"
        super().__init__(message, details="", recoverable=False)

    def to_dict(self) -> dict:
        d = super().to_dict()
        d["timeout_seconds"] = self.timeout_seconds
        return d


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
