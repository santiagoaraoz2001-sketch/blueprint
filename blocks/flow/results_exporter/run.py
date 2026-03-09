"""Results Exporter — export pipeline results to CSV, JSON, JSONL, or Parquet."""

import csv
import io
import json
import os
from datetime import datetime, timezone


def _load_data(raw):
    """Resolve raw input to a Python object (list of dicts preferred)."""
    if isinstance(raw, str):
        if os.path.isfile(raw):
            with open(raw, "r", encoding="utf-8") as f:
                return json.load(f)
        if os.path.isdir(raw):
            data_file = os.path.join(raw, "data.json")
            if os.path.isfile(data_file):
                with open(data_file, "r", encoding="utf-8") as f:
                    return json.load(f)
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return [{"value": raw}]
    return raw


def _normalize_rows(data):
    """Ensure data is a list of flat dicts for tabular export."""
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
    """Collect all unique keys across rows, preserving insertion order."""
    seen = {}
    for row in rows:
        for key in row:
            if key not in seen:
                seen[key] = True
    return list(seen.keys())


def _write_csv(rows):
    headers = _collect_headers(rows)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(headers)
    for row in rows:
        writer.writerow([row.get(h, "") for h in headers])
    return buf.getvalue()


def _write_json(data, indent=2):
    return json.dumps(data, indent=indent, default=str, ensure_ascii=False)


def _write_jsonl(rows):
    lines = []
    for row in rows:
        lines.append(json.dumps(row, default=str, ensure_ascii=False))
    return "\n".join(lines) + "\n"


def _write_parquet(rows, file_path):
    """Write rows to a Parquet file. Returns True on success."""
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError:
        pass
    else:
        headers = _collect_headers(rows)
        columns = {}
        for h in headers:
            columns[h] = [row.get(h) for row in rows]
        table = pa.table(columns)
        pq.write_table(table, file_path)
        return True

    try:
        import pandas as pd
        df = pd.DataFrame(rows)
        df.to_parquet(file_path, index=False)
        return True
    except ImportError:
        return False


FORMAT_EXTENSIONS = {
    "csv": ".csv",
    "json": ".json",
    "jsonl": ".jsonl",
    "parquet": ".parquet",
}


def run(ctx):
    export_format = ctx.config.get("format", "csv").lower().strip()
    file_name = ctx.config.get("file_name", "results").strip()
    output_path = ctx.config.get("output_path", "").strip()
    include_metadata = ctx.config.get("include_metadata", True)
    overwrite = ctx.config.get("overwrite", True)
    timestamp_filename = ctx.config.get("timestamp_filename", False)
    columns_filter = ctx.config.get("columns_filter", "").strip()
    sort_by = ctx.config.get("sort_by", "").strip()

    ctx.log_message(f"Results Exporter starting (format={export_format})")
    ctx.report_progress(0, 5)

    # Validate format
    if export_format not in FORMAT_EXTENSIONS:
        supported = ", ".join(sorted(FORMAT_EXTENSIONS.keys()))
        raise ValueError(f"Unsupported format '{export_format}'. Supported: {supported}")

    # ---- Step 1: Load input data ----
    ctx.report_progress(1, 5)
    raw_data = ctx.load_input("data")
    if raw_data is None:
        raise ValueError("No input data provided. Connect a 'data' input to this block.")

    resolved = _load_data(raw_data)
    rows = _normalize_rows(resolved)

    # Sort rows if specified
    if sort_by and rows:
        desc = sort_by.startswith("-")
        col = sort_by.lstrip("-")
        if any(col in row for row in rows):
            rows.sort(key=lambda r: r.get(col, ""), reverse=desc)
            ctx.log_message(f"Sorted by '{col}' ({'desc' if desc else 'asc'})")

    # Filter columns if specified
    if columns_filter and rows:
        selected = [c.strip() for c in columns_filter.split(",") if c.strip()]
        rows = [{k: row.get(k) for k in selected if k in row} for row in rows]
        ctx.log_message(f"Filtered to columns: {selected}")

    ctx.log_message(f"Loaded {len(rows)} rows for export")

    # ---- Step 2: Build metadata ----
    ctx.report_progress(2, 5)
    metadata = None
    if include_metadata:
        metadata = {
            "export_timestamp": datetime.now(timezone.utc).isoformat(),
            "format": export_format,
            "row_count": len(rows),
            "columns": _collect_headers(rows),
        }

    # ---- Step 3: Determine output file path ----
    ctx.report_progress(3, 5)
    ext = FORMAT_EXTENSIONS[export_format]

    if timestamp_filename:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_filename = f"{file_name}_{ts}{ext}"
    elif not file_name.endswith(ext):
        out_filename = file_name + ext
    else:
        out_filename = file_name

    # Resolve output directory
    if output_path:
        if os.path.isabs(output_path):
            out_dir = output_path
        else:
            out_dir = os.path.join(ctx.run_dir, output_path)
    else:
        out_dir = ctx.run_dir

    os.makedirs(out_dir, exist_ok=True)
    out_filepath = os.path.join(out_dir, out_filename)

    # Overwrite check
    if os.path.exists(out_filepath) and not overwrite:
        raise FileExistsError(
            f"File already exists: {out_filepath}. Enable 'Overwrite Existing' or use 'Timestamp Filename'."
        )

    # ---- Step 4: Write output ----
    ctx.report_progress(4, 5)

    if export_format == "csv":
        content = _write_csv(rows)
        with open(out_filepath, "w", encoding="utf-8", newline="") as f:
            f.write(content)

    elif export_format == "json":
        if include_metadata and metadata:
            payload = {"metadata": metadata, "data": rows}
        else:
            payload = rows
        content = _write_json(payload)
        with open(out_filepath, "w", encoding="utf-8") as f:
            f.write(content)

    elif export_format == "jsonl":
        content = _write_jsonl(rows)
        with open(out_filepath, "w", encoding="utf-8") as f:
            f.write(content)
        if include_metadata and metadata:
            meta_path = out_filepath + ".meta.json"
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2, default=str)
            ctx.log_message(f"Metadata sidecar written to {meta_path}")

    elif export_format == "parquet":
        success = _write_parquet(rows, out_filepath)
        if not success:
            ctx.log_message(
                "WARNING: pyarrow and pandas not available. "
                "Install pyarrow for Parquet support. Falling back to CSV."
            )
            out_filepath = out_filepath.replace(".parquet", ".parquet_fallback.csv")
            content = _write_csv(rows)
            with open(out_filepath, "w", encoding="utf-8", newline="") as f:
                f.write(content)
        if include_metadata and metadata:
            meta_path = out_filepath + ".meta.json"
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2, default=str)

    # ---- Step 5: Finalize ----
    ctx.report_progress(5, 5)
    file_size = os.path.getsize(out_filepath)
    col_count = len(_collect_headers(rows))
    ctx.log_message(f"Exported {len(rows)} rows ({col_count} cols) to {out_filepath} ({file_size:,} bytes)")

    # Save outputs for downstream chaining
    ctx.save_output("file_path", out_filepath)
    ctx.save_output("summary", {
        "rows_exported": len(rows),
        "columns": col_count,
        "file_size_bytes": file_size,
        "format": export_format,
    })

    ctx.save_artifact("exported_results", out_filepath)
    ctx.log_metric("rows_exported", float(len(rows)))
    ctx.log_metric("file_size_bytes", float(file_size))
    ctx.log_metric("column_count", float(col_count))

    ctx.log_message("Results export complete.")
