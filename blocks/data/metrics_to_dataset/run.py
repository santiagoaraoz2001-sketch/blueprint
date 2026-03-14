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


def _load_metrics(ctx, input_id):
    """Load metrics from an input, handling both dict and file path formats."""
    raw = ctx.load_input(input_id)
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and os.path.isfile(raw):
        with open(raw, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
            raise BlockDataError(
                f"Metrics file for '{input_id}' must contain a JSON object, "
                f"got {type(data).__name__}"
            )
    raise BlockInputError(f"Cannot parse metrics from input '{input_id}'", recoverable=False)


def _flatten_dict(d, parent_key="", sep="/"):
    """Flatten nested dicts into dot-separated keys for tabular output."""
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(_flatten_dict(v, new_key, sep).items())
        else:
            items.append((new_key, v))
    return dict(items)


def run(ctx):
    metrics = _load_metrics(ctx, "metrics")
    fmt = ctx.config.get("format", "rows")
    label = ctx.config.get("label", "")

    # Flatten nested metrics for consistent tabular output
    metrics = _flatten_dict(metrics)

    # Collect optional second metrics
    all_metrics = [("a", metrics)]
    try:
        metrics_b = _flatten_dict(_load_metrics(ctx, "metrics_b"))
        all_metrics.append(("b", metrics_b))
    except (ValueError, KeyError):
        pass

    total_metric_count = sum(len(m) for _, m in all_metrics)

    ctx.log_message(
        f"Processing {total_metric_count} metrics from "
        f"{len(all_metrics)} input(s). Format: {fmt}"
    )

    if fmt == "rows":
        # One row per metric: {metric, value, [label]}
        data = []
        for tag, m in all_metrics:
            run_label = label if label else tag
            for key, value in m.items():
                row = {"metric": key, "value": value}
                if len(all_metrics) > 1 or label:
                    row["label"] = run_label
                data.append(row)
    else:
        # Columns: one row with each metric as a column
        data = []
        for tag, m in all_metrics:
            row = dict(m)
            if len(all_metrics) > 1 or label:
                row["label"] = label if label else tag
            data.append(row)

    out_dir = os.path.join(ctx.run_dir, "dataset")
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "data.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    stats = {
        "row_count": len(data),
        "metric_count": total_metric_count,
        "input_count": len(all_metrics),
        "format": fmt,
    }

    ctx.save_output("dataset", out_dir)
    ctx.save_output("metrics", stats)
    ctx.log_metric("row_count", len(data))
    ctx.log_metric("metric_count", total_metric_count)
    ctx.log_message(
        f"Converted {total_metric_count} metrics into "
        f"{len(data)}-row dataset (format: {fmt})"
    )
    ctx.report_progress(1, 1)
