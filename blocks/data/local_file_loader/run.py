"""Local File Loader — loads data from CSV, TSV, JSONL, JSON, Parquet, Excel, or text files."""

import csv
import json
import os


def run(ctx):
    file_path = ctx.config.get("file_path", "")
    fmt = ctx.config.get("format", "auto")
    encoding = ctx.config.get("encoding", "utf-8")
    delimiter = ctx.config.get("delimiter", ",")
    skip_rows = int(ctx.config.get("skip_rows", 0))
    max_rows = int(ctx.config.get("max_rows", 0))
    columns = ctx.config.get("columns", "")
    sheet_name = ctx.config.get("sheet_name", "")
    has_header = ctx.config.get("has_header", True)

    # Apply overrides from connected config input
    try:
        _ci = ctx.load_input("config")
        if _ci:
            _ov = json.load(open(_ci)) if isinstance(_ci, str) and os.path.isfile(_ci) else (_ci if isinstance(_ci, dict) else {})
            if isinstance(_ov, dict) and _ov:
                ctx.log_message(f"Applying {len(_ov)} config override(s) from input")
                file_path = _ov.get("file_path", file_path)
                fmt = _ov.get("format", fmt)
                encoding = _ov.get("encoding", encoding)
                columns = _ov.get("columns", columns)
                max_rows = int(_ov.get("max_rows", max_rows))
                sheet_name = _ov.get("sheet_name", sheet_name)
    except (ValueError, KeyError):
        pass

    # Normalize boolean
    if isinstance(has_header, str):
        has_header = has_header.lower() in ("true", "1", "yes")

    if not file_path:
        raise ValueError("file_path is required")

    file_path = os.path.expanduser(file_path)
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    ctx.log_message(f"Loading file: {file_path}")

    # Detect format from extension
    if fmt == "auto":
        ext = os.path.splitext(file_path)[1].lower()
        fmt = {
            ".csv": "csv",
            ".tsv": "tsv",
            ".jsonl": "jsonl",
            ".json": "json",
            ".parquet": "parquet",
            ".xlsx": "xlsx",
            ".xls": "xlsx",
            ".txt": "txt",
        }.get(ext, "csv")
        ctx.log_message(f"Auto-detected format: {fmt}")

    out_path = os.path.join(ctx.run_dir, "dataset")
    os.makedirs(out_path, exist_ok=True)

    rows = []

    # Determine total lines for progress reporting (estimate for large files)
    _file_size = os.path.getsize(file_path)
    _est_total = max_rows if max_rows > 0 else max(1, _file_size // 100)  # rough estimate
    _progress_interval = max(1000, _est_total // 10)  # every 1000 rows or 10%

    if fmt in ("csv", "tsv"):
        sep = "\t" if fmt == "tsv" else delimiter
        with open(file_path, "r", encoding=encoding) as f:
            if has_header:
                reader = csv.DictReader(f, delimiter=sep)
            else:
                # No header row — auto-generate column names (col_0, col_1, ...)
                sample = f.readline()
                f.seek(0)
                num_cols = len(sample.split(sep))
                fieldnames = [f"col_{j}" for j in range(num_cols)]
                reader = csv.DictReader(f, fieldnames=fieldnames, delimiter=sep)
                ctx.log_message(f"No header: auto-generated {num_cols} column names")
            for i, row in enumerate(reader):
                if i < skip_rows:
                    continue
                rows.append(row)
                if len(rows) % _progress_interval == 0:
                    ctx.report_progress(len(rows), _est_total)
                if max_rows > 0 and len(rows) >= max_rows:
                    break

    elif fmt in ("jsonl", "json"):
        with open(file_path, "r", encoding=encoding) as f:
            content = f.read().strip()

        # Detect if it's a JSON array or JSONL
        if content.startswith("["):
            all_rows = json.loads(content)
            if not isinstance(all_rows, list):
                all_rows = [all_rows]
        else:
            lines = content.splitlines()
            all_rows = []
            for idx, line in enumerate(lines):
                if line.strip():
                    all_rows.append(json.loads(line))
                if (idx + 1) % _progress_interval == 0:
                    ctx.report_progress(idx + 1, len(lines))

        # Apply skip_rows and max_rows
        all_rows = all_rows[skip_rows:]
        if max_rows > 0:
            all_rows = all_rows[:max_rows]
        rows = all_rows

    elif fmt == "parquet":
        try:
            import pandas as pd
            df = pd.read_parquet(file_path)
            if skip_rows > 0:
                df = df.iloc[skip_rows:]
            if max_rows > 0:
                df = df.head(max_rows)
            rows = df.to_dict(orient="records")
        except ImportError:
            raise RuntimeError("pandas required for parquet files: pip install pandas pyarrow")

    elif fmt == "xlsx":
        try:
            import pandas as pd
            read_kwargs = {"io": file_path}
            if sheet_name:
                read_kwargs["sheet_name"] = sheet_name
            df = pd.read_excel(**read_kwargs)
            if skip_rows > 0:
                df = df.iloc[skip_rows:]
            if max_rows > 0:
                df = df.head(max_rows)
            rows = df.to_dict(orient="records")
            ctx.log_message(f"Excel sheet: {sheet_name or '(default)'}")
        except ImportError:
            raise RuntimeError("pandas + openpyxl required for Excel files: pip install pandas openpyxl")

    elif fmt == "txt":
        with open(file_path, "r", encoding=encoding) as f:
            lines = f.readlines()
        # Apply skip_rows
        lines = lines[skip_rows:]
        if max_rows > 0:
            lines = lines[:max_rows]
        rows = []
        for i, line in enumerate(lines):
            rows.append({"line_number": i + 1, "text": line.rstrip("\n\r")})
            if (i + 1) % _progress_interval == 0:
                ctx.report_progress(i + 1, len(lines))

    else:
        ctx.log_message(f"WARNING: Unknown format '{fmt}', falling back to CSV")
        with open(file_path, "r", encoding=encoding) as f:
            reader = csv.DictReader(f, delimiter=delimiter)
            for i, row in enumerate(reader):
                if i < skip_rows:
                    continue
                rows.append(row)
                if max_rows > 0 and len(rows) >= max_rows:
                    break

    # Apply column filtering
    if columns:
        col_list = [c.strip() for c in columns.split(",") if c.strip()]
        if col_list and rows:
            available = set(rows[0].keys()) if rows else set()
            valid = [c for c in col_list if c in available]
            if valid:
                rows = [{k: row.get(k) for k in valid} for row in rows]
                ctx.log_message(f"Filtered to columns: {valid}")
            else:
                ctx.log_message(f"WARNING: None of the requested columns {col_list} found. Available: {sorted(available)}")

    # Save as JSON
    with open(os.path.join(out_path, "data.json"), "w", encoding="utf-8") as f:
        json.dump(rows, f, default=str)

    ctx.log_metric("row_count", len(rows))
    if rows:
        ctx.log_metric("column_count", len(rows[0]))
        ctx.log_message(f"Columns: {list(rows[0].keys())}")
    ctx.log_message(f"Loaded {len(rows)} rows ({fmt})")
    ctx.report_progress(1, 1)
    ctx.save_output("dataset", out_path)

    # Save metrics output
    _col_names = list(rows[0].keys()) if rows else []
    _metrics = {"row_count": len(rows), "column_count": len(_col_names), "columns": _col_names, "format": fmt, "file_size_bytes": os.path.getsize(file_path)}
    _mp = os.path.join(ctx.run_dir, "metrics.json")
    with open(_mp, "w") as f:
        json.dump(_metrics, f, indent=2)
    ctx.save_output("metrics", _mp)
