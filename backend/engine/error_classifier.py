"""Error Classifier — maps exceptions to structured, actionable error messages.

Each classified error includes a title, user-facing message, suggested action,
and severity level so the frontend can display meaningful diagnostics.
"""

import json
import re
from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class ClassifiedError:
    """A structured error with title, message, action, and severity."""
    title: str
    message: str
    action: str
    severity: str  # 'error' | 'warning'
    original_type: str  # The original exception class name
    block_type: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


# Each entry: exception_type -> dict with title, message (may contain {placeholders}),
# action, severity. Message templates can reference: {service}, {path}, {detail}, {module}.
ERROR_MAP: dict[type, dict] = {
    ConnectionRefusedError: {
        "title": "Service Unavailable",
        "message": "Could not connect to {service}",
        "action": "Start {service} and retry",
        "severity": "error",
    },
    FileNotFoundError: {
        "title": "File Not Found",
        "message": 'File "{path}" does not exist',
        "action": "Check file path in block config",
        "severity": "error",
    },
    MemoryError: {
        "title": "Out of Memory",
        "message": "Insufficient memory to complete operation",
        "action": "Reduce batch size or use a smaller model",
        "severity": "error",
    },
    json.JSONDecodeError: {
        "title": "Invalid Data Format",
        "message": "Failed to parse JSON data: {detail}",
        "action": "Verify the input data is valid JSON",
        "severity": "error",
    },
    ImportError: {
        "title": "Missing Dependency",
        "message": 'Could not import module "{module}"',
        "action": "Install the missing package: pip install {module}",
        "severity": "error",
    },
    ModuleNotFoundError: {
        "title": "Missing Dependency",
        "message": 'Module "{module}" is not installed',
        "action": "Install the missing package: pip install {module}",
        "severity": "error",
    },
    PermissionError: {
        "title": "Permission Denied",
        "message": "Insufficient permissions to access {path}",
        "action": "Check file/directory permissions",
        "severity": "error",
    },
    TimeoutError: {
        "title": "Operation Timed Out",
        "message": "The operation exceeded the allowed time limit",
        "action": "Increase the timeout or reduce data size",
        "severity": "error",
    },
    ValueError: {
        "title": "Invalid Value",
        "message": "{detail}",
        "action": "Check the block configuration for invalid parameters",
        "severity": "error",
    },
    KeyError: {
        "title": "Missing Key",
        "message": 'Required key "{detail}" not found in data',
        "action": "Verify that upstream blocks produce the expected output fields",
        "severity": "error",
    },
    RuntimeError: {
        "title": "Runtime Error",
        "message": "{detail}",
        "action": "Check model compatibility and available resources",
        "severity": "error",
    },
    OSError: {
        "title": "System Error",
        "message": "{detail}",
        "action": "Check disk space and system resources",
        "severity": "error",
    },
    TypeError: {
        "title": "Type Mismatch",
        "message": "{detail}",
        "action": "Check that inputs match the expected data types",
        "severity": "error",
    },
    StopIteration: {
        "title": "Empty Dataset",
        "message": "No data available to process",
        "action": "Verify the data source is not empty",
        "severity": "error",
    },
    UnicodeDecodeError: {
        "title": "Encoding Error",
        "message": "Could not decode file — unexpected character encoding",
        "action": "Ensure the file is UTF-8 encoded or specify the correct encoding",
        "severity": "error",
    },
    ZeroDivisionError: {
        "title": "Division by Zero",
        "message": "A calculation attempted to divide by zero",
        "action": "Check metric calculations and normalization parameters",
        "severity": "error",
    },
    NotImplementedError: {
        "title": "Not Implemented",
        "message": "This operation is not supported: {detail}",
        "action": "Check block documentation for supported features",
        "severity": "error",
    },
    OverflowError: {
        "title": "Numeric Overflow",
        "message": "A numeric value exceeded the allowed range",
        "action": "Reduce learning rate, batch size, or use gradient clipping",
        "severity": "error",
    },
}


# Regex patterns for refining RuntimeError messages from ML frameworks
_ML_PATTERNS: list[tuple[re.Pattern, dict]] = [
    (
        re.compile(r"CUDA out of memory", re.IGNORECASE),
        {
            "title": "GPU Out of Memory",
            "message": "GPU memory exhausted during computation",
            "action": "Reduce batch size, use a smaller model, or enable gradient checkpointing",
            "severity": "error",
        },
    ),
    (
        re.compile(r"MPS backend out of memory|MLX.*memory", re.IGNORECASE),
        {
            "title": "GPU Out of Memory",
            "message": "Apple GPU memory exhausted during computation",
            "action": "Reduce batch size or use a smaller model",
            "severity": "error",
        },
    ),
    (
        re.compile(r"size mismatch|shape.*mismatch|dimension", re.IGNORECASE),
        {
            "title": "Tensor Shape Mismatch",
            "message": "Tensor dimensions are incompatible",
            "action": "Check model input dimensions and preprocessing steps",
            "severity": "error",
        },
    ),
    (
        re.compile(r"No space left on device", re.IGNORECASE),
        {
            "title": "Disk Full",
            "message": "No disk space available for writing outputs",
            "action": "Free disk space or change the output directory",
            "severity": "error",
        },
    ),
    (
        re.compile(r"Connection refused|ECONNREFUSED", re.IGNORECASE),
        {
            "title": "Connection Refused",
            "message": "Could not connect to the remote service",
            "action": "Verify the service URL and ensure the server is running",
            "severity": "error",
        },
    ),
]


def _extract_context(exc: BaseException) -> dict[str, str]:
    """Extract template variables from an exception's args and attributes."""
    ctx: dict[str, str] = {}
    msg = str(exc)

    ctx["detail"] = msg

    # FileNotFoundError has a .filename attribute
    if hasattr(exc, "filename") and exc.filename:
        ctx["path"] = str(exc.filename)
    elif "No such file" in msg:
        # Try to extract path from message
        parts = msg.split("'")
        if len(parts) >= 2:
            ctx["path"] = parts[1]
    ctx.setdefault("path", "unknown")

    # ImportError / ModuleNotFoundError has a .name attribute
    if hasattr(exc, "name") and exc.name:
        ctx["module"] = exc.name
    else:
        # Try to extract module from "No module named 'xxx'"
        match = re.search(r"No module named '([^']+)'", msg)
        if match:
            ctx["module"] = match.group(1)
    ctx.setdefault("module", "unknown")

    # ConnectionRefusedError — try to extract service name
    if isinstance(exc, ConnectionRefusedError):
        ctx.setdefault("service", "the required service")
    ctx.setdefault("service", "the remote service")

    return ctx


def classify_error(
    exception: BaseException,
    block_type: str | None = None,
) -> ClassifiedError:
    """Classify an exception into a structured error with title, message, action, severity.

    Args:
        exception: The caught exception.
        block_type: Optional block type for context-specific messages.

    Returns:
        ClassifiedError with user-friendly information.
    """
    exc_type = type(exception)
    msg = str(exception)

    # 1. Look up exact type in ERROR_MAP, walking the MRO
    template = None
    for cls in exc_type.__mro__:
        if cls in ERROR_MAP:
            template = ERROR_MAP[cls]
            break

    # 2. For generic types (RuntimeError, OSError), check ML-specific patterns
    #    to provide more specific diagnostics
    if exc_type in (RuntimeError, OSError) or (template is not None and exc_type not in ERROR_MAP):
        for pattern, ml_template in _ML_PATTERNS:
            if pattern.search(msg):
                return ClassifiedError(
                    title=ml_template["title"],
                    message=ml_template["message"],
                    action=ml_template["action"],
                    severity=ml_template["severity"],
                    original_type=exc_type.__name__,
                    block_type=block_type,
                )

    if template is None:
        # Fallback for unknown exceptions
        return ClassifiedError(
            title="Unexpected Error",
            message=msg[:200] if msg else "An unexpected error occurred",
            action="Check the block logs for details",
            severity="error",
            original_type=exc_type.__name__,
            block_type=block_type,
        )

    # 3. Fill template with context
    ctx = _extract_context(exception)
    try:
        filled_message = template["message"].format(**ctx)
    except (KeyError, IndexError):
        filled_message = template["message"]
    try:
        filled_action = template["action"].format(**ctx)
    except (KeyError, IndexError):
        filled_action = template["action"]

    return ClassifiedError(
        title=template["title"],
        message=filled_message,
        action=filled_action,
        severity=template["severity"],
        original_type=exc_type.__name__,
        block_type=block_type,
    )
