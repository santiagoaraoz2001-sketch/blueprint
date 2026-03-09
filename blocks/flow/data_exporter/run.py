"""Data Exporter — export pipeline data to JSON, JSONL, CSV, TSV, Markdown, or LaTeX."""

import csv
import io
import json
import os
import time
from datetime import datetime, timezone


def _normalize_rows(data):
    """Ensure data is a list of dicts suitable for tabular export."""
    if data is None:
        return []
    if isinstance(data, dict):
        if "data" in data and isinstance(data["data"], list):
            return _normalize_rows(data["data"])
        return [data]
    if isinstance(data, list):
        normalised = []
        for item in data:
            if isinstance(item, dict):
                normalised.append(item)
            else:
                normalised.append({"value": item})
        return normalised
    return [{"value": data}]


def _resolve_data(raw):
    """Resolve raw input to a Python object — handles file paths, dirs, and JSON strings."""
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


def _collect_headers(rows):
    """Collect all unique keys across rows, preserving insertion order."""
    seen = {}
    for row in rows:
        for key in row:
            if key not in seen:
                seen[key] = True
    return list(seen.keys())


def _write_json(data, indent):
    return json.dumps(data, indent=indent, default=str, ensure_ascii=False)


def _write_jsonl(rows):
    lines = []
    for row in rows:
        lines.append(json.dumps(row, default=str, ensure_ascii=False))
    return "\n".join(lines) + "\n"


def _write_csv_tsv(rows, delimiter):
    headers = _collect_headers(rows)
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=delimiter)
    writer.writerow(headers)
    for row in rows:
        writer.writerow([row.get(h, "") for h in headers])
    return buf.getvalue()


def _write_markdown(rows):
    headers = _collect_headers(rows)
    if not headers:
        return "(empty table)\n"
    col_widths = {h: len(str(h)) for h in headers}
    str_rows = []
    for row in rows:
        str_row = {}
        for h in headers:
            val = str(row.get(h, ""))
            str_row[h] = val
            col_widths[h] = max(col_widths[h], len(val))
        str_rows.append(str_row)
    header_line = "| " + " | ".join(str(h).ljust(col_widths[h]) for h in headers) + " |"
    separator = "| " + " | ".join("-" * col_widths[h] for h in headers) + " |"
    lines = [header_line, separator]
    for sr in str_rows:
        line = "| " + " | ".join(sr[h].ljust(col_widths[h]) for h in headers) + " |"
        lines.append(line)
    return "\n".join(lines) + "\n"


def _write_latex(rows):
    headers = _collect_headers(rows)
    if not headers:
        return "% empty table\n"
    col_spec = "|".join(["l"] * len(headers))
    lines = [
        "\\begin{tabular}{|" + col_spec + "|}",
        "\\hline",
        " & ".join(_latex_escape(h) for h in headers) + " \\\\",
        "\\hline",
    ]
    for row in rows:
        cells = [_latex_escape(str(row.get(h, ""))) for h in headers]
        lines.append(" & ".join(cells) + " \\\\")
    lines.append("\\hline")
    lines.append("\\end{tabular}")
    return "\n".join(lines) + "\n"


def _latex_escape(text):
    """Escape special LaTeX characters."""
    replacements = [
        ("\\", "\\textbackslash{}"),
        ("&", "\\&"),
        ("%", "\\%"),
        ("$", "\\$"),
        ("#", "\\#"),
        ("_", "\\_"),
        ("{", "\\{"),
        ("}", "\\}"),
        ("~", "\\textasciitilde{}"),
        ("^", "\\textasciicircum{}"),
    ]
    for old, new in replacements:
        text = text.replace(old, new)
    return text


FORMAT_EXTENSIONS = {
    "json": ".json",
    "jsonl": ".jsonl",
    "csv": ".csv",
    "tsv": ".tsv",
    "markdown": ".md",
    "latex": ".tex",
}


def run(ctx):
    export_format = ctx.config.get("format", "json").lower().strip()
    filename = ctx.config.get("filename", "output").strip()
    export_path = ctx.config.get("path", "./exports/").strip()
    indent = int(ctx.config.get("indent", 2))
    include_metadata = ctx.config.get("include_metadata", False)
    overwrite = ctx.config.get("overwrite", True)
    timestamp_filename = ctx.config.get("timestamp_filename", False)
    encoding = ctx.config.get("encoding", "utf-8")
    columns_filter = ctx.config.get("columns_filter", "").strip()
    max_rows = int(ctx.config.get("max_rows", 0))

    ctx.log_message(f"Data Exporter starting (format={export_format})")
    ctx.report_progress(0, 5)

    # Validate format
    if export_format not in FORMAT_EXTENSIONS:
        supported = ", ".join(sorted(FORMAT_EXTENSIONS.keys()))
        raise ValueError(f"Unsupported format '{export_format}'. Supported: {supported}")

    # ---- Step 1: Load input data ----
    ctx.report_progress(1, 5)
    raw_data = None
    for input_name in ["data", "input", "dataset"]:
        try:
            raw_data = ctx.load_input(input_name)
            if raw_data is not None:
                ctx.log_message(f"Loaded input from '{input_name}'")
                break
        except Exception:
            pass

    if raw_data is None:
        ctx.log_message("WARNING: No input data found. Exporting empty dataset.")
        raw_data = []

    resolved = _resolve_data(raw_data)
    rows = _normalize_rows(resolved)

    # Apply max_rows limit
    if max_rows > 0 and len(rows) > max_rows:
        ctx.log_message(f"Limiting output from {len(rows)} to {max_rows} rows")
        rows = rows[:max_rows]

    # Filter columns if specified
    if columns_filter and rows:
        selected = [c.strip() for c in columns_filter.split(",") if c.strip()]
        rows = [{k: row.get(k) for k in selected if k in row} for row in rows]
        ctx.log_message(f"Filtered to columns: {selected}")

    ctx.log_message(f"Prepared {len(rows)} rows for export")

    # ---- Step 2: Load optional metrics ----
    ctx.report_progress(2, 5)
    metrics_data = None
    try:
        metrics_data = ctx.load_input("metrics")
    except Exception:
        pass

    # ---- Step 3: Build output content ----
    ctx.report_progress(3, 5)

    if include_metadata:
        metadata = {
            "_export_timestamp": datetime.now(timezone.utc).isoformat(),
            "_format": export_format,
            "_row_count": len(rows),
        }
        if metrics_data and isinstance(metrics_data, dict):
            metadata["_metrics"] = metrics_data

    if export_format == "json":
        if include_metadata:
            payload = {"metadata": metadata, "data": rows}
        else:
            payload = rows
        content = _write_json(payload, indent)
    elif export_format == "jsonl":
        content = _write_jsonl(rows)
    elif export_format == "csv":
        content = _write_csv_tsv(rows, delimiter=",")
    elif export_format == "tsv":
        content = _write_csv_tsv(rows, delimiter="\t")
    elif export_format == "markdown":
        content = _write_markdown(rows)
    elif export_format == "latex":
        content = _write_latex(rows)
    else:
        raise ValueError(f"Unsupported format: {export_format}")

    # ---- Step 4: Resolve path and write file ----
    ctx.report_progress(4, 5)
    ext = FORMAT_EXTENSIONS[export_format]

    # Apply timestamp if requested
    if timestamp_filename:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_filename = f"{filename}_{ts}{ext}"
    elif not filename.endswith(ext):
        out_filename = filename + ext
    else:
        out_filename = filename

    # Resolve export path (relative to run_dir if not absolute)
    if os.path.isabs(export_path):
        out_dir = export_path
    else:
        out_dir = os.path.join(ctx.run_dir, export_path)

    os.makedirs(out_dir, exist_ok=True)
    out_filepath = os.path.join(out_dir, out_filename)

    # Overwrite check
    if os.path.exists(out_filepath) and not overwrite:
        raise FileExistsError(
            f"File already exists: {out_filepath}. Enable 'Overwrite Existing' or use 'Timestamp Filename'."
        )

    with open(out_filepath, "w", encoding=encoding) as f:
        f.write(content)

    # Write metadata sidecar for non-JSON formats if metadata is requested
    if include_metadata and export_format != "json":
        meta_path = out_filepath + ".meta.json"
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2, default=str)
        ctx.log_message(f"Metadata sidecar written to {meta_path}")

    # ---- Step 5: Finalize ----
    ctx.report_progress(5, 5)
    file_size = os.path.getsize(out_filepath)
    ctx.log_message(f"Exported {len(rows)} rows to {out_filepath} ({file_size:,} bytes)")

    # Save outputs for downstream chaining
    ctx.save_output("file_path", out_filepath)
    ctx.save_output("row_count", {"rows_exported": len(rows), "file_size_bytes": file_size, "format": export_format})

    ctx.save_artifact("exported_data", out_filepath)
    ctx.log_metric("rows_exported", len(rows))
    ctx.log_metric("file_size_bytes", file_size)

    if metrics_data and isinstance(metrics_data, dict):
        ctx.log_message(f"Metrics received: {len(metrics_data)} keys")

    ctx.log_message("Data export complete.")
