"""Column Transform — rename, drop, keep, cast, or derive columns in a dataset."""

import json
import os

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
    dataset_path = ctx.load_input("dataset")
    operation = ctx.config.get("operation", "rename")

    # Load dataset
    data_file = os.path.join(dataset_path, "data.json") if os.path.isdir(dataset_path) else dataset_path
    if not os.path.isfile(data_file):
        raise BlockInputError(f"Dataset not found at: {dataset_path}", details="Check that the upstream block produced output", recoverable=False)

    with open(data_file, "r", encoding="utf-8") as f:
        rows = json.load(f)

    if not isinstance(rows, list):
        raise BlockDataError("Dataset must be a JSON array", details="Expected a list of objects from upstream block")

    if not rows:
        ctx.log_message("Empty dataset — passing through.")
        out_dir = os.path.join(ctx.run_dir, "dataset")
        os.makedirs(out_dir, exist_ok=True)
        with open(os.path.join(out_dir, "data.json"), "w") as f:
            json.dump([], f)
        # Branch: empty dataset — return early
        ctx.save_output("transformed_dataset", out_dir)
        ctx.report_progress(1, 1)
        return

    original_cols = list(rows[0].keys())
    ctx.log_message(f"Loaded {len(rows)} rows. Operation: {operation}")
    ctx.log_message(f"Original columns: {original_cols}")

    if operation == "rename":
        rename_str = ctx.config.get("rename_map", "{}")
        try:
            rename_map = json.loads(rename_str) if isinstance(rename_str, str) else rename_str
        except json.JSONDecodeError:
            raise BlockConfigError("rename_map", f"Invalid JSON in rename_map: {rename_str}")
        if not isinstance(rename_map, dict):
            raise BlockConfigError("rename_map", "rename_map must be a JSON object")
        rows = [{rename_map.get(k, k): v for k, v in row.items()} for row in rows]
        ctx.log_message(f"Renamed: {rename_map}")

    elif operation == "drop":
        drop_str = ctx.config.get("drop_columns", "")
        drop_set = {c.strip() for c in drop_str.split(",") if c.strip()}
        if not drop_set:
            raise BlockConfigError("drop_columns", "drop_columns cannot be empty for 'drop' operation")
        rows = [{k: v for k, v in row.items() if k not in drop_set} for row in rows]
        ctx.log_message(f"Dropped: {drop_set}")

    elif operation == "keep":
        keep_str = ctx.config.get("keep_columns", "")
        keep_set = {c.strip() for c in keep_str.split(",") if c.strip()}
        if not keep_set:
            raise BlockConfigError("keep_columns", "keep_columns cannot be empty for 'keep' operation")
        rows = [{k: v for k, v in row.items() if k in keep_set} for row in rows]
        ctx.log_message(f"Kept: {keep_set}")

    elif operation == "cast":
        cast_str = ctx.config.get("cast_map", "{}")
        try:
            cast_map = json.loads(cast_str) if isinstance(cast_str, str) else cast_str
        except json.JSONDecodeError:
            raise BlockConfigError("cast_map", f"Invalid JSON in cast_map: {cast_str}")
        if not isinstance(cast_map, dict):
            raise BlockConfigError("cast_map", "cast_map must be a JSON object")
        for row in rows:
            for col, target_type in cast_map.items():
                if col in row:
                    val = row[col]
                    try:
                        if target_type == "int":
                            row[col] = int(float(val)) if val is not None else 0
                        elif target_type == "float":
                            row[col] = float(val) if val is not None else 0.0
                        elif target_type == "str":
                            row[col] = str(val) if val is not None else ""
                        elif target_type == "bool":
                            row[col] = bool(val)
                    except (ValueError, TypeError):
                        pass  # keep original value if cast fails
        ctx.log_message(f"Cast: {cast_map}")

    elif operation == "template":
        col_name = ctx.config.get("template_column", "derived")
        template = ctx.config.get("template_expr", "")
        if not template:
            raise BlockConfigError("template_expr", "template_expr is required for 'template' operation")
        for row in rows:
            try:
                row[col_name] = template.format_map(row)
            except (KeyError, ValueError) as e:
                row[col_name] = None
                ctx.log_message(f"Template error on row: {e}")
        ctx.log_message(f"Derived column '{col_name}' from template")

    elif operation == "lowercase":
        lower_str = ctx.config.get("lowercase_columns", "")
        lower_cols = [c.strip() for c in lower_str.split(",") if c.strip()]
        if not lower_cols:
            raise BlockConfigError("lowercase_columns", "lowercase_columns cannot be empty for 'lowercase' operation")
        for row in rows:
            for col in lower_cols:
                if col in row and isinstance(row[col], str):
                    row[col] = row[col].lower()
        ctx.log_message(f"Lowercased: {lower_cols}")

    else:
        raise BlockConfigError("operation", f"Unknown operation: {operation}")

    # Save
    final_cols = list(rows[0].keys()) if rows else []
    out_dir = os.path.join(ctx.run_dir, "dataset")
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "data.json"), "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2)

    stats = {
        "rows": len(rows),
        "columns_before": len(original_cols),
        "columns_after": len(final_cols),
        "operation": operation,
        "original_columns": original_cols,
        "result_columns": final_cols,
    }

    # Branch: normal execution — transformed dataset
    ctx.save_output("transformed_dataset", out_dir)
    ctx.save_output("stats", stats)
    ctx.log_metric("rows", len(rows))
    ctx.log_metric("columns_before", len(original_cols))
    ctx.log_metric("columns_after", len(final_cols))
    ctx.log_message(f"Result: {len(rows)} rows, columns: {final_cols}")
    ctx.report_progress(1, 1)
