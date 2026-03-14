"""Save Parquet — save pipeline data as a Parquet columnar file."""

import csv as csv_mod
import json
import os

from backend.block_sdk.exceptions import BlockDependencyError, BlockInputError


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
                        return list(csv_mod.DictReader(f))
                elif ext in (".yaml", ".yml"):
                    try:
                        import yaml
                        with open(raw, "r", encoding="utf-8") as f:
                            result = yaml.safe_load(f)
                            return result if result is not None else []
                    except ImportError:
                        with open(raw, "r", encoding="utf-8", errors="replace") as f:
                            return [{"value": f.read()}]
                elif ext == ".parquet":
                    try:
                        import pandas as pd
                        return pd.read_parquet(raw).to_dict(orient="records")
                    except ImportError:
                        return [{"file_path": raw}]
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
            raise BlockInputError(
                "Cannot save data in Parquet format: expected tabular data, got raw string",
                details=f"Upstream block produced: {raw[:200]}",
                recoverable=False,
            )
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
    seen = {}
    for row in rows:
        for key in row:
            if key not in seen:
                seen[key] = True
    return list(seen.keys())


def _write_parquet_pyarrow(rows, file_path, compression, row_group_size):
    """Write Parquet using pyarrow."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    headers = _collect_headers(rows)
    columns = {}
    for h in headers:
        columns[h] = [row.get(h) for row in rows]

    table = pa.table(columns)
    rg_size = row_group_size if row_group_size > 0 else None
    comp = compression if compression != "none" else None
    pq.write_table(table, file_path, compression=comp, row_group_size=rg_size)


def _write_parquet_pandas(rows, file_path, compression):
    """Fallback: write Parquet using pandas."""
    try:
        import pandas as pd
    except ImportError as e:
        missing = getattr(e, "name", None) or "pandas"
        raise BlockDependencyError(
            missing,
            f"Required library not installed: {e}",
            install_hint="pip install pandas",
        )

    df = pd.DataFrame(rows)
    comp = compression if compression != "none" else None
    df.to_parquet(file_path, index=False, compression=comp)


def run(ctx):
    output_path = ctx.config.get("output_path", "./output").strip()
    filename = ctx.config.get("filename", "data.parquet").strip()
    compression = ctx.config.get("compression", "snappy").lower().strip()
    row_group_size = int(ctx.config.get("row_group_size", 0))
    overwrite = ctx.config.get("overwrite_existing", True)
    timestamp_filename = ctx.config.get("timestamp_filename", False)

    ctx.log_message(f"Save Parquet starting (compression={compression})")
    ctx.report_progress(0, 3)

    # ---- Step 1: Load data ----
    ctx.report_progress(1, 3)
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
            "Cannot save data in Parquet format: expected tabular data (list of dicts), got empty data",
            details=f"Upstream block produced: {str(raw_data)[:200]}",
            recoverable=False,
        )

    headers = _collect_headers(rows)
    ctx.log_message(f"Loaded {len(rows)} rows, {len(headers)} columns")

    # ---- Step 2: Resolve path ----
    ctx.report_progress(2, 3)
    if os.path.isabs(output_path):
        out_dir = output_path
    else:
        out_dir = os.path.join(ctx.run_dir, output_path)
    os.makedirs(out_dir, exist_ok=True)

    if not filename.endswith(".parquet"):
        filename += ".parquet"

    # Apply timestamp to filename
    if timestamp_filename:
        from datetime import datetime
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        base = filename.rsplit(".", 1)[0]
        filename = f"{base}_{ts}.parquet"

    out_filepath = os.path.join(out_dir, filename)

    if os.path.exists(out_filepath) and not overwrite:
        raise BlockInputError(
            f"File already exists: {out_filepath}. Enable 'Overwrite Existing'.",
            recoverable=True,
        )

    # ---- Step 3: Write Parquet ----
    written = False
    try:
        _write_parquet_pyarrow(rows, out_filepath, compression, row_group_size)
        written = True
        ctx.log_message("Written using pyarrow")
    except ImportError:
        pass

    if not written:
        try:
            _write_parquet_pandas(rows, out_filepath, compression)
            written = True
            ctx.log_message("Written using pandas")
        except ImportError:
            pass

    if not written:
        raise BlockDependencyError(
            "pyarrow",
            "Neither pyarrow nor pandas is installed for Parquet support",
            install_hint="pip install pyarrow",
        )

    ctx.report_progress(3, 3)
    file_size = os.path.getsize(out_filepath)
    ctx.log_message(f"Saved {len(rows)} rows to {out_filepath} ({file_size:,} bytes)")

    ctx.save_output("file_path", out_filepath)
    ctx.save_output("summary", {
        "rows": len(rows),
        "columns": len(headers),
        "file_size_bytes": file_size,
        "compression": compression,
    })
    ctx.save_artifact("parquet_output", out_filepath)
    ctx.log_metric("rows_saved", float(len(rows)))
    ctx.log_metric("file_size_bytes", float(file_size))

    ctx.log_message("Save Parquet complete.")
