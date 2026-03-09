"""Save Local — save any pipeline output to a specific directory with auto-format detection."""

import csv
import io
import json
import os
import shutil
from datetime import datetime, timezone


def _resolve_data(raw):
    """Resolve raw input to a Python object."""
    if isinstance(raw, str):
        if os.path.isfile(raw):
            return raw  # Keep as file path for copying
        if os.path.isdir(raw):
            return raw  # Keep as directory path for copying
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return raw  # Plain string
    return raw


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

    # ---- Step 1: Load data ----
    ctx.report_progress(1, 4)
    raw_data = ctx.load_input("data")
    if raw_data is None:
        raise ValueError("No input data provided. Connect a 'data' input.")

    data = _resolve_data(raw_data)

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
        raise FileNotFoundError(f"Output directory does not exist: {out_dir}. Enable 'Create Directories'.")

    # Apply timestamp
    if timestamp_filename:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{filename}_{ts}"

    # ---- Step 4: Write output ----
    ctx.report_progress(3, 4)

    if fmt == "copy":
        # Copy existing file or directory
        src_path = data
        if os.path.isfile(src_path):
            ext = os.path.splitext(src_path)[1]
            out_filepath = os.path.join(out_dir, filename + ext)
            if os.path.exists(out_filepath) and not overwrite:
                raise FileExistsError(f"File already exists: {out_filepath}")
            shutil.copy2(src_path, out_filepath)
        elif os.path.isdir(src_path):
            out_filepath = os.path.join(out_dir, filename)
            if os.path.exists(out_filepath) and not overwrite:
                raise FileExistsError(f"Directory already exists: {out_filepath}")
            if os.path.exists(out_filepath):
                shutil.rmtree(out_filepath)
            shutil.copytree(src_path, out_filepath)
        else:
            raise FileNotFoundError(f"Source not found: {src_path}")

    elif fmt == "json":
        out_filepath = os.path.join(out_dir, filename + ".json")
        if os.path.exists(out_filepath) and not overwrite:
            raise FileExistsError(f"File already exists: {out_filepath}")
        content = json.dumps(data, indent=2, default=str, ensure_ascii=False)
        with open(out_filepath, "w", encoding="utf-8") as f:
            f.write(content)

    elif fmt == "csv":
        out_filepath = os.path.join(out_dir, filename + ".csv")
        if os.path.exists(out_filepath) and not overwrite:
            raise FileExistsError(f"File already exists: {out_filepath}")
        rows = _normalize_rows(data)
        headers = _collect_headers(rows)
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(headers)
        for row in rows:
            writer.writerow([str(row.get(h, "")) for h in headers])
        with open(out_filepath, "w", encoding="utf-8", newline="") as f:
            f.write(buf.getvalue())

    elif fmt == "txt":
        out_filepath = os.path.join(out_dir, filename + ".txt")
        if os.path.exists(out_filepath) and not overwrite:
            raise FileExistsError(f"File already exists: {out_filepath}")
        if isinstance(data, str):
            content = data
        else:
            content = json.dumps(data, indent=2, default=str, ensure_ascii=False)
        with open(out_filepath, "w", encoding="utf-8") as f:
            f.write(content)

    elif fmt == "yaml":
        out_filepath = os.path.join(out_dir, filename + ".yaml")
        if os.path.exists(out_filepath) and not overwrite:
            raise FileExistsError(f"File already exists: {out_filepath}")
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
            raise FileExistsError(f"File already exists: {out_filepath}")
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
            except ImportError:
                raise ImportError("Install pyarrow or pandas for Parquet support.")
    else:
        raise ValueError(f"Unsupported format: {fmt}")

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
            os.path.getsize(os.path.join(dp, f))
            for dp, _, fns in os.walk(out_filepath)
            for f in fns
        )

    ctx.log_message(f"Saved to {out_filepath} ({file_size:,} bytes)")

    ctx.save_output("file_path", out_filepath)
    ctx.save_output("summary", {"file_size_bytes": file_size, "format": fmt})
    if os.path.isfile(out_filepath):
        ctx.save_artifact("local_output", out_filepath)
    ctx.log_metric("file_size_bytes", float(file_size))

    ctx.log_message("Save Local complete.")
