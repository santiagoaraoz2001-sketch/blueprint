"""Aggregator — collect multiple inputs and merge into a single output."""

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


def _load_data(raw):
    """Resolve raw input value to Python data, handling file/directory paths."""
    if isinstance(raw, str) and os.path.isdir(raw):
        data_file = os.path.join(raw, "data.json")
        if os.path.isfile(data_file):
            with open(data_file, "r") as f:
                return json.load(f)
        return None
    elif isinstance(raw, str) and os.path.isfile(raw):
        with open(raw, "r") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return f.read()
    return raw


def _normalize_to_rows(data):
    """Normalize data to a list of items."""
    if isinstance(data, list):
        return data
    elif isinstance(data, dict):
        return [data]
    elif isinstance(data, str):
        return [{"text": data}]
    elif data is not None:
        return [{"value": data}]
    return []


def run(ctx):
    strategy = ctx.config.get("strategy", "concatenate")
    deduplicate = ctx.config.get("deduplicate", False)
    add_source_label = ctx.config.get("add_source_label", False)
    sort_by = ctx.config.get("sort_by", "").strip()
    join_key = ctx.config.get("join_key", "").strip()
    limit = int(ctx.config.get("limit", 0))

    # Collect from input ports in_1 through in_5
    required_ports = {"in_1", "in_2"}
    input_port_ids = ["in_1", "in_2", "in_3", "in_4", "in_5"]
    collected = []  # list of (port_name, loaded_data)

    for port_id in input_port_ids:
        try:
            raw = ctx.load_input(port_id)
            if raw is not None:
                data = _load_data(raw)
                if data is not None:
                    collected.append((port_id, data))
        except (ValueError, Exception):
            pass

    # Validate that required ports provided data
    loaded_ports = {name for name, _ in collected}
    missing = required_ports - loaded_ports
    if missing:
        raise BlockInputError(
            f"Required input(s) {', '.join(sorted(missing))} not connected "
            f"or produced no data. The Aggregator needs at least 2 inputs.",
            recoverable=False
        )

    ctx.log_message(f"Aggregating {len(collected)} inputs (strategy={strategy})")

    if not collected:
        ctx.log_message("No inputs received. Producing empty output.")
        merged = []
    elif strategy == "pick_first":
        # Use the first non-empty input
        first_name, first_data = collected[0]
        merged = _normalize_to_rows(first_data)
        ctx.log_message(f"Picked first non-empty input: {first_name} ({len(merged)} rows)")
    elif strategy == "merge_fields":
        all_inputs_rows = []
        for name, data in collected:
            rows = _normalize_to_rows(data)
            all_inputs_rows.append(rows)
            ctx.log_message(f"  {name}: {len(rows)} rows")

        if join_key:
            # Key-based JOIN: match rows by a shared field (like SQL JOIN)
            # Build index from first input
            merged = []
            base_index = {}
            base_rows = all_inputs_rows[0] if all_inputs_rows else []
            for row in base_rows:
                if isinstance(row, dict) and join_key in row:
                    key_val = str(row[join_key])
                    base_index[key_val] = dict(row)

            # Merge other inputs by key
            for input_rows in all_inputs_rows[1:]:
                for row in input_rows:
                    if isinstance(row, dict) and join_key in row:
                        key_val = str(row[join_key])
                        if key_val in base_index:
                            base_index[key_val].update(row)
                        else:
                            base_index[key_val] = dict(row)

            merged = list(base_index.values())
            ctx.log_message(f"Key-based merge on '{join_key}': {len(merged)} joined rows")
        else:
            # Zip rows from all inputs, merging dicts at each index
            max_len = max(len(r) for r in all_inputs_rows) if all_inputs_rows else 0
            merged = []
            for i in range(max_len):
                combined_row = {}
                for input_rows in all_inputs_rows:
                    if i < len(input_rows) and isinstance(input_rows[i], dict):
                        combined_row.update(input_rows[i])
                merged.append(combined_row)
            ctx.log_message(f"Merged fields: {len(merged)} rows with combined keys")
    elif strategy == "interleave":
        # Alternate rows from each input for balanced mixing (A/B test consolidation, balanced training)
        all_inputs_rows = []
        for name, data in collected:
            rows = _normalize_to_rows(data)
            all_inputs_rows.append((name, rows))
            ctx.log_message(f"  {name}: {len(rows)} rows")

        merged = []
        max_len = max(len(r) for _, r in all_inputs_rows) if all_inputs_rows else 0
        for i in range(max_len):
            for name, rows in all_inputs_rows:
                if i < len(rows):
                    row = rows[i]
                    if add_source_label and isinstance(row, dict):
                        row["_source"] = name
                    merged.append(row)
        ctx.log_message(f"Interleaved: {len(merged)} rows from {len(all_inputs_rows)} inputs")
    elif strategy == "flatten":
        # Flatten nested lists recursively
        all_rows = []
        for name, data in collected:
            rows = _normalize_to_rows(data)
            for item in rows:
                if isinstance(item, list):
                    all_rows.extend(item)
                else:
                    all_rows.append(item)
            ctx.log_message(f"  {name}: {len(rows)} items")
        merged = all_rows
    else:  # concatenate (default)
        merged = []
        for name, data in collected:
            rows = _normalize_to_rows(data)
            if add_source_label:
                for row in rows:
                    if isinstance(row, dict):
                        row["_source"] = name
            merged.extend(rows)
            ctx.log_message(f"  {name}: {len(rows)} rows")

    # Add source labels for non-concatenate strategies if requested
    if add_source_label and strategy not in ("concatenate", "pick_first"):
        # For merge_fields and flatten, source labeling is trickier;
        # we mark each row with combined sources
        pass  # Already handled inline for concatenate; skip for others

    # Deduplicate
    if deduplicate and merged:
        seen = set()
        unique = []
        for row in merged:
            key = json.dumps(row, sort_keys=True, default=str)
            if key not in seen:
                seen.add(key)
                unique.append(row)
        ctx.log_message(f"Deduplicated: {len(merged)} -> {len(unique)} rows")
        merged = unique

    # Sort by field if requested
    if sort_by and merged:
        descending = sort_by.startswith("-")
        key_name = sort_by.lstrip("-")
        try:
            merged.sort(key=lambda row: row.get(key_name, "") if isinstance(row, dict) else "", reverse=descending)
            ctx.log_message(f"Sorted by '{key_name}' ({'desc' if descending else 'asc'})")
        except (TypeError, AttributeError):
            ctx.log_message(f"Warning: could not sort by '{key_name}'")

    # Limit output rows
    if limit > 0 and len(merged) > limit:
        ctx.log_message(f"Limiting output: {len(merged)} -> {limit} rows")
        merged = merged[:limit]

    ctx.log_message(f"Aggregated result: {len(merged)} total rows")

    # Save output
    out_dir = os.path.join(ctx.run_dir, "output")
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "data.json"), "w") as f:
        json.dump(merged, f, indent=2)

    ctx.save_output("output", out_dir)

    agg_metrics = {
        "total_rows": len(merged),
        "num_inputs": len(collected),
        "strategy": strategy,
        "input_sizes": {name: len(_normalize_to_rows(data)) for name, data in collected},
    }
    ctx.save_output("metrics", agg_metrics)

    ctx.log_metric("total_rows", len(merged))
    ctx.log_metric("num_inputs", len(collected))
    ctx.report_progress(1, 1)
