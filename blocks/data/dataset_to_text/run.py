import json
import os


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
    column = ctx.config.get("column", "text")
    join_with = ctx.config.get("join_with", "\n")
    max_rows = int(ctx.config.get("max_rows", 0))
    row_index = int(ctx.config.get("row_index", -1))

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
        ctx.log_message("Empty dataset — producing empty text output.")
        out_path = os.path.join(ctx.run_dir, "extracted_text.txt")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("")
        ctx.save_output("text", out_path)
        ctx.save_output("metrics", {"row_count": 0, "char_count": 0})
        ctx.log_metric("row_count", 0)
        ctx.log_metric("char_count", 0)
        ctx.report_progress(1, 1)
        return

    original_count = len(rows)

    # Auto-detect column if not specified or not found
    if not column or column not in rows[0]:
        column = _auto_detect_column(rows[0], column)
        ctx.log_message(f"Auto-detected column: '{column}'")

    ctx.log_message(
        f"Loaded {original_count} rows. Extracting column '{column}'"
    )

    # Extract single row by index
    if row_index >= 0:
        if row_index >= len(rows):
            raise ValueError(
                f"Row index {row_index} out of range "
                f"(dataset has {len(rows)} rows)"
            )
        extracted = str(rows[row_index].get(column, ""))
        row_count = 1
    else:
        # Extract all rows (with optional limit)
        if max_rows > 0:
            rows = rows[:max_rows]
        extracted = join_with.join(str(row.get(column, "")) for row in rows)
        row_count = len(rows)

    # Save text output
    out_path = os.path.join(ctx.run_dir, "extracted_text.txt")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(extracted)

    stats = {
        "row_count": row_count,
        "original_count": original_count,
        "char_count": len(extracted),
        "column": column,
    }

    ctx.save_output("text", out_path)
    ctx.save_output("metrics", stats)
    ctx.log_metric("row_count", row_count)
    ctx.log_metric("char_count", len(extracted))
    ctx.log_message(
        f"Extracted {row_count} row(s) from column '{column}' "
        f"({len(extracted)} chars)"
    )
    ctx.report_progress(1, 1)
