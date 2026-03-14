import json
import os
import random


def _auto_detect_column(row, preferred="text"):
    """Auto-detect the best text column from a dataset row."""
    available = list(row.keys())
    if preferred and preferred in available:
        return preferred
    for candidate in ["text", "content", "prompt", "input", "sentence", "question"]:
        if candidate in available:
            return candidate
    return available[0] if available else "text"


def run(ctx):
    dataset_path = ctx.load_input("dataset")
    mode = ctx.config.get("mode", "first")
    index = int(ctx.config.get("index", 0))
    count = int(ctx.config.get("count", 1))
    filter_column = ctx.config.get("filter_column", "")
    filter_value = ctx.config.get("filter_value", "")
    seed = int(ctx.config.get("seed", 42))
    text_column = ctx.config.get("text_column", "text")

    # Load dataset
    data_file = (
        os.path.join(dataset_path, "data.json")
        if os.path.isdir(dataset_path)
        else dataset_path
    )
    if not os.path.isfile(data_file):
        raise FileNotFoundError(f"Dataset not found at: {dataset_path}")

    with open(data_file, "r", encoding="utf-8") as f:
        rows = json.load(f)

    if not isinstance(rows, list):
        raise ValueError("Dataset must be a JSON array")

    # Handle empty dataset gracefully
    if len(rows) == 0:
        ctx.log_message("Empty dataset — producing empty outputs.")
        out_dir = os.path.join(ctx.run_dir, "dataset")
        os.makedirs(out_dir, exist_ok=True)
        with open(os.path.join(out_dir, "data.json"), "w", encoding="utf-8") as f:
            json.dump([], f)
        ctx.save_output("dataset", out_dir)
        ctx.save_output("metrics", {"input_rows": 0, "selected_rows": 0})
        ctx.log_metric("input_rows", 0)
        ctx.log_metric("selected_rows", 0)
        ctx.report_progress(1, 1)
        return

    original_count = len(rows)
    ctx.log_message(
        f"Loaded {original_count} rows. Selection mode: {mode}, count: {count}"
    )

    # Apply selection mode
    if mode == "first":
        selected = rows[:count]
    elif mode == "last":
        selected = rows[-count:]
    elif mode == "index":
        if index < 0 or index >= len(rows):
            raise ValueError(
                f"Index {index} out of range (dataset has {len(rows)} rows)"
            )
        end = min(index + count, len(rows))
        selected = rows[index:end]
    elif mode == "random":
        random.seed(seed)
        sample_size = min(count, len(rows))
        selected = random.sample(rows, sample_size)
        ctx.log_message(f"Random sampling with seed={seed}")
    elif mode == "filter":
        if not filter_column:
            raise ValueError("Filter column must be specified for filter mode")
        selected = [
            row for row in rows
            if str(row.get(filter_column, "")) == filter_value
        ]
        ctx.log_message(
            f"Filter matched {len(selected)} row(s) "
            f"where '{filter_column}' == '{filter_value}'"
        )
        if count > 0 and len(selected) > count:
            selected = selected[:count]
    else:
        raise ValueError(f"Unknown selection mode: {mode}")

    if len(selected) == 0:
        ctx.log_message("Warning: no rows matched the selection criteria")

    # Save selected rows as dataset
    out_dir = os.path.join(ctx.run_dir, "dataset")
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "data.json"), "w", encoding="utf-8") as f:
        json.dump(selected, f, indent=2)
    ctx.save_output("dataset", out_dir)

    # Save first row's text column as text output
    if selected:
        col = _auto_detect_column(selected[0], text_column)
        if col != text_column:
            ctx.log_message(f"Text column '{text_column}' not found, using '{col}'")

        text_value = str(selected[0].get(col, ""))
        text_path = os.path.join(ctx.run_dir, "selected_text.txt")
        with open(text_path, "w", encoding="utf-8") as f:
            f.write(text_value)
        ctx.save_output("text", text_path)

    stats = {
        "input_rows": original_count,
        "selected_rows": len(selected),
        "mode": mode,
        "selection_rate": round(len(selected) / original_count, 4),
    }

    ctx.save_output("metrics", stats)
    ctx.log_metric("input_rows", original_count)
    ctx.log_metric("selected_rows", len(selected))
    ctx.log_metric("selection_rate", stats["selection_rate"])
    ctx.log_message(
        f"Selected {len(selected)} row(s) from {original_count} "
        f"using mode '{mode}'"
    )
    ctx.report_progress(1, 1)
