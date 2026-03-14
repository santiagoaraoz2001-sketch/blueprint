"""Database Writer — write pipeline results to a SQL database."""

import json
import os
import sqlite3


def _resolve_data(raw):
    """Resolve raw input to a Python object."""
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
        from backend.block_sdk.exceptions import BlockDependencyError
        missing = str(e).split("'")[-2] if "'" in str(e) else str(e)
        raise BlockDependencyError(
            missing,
            f"Required library not installed: {e}",
            install_hint="pip install pandas",
        )
    from sqlalchemy import create_engine

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
        raise ValueError("No columns found in data")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        if if_exists == "replace":
            cursor.execute(f"DROP TABLE IF EXISTS [{table_name}]")

        if if_exists == "fail":
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table_name,)
            )
            if cursor.fetchone():
                raise ValueError(f"Table '{table_name}' already exists and if_exists='fail'")

        # Create table if needed
        if create_table:
            if schema_dict:
                col_defs = []
                for h in headers:
                    sql_type = schema_dict.get(h, "TEXT")
                    col_defs.append(f"[{h}] {sql_type}")
            else:
                col_defs = []
                for h in headers:
                    values = [row.get(h) for row in rows[:100]]
                    sql_type = _infer_sql_type(values)
                    col_defs.append(f"[{h}] {sql_type}")

            create_sql = f"CREATE TABLE IF NOT EXISTS [{table_name}] ({', '.join(col_defs)})"
            cursor.execute(create_sql)

        # Insert data in batches
        placeholders = ", ".join(["?"] * len(headers))
        insert_sql = f"INSERT INTO [{table_name}] ({', '.join(f'[{h}]' for h in headers)}) VALUES ({placeholders})"

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
        raise ValueError("Connection string is required (e.g. sqlite:///data.db).")
    if not table_name:
        raise ValueError("Table name is required.")

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
        raise ValueError("No input data provided. Connect a 'data' input.")

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
        os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else ".", exist_ok=True)

        rows_written = _write_with_sqlite(rows, db_path, table_name, if_exists, create_table, schema_dict, batch_size)
        ctx.log_message(f"Written {rows_written} rows to SQLite: {db_path}")
    else:
        # Use pandas + sqlalchemy for other databases
        try:
            rows_written = _write_with_pandas(rows, connection_string, table_name, if_exists, dtype_mapping, batch_size)
            ctx.log_message(f"Written {rows_written} rows via SQLAlchemy")
        except ImportError:
            raise ImportError(
                "pandas and sqlalchemy are required for non-SQLite databases. "
                "Install with: pip install pandas sqlalchemy"
            )

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
