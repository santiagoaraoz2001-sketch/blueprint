"""Data Merger — merge or concatenate multiple datasets."""

import hashlib
import json
import os
import random


def _load_dataset(path):
    """Load a dataset from a path, returning an empty list if not available."""
    if path is None:
        return []
    data_file = os.path.join(path, "data.json") if os.path.isdir(path) else path
    if os.path.isfile(data_file):
        with open(data_file, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def _join(rows_a, rows_b, join_key, join_type, join_suffix="_b"):
    """Perform a key-based join between two row lists."""
    if not join_key:
        raise ValueError("join_key is required for join method")

    # Index dataset B by join key
    b_index = {}
    for row in rows_b:
        key_val = row.get(join_key)
        if key_val is not None:
            b_index.setdefault(str(key_val), []).append(row)

    merged = []
    b_keys_seen = set()

    for row_a in rows_a:
        key_val = str(row_a.get(join_key, ""))
        if key_val in b_index:
            b_keys_seen.add(key_val)
            for row_b in b_index[key_val]:
                combined = {**row_a}
                for k, v in row_b.items():
                    if k != join_key:
                        combined[f"{k}{join_suffix}"] = v
                merged.append(combined)
        elif join_type in ("left", "outer"):
            merged.append(dict(row_a))

    # For outer join, add unmatched B rows
    if join_type == "outer":
        for row_b in rows_b:
            key_val = str(row_b.get(join_key, ""))
            if key_val not in b_keys_seen:
                merged.append(dict(row_b))

    return merged


def _interleave(datasets):
    """Interleave rows from multiple datasets."""
    merged = []
    max_len = max(len(ds) for ds in datasets) if datasets else 0
    for i in range(max_len):
        for ds in datasets:
            if i < len(ds):
                merged.append(ds[i])
    return merged


def _dedup(rows, dedup_columns_str):
    """Deduplicate rows based on specified columns or all columns."""
    dedup_cols = [c.strip() for c in dedup_columns_str.split(",") if c.strip()] if dedup_columns_str else None
    seen = set()
    unique = []
    for row in rows:
        if dedup_cols:
            key_data = json.dumps({k: row.get(k) for k in dedup_cols}, sort_keys=True)
        else:
            key_data = json.dumps(row, sort_keys=True)
        key_hash = hashlib.md5(key_data.encode()).hexdigest()
        if key_hash not in seen:
            seen.add(key_hash)
            unique.append(row)
    return unique


def run(ctx):
    method = ctx.config.get("method", "concat")
    join_key = ctx.config.get("join_key", "")
    join_type = ctx.config.get("join_type", "inner")
    dedup_columns_str = ctx.config.get("dedup_columns", "")
    add_source = ctx.config.get("add_source_column", False)
    shuffle = ctx.config.get("shuffle", False)
    seed = int(ctx.config.get("seed", 42))
    weight_a = int(ctx.config.get("weight_a", 1))
    weight_b = int(ctx.config.get("weight_b", 1))
    weight_c = int(ctx.config.get("weight_c", 1))
    join_suffix = ctx.config.get("join_suffix", "_b")

    # Load datasets
    dataset_a_path = ctx.load_input("dataset_a")
    dataset_b_path = ctx.load_input("dataset_b")
    try:
        dataset_c_path = ctx.load_input("dataset_c")
    except ValueError:
        dataset_c_path = None

    rows_a = _load_dataset(dataset_a_path)
    rows_b = _load_dataset(dataset_b_path)
    rows_c = _load_dataset(dataset_c_path)

    ctx.log_message(f"Dataset A: {len(rows_a)} rows")
    ctx.log_message(f"Dataset B: {len(rows_b)} rows")
    if rows_c:
        ctx.log_message(f"Dataset C: {len(rows_c)} rows")
    ctx.log_message(f"Method: {method}")

    # Add source tags if requested
    if add_source:
        for r in rows_a:
            r["_source"] = "a"
        for r in rows_b:
            r["_source"] = "b"
        for r in rows_c:
            r["_source"] = "c"

    # Apply weights (repeat datasets for weighted mixing)
    if weight_a > 1:
        rows_a = rows_a * weight_a
        ctx.log_message(f"Dataset A repeated {weight_a}x -> {len(rows_a)} rows")
    if weight_b > 1:
        rows_b = rows_b * weight_b
        ctx.log_message(f"Dataset B repeated {weight_b}x -> {len(rows_b)} rows")
    if weight_c > 1 and rows_c:
        rows_c = rows_c * weight_c
        ctx.log_message(f"Dataset C repeated {weight_c}x -> {len(rows_c)} rows")

    # Merge
    if method == "concat":
        merged = rows_a + rows_b + rows_c
        ctx.log_message(f"Concatenated: {len(merged)} rows")

    elif method == "join":
        merged = _join(rows_a, rows_b, join_key, join_type, join_suffix)
        if rows_c:
            merged = _join(merged, rows_c, join_key, join_type, join_suffix)
        ctx.log_message(f"Joined on '{join_key}' ({join_type}): {len(merged)} rows")

    elif method == "interleave":
        all_datasets = [rows_a, rows_b] + ([rows_c] if rows_c else [])
        merged = _interleave(all_datasets)
        ctx.log_message(f"Interleaved: {len(merged)} rows")

    elif method in ("dedup", "deduplicate"):
        combined = rows_a + rows_b + rows_c
        merged = _dedup(combined, dedup_columns_str)
        ctx.log_message(f"Deduplicated: {len(combined)} -> {len(merged)} rows")

    else:
        merged = rows_a + rows_b + rows_c
        ctx.log_message(f"Unknown method '{method}', falling back to concatenation: {len(merged)} rows")

    # Post-merge shuffle (critical for training data mixing)
    if shuffle:
        random.seed(seed)
        random.shuffle(merged)
        ctx.log_message(f"Shuffled {len(merged)} rows (seed={seed})")

    # Save
    out_dir = os.path.join(ctx.run_dir, "dataset")
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "data.json"), "w", encoding="utf-8") as f:
        json.dump(merged, f, indent=2)

    stats = {
        "rows_a": len(rows_a),
        "rows_b": len(rows_b),
        "rows_c": len(rows_c),
        "merged_rows": len(merged),
        "method": method,
    }

    ctx.save_output("dataset", out_dir)
    ctx.save_output("stats", stats)
    ctx.log_metric("rows_a", len(rows_a))
    ctx.log_metric("rows_b", len(rows_b))
    ctx.log_metric("merged_rows", len(merged))
    ctx.report_progress(1, 1)
