"""SQL Query — execute SQL queries against a database with parameterized query support."""

import json
import os
import signal
import sqlite3
import time

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


def run(ctx):
    connection_string = ctx.config.get("connection_string", "")
    query = ctx.config.get("query", "")
    timeout = int(ctx.config.get("timeout", 30))
    max_rows = int(ctx.config.get("max_rows", 0))
    parameterized = ctx.config.get("parameterized", False)
    params_str = ctx.config.get("params", "")
    ssl_ca = ctx.config.get("ssl_ca", "")
    ssl_cert = ctx.config.get("ssl_cert", "")
    ssl_key = ctx.config.get("ssl_key", "")

    # Apply overrides from connected config input
    try:
        _ci = ctx.load_input("config")
        if _ci:
            _ov = json.load(open(_ci)) if isinstance(_ci, str) and os.path.isfile(_ci) else (_ci if isinstance(_ci, dict) else {})
            if isinstance(_ov, dict) and _ov:
                ctx.log_message(f"Applying {len(_ov)} config override(s) from input")
                connection_string = _ov.get("connection_string", connection_string)
                query = _ov.get("query", query)
                max_rows = int(_ov.get("max_rows", max_rows))
                if "params" in _ov:
                    params_str = json.dumps(_ov["params"]) if isinstance(_ov["params"], list) else str(_ov["params"])
                    parameterized = True
    except (ValueError, KeyError):
        pass

    # Normalize booleans
    if isinstance(parameterized, str):
        parameterized = parameterized.lower() in ("true", "1", "yes")

    if not query:
        raise BlockConfigError("query", "query is required — provide a SQL query to execute")

    ctx.log_message(f"Database: {connection_string or '(in-memory demo)'}")
    ctx.log_message(f"Query: {query[:200]}{'...' if len(query) > 200 else ''}")

    # Parse parameterized query params
    query_params = None
    if parameterized and params_str.strip():
        try:
            query_params = json.loads(params_str)
            if not isinstance(query_params, (list, tuple)):
                query_params = [query_params]
            ctx.log_message(f"Using {len(query_params)} query parameter(s)")
        except json.JSONDecodeError as e:
            ctx.log_message(f"WARNING: Could not parse params JSON: {e}. Running without parameters.")
            query_params = None

    conn = None

    # Determine connection type
    if connection_string:
        cs = connection_string.strip()

        # Check if it's a SQLAlchemy-style URI for non-SQLite databases
        if cs.startswith(("postgresql://", "postgres://", "mysql://", "mssql://", "oracle://")):
            try:
                import sqlalchemy
                connect_args = {}
                if ssl_ca or ssl_cert or ssl_key:
                    if cs.startswith(("postgresql://", "postgres://")):
                        if ssl_ca: connect_args["sslrootcert"] = os.path.expanduser(ssl_ca)
                        if ssl_cert: connect_args["sslcert"] = os.path.expanduser(ssl_cert)
                        if ssl_key: connect_args["sslkey"] = os.path.expanduser(ssl_key)
                        connect_args["sslmode"] = "verify-full"
                    elif cs.startswith("mysql://"):
                        ssl_dict = {}
                        if ssl_ca: ssl_dict["ca"] = os.path.expanduser(ssl_ca)
                        if ssl_cert: ssl_dict["cert"] = os.path.expanduser(ssl_cert)
                        if ssl_key: ssl_dict["key"] = os.path.expanduser(ssl_key)
                        connect_args["ssl"] = ssl_dict
                    ctx.log_message("SSL certificates configured")
                engine = sqlalchemy.create_engine(cs, connect_args=connect_args if connect_args else {})
                ctx.log_message(f"Connected via SQLAlchemy: {cs.split('@')[-1] if '@' in cs else cs}")
                ctx.log_metric("simulation_mode", 0.0)

                with engine.connect() as sa_conn:
                    if query_params:
                        result = sa_conn.execute(sqlalchemy.text(query), query_params if isinstance(query_params, dict) else {})
                    else:
                        result = sa_conn.execute(sqlalchemy.text(query))

                    columns = list(result.keys()) if result.returns_rows else []
                    if result.returns_rows:
                        if max_rows > 0:
                            raw_rows = result.fetchmany(max_rows)
                        else:
                            raw_rows = result.fetchall()
                        rows = [dict(zip(columns, row)) for row in raw_rows]
                    else:
                        rows = []
                        ctx.log_message("Query executed (no rows returned — likely INSERT/UPDATE/DELETE)")

                ctx.log_message(f"Query returned {len(rows)} rows, {len(columns)} columns")
                if columns:
                    ctx.log_message(f"Columns: {', '.join(columns)}")

                # Save and return early
                _save_output(ctx, rows, columns)
                return

            except ImportError:
                raise BlockDependencyError("sqlalchemy", install_hint=f"pip install sqlalchemy")

        # SQLite: handle sqlite:/// prefix or plain file path
        if cs.startswith("sqlite:///"):
            db_path = cs[len("sqlite:///"):]
        else:
            db_path = cs

        db_path = os.path.expanduser(db_path)
        if os.path.isfile(db_path):
            conn = sqlite3.connect(db_path)
            ctx.log_message(f"Connected to SQLite: {db_path}")
            ctx.log_metric("simulation_mode", 0.0)
        else:
            try:
                conn = sqlite3.connect(db_path)
                ctx.log_message(f"Created/connected to SQLite: {db_path}")
                ctx.log_metric("simulation_mode", 0.0)
            except Exception as e:
                ctx.log_message(f"Cannot connect to {db_path}: {e}. Using in-memory database.")
                conn = sqlite3.connect(":memory:")
                ctx.log_metric("simulation_mode", 0.0)
    else:
        # Demo mode with in-memory database
        ctx.log_message("⚠️ SIMULATION MODE: No connection string provided. Using in-memory demo database with synthetic data. Set connection_string for real database queries.")
        ctx.log_metric("simulation_mode", 1.0)
        conn = sqlite3.connect(":memory:")
        conn.execute("""CREATE TABLE demo_data (
            id INTEGER PRIMARY KEY, name TEXT, value REAL, category TEXT
        )""")
        demo_rows = [
            (1, "alpha", 0.95, "A"), (2, "beta", 0.87, "B"),
            (3, "gamma", 0.92, "A"), (4, "delta", 0.78, "C"),
            (5, "epsilon", 0.85, "B"), (6, "zeta", 0.91, "A"),
            (7, "eta", 0.73, "C"), (8, "theta", 0.88, "B"),
        ]
        conn.executemany("INSERT INTO demo_data VALUES (?, ?, ?, ?)", demo_rows)
        conn.commit()
        if not query.strip():
            query = "SELECT * FROM demo_data"

    # Execute with timeout (Unix only)
    use_alarm = hasattr(signal, "SIGALRM")

    def _timeout_handler(signum, frame):
        raise TimeoutError(f"Query exceeded {timeout}s timeout")

    if use_alarm:
        old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
        signal.alarm(timeout)

    try:
        if query_params:
            cursor = conn.execute(query, query_params)
        else:
            cursor = conn.execute(query)

        columns = [desc[0] for desc in cursor.description] if cursor.description else []

        if max_rows > 0:
            raw_rows = cursor.fetchmany(max_rows)
        else:
            raw_rows = cursor.fetchall()

        rows = [dict(zip(columns, row)) for row in raw_rows]
        ctx.log_message(f"Query returned {len(rows)} rows, {len(columns)} columns")
        if columns:
            ctx.log_message(f"Columns: {', '.join(columns)}")

    except TimeoutError:
        ctx.log_message(f"TIMEOUT: Query exceeded {timeout}s limit")
        raise
    except Exception as e:
        raise BlockExecutionError(f"SQL query failed: {e}", details=str(e))
    finally:
        if use_alarm:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old_handler)
        if conn:
            conn.close()

    _save_output(ctx, rows, columns)


def _save_output(ctx, rows, columns):
    """Save query results as dataset + metrics."""
    out_dir = os.path.join(ctx.run_dir, "dataset")
    os.makedirs(out_dir, exist_ok=True)
    out_file = os.path.join(out_dir, "data.json")
    with open(out_file, "w") as f:
        json.dump(rows, f, indent=2, default=str)

    ctx.save_output("dataset", out_dir)
    ctx.log_metric("row_count", len(rows))
    ctx.log_metric("column_count", len(columns))
    ctx.report_progress(1, 1)

    # Save metrics output
    _metrics = {"row_count": len(rows), "column_count": len(columns), "columns": columns}
    _mp = os.path.join(ctx.run_dir, "metrics.json")
    with open(_mp, "w") as f:
        json.dump(_metrics, f, indent=2)
    ctx.save_output("metrics", _mp)
