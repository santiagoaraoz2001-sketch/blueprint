"""Data Preview — compute statistics and preview sample rows."""

import json
import os


def run(ctx):
    dataset_path = ctx.load_input("dataset")
    num_rows = int(ctx.config.get("num_rows", 20))
    include_text_stats = ctx.config.get("include_text_stats", True)
    passthrough = ctx.config.get("passthrough", True)
    sort_by = ctx.config.get("sort_by", "")
    sample_mode = ctx.config.get("sample_mode", "head")
    filter_column = ctx.config.get("filter_column", "")
    filter_value = ctx.config.get("filter_value", "")

    data_file = os.path.join(dataset_path, "data.json") if os.path.isdir(dataset_path) else dataset_path
    if not os.path.isfile(data_file):
        raise FileNotFoundError(f"Dataset not found: {data_file}")

    with open(data_file, "r", encoding="utf-8") as f:
        rows = json.load(f)

    if not isinstance(rows, list):
        raise ValueError("Dataset must be a JSON array")

    ctx.log_message(f"Dataset has {len(rows)} rows")
    ctx.report_progress(1, 3)

    # Compute basic stats
    stats = {"total_rows": len(rows)}

    if rows:
        columns = list(rows[0].keys())
        stats["columns"] = columns
        stats["num_columns"] = len(columns)

        # Per-column stats
        for col in columns:
            values = [r.get(col) for r in rows]
            non_null = [v for v in values if v is not None]
            stats[f"{col}_null_count"] = len(values) - len(non_null)
            stats[f"{col}_unique"] = len(set(str(v) for v in non_null))

            # Numeric stats
            nums = [v for v in non_null if isinstance(v, (int, float))]
            if nums:
                stats[f"{col}_min"] = min(nums)
                stats[f"{col}_max"] = max(nums)
                stats[f"{col}_mean"] = round(sum(nums) / len(nums), 4)

            # Text length stats
            if include_text_stats:
                strings = [v for v in non_null if isinstance(v, str)]
                if strings:
                    lengths = sorted(len(s) for s in strings)
                    stats[f"{col}_text_count"] = len(strings)
                    stats[f"{col}_text_min_len"] = lengths[0]
                    stats[f"{col}_text_max_len"] = lengths[-1]
                    stats[f"{col}_text_mean_len"] = round(sum(lengths) / len(lengths), 1)
                    stats[f"{col}_text_median_len"] = lengths[len(lengths) // 2]

    ctx.report_progress(2, 3)

    # Filter rows for targeted inspection (quality monitoring workflow)
    filtered_rows = rows
    if filter_column and rows and filter_column in rows[0]:
        if filter_value:
            filtered_rows = [r for r in rows if str(r.get(filter_column, "")) == filter_value]
        else:
            # Show only rows where the column is non-empty
            filtered_rows = [r for r in rows if r.get(filter_column) is not None and str(r.get(filter_column, "")).strip()]
        ctx.log_message(f"Filtered by '{filter_column}'{'=' + filter_value if filter_value else ' (non-empty)'}: {len(filtered_rows)}/{len(rows)} rows")

    # Sort rows if requested (quality monitoring workflow)
    sorted_rows = filtered_rows
    if sort_by and rows and sort_by in rows[0]:
        sorted_rows = sorted(rows, key=lambda r: r.get(sort_by, 0) if isinstance(r.get(sort_by), (int, float)) else str(r.get(sort_by, "")))
        ctx.log_message(f"Sorted by '{sort_by}'")

    # Select preview rows based on sample_mode
    if sample_mode == "tail":
        preview = sorted_rows[-num_rows:]
    elif sample_mode == "random":
        import random
        preview = random.sample(sorted_rows, min(num_rows, len(sorted_rows)))
    else:
        preview = sorted_rows[:num_rows]
    preview_dir = os.path.join(ctx.run_dir, "preview")
    os.makedirs(preview_dir, exist_ok=True)
    with open(os.path.join(preview_dir, "data.json"), "w", encoding="utf-8") as f:
        json.dump(preview, f, indent=2)

    ctx.save_output("stats", stats)
    ctx.save_output("preview", preview_dir)

    # Passthrough: forward the full dataset so downstream blocks can use it
    if passthrough:
        ctx.save_output("dataset", dataset_path)

    ctx.log_metric("total_rows", stats["total_rows"])
    ctx.log_metric("num_columns", stats.get("num_columns", 0))
    ctx.log_message(f"Preview: {len(preview)} rows saved")
    ctx.report_progress(3, 3)
