"""
Custom exception hierarchy for Blueprint blocks.

These exceptions provide structured, user-friendly error messages
that the executor can catch and surface cleanly via SSE events.
"""


class BlockError(Exception):
    """Base exception for all block-related errors."""

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
    """Raised when a block's input validation fails."""

    def __init__(self, message: str, *, details: str = "", recoverable: bool = False):
        super().__init__(message, details=details, recoverable=recoverable)


class BlockConfigError(BlockError):
    """Raised when a block's config validation fails."""

    def __init__(self, field: str, message: str, *, details: str = "", recoverable: bool = True):
        self.field = field
        super().__init__(message, details=details, recoverable=recoverable)

    def to_dict(self) -> dict:
        d = super().to_dict()
        d["field"] = self.field
        return d


class BlockTimeoutError(BlockError):
    """Raised when a block exceeds its configured timeout."""

    def __init__(self, timeout_seconds: int | float, message: str = ""):
        self.timeout_seconds = timeout_seconds
        if not message:
            message = f"Block execution exceeded {timeout_seconds}s timeout"
        super().__init__(message, details="", recoverable=False)

    def to_dict(self) -> dict:
        d = super().to_dict()
        d["timeout_seconds"] = self.timeout_seconds
        return d
