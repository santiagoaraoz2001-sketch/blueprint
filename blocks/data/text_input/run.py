"""Text Input — simple block that passes a configured text payload downstream."""

import json
import os

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
    text_value = ctx.config.get("text_value", "")
    fmt = ctx.config.get("format", "plain")
    encoding = ctx.config.get("encoding", "utf-8")

    ctx.log_message(f"Text input: {len(text_value)} chars (format={fmt}, encoding={encoding})")

    # Validate format-specific content
    if fmt == "json":
        try:
            json.loads(text_value)
            ctx.log_message("JSON syntax is valid")
        except (json.JSONDecodeError, ValueError) as e:
            ctx.log_message(f"WARNING: Text marked as JSON but is not valid JSON: {e}")

    elif fmt == "csv":
        line_count = len(text_value.strip().splitlines())
        ctx.log_message(f"CSV format: {line_count} lines")

    # Write text output with specified encoding
    out_path = os.path.join(ctx.run_dir, "text_input.txt")
    with open(out_path, "w", encoding=encoding) as f:
        f.write(text_value)

    # Write metadata sidecar
    metadata = {
        "format": fmt,
        "encoding": encoding,
        "char_count": len(text_value),
        "line_count": len(text_value.splitlines()),
    }
    meta_path = os.path.join(ctx.run_dir, "metadata.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    ctx.log_metric("char_count", len(text_value))
    ctx.log_metric("line_count", len(text_value.splitlines()))
    ctx.report_progress(1, 1)
    ctx.save_output("text", out_path)
