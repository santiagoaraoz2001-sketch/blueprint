"""Train/Val/Test Split — splits a dataset into three partitions."""

import json
import os
import random
from collections import defaultdict


def run(ctx):
    dataset_path = ctx.load_input("dataset")
    train_ratio = float(ctx.config.get("train_ratio", 0.8))
    val_ratio = float(ctx.config.get("val_ratio", 0.1))
    test_ratio = float(ctx.config.get("test_ratio", 0.1))
    seed = int(ctx.config.get("seed", 42))
    stratify_column = ctx.config.get("stratify_column", "")
    shuffle = ctx.config.get("shuffle", True)
    group_column = ctx.config.get("group_column", "")
    sort_column = ctx.config.get("sort_column", "")

    # Validate ratios
    ratio_sum = train_ratio + val_ratio + test_ratio
    if abs(ratio_sum - 1.0) > 0.01:
        ctx.log_message(f"Warning: ratios sum to {ratio_sum:.3f}, normalizing to 1.0")
        train_ratio /= ratio_sum
        val_ratio /= ratio_sum
        test_ratio /= ratio_sum

    ctx.log_message(f"Splitting: train={train_ratio:.2f}, val={val_ratio:.2f}, test={test_ratio:.2f}")

    # Load
    data_file = os.path.join(dataset_path, "data.json") if os.path.isdir(dataset_path) else dataset_path
    if not os.path.isfile(data_file):
        raise FileNotFoundError(f"Dataset not found: {data_file}")

    with open(data_file, "r", encoding="utf-8") as f:
        rows = json.load(f)

    if not isinstance(rows, list):
        raise ValueError("Dataset must be a JSON array")

    random.seed(seed)

    # Sort by column before splitting (temporal/ordered split workflow)
    if sort_column and rows and sort_column in rows[0]:
        rows = sorted(rows, key=lambda r: r.get(sort_column, 0) if isinstance(r.get(sort_column), (int, float)) else str(r.get(sort_column, "")))
        ctx.log_message(f"Sorted by '{sort_column}' before splitting")

    def split_list(items):
        if shuffle:
            random.shuffle(items)
        n = len(items)
        train_end = int(n * train_ratio)
        val_end = train_end + int(n * val_ratio)
        return items[:train_end], items[train_end:val_end], items[val_end:]

    if group_column and rows and group_column in rows[0]:
        # Group-aware split: all rows with the same group key stay together
        groups = defaultdict(list)
        for row in rows:
            groups[row.get(group_column, "__none__")].append(row)
        group_keys = list(groups.keys())
        if shuffle:
            random.shuffle(group_keys)
        n_groups = len(group_keys)
        train_end = int(n_groups * train_ratio)
        val_end = train_end + int(n_groups * val_ratio)
        train_rows, val_rows, test_rows = [], [], []
        for gk in group_keys[:train_end]:
            train_rows.extend(groups[gk])
        for gk in group_keys[train_end:val_end]:
            val_rows.extend(groups[gk])
        for gk in group_keys[val_end:]:
            test_rows.extend(groups[gk])
        ctx.log_message(f"Group-aware split by '{group_column}' ({n_groups} groups)")

    elif stratify_column and rows and stratify_column in rows[0]:
        # Group by stratify column
        groups = defaultdict(list)
        for row in rows:
            groups[row.get(stratify_column, "__none__")].append(row)

        train_rows, val_rows, test_rows = [], [], []
        for label, group_rows in groups.items():
            t, v, te = split_list(group_rows)
            train_rows.extend(t)
            val_rows.extend(v)
            test_rows.extend(te)

        # Shuffle the combined splits
        if shuffle:
            random.shuffle(train_rows)
            random.shuffle(val_rows)
            random.shuffle(test_rows)

        ctx.log_message(f"Stratified by '{stratify_column}' ({len(groups)} groups)")
    else:
        train_rows, val_rows, test_rows = split_list(list(rows))
        if stratify_column:
            ctx.log_message(f"Warning: stratify_column '{stratify_column}' not found in data, using random split")

    splits = {"train": train_rows, "val": val_rows, "test": test_rows}

    ctx.report_progress(1, 2)

    for name, split_data in splits.items():
        out_path = os.path.join(ctx.run_dir, name)
        os.makedirs(out_path, exist_ok=True)
        with open(os.path.join(out_path, "data.json"), "w", encoding="utf-8") as f:
            json.dump(split_data, f)
        ctx.log_metric(f"{name}_count", len(split_data))
        ctx.log_message(f"  {name}: {len(split_data)} rows")

    ctx.save_output("train", os.path.join(ctx.run_dir, "train"))
    ctx.save_output("val", os.path.join(ctx.run_dir, "val"))
    ctx.save_output("test", os.path.join(ctx.run_dir, "test"))

    stats = {k: len(v) for k, v in splits.items()}
    stats["total"] = len(rows)
    stats["stratified"] = bool(stratify_column and rows and stratify_column in rows[0])
    ctx.save_output("stats", stats)
    ctx.report_progress(2, 2)
