"""Block SDK type definitions."""

from typing import Any, Literal

DataType = Literal["dataset", "text", "model", "metrics", "artifact", "config", "embedding", "agent", "llm", "any"]

BlockStatus = Literal["pending", "running", "complete", "failed", "skipped"]

ErrorType = Literal[
    "BlockInputError", "BlockConfigError", "BlockTimeoutError",
    "BlockMemoryError", "BlockDependencyError", "BlockDataError",
]
