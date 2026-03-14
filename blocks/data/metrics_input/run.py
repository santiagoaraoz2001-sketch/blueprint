"""Metrics Input — define metric key-value pairs for downstream blocks."""

import json

try:
    from backend.block_sdk.exceptions import (
        BlockConfigError, BlockInputError, BlockDataError,
        BlockDependencyError, BlockExecutionError,
    )
except ImportError:
    class BlockConfigError(ValueError):
        def __init__(self, field, message, **kw): super().__init__(message)
    class BlockInputError(ValueError):
        def __init__(self, message, **kw): super().__init__(message)
    class BlockDataError(ValueError):
        pass
    class BlockDependencyError(ImportError):
        def __init__(self, dep, message="", **kw): super().__init__(message or dep)
    class BlockExecutionError(RuntimeError):
        def __init__(self, message, **kw): super().__init__(message)


def run(ctx):
    fmt = ctx.config.get("format", "json")

    metrics = {}

    if fmt == "key_value":
        raw = ctx.config.get("key_value_text", "")
        for line in raw.strip().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" not in line:
                ctx.log_message(f"Skipping invalid line (no colon): {line}")
                continue
            key, _, val = line.partition(":")
            key = key.strip()
            val = val.strip()
            # Try to parse as number
            try:
                val = int(val)
            except ValueError:
                try:
                    val = float(val)
                except ValueError:
                    pass  # keep as string
            metrics[key] = val
    else:
        raw = ctx.config.get("metrics_json", "{}")
        try:
            metrics = json.loads(raw)
            if not isinstance(metrics, dict):
                raise BlockConfigError("metrics_json", "Metrics JSON must be an object (dict), not a list or scalar")
        except (json.JSONDecodeError, ValueError) as e:
            raise BlockConfigError("metrics_json", f"Invalid metrics JSON: {e}")

    ctx.log_message(f"Metrics input: {len(metrics)} entries")
    for key, val in metrics.items():
        if isinstance(val, (int, float)):
            ctx.log_metric(key, val)

    ctx.save_output("metrics", metrics)
    ctx.report_progress(1, 1)
