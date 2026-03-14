"""Database Writer — write pipeline results to a SQL database."""

import csv as csv_mod
import json
import os
import re
import sqlite3

from backend.block_sdk.exceptions import (
    BlockDependencyError,
    BlockExecutionError,
    BlockInputError,
)

# Pattern for validating SQL identifiers from user config
_SAFE_TABLE_NAME_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_.]*$")


def _quote_identifier(name):
    """Safely quote a SQL identifier using double-quote escaping (SQL standard)."""
    safe = str(name).replace('"', '""')
    return f'"{safe}"'


def _validate_table_name(name):
    """Validate table name from user config to prevent SQL injection."""
    if not _SAFE_TABLE_NAME_RE.match(name):
        raise BlockInputError(
            f"Invalid table name: {name!r}. "
            "Only letters, numbers, underscores, and dots allowed (must start with letter or underscore).",
            recoverable=True,
        )
    return name


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
    seen = {}
    for row in rows:
        for key in row:
            if key not in seen:
                seen[key] = True
    return list(seen.keys())


def _infer_sql_type(values):
    """Infer SQL type from a list of Python values."""
    for v in values:
        if v is None:
            continue
        if isinstance(v, bool):
            return "INTEGER"
        if isinstance(v, int):
            return "INTEGER"
        if isinstance(v, float):
            return "REAL"
        return "TEXT"
    return "TEXT"


def _write_with_pandas(rows, connection_string, table_name, if_exists, dtype_mapping, batch_size):
    """Write using pandas + sqlalchemy (supports PostgreSQL, MySQL, etc.)."""
    try:
        import pandas as pd
    except ImportError as e:
        missing = getattr(e, "name", None) or "pandas"
        raise BlockDependencyError(
            missing,
            f"Required library not installed: {e}",
            install_hint="pip install pandas",
        )
    try:
        from sqlalchemy import create_engine
    except ImportError as e:
        missing = getattr(e, "name", None) or "sqlalchemy"
        raise BlockDependencyError(
            missing,
            f"Required library not installed: {e}",
            install_hint="pip install sqlalchemy",
        )

    engine = create_engine(connection_string)
    df = pd.DataFrame(rows)

    dtype = None
    if dtype_mapping:
        from sqlalchemy import types as sa_types
        type_map = {
            "TEXT": sa_types.Text,
            "INTEGER": sa_types.Integer,
            "REAL": sa_types.Float,
            "FLOAT": sa_types.Float,
            "BOOLEAN": sa_types.Boolean,
            "TIMESTAMP": sa_types.DateTime,
            "VARCHAR": sa_types.String,
        }
        dtype = {}
        for col, sql_type in dtype_mapping.items():
            sa_type = type_map.get(sql_type.upper())
            if sa_type:
                dtype[col] = sa_type()

    df.to_sql(
        table_name,
        engine,
        if_exists=if_exists,
        index=False,
        chunksize=batch_size,
        dtype=dtype,
    )
    return len(df)


def _write_with_sqlite(rows, db_path, table_name, if_exists, create_table, schema_dict, batch_size):
    """Write using sqlite3 directly (no external dependencies)."""
    headers = _collect_headers(rows)
    if not headers:
        raise BlockInputError(
            "Cannot write to database: no columns found in data",
            details=f"Data has {len(rows)} rows but no dict keys",
            recoverable=False,
        )

    # Quote table name and column names to prevent SQL injection
    quoted_table = _quote_identifier(table_name)
    quoted_headers = [_quote_identifier(h) for h in headers]

    try:
        conn = sqlite3.connect(db_path)
    except sqlite3.OperationalError as e:
        raise BlockExecutionError(
            f"Cannot connect to SQLite database at {db_path}: {e}",
            recoverable=False,
        )
    cursor = conn.cursor()

    try:
        if if_exists == "replace":
            cursor.execute(f"DROP TABLE IF EXISTS {quoted_table}")

        if if_exists == "fail":
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table_name,)
            )
            if cursor.fetchone():
                raise BlockInputError(
                    f"Table '{table_name}' already exists and if_exists='fail'",
                    recoverable=True,
                )

        # Create table if needed
        if create_table:
            if schema_dict:
                col_defs = []
                for h, qh in zip(headers, quoted_headers):
                    sql_type = schema_dict.get(h, "TEXT")
                    col_defs.append(f"{qh} {sql_type}")
            else:
                col_defs = []
                for h, qh in zip(headers, quoted_headers):
                    values = [row.get(h) for row in rows[:100]]
                    sql_type = _infer_sql_type(values)
                    col_defs.append(f"{qh} {sql_type}")

            create_sql = f"CREATE TABLE IF NOT EXISTS {quoted_table} ({', '.join(col_defs)})"
            cursor.execute(create_sql)

        # Insert data in batches
        placeholders = ", ".join(["?"] * len(headers))
        insert_sql = f"INSERT INTO {quoted_table} ({', '.join(quoted_headers)}) VALUES ({placeholders})"

        total_inserted = 0
        for i in range(0, len(rows), batch_size):
            batch = rows[i:i + batch_size]
            values = []
            for row in batch:
                row_values = []
                for h in headers:
                    v = row.get(h)
                    if isinstance(v, (dict, list)):
                        v = json.dumps(v, default=str)
                    row_values.append(v)
                values.append(tuple(row_values))
            cursor.executemany(insert_sql, values)
            total_inserted += len(batch)

        conn.commit()
        return total_inserted
    except sqlite3.Error as e:
        conn.rollback()
        raise BlockExecutionError(
            f"SQLite error writing to table '{table_name}': {e}",
            recoverable=False,
        )
    finally:
        conn.close()


def run(ctx):
    connection_string = ctx.config.get("connection_string", "").strip()
    table_name = ctx.config.get("table_name", "").strip()
    if_exists = ctx.config.get("if_exists", "append").lower().strip()
    batch_size = int(ctx.config.get("batch_size", 1000))
    create_table = ctx.config.get("create_table", True)
    schema_str = ctx.config.get("schema", "").strip()
    dtype_str = ctx.config.get("dtype_mapping", "").strip()
    timestamp_column = ctx.config.get("timestamp_column", "").strip()

    if not connection_string:
        raise BlockInputError(
            "Connection string is required (e.g. sqlite:///data.db).",
            recoverable=True,
        )
    if not table_name:
        raise BlockInputError(
            "Table name is required.",
            recoverable=True,
        )

    # Validate table name to prevent SQL injection
    _validate_table_name(table_name)

    ctx.log_message(f"Database Writer starting (table={table_name})")
    ctx.report_progress(0, 4)

    # Parse schema
    schema_dict = None
    if schema_str:
        try:
            schema_dict = json.loads(schema_str)
        except json.JSONDecodeError:
            ctx.log_message("WARNING: Invalid schema JSON, ignoring")

    dtype_mapping = None
    if dtype_str:
        try:
            dtype_mapping = json.loads(dtype_str)
        except json.JSONDecodeError:
            ctx.log_message("WARNING: Invalid dtype mapping JSON, ignoring")

    # ---- Step 1: Load data ----
    ctx.report_progress(1, 4)
    raw_data = ctx.load_input("data")
    if raw_data is None:
        raise BlockInputError(
            "No input data provided. Connect a 'data' input.",
            recoverable=False,
        )

    resolved = _resolve_data(raw_data)
    rows = _normalize_rows(resolved)

    # Auto-add timestamp column if configured
    if timestamp_column and rows:
        from datetime import datetime, timezone
        ts = datetime.now(timezone.utc).isoformat()
        for row in rows:
            row[timestamp_column] = ts
        ctx.log_message(f"Added timestamp column: {timestamp_column}")

    headers = _collect_headers(rows)
    ctx.log_message(f"Loaded {len(rows)} rows, {len(headers)} columns")

    if not rows:
        ctx.log_message("WARNING: No data to write")
        # Branch: no data to write — return early
        ctx.save_output("status", "No data to write")
        # Branch: no data to write — return early
        ctx.save_output("summary", {"rows_written": 0})
        ctx.report_progress(4, 4)
        return

    # ---- Step 2: Determine database type ----
    ctx.report_progress(2, 4)
    is_sqlite = connection_string.startswith("sqlite")

    # ---- Step 3: Write data ----
    ctx.report_progress(3, 4)
    rows_written = 0

    if is_sqlite:
        # Extract path from sqlite:///path
        db_path = connection_string.replace("sqlite:///", "").replace("sqlite://", "")
        if not os.path.isabs(db_path):
            db_path = os.path.join(ctx.run_dir, db_path)
        db_dir = os.path.dirname(db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)

        rows_written = _write_with_sqlite(rows, db_path, table_name, if_exists, create_table, schema_dict, batch_size)
        ctx.log_message(f"Written {rows_written} rows to SQLite: {db_path}")
    else:
        # Use pandas + sqlalchemy for other databases
        rows_written = _write_with_pandas(rows, connection_string, table_name, if_exists, dtype_mapping, batch_size)
        ctx.log_message(f"Written {rows_written} rows via SQLAlchemy")

    # ---- Step 4: Finalize ----
    ctx.report_progress(4, 4)
    status_msg = f"Wrote {rows_written} rows to {table_name}"
    ctx.log_message(status_msg)

    # Branch: successful write
    ctx.save_output("status", status_msg)
    # Branch: successful write
    ctx.save_output("summary", {
        "rows_written": rows_written,
        "columns": len(headers),
        "table_name": table_name,
        "if_exists": if_exists,
        "database_type": "sqlite" if is_sqlite else "sqlalchemy",
    })
    ctx.log_metric("rows_written", float(rows_written))
    ctx.log_metric("columns", float(len(headers)))

    ctx.log_message("Database Writer complete.")
