"""Save CSV — save pipeline data as a CSV file."""

import csv
import io
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


def _normalize_rows(data):
    """Ensure data is a list of dicts."""
    if data is None:
        return []
    if isinstance(data, dict):
        if "data" in data and isinstance(data["data"], list):
            return _normalize_rows(data["data"])
        return [data]
    if isinstance(data, list):
        rows = []
        for item in data:
            if isinstance(item, dict):
                rows.append(item)
            else:
                rows.append({"value": item})
        return rows
    return [{"value": data}]


def _collect_headers(rows):
    """Collect unique keys preserving insertion order."""
    seen = {}
    for row in rows:
        for key in row:
            if key not in seen:
                seen[key] = True
    return list(seen.keys())


def run(ctx):
    output_path = ctx.config.get("output_path", "./output").strip()
    filename = ctx.config.get("filename", "data.csv").strip()
    delimiter = ctx.config.get("delimiter", ",")
    include_header = ctx.config.get("include_header", True)
    encoding = ctx.config.get("encoding", "utf-8")
    overwrite = ctx.config.get("overwrite_existing", True)
    quote_all = ctx.config.get("quote_all", False)
    timestamp_filename = ctx.config.get("timestamp_filename", False)
    columns = ctx.config.get("columns", "").strip()
    na_value = ctx.config.get("na_value", "")

    # Handle escaped tab delimiter
    if delimiter == "\\t":
        delimiter = "\t"

    ctx.log_message("Save CSV starting")
    ctx.report_progress(0, 4)

    # ── Loop-aware file handling ──
    loop = ctx.get_loop_metadata()
    if isinstance(loop, dict):
        file_mode = loop.get("file_mode", "overwrite")
        iteration = loop.get("iteration", 0)
        ctx.log_message(f"[Loop iter {iteration}] file_mode={file_mode}")
    else:
        file_mode = "overwrite"
        iteration = 0

    # ---- Step 1: Load and normalize data ----
    ctx.report_progress(1, 4)
    raw_data = ctx.resolve_as_data("data")
    if not raw_data:
        raise BlockInputError(
            "No input data provided. Connect a 'data' input.",
            recoverable=False,
        )

    rows = _normalize_rows(raw_data)

    if not rows:
        raise BlockInputError(
            "Cannot save data in CSV format: expected list of dicts, got empty data",
            details=f"Upstream block produced: {str(raw_data)[:200]}",
            recoverable=False,
        )

    headers = _collect_headers(rows)

    # Filter columns if specified
    if columns:
        selected = [c.strip() for c in columns.split(",") if c.strip()]
        headers = [h for h in headers if h in selected]
        if not headers:
            raise BlockInputError(
                f"None of the specified columns found. Available: {_collect_headers(_normalize_rows(raw_data))}",
                recoverable=True,
            )

    ctx.log_message(f"Loaded {len(rows)} rows, {len(headers)} columns")

    # ---- Step 2: Write CSV ----
    ctx.report_progress(2, 4)
    quoting = csv.QUOTE_ALL if quote_all else csv.QUOTE_MINIMAL

    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=delimiter, quoting=quoting)
    if include_header:
        writer.writerow(headers)
    for row in rows:
        writer.writerow([na_value if row.get(h) is None else str(row.get(h, na_value)) for h in headers])
    content = buf.getvalue()

    # ---- Step 3: Save to file ----
    ctx.report_progress(3, 4)
    if os.path.isabs(output_path):
        out_dir = output_path
    else:
        out_dir = os.path.join(ctx.run_dir, output_path)
    os.makedirs(out_dir, exist_ok=True)

    if not filename.endswith(".csv"):
        filename += ".csv"

    # Apply timestamp to filename
    if timestamp_filename:
        from datetime import datetime
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        base = filename.rsplit(".", 1)[0]
        filename = f"{base}_{ts}.csv"

    # Loop versioned: create iteration-specific filename
    if file_mode == "versioned":
        base = filename.rsplit(".", 1)[0]
        filename = f"{base}_iter{iteration}.csv"

    out_filepath = os.path.join(out_dir, filename)

    if file_mode != "append" and os.path.exists(out_filepath) and not overwrite:
        raise BlockInputError(
            f"File already exists: {out_filepath}. Enable 'Overwrite Existing'.",
            recoverable=True,
        )

    # Loop append: append rows without repeating header
    if file_mode == "append" and os.path.isfile(out_filepath):
        # Read existing headers to validate schema consistency
        try:
            with open(out_filepath, "r", encoding=encoding, newline="") as f:
                reader = csv.reader(f, delimiter=delimiter)
                existing_headers = next(reader, None)
            if existing_headers and existing_headers != headers:
                ctx.log_message(
                    f"WARNING: Column mismatch on append. "
                    f"Existing: {existing_headers}, Current: {headers}. "
                    f"Using existing column order."
                )
                headers = existing_headers
        except (OSError, StopIteration):
            pass

        buf = io.StringIO()
        writer = csv.writer(buf, delimiter=delimiter, quoting=quoting)
        for row in rows:
            writer.writerow([na_value if row.get(h) is None else str(row.get(h, na_value)) for h in headers])
        append_content = buf.getvalue()
        # Ensure file ends with newline before appending
        with open(out_filepath, "rb") as f:
            f.seek(0, 2)
            needs_newline = False
            if f.tell() > 0:
                f.seek(-1, 2)
                needs_newline = f.read(1) != b"\n"
        with open(out_filepath, "a", encoding=encoding, newline="") as f:
            if needs_newline:
                f.write("\n")
            f.write(append_content)
    else:
        with open(out_filepath, "w", encoding=encoding, newline="") as f:
            f.write(content)

    # ---- Step 4: Finalize ----
    ctx.report_progress(4, 4)
    file_size = os.path.getsize(out_filepath)
    ctx.log_message(f"Saved {len(rows)} rows to {out_filepath} ({file_size:,} bytes)")

    ctx.save_output("file_path", out_filepath)
    ctx.save_output("summary", {
        "rows": len(rows),
        "columns": len(headers),
        "file_size_bytes": file_size,
        "delimiter": delimiter,
    })
    ctx.save_artifact("csv_output", out_filepath)
    ctx.log_metric("rows_saved", float(len(rows)))
    ctx.log_metric("file_size_bytes", float(file_size))

    ctx.log_message("Save CSV complete.")
