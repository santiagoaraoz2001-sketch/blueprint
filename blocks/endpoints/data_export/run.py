"""Data Export — unified block for exporting pipeline data in multiple formats."""

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


# ── Shared helpers ─────────────────────────────────────────────────────

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


def _detect_format(data):
    """Auto-detect the best format for the given data."""
    if isinstance(data, str):
        if os.path.isfile(data) or os.path.isdir(data):
            return "copy"
        return "txt"
    if isinstance(data, list):
        if all(isinstance(item, dict) for item in data):
            return "csv"
        return "json"
    if isinstance(data, dict):
        return "json"
    return "txt"


FORMAT_EXTENSIONS = {
    "json": ".json", "jsonl": ".jsonl", "csv": ".csv",
    "txt": ".txt", "yaml": ".yaml", "parquet": ".parquet",
}


def _resolve_path(ctx, output_path, filename, ext, timestamp_filename, file_mode, iteration, create_dirs):
    """Resolve the output directory and full filepath."""
    if os.path.isabs(output_path):
        out_dir = output_path
    elif output_path:
        out_dir = os.path.join(ctx.run_dir, output_path)
    else:
        out_dir = ctx.run_dir

    if create_dirs:
        os.makedirs(out_dir, exist_ok=True)
    elif not os.path.isdir(out_dir):
        raise BlockInputError(
            f"Output directory does not exist: {out_dir}. Enable 'Create Directories'.",
            recoverable=True,
        )

    # Ensure correct extension
    base = os.path.splitext(filename)[0] if os.path.splitext(filename)[1] else filename
    filename = base + ext

    if timestamp_filename:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_name, fext = os.path.splitext(filename)
        filename = f"{base_name}_{ts}{fext}"

    if file_mode == "versioned":
        base_name, fext = os.path.splitext(filename)
        filename = f"{base_name}_iter{iteration}{fext}"

    return out_dir, os.path.join(out_dir, filename)


# ── Format-specific writers ─────────────────────────────────────────────

def _save_csv(ctx, data, out_filepath, config, file_mode, overwrite):
    delimiter = config.get("delimiter", ",")
    if delimiter == "\\t":
        delimiter = "\t"
    include_header = config.get("include_header", True)
    encoding = config.get("csv_encoding", config.get("encoding", "utf-8"))
    quote_all = config.get("quote_all", False)
    columns = config.get("columns", "").strip()
    na_value = config.get("na_value", "")

    rows = _normalize_rows(data)
    if not rows:
        raise BlockInputError("Cannot export as CSV: no tabular data found", recoverable=False)

    headers = _collect_headers(rows)
    if columns:
        selected = [c.strip() for c in columns.split(",") if c.strip()]
        headers = [h for h in headers if h in selected]
        if not headers:
            raise BlockInputError(f"None of the specified columns found. Available: {_collect_headers(_normalize_rows(data))}", recoverable=True)

    quoting = csv.QUOTE_ALL if quote_all else csv.QUOTE_MINIMAL

    if file_mode == "append" and os.path.isfile(out_filepath):
        try:
            with open(out_filepath, "r", encoding=encoding, newline="") as f:
                reader = csv.reader(f, delimiter=delimiter)
                existing_headers = next(reader, None)
            if existing_headers and existing_headers != headers:
                ctx.log_message(f"WARNING: Column mismatch on append. Using existing column order.")
                headers = existing_headers
        except (OSError, StopIteration):
            pass
        buf = io.StringIO()
        writer = csv.writer(buf, delimiter=delimiter, quoting=quoting)
        for row in rows:
            writer.writerow([na_value if row.get(h) is None else str(row.get(h, na_value)) for h in headers])
        with open(out_filepath, "a", encoding=encoding, newline="") as f:
            f.write(buf.getvalue())
    else:
        if os.path.exists(out_filepath) and not overwrite:
            raise BlockInputError(f"File already exists: {out_filepath}. Enable 'Overwrite Existing'.", recoverable=True)
        buf = io.StringIO()
        writer = csv.writer(buf, delimiter=delimiter, quoting=quoting)
        if include_header:
            writer.writerow(headers)
        for row in rows:
            writer.writerow([na_value if row.get(h) is None else str(row.get(h, na_value)) for h in headers])
        with open(out_filepath, "w", encoding=encoding, newline="") as f:
            f.write(buf.getvalue())

    return {"rows": len(rows), "columns": len(headers)}


def _save_json(ctx, data, out_filepath, config, file_mode, overwrite, is_jsonl=False):
    pretty_print = config.get("pretty_print", True)
    indent = int(config.get("indent", 2))
    sort_keys = config.get("sort_keys", False)
    ensure_ascii = config.get("ensure_ascii", False)
    root_key = config.get("root_key", "").strip()

    if root_key and not is_jsonl:
        data = {root_key: data}

    record_count = len(data) if isinstance(data, list) else 1
    json_indent = indent if (pretty_print and not is_jsonl) else None

    if is_jsonl:
        rows = data if isinstance(data, list) else [data]
        content = "\n".join(json.dumps(row, default=str, ensure_ascii=ensure_ascii, sort_keys=sort_keys) for row in rows) + "\n"
    else:
        content = json.dumps(data, indent=json_indent, default=str, ensure_ascii=ensure_ascii, sort_keys=sort_keys)

    if file_mode == "append" and os.path.isfile(out_filepath):
        if is_jsonl:
            with open(out_filepath, "a", encoding="utf-8") as f:
                f.write(content)
        else:
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
            content = json.dumps(data, indent=json_indent, default=str, ensure_ascii=ensure_ascii, sort_keys=sort_keys)
            with open(out_filepath, "w", encoding="utf-8") as f:
                f.write(content)
    else:
        if os.path.exists(out_filepath) and not overwrite:
            raise BlockInputError(f"File already exists: {out_filepath}. Enable 'Overwrite Existing'.", recoverable=True)
        with open(out_filepath, "w", encoding="utf-8") as f:
            f.write(content)

    return {"records": record_count, "format": "jsonl" if is_jsonl else "json"}


def _save_parquet(ctx, data, out_filepath, config, file_mode, overwrite):
    compression = config.get("compression", "snappy").lower().strip()
    row_group_size = int(config.get("row_group_size", 0))

    rows = _normalize_rows(data)
    if not rows:
        raise BlockInputError("Cannot export as Parquet: no tabular data found", recoverable=False)

    if file_mode == "append" and os.path.isfile(out_filepath):
        try:
            import pyarrow.parquet as pq
            existing_table = pq.read_table(out_filepath)
            existing_rows = existing_table.to_pylist()
            rows = existing_rows + rows
            ctx.log_message(f"Appending to existing parquet ({len(existing_rows)} + {len(rows) - len(existing_rows)} rows)")
        except ImportError:
            ctx.log_message("WARNING: pyarrow not available for append, overwriting")
        except (OSError, ValueError) as e:
            ctx.log_message(f"WARNING: Could not read existing parquet ({e}), overwriting")

    if file_mode != "append" and os.path.exists(out_filepath) and not overwrite:
        raise BlockInputError(f"File already exists: {out_filepath}. Enable 'Overwrite Existing'.", recoverable=True)

    headers = _collect_headers(rows)
    written = False

    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
        columns = {h: [row.get(h) for row in rows] for h in headers}
        table = pa.table(columns)
        rg_size = row_group_size if row_group_size > 0 else None
        comp = compression if compression != "none" else None
        pq.write_table(table, out_filepath, compression=comp, row_group_size=rg_size)
        written = True
    except ImportError:
        pass

    if not written:
        try:
            import pandas as pd
            df = pd.DataFrame(rows)
            comp = compression if compression != "none" else None
            df.to_parquet(out_filepath, index=False, compression=comp)
            written = True
        except ImportError:
            pass

    if not written:
        raise BlockDependencyError("pyarrow", "Neither pyarrow nor pandas is installed", install_hint="pip install pyarrow")

    return {"rows": len(rows), "columns": len(headers), "compression": compression}


def _save_txt(ctx, data, out_filepath, config, file_mode, overwrite):
    encoding = config.get("txt_encoding", config.get("encoding", "utf-8"))
    append_mode = config.get("append_mode", False)
    max_length = int(config.get("max_length", 0))
    line_ending = config.get("line_ending", "LF")
    prefix = config.get("prefix", "")
    suffix = config.get("suffix", "")
    trim_whitespace = config.get("trim_whitespace", False)

    if isinstance(data, str):
        content = data
    else:
        content = json.dumps(data, indent=2, default=str, ensure_ascii=False)

    if trim_whitespace:
        content = "\n".join(line.strip() for line in content.splitlines())
    if max_length > 0 and len(content) > max_length:
        content = content[:max_length]
    if prefix:
        content = prefix + "\n" + content
    if suffix:
        content = content + "\n" + suffix
    if line_ending.upper() == "CRLF":
        content = content.replace("\r\n", "\n").replace("\n", "\r\n")

    effective_append = append_mode or (file_mode == "append")
    newline_char = "" if line_ending.upper() == "CRLF" else None

    if effective_append and os.path.isfile(out_filepath):
        with open(out_filepath, "a", encoding=encoding, newline=newline_char) as f:
            f.write("\n")
            f.write(content)
    else:
        if os.path.exists(out_filepath) and not overwrite:
            raise BlockInputError(f"File already exists: {out_filepath}. Enable 'Overwrite Existing'.", recoverable=True)
        with open(out_filepath, "w", encoding=encoding, newline=newline_char) as f:
            f.write(content)

    return {"characters": len(content)}


def _save_yaml(ctx, data, out_filepath, config, file_mode, overwrite):
    default_flow_style = config.get("default_flow_style", False)
    sort_keys = config.get("sort_keys", False)
    allow_unicode = config.get("allow_unicode", True)
    header_comment = config.get("header_comment", "").strip()

    try:
        import yaml
    except ImportError as e:
        raise BlockDependencyError("pyyaml", "PyYAML is required for YAML output", install_hint="pip install pyyaml")

    content = yaml.dump(data, default_flow_style=default_flow_style, sort_keys=sort_keys, allow_unicode=allow_unicode, indent=2)

    if file_mode == "append" and os.path.isfile(out_filepath):
        with open(out_filepath, "a", encoding="utf-8") as f:
            f.write("\n---\n")
            f.write(content)
    else:
        if os.path.exists(out_filepath) and not overwrite:
            raise BlockInputError(f"File already exists: {out_filepath}. Enable 'Overwrite Existing'.", recoverable=True)
        with open(out_filepath, "w", encoding="utf-8") as f:
            if header_comment:
                for line in header_comment.splitlines():
                    f.write(f"# {line}\n")
                f.write("\n")
            f.write(content)

    return {}


def _save_copy(ctx, data, out_dir, filename, overwrite):
    """Copy existing file or directory."""
    src_path = data
    if os.path.isfile(src_path):
        ext = os.path.splitext(src_path)[1]
        out_filepath = os.path.join(out_dir, filename + ext)
        if os.path.exists(out_filepath) and not overwrite:
            raise BlockInputError(f"File already exists: {out_filepath}", recoverable=True)
        shutil.copy2(src_path, out_filepath)
    elif os.path.isdir(src_path):
        out_filepath = os.path.join(out_dir, filename)
        if os.path.exists(out_filepath) and not overwrite:
            raise BlockInputError(f"Directory already exists: {out_filepath}", recoverable=True)
        if os.path.exists(out_filepath):
            shutil.rmtree(out_filepath)
        shutil.copytree(src_path, out_filepath)
    else:
        raise BlockInputError(f"Source not found: {src_path}", recoverable=False)
    return out_filepath


# ── Main entry point ─────────────────────────────────────────────────

def run(ctx):
    fmt = ctx.config.get("format", "auto").lower().strip()
    output_path = ctx.config.get("output_path",
                                  ctx.config.get("output_directory", "./output")).strip()
    filename = ctx.config.get("filename", "output").strip()
    overwrite = ctx.config.get("overwrite_existing",
                                ctx.config.get("overwrite", True))
    timestamp_filename = ctx.config.get("timestamp_filename", False)
    create_dirs = ctx.config.get("create_dirs", True)
    include_metadata = ctx.config.get("include_metadata", False)

    ctx.log_message(f"Data Export starting (format={fmt})")
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

    # ---- Step 1: Load data ----
    ctx.report_progress(1, 4)
    raw_data = ctx.load_input("data")
    if raw_data is None:
        raise BlockInputError("No input data provided. Connect a 'data' input.", recoverable=False)
    data = raw_data

    # ---- Step 2: Resolve format ----
    ctx.report_progress(2, 4)
    if fmt == "auto":
        fmt = _detect_format(data)
        ctx.log_message(f"Auto-detected format: {fmt}")

    # ---- Step 3: Resolve path and write ----
    ctx.report_progress(3, 4)

    if fmt == "copy":
        out_dir, _ = _resolve_path(ctx, output_path, filename, "", timestamp_filename, file_mode, iteration, create_dirs)
        out_filepath = _save_copy(ctx, data, out_dir, os.path.splitext(filename)[0], overwrite)
        extra_summary = {"format": "copy"}
    else:
        ext = FORMAT_EXTENSIONS.get(fmt, f".{fmt}")
        out_dir, out_filepath = _resolve_path(ctx, output_path, filename, ext, timestamp_filename, file_mode, iteration, create_dirs)

        if fmt == "csv":
            extra_summary = _save_csv(ctx, data, out_filepath, ctx.config, file_mode, overwrite)
        elif fmt in ("json", "jsonl"):
            extra_summary = _save_json(ctx, data, out_filepath, ctx.config, file_mode, overwrite, is_jsonl=(fmt == "jsonl"))
        elif fmt == "parquet":
            extra_summary = _save_parquet(ctx, data, out_filepath, ctx.config, file_mode, overwrite)
        elif fmt == "txt":
            extra_summary = _save_txt(ctx, data, out_filepath, ctx.config, file_mode, overwrite)
        elif fmt == "yaml":
            extra_summary = _save_yaml(ctx, data, out_filepath, ctx.config, file_mode, overwrite)
        else:
            raise BlockInputError(f"Unsupported format: {fmt}", recoverable=True)

    # ---- Step 4: Finalize ----
    ctx.report_progress(4, 4)
    if os.path.isfile(out_filepath):
        file_size = os.path.getsize(out_filepath)
    elif os.path.isdir(out_filepath):
        file_size = sum(
            os.path.getsize(os.path.join(dp, fn))
            for dp, _, fns in os.walk(out_filepath, followlinks=False)
            for fn in fns
        )
    else:
        file_size = 0

    ctx.log_message(f"Saved to {out_filepath} ({file_size:,} bytes)")

    # Write metadata sidecar if requested
    if include_metadata:
        meta = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "format": fmt,
            "filename": os.path.basename(out_filepath),
        }
        meta_path = out_filepath + ".meta.json"
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)

    summary = {"file_size_bytes": file_size, "format": fmt}
    summary.update(extra_summary)

    ctx.save_output("file_path", out_filepath)
    ctx.save_output("summary", summary)
    if os.path.isfile(out_filepath):
        ctx.save_artifact("data_export_output", out_filepath)
    ctx.log_metric("file_size_bytes", float(file_size))

    ctx.log_message("Data Export complete.")
