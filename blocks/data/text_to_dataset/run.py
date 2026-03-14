import json
import os
import re


def _resolve_text(data):
    """Resolve a loaded input to text, handling file paths and raw strings."""
    if data is None:
        return ""
    if isinstance(data, str):
        if os.path.isfile(data):
            with open(data, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()
        return data
    return str(data)


def run(ctx):
    text = _resolve_text(ctx.load_input("text"))
    col_name = ctx.config.get("column_name", "text")
    split_by = ctx.config.get("split_by", "none")

    # Collect all text inputs
    texts = [text]
    for extra in ["text_b", "text_c"]:
        try:
            t = _resolve_text(ctx.load_input(extra))
            if t:
                texts.append(t)
        except (ValueError, KeyError):
            pass

    input_count = len(texts)
    combined = "\n\n".join(texts)

    ctx.log_message(
        f"Received {input_count} text input(s), {len(combined)} chars total. "
        f"Split strategy: {split_by}"
    )

    # Split into rows
    if split_by == "newline":
        rows = [line.strip() for line in combined.split("\n") if line.strip()]
    elif split_by == "paragraph":
        rows = [p.strip() for p in combined.split("\n\n") if p.strip()]
    elif split_by == "sentence":
        rows = [s.strip() for s in re.split(r'(?<=[.!?])\s+', combined) if s.strip()]
    else:
        rows = [combined]

    data = [{col_name: row} for row in rows]

    out_path = os.path.join(ctx.run_dir, "dataset")
    os.makedirs(out_path, exist_ok=True)
    with open(os.path.join(out_path, "data.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    stats = {
        "row_count": len(data),
        "input_count": input_count,
        "total_chars": len(combined),
        "column_name": col_name,
        "split_strategy": split_by,
    }

    ctx.save_output("dataset", out_path)
    ctx.save_output("metrics", stats)
    ctx.log_metric("row_count", len(data))
    ctx.log_metric("input_count", input_count)
    ctx.log_metric("total_chars", len(combined))
    ctx.log_message(f"Created dataset with {len(data)} row(s), column: '{col_name}'")
    ctx.report_progress(1, 1)
