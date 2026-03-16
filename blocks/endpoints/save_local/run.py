"""Save Local — save any pipeline output to a specific directory with auto-format detection."""

import csv
import io
import json
import os
import shutil
from datetime import datetime, timezone

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


def _detect_format(data):
    """Auto-detect the best format for the given data."""
    if isinstance(data, str):
        if os.path.isfile(data) or os.path.isdir(data):
            return "copy"  # Copy existing file/dir
        return "txt"
    if isinstance(data, list):
        if all(isinstance(item, dict) for item in data):
            return "csv"
        return "json"
    if isinstance(data, dict):
        return "json"
    return "txt"


def _collect_headers(rows):
    seen = {}
    for row in rows:
        for key in row:
            if key not in seen:
                seen[key] = True
    return list(seen.keys())


def _normalize_rows(data):
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


FORMAT_EXTENSIONS = {
    "json": ".json",
    "csv": ".csv",
    "txt": ".txt",
    "yaml": ".yaml",
    "parquet": ".parquet",
}


def run(ctx):
    output_directory = ctx.config.get("output_directory", "").strip()
    filename = ctx.config.get("filename", "output").strip()
    fmt = ctx.config.get("format", "auto").lower().strip()
    create_dirs = ctx.config.get("create_dirs", True)
    overwrite = ctx.config.get("overwrite", False)
    include_metadata = ctx.config.get("include_metadata", False)
    timestamp_filename = ctx.config.get("timestamp_filename", False)

    ctx.log_message("Save Local starting")
    ctx.report_progress(0, 4)

    # ── Loop-aware file handling ──
    loop = ctx.get_loop_metadata()
    if isinstance(loop, dict):
        file_mode_loop = loop.get("file_mode", "overwrite")
        iteration = loop.get("iteration", 0)
        ctx.log_message(f"[Loop iter {iteration}] file_mode={file_mode_loop}")
    else:
        file_mode_loop = "overwrite"
        iteration = 0

    # Loop append: for text-based formats, append to existing file
    loop_append = file_mode_loop == "append" and iteration > 0

    # ---- Step 1: Load data ----
    ctx.report_progress(1, 4)
    # Use load_input directly — save_local needs to handle file/dir copy mode,
    # which requires preserving the original file path string.
    raw_data = ctx.load_input("data")
    if raw_data is None:
        raise BlockInputError(
            "No input data provided. Connect a 'data' input.",
            recoverable=False,
        )

    data = raw_data

    # ---- Step 2: Resolve format ----
    ctx.report_progress(2, 4)
    if fmt == "auto":
        fmt = _detect_format(data)
        ctx.log_message(f"Auto-detected format: {fmt}")

    # ---- Step 3: Resolve output path ----
    if output_directory:
        if not os.path.isabs(output_directory):
            out_dir = os.path.join(ctx.run_dir, output_directory)
        else:
            out_dir = output_directory
    else:
        out_dir = ctx.run_dir

    if create_dirs:
        os.makedirs(out_dir, exist_ok=True)
    elif not os.path.isdir(out_dir):
        raise BlockInputError(
            f"Output directory does not exist: {out_dir}. Enable 'Create Directories'.",
            recoverable=True,
        )

    # Apply timestamp
    if timestamp_filename:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{filename}_{ts}"

    # Loop versioned: create iteration-specific filename
    if file_mode_loop == "versioned":
        filename = f"{filename}_iter{iteration}"

    # ---- Step 4: Write output ----
    ctx.report_progress(3, 4)

    if fmt == "copy":
        # Copy existing file or directory
        src_path = data
        if os.path.isfile(src_path):
            ext = os.path.splitext(src_path)[1]
            out_filepath = os.path.join(out_dir, filename + ext)
            if os.path.exists(out_filepath) and not overwrite:
                raise BlockInputError(
                    f"File already exists: {out_filepath}",
                    recoverable=True,
                )
            shutil.copy2(src_path, out_filepath)
        elif os.path.isdir(src_path):
            out_filepath = os.path.join(out_dir, filename)
            if os.path.exists(out_filepath) and not overwrite:
                raise BlockInputError(
                    f"Directory already exists: {out_filepath}",
                    recoverable=True,
                )
            if os.path.exists(out_filepath):
                shutil.rmtree(out_filepath)
            shutil.copytree(src_path, out_filepath)
        else:
            raise BlockInputError(
                f"Cannot save data in copy format: source not found at {src_path}",
                details=f"Upstream block produced: {str(data)[:200]}",
                recoverable=False,
            )

    elif fmt == "json":
        out_filepath = os.path.join(out_dir, filename + ".json")
        if not loop_append and os.path.exists(out_filepath) and not overwrite:
            raise BlockInputError(
                f"File already exists: {out_filepath}",
                recoverable=True,
            )
        if loop_append and os.path.isfile(out_filepath):
            # Merge with existing JSON
            try:
                with open(out_filepath, "r", encoding="utf-8") as f:
                    existing = json.load(f)
            except (json.JSONDecodeError, ValueError):
                existing = None
            if existing is not None:
                if isinstance(existing, list) and isinstance(data, list):
                    data = existing + data
                elif isinstance(existing, list):
                    existing.append(data)
                    data = existing
                else:
                    data = [existing, data]
        content = json.dumps(data, indent=2, default=str, ensure_ascii=False)
        with open(out_filepath, "w", encoding="utf-8") as f:
            f.write(content)

    elif fmt == "csv":
        out_filepath = os.path.join(out_dir, filename + ".csv")
        if not loop_append and os.path.exists(out_filepath) and not overwrite:
            raise BlockInputError(
                f"File already exists: {out_filepath}",
                recoverable=True,
            )
        rows = _normalize_rows(data)
        headers = _collect_headers(rows)
        if loop_append and os.path.isfile(out_filepath):
            # Append rows without header
            buf = io.StringIO()
            writer = csv.writer(buf)
            for row in rows:
                writer.writerow([str(row.get(h, "")) for h in headers])
            with open(out_filepath, "a", encoding="utf-8", newline="") as f:
                f.write(buf.getvalue())
        else:
            buf = io.StringIO()
            writer = csv.writer(buf)
            writer.writerow(headers)
            for row in rows:
                writer.writerow([str(row.get(h, "")) for h in headers])
            with open(out_filepath, "w", encoding="utf-8", newline="") as f:
                f.write(buf.getvalue())

    elif fmt == "txt":
        out_filepath = os.path.join(out_dir, filename + ".txt")
        if not loop_append and os.path.exists(out_filepath) and not overwrite:
            raise BlockInputError(
                f"File already exists: {out_filepath}",
                recoverable=True,
            )
        if isinstance(data, str):
            content = data
        else:
            content = json.dumps(data, indent=2, default=str, ensure_ascii=False)
        if loop_append and os.path.isfile(out_filepath):
            with open(out_filepath, "a", encoding="utf-8") as f:
                f.write("\n")
                f.write(content)
        else:
            with open(out_filepath, "w", encoding="utf-8") as f:
                f.write(content)

    elif fmt == "yaml":
        out_filepath = os.path.join(out_dir, filename + ".yaml")
        if os.path.exists(out_filepath) and not overwrite:
            raise BlockInputError(
                f"File already exists: {out_filepath}",
                recoverable=True,
            )
        try:
            import yaml
            content = yaml.dump(data, default_flow_style=False, allow_unicode=True)
        except ImportError:
            content = json.dumps(data, indent=2, default=str, ensure_ascii=False)
            ctx.log_message("WARNING: PyYAML not installed, falling back to JSON format with .yaml extension")
        with open(out_filepath, "w", encoding="utf-8") as f:
            f.write(content)

    elif fmt == "parquet":
        out_filepath = os.path.join(out_dir, filename + ".parquet")
        if os.path.exists(out_filepath) and not overwrite:
            raise BlockInputError(
                f"File already exists: {out_filepath}",
                recoverable=True,
            )
        rows = _normalize_rows(data)
        try:
            import pyarrow as pa
            import pyarrow.parquet as pq
            headers = _collect_headers(rows)
            columns = {h: [row.get(h) for row in rows] for h in headers}
            table = pa.table(columns)
            pq.write_table(table, out_filepath)
        except ImportError:
            try:
                import pandas as pd
                df = pd.DataFrame(rows)
                df.to_parquet(out_filepath, index=False)
            except ImportError as e:
                missing = getattr(e, "name", None) or "pandas"
                raise BlockDependencyError(
                    missing,
                    f"Required library not installed: {e}",
                    install_hint="pip install pandas",
                )
    else:
        raise BlockInputError(
            f"Cannot save data in {fmt} format: unsupported format",
            details="Supported formats: auto, copy, json, csv, txt, yaml, parquet",
            recoverable=True,
        )

    # Write metadata sidecar
    if include_metadata:
        meta = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "format": fmt,
            "filename": os.path.basename(out_filepath),
        }
        meta_path = out_filepath + ".meta.json"
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)
        ctx.log_message(f"Metadata written to {meta_path}")

    ctx.report_progress(4, 4)
    if os.path.isfile(out_filepath):
        file_size = os.path.getsize(out_filepath)
    else:
        file_size = sum(
            os.path.getsize(os.path.join(dp, fn))
            for dp, _, fns in os.walk(out_filepath, followlinks=False)
            for fn in fns
        )

    ctx.log_message(f"Saved to {out_filepath} ({file_size:,} bytes)")

    ctx.save_output("file_path", out_filepath)
    ctx.save_output("summary", {"file_size_bytes": file_size, "format": fmt})
    if os.path.isfile(out_filepath):
        ctx.save_artifact("local_output", out_filepath)
    ctx.log_metric("file_size_bytes", float(file_size))

    ctx.log_message("Save Local complete.")
