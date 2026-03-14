"""Save CSV — save pipeline data as a CSV file."""

import csv
import io
import json
import os

from backend.block_sdk.exceptions import BlockInputError


def _read_jsonl(f):
    """Read JSONL file with per-line error handling."""
    records = []
    for line in f:
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            records.append({"_raw_line": line, "_parse_error": True})
    return records


def _resolve_data(raw):
    """Resolve raw input to a Python object, handling any upstream format."""
    if isinstance(raw, str):
        if os.path.isfile(raw):
            ext = os.path.splitext(raw)[1].lower()
            try:
                if ext == ".jsonl":
                    with open(raw, "r", encoding="utf-8", errors="replace") as f:
                        return _read_jsonl(f)
                elif ext in (".json",):
                    with open(raw, "r", encoding="utf-8") as f:
                        return json.load(f)
                elif ext == ".csv":
                    with open(raw, "r", encoding="utf-8", errors="replace") as f:
                        return list(csv.DictReader(f))
                elif ext in (".yaml", ".yml"):
                    try:
                        import yaml
                        with open(raw, "r", encoding="utf-8") as f:
                            result = yaml.safe_load(f)
                            return result if result is not None else []
                    except ImportError:
                        with open(raw, "r", encoding="utf-8", errors="replace") as f:
                            return [{"value": f.read()}]
                else:
                    with open(raw, "r", encoding="utf-8", errors="replace") as f:
                        content = f.read()
                    try:
                        return json.loads(content)
                    except (json.JSONDecodeError, ValueError):
                        return [{"value": content}]
            except (UnicodeDecodeError, json.JSONDecodeError):
                return [{"value": f"<unreadable file: {os.path.basename(raw)}>"}]
        if os.path.isdir(raw):
            for name in ("data.json", "results.json", "output.json", "data.csv", "data.yaml"):
                fpath = os.path.join(raw, name)
                if os.path.isfile(fpath):
                    return _resolve_data(fpath)
            try:
                files = [f for f in os.listdir(raw) if not f.startswith(".")]
            except OSError:
                files = []
            return [{"directory": raw, "files": ", ".join(files)}]
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return [{"value": raw}]
    if isinstance(raw, (dict, list)):
        return raw
    return [{"value": str(raw)}]


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

    # ---- Step 1: Load and normalize data ----
    ctx.report_progress(1, 4)
    raw_data = ctx.load_input("data")
    if raw_data is None:
        raise BlockInputError(
            "No input data provided. Connect a 'data' input.",
            recoverable=False,
        )

    resolved = _resolve_data(raw_data)
    rows = _normalize_rows(resolved)

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
                f"None of the specified columns found. Available: {_collect_headers(_normalize_rows(resolved))}",
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

    out_filepath = os.path.join(out_dir, filename)

    if os.path.exists(out_filepath) and not overwrite:
        raise BlockInputError(
            f"File already exists: {out_filepath}. Enable 'Overwrite Existing'.",
            recoverable=True,
        )

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
