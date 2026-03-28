"""Utilities for redacting secret values from output paths."""

from __future__ import annotations

import re
from typing import Any

# Pattern to match $secret:NAME references
_SECRET_REF_PATTERN = re.compile(r"\$secret:\S+")

# Config keys whose values should always be redacted in outputs
_SENSITIVE_KEY_PATTERNS = re.compile(
    r"(api[_-]?key|secret|token|password|credential|auth)",
    re.IGNORECASE,
)

_REDACTED = "***REDACTED***"


def redact_config(config: Any) -> Any:
    """Recursively redact secret references and sensitive-looking values.

    - Replaces ``$secret:NAME`` string values with ``***REDACTED***``
    - Replaces values whose keys match sensitive patterns
    - Works on nested dicts and lists
    """
    if isinstance(config, dict):
        result = {}
        for key, value in config.items():
            if isinstance(value, str) and value.startswith("$secret:"):
                result[key] = _REDACTED
            elif isinstance(value, str) and _SENSITIVE_KEY_PATTERNS.search(key):
                result[key] = _REDACTED
            elif isinstance(value, (dict, list)):
                result[key] = redact_config(value)
            else:
                result[key] = value
        return result
    elif isinstance(config, list):
        return [redact_config(item) for item in config]
    return config


def scrub_traceback(tb: str, resolved_secrets: list[str] | None = None) -> str:
    """Remove secret references and resolved values from traceback text.

    - Replaces $secret:NAME references with ***REDACTED***
    - If resolved_secrets is provided, replaces those literal values too
    """
    result = _SECRET_REF_PATTERN.sub(_REDACTED, tb)
    if resolved_secrets:
        for secret_val in resolved_secrets:
            if secret_val and len(secret_val) >= 4:
                result = result.replace(secret_val, _REDACTED)
    return result
