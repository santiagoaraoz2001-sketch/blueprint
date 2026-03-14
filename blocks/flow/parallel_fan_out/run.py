"""Parallel Fan-Out — split input data across branches or broadcast a full copy to each."""

import json
import math
import os
import random

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


def _save_branch(ctx, branch_index, data):
    """Save data for a branch output port, writing to a dataset directory."""
    port_name = f"out_{branch_index + 1}"
    if isinstance(data, list):
        out_dir = os.path.join(ctx.run_dir, port_name)
        os.makedirs(out_dir, exist_ok=True)
        with open(os.path.join(out_dir, "data.json"), "w") as f:
            json.dump(data, f, indent=2)
        ctx.save_output(port_name, out_dir)
    else:
        ctx.save_output(port_name, data)


def _parse_ratios(ratio_str, num_branches):
    """Parse a ratio string like '0.8,0.2' or '80,20' into normalized proportions."""
    parts = [p.strip() for p in ratio_str.split(",") if p.strip()]
    if not parts:
        return [1.0 / num_branches] * num_branches
    values = []
    for p in parts[:num_branches]:
        try:
            values.append(float(p))
        except ValueError:
            values.append(1.0)
    # Pad with 0 if fewer values than branches
    while len(values) < num_branches:
        values.append(0.0)
    total = sum(values)
    if total <= 0:
        return [1.0 / num_branches] * num_branches
    return [v / total for v in values]


def run(ctx):
    num_branches = max(2, min(5, int(ctx.config.get("num_branches", 2))))
    split_mode = ctx.config.get("split_mode", "split_equal")
    split_field = ctx.config.get("split_field", "").strip()
    split_ratio = ctx.config.get("split_ratio", "").strip()
    random_seed = ctx.config.get("random_seed", 0)
    random_seed = int(random_seed) if random_seed else 0

    # Load input
    input_data = _load_data(ctx, "input")
    if input_data is None:
        input_data = _load_data(ctx, "dataset")
    if input_data is None:
        raise BlockInputError(
            "Required input 'input' not connected or produced no data. "
            "Connect data to the 'Input Data' port.",
            recoverable=False
        )

    # Normalize to list for splitting
    if isinstance(input_data, list):
        rows = input_data
    elif isinstance(input_data, dict):
        rows = [input_data]
    elif isinstance(input_data, str):
        rows = [{"text": input_data}]
    elif input_data is not None:
        rows = [{"value": input_data}]
    else:
        rows = []

    total = len(rows)
    ctx.log_message(f"Fan-out: {total} items into {num_branches} branches (mode={split_mode})")

    branch_sizes = []

    if split_mode == "broadcast":
        # Send full copy of all data to every branch
        for i in range(num_branches):
            _save_branch(ctx, i, rows)
            branch_sizes.append(total)
            ctx.log_message(f"  Branch {i + 1}: {total} items (full copy)")
            ctx.report_progress(i + 1, num_branches)

        # Unused branches get None
        for i in range(num_branches, 5):
            ctx.save_output(f"out_{i + 1}", None)

    elif split_mode == "split_by_field" and split_field:
        # Group rows by a field value and send each group to a branch
        groups = {}
        ungrouped = []
        for row in rows:
            if isinstance(row, dict) and split_field in row:
                key = str(row[split_field])
                groups.setdefault(key, []).append(row)
            else:
                ungrouped.append(row)

        group_keys = sorted(groups.keys())
        for i in range(num_branches):
            if i < len(group_keys):
                chunk = groups[group_keys[i]]
                # If there are more groups than branches, last branch gets overflow
                if i == num_branches - 1 and len(group_keys) > num_branches:
                    for overflow_key in group_keys[num_branches:]:
                        chunk = chunk + groups[overflow_key]
                    chunk = chunk + ungrouped
                _save_branch(ctx, i, chunk)
                branch_sizes.append(len(chunk))
                ctx.log_message(f"  Branch {i + 1}: {len(chunk)} items ('{split_field}' = '{group_keys[i]}'{' + overflow' if i == num_branches - 1 and len(group_keys) > num_branches else ''})")
            else:
                _save_branch(ctx, i, [])
                branch_sizes.append(0)
            ctx.report_progress(i + 1, num_branches)

        for i in range(num_branches, 5):
            ctx.save_output(f"out_{i + 1}", None)

    elif split_mode == "split_ratio":
        # Split by custom ratios (e.g. "0.8,0.2" for 80/20 train/test)
        ratios = _parse_ratios(split_ratio, num_branches)
        # Shuffle rows for random split; use seed for reproducibility
        shuffled = rows[:]
        if random_seed:
            random.seed(random_seed)
            ctx.log_message(f"Using random seed {random_seed} for reproducible split")
        random.shuffle(shuffled)

        cursor = 0
        for i in range(num_branches):
            if i == num_branches - 1:
                # Last branch gets all remaining rows (avoids rounding issues)
                chunk = shuffled[cursor:]
            else:
                count = round(ratios[i] * total)
                chunk = shuffled[cursor:cursor + count]
                cursor += count
            _save_branch(ctx, i, chunk)
            branch_sizes.append(len(chunk))
            ctx.log_message(f"  Branch {i + 1}: {len(chunk)} items ({ratios[i]*100:.1f}%)")
            ctx.report_progress(i + 1, num_branches)

        for i in range(num_branches, 5):
            ctx.save_output(f"out_{i + 1}", None)

    elif split_mode == "split_round_robin":
        chunks = [[] for _ in range(num_branches)]
        for i, row in enumerate(rows):
            chunks[i % num_branches].append(row)

        for i in range(num_branches):
            _save_branch(ctx, i, chunks[i])
            branch_sizes.append(len(chunks[i]))
            ctx.log_message(f"  Branch {i + 1}: {len(chunks[i])} items")
            ctx.report_progress(i + 1, num_branches)

        for i in range(num_branches, 5):
            ctx.save_output(f"out_{i + 1}", None)

    else:  # split_equal (default), also fallback for split_by_field without split_field
        chunk_size = math.ceil(total / max(num_branches, 1)) if total > 0 else 0
        for i in range(num_branches):
            start = i * chunk_size
            end = min(start + chunk_size, total)
            chunk = rows[start:end] if start < total else []
            _save_branch(ctx, i, chunk)
            branch_sizes.append(len(chunk))
            ctx.log_message(f"  Branch {i + 1}: {len(chunk)} items (rows {start}-{end})")
            ctx.report_progress(i + 1, num_branches)

        for i in range(num_branches, 5):
            ctx.save_output(f"out_{i + 1}", None)

    split_metrics = {
        "total_items": total,
        "num_branches": num_branches,
        "split_mode": split_mode,
        "branch_sizes": branch_sizes,
    }
    ctx.save_output("metrics", split_metrics)

    ctx.log_metric("num_branches", num_branches)
    ctx.log_metric("total_items", total)
    ctx.log_message(f"Fan-out complete: {total} items across {num_branches} branches")
    ctx.report_progress(1, 1)
