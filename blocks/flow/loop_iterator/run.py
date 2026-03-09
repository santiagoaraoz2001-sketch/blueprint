"""Loop Iterator — iterate over dataset rows, emit batches, or repeat N times."""

import json
import os
import random


def _load_data(ctx, port_name):
    """Load and resolve input data from a port, handling file/directory paths."""
    try:
        raw = ctx.load_input(port_name)
    except (ValueError, Exception):
        return None

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


def run(ctx):
    mode = ctx.config.get("mode", "iterate_rows")
    count = max(1, int(ctx.config.get("count", 3)))
    batch_size = max(1, int(ctx.config.get("batch_size", 1)))
    start_index = max(0, int(ctx.config.get("start_index", 0)))
    max_iterations = int(ctx.config.get("max_iterations", 0))
    shuffle = ctx.config.get("shuffle", False)
    emit_index = ctx.config.get("emit_index", False)
    stride = int(ctx.config.get("stride", 0))

    # Load input
    input_data = _load_data(ctx, "input")
    if input_data is None:
        input_data = _load_data(ctx, "dataset")

    # Normalize to list
    if isinstance(input_data, list):
        rows = input_data
    elif isinstance(input_data, dict):
        rows = [input_data]
    elif isinstance(input_data, str):
        rows = [{"text": input_data}]
    elif input_data is None and mode == "count":
        rows = []
    else:
        rows = [{"value": input_data}] if input_data is not None else []

    total_input = len(rows)

    # Shuffle rows before iterating (useful for training, cross-validation, grid search)
    if shuffle and rows:
        rows = rows[:]  # copy to avoid mutating input
        random.shuffle(rows)
        ctx.log_message(f"Shuffled {len(rows)} items")

    if mode == "count":
        # Repeat N times — pass the entire input through each time
        ctx.log_message(f"Count mode: repeating {count} times")
        output_items = []
        effective_count = min(count, max_iterations) if max_iterations > 0 else count
        for i in range(effective_count):
            if rows:
                if emit_index:
                    for row in rows:
                        tagged = {"_index": i, **(row if isinstance(row, dict) else {"value": row})}
                        output_items.append(tagged)
                else:
                    output_items.extend(rows)
            else:
                output_items.append({"_index": i} if emit_index else {"iteration": i})
            ctx.report_progress(i + 1, effective_count)

        last_item = output_items[-1] if output_items else None
        num_iterations = effective_count
        ctx.log_message(f"Completed {num_iterations} repetitions, {len(output_items)} total output items")

    elif mode in ("iterate_rows", "batch"):
        # Apply start_index
        working_rows = rows[start_index:] if start_index > 0 else rows[:]
        if start_index > 0:
            ctx.log_message(f"Skipped first {start_index} items, {len(working_rows)} remaining")

        # Determine effective batch size and stride
        effective_batch = 1 if mode == "iterate_rows" else batch_size
        # stride controls step between window starts (0 = use batch size, i.e. no overlap)
        effective_stride = stride if stride > 0 and mode == "batch" else effective_batch
        if effective_stride != effective_batch and mode == "batch":
            ctx.log_message(f"Sliding window: size={effective_batch}, stride={effective_stride}")

        # Build batches
        output_items = []
        num_iterations = 0
        total_to_process = len(working_rows)

        for i in range(0, total_to_process, effective_stride):
            if max_iterations > 0 and num_iterations >= max_iterations:
                ctx.log_message(f"Hit max_iterations cap ({max_iterations})")
                break

            batch = working_rows[i:i + effective_batch]
            num_iterations += 1

            if emit_index:
                if effective_batch == 1 and len(batch) == 1:
                    item = batch[0]
                    output_items.append({"_index": num_iterations - 1, **(item if isinstance(item, dict) else {"value": item})})
                else:
                    output_items.append([{"_index": num_iterations - 1, **(r if isinstance(r, dict) else {"value": r})} for r in batch])
            else:
                if effective_batch == 1 and len(batch) == 1:
                    output_items.append(batch[0])
                else:
                    output_items.append(batch)

            ctx.report_progress(min(i + effective_batch, total_to_process), total_to_process)

        last_item = output_items[-1] if output_items else None
        ctx.log_message(f"Mode '{mode}': {num_iterations} iterations, {len(output_items)} outputs from {total_input} input items")

    else:
        ctx.log_message(f"Unknown mode '{mode}', falling back to iterate_rows")
        output_items = rows
        last_item = rows[-1] if rows else None
        num_iterations = len(rows)

    # Flatten output_items for dataset saving
    flat_items = []
    for item in output_items:
        if isinstance(item, list):
            flat_items.extend(item)
        else:
            flat_items.append(item)

    # Save dataset output
    out_dir = os.path.join(ctx.run_dir, "dataset")
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "data.json"), "w") as f:
        json.dump(flat_items, f, indent=2)

    ctx.save_output("dataset", out_dir)
    ctx.save_output("item", last_item)

    iteration_metrics = {
        "total_input_items": total_input,
        "iterations": num_iterations,
        "output_items": len(flat_items),
        "mode": mode,
        "batch_size": batch_size if mode == "batch" else 1,
    }
    ctx.save_output("metrics", iteration_metrics)

    ctx.log_metric("iterations", num_iterations)
    ctx.log_metric("total_items", total_input)
    ctx.log_metric("output_items", len(flat_items))
    ctx.report_progress(1, 1)
