"""Save JSON — save pipeline data as JSON or JSONL file."""

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
    output_path = ctx.config.get("output_path", "./output").strip()
    filename = ctx.config.get("filename", "data.json").strip()
    fmt = ctx.config.get("format", "json").lower().strip()
    pretty_print = ctx.config.get("pretty_print", True)
    indent = int(ctx.config.get("indent", 2))
    sort_keys = ctx.config.get("sort_keys", False)
    overwrite = ctx.config.get("overwrite_existing", True)
    ensure_ascii = ctx.config.get("ensure_ascii", False)
    timestamp_filename = ctx.config.get("timestamp_filename", False)
    root_key = ctx.config.get("root_key", "").strip()

    ctx.log_message(f"Save JSON starting (format={fmt})")
    ctx.report_progress(0, 3)

    # ---- Step 1: Load data ----
    ctx.report_progress(1, 3)
    raw_data = ctx.resolve_as_data("data")
    if not raw_data:
        raise BlockInputError(
            "No input data provided. Connect a 'data' input.",
            recoverable=False,
        )

    data = raw_data

    # Wrap data under root key if specified (e.g. {"results": [...]})
    if root_key:
        data = {root_key: data}

    # Count records
    if isinstance(data, list):
        record_count = len(data)
    elif isinstance(data, dict):
        inner = data.get(root_key) if root_key else None
        record_count = len(inner) if isinstance(inner, list) else 1
    else:
        record_count = 1
        data = {"value": data}

    ctx.log_message(f"Loaded {record_count} records")

    # ---- Step 2: Serialize ----
    ctx.report_progress(2, 3)
    if fmt == "jsonl":
        # JSONL: one JSON object per line
        rows = data if isinstance(data, list) else [data]
        lines = []
        for row in rows:
            lines.append(json.dumps(row, default=str, ensure_ascii=ensure_ascii, sort_keys=sort_keys))
        content = "\n".join(lines) + "\n"
        ext = ".jsonl"
    else:
        # Standard JSON
        json_indent = indent if pretty_print else None
        content = json.dumps(data, indent=json_indent, default=str, ensure_ascii=ensure_ascii, sort_keys=sort_keys)
        ext = ".json"

    # ---- Step 3: Write file ----
    if os.path.isabs(output_path):
        out_dir = output_path
    else:
        out_dir = os.path.join(ctx.run_dir, output_path)
    os.makedirs(out_dir, exist_ok=True)

    # Ensure correct extension
    if not filename.endswith(ext):
        base = os.path.splitext(filename)[0]
        filename = base + ext

    # Apply timestamp to filename
    if timestamp_filename:
        from datetime import datetime
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        base, fext = os.path.splitext(filename)
        filename = f"{base}_{ts}{fext}"

    out_filepath = os.path.join(out_dir, filename)

    if os.path.exists(out_filepath) and not overwrite:
        raise BlockInputError(
            f"File already exists: {out_filepath}. Enable 'Overwrite Existing'.",
            recoverable=True,
        )

    with open(out_filepath, "w", encoding="utf-8") as f:
        f.write(content)

    ctx.report_progress(3, 3)
    file_size = os.path.getsize(out_filepath)
    ctx.log_message(f"Saved {record_count} records to {out_filepath} ({file_size:,} bytes)")

    ctx.save_output("file_path", out_filepath)
    ctx.save_output("summary", {
        "records": record_count,
        "file_size_bytes": file_size,
        "format": fmt,
    })
    ctx.save_artifact("json_output", out_filepath)
    ctx.log_metric("records_saved", float(record_count))
    ctx.log_metric("file_size_bytes", float(file_size))

    ctx.log_message("Save JSON complete.")
