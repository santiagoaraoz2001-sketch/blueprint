"""Block SDK type definitions."""

from typing import Any, Literal

DataType = Literal["dataset", "model", "metrics", "artifact", "config", "any"]

BlockStatus = Literal["pending", "running", "complete", "failed", "skipped"]

ErrorType = Literal[
    "BlockInputError", "BlockConfigError", "BlockTimeoutError",
    "BlockMemoryError", "BlockDependencyError", "BlockDataError",
]
