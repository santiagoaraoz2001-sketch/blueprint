"""Filter & Sample — filter rows by various methods or take a random sample."""

import hashlib
import json
import os
import random
import re


def run(ctx):
    dataset_path = ctx.resolve_as_file_path("dataset")

    # Read upstream dataset metadata
    _dataset_meta = {}
    try:
        _meta_input = ctx.load_input("dataset_meta")
        if isinstance(_meta_input, dict):
            _dataset_meta = _meta_input
    except (ValueError, KeyError):
        pass

    method = ctx.config.get("method", "length")
    text_column = _dataset_meta.get("text_column", ctx.config.get("text_column", "text"))
    min_length = int(ctx.config.get("min_length", 10))
    max_length = int(ctx.config.get("max_length", 0))
    regex_pattern = ctx.config.get("regex_pattern", "")
    regex_mode = ctx.config.get("regex_mode", "keep_match")
    score_column = ctx.config.get("score_column", "quality_score")
    min_score = float(ctx.config.get("min_score", 0.5))
    dedup_columns_str = ctx.config.get("dedup_columns", "")
    top_k = int(ctx.config.get("top_k", 100))
    match_values_str = ctx.config.get("match_values", "")
    sample_size = int(ctx.config.get("sample_size", 0))
    seed = int(ctx.config.get("seed") or _dataset_meta.get("seed", 42))

    random.seed(seed)

    # Load data
    data_file = os.path.join(dataset_path, "data.json") if os.path.isdir(dataset_path) else dataset_path
    if not os.path.isfile(data_file):
        raise FileNotFoundError(f"Dataset file not found: {data_file}")
    with open(data_file, "r", encoding="utf-8") as f:
        rows = json.load(f)

    if not isinstance(rows, list):
        raise ValueError("Dataset must be a JSON array")

    original_count = len(rows)
    ctx.log_message(f"Loaded {original_count} rows. Method: {method}")
    ctx.report_progress(1, 4)

    # Apply filter
    kept, rejected = [], []

    if method == "length":
        for r in rows:
            text_len = len(str(r.get(text_column, "")))
            if text_len >= min_length and (max_length == 0 or text_len <= max_length):
                kept.append(r)
            else:
                rejected.append(r)

    elif method == "quality_score":
        for r in rows:
            score = r.get(score_column)
            if score is not None:
                try:
                    if float(score) >= min_score:
                        kept.append(r)
                    else:
                        rejected.append(r)
                except (ValueError, TypeError):
                    rejected.append(r)
            else:
                rejected.append(r)

    elif method == "regex":
        if not regex_pattern:
            raise ValueError("regex_pattern is required for regex filter method")
        try:
            compiled = re.compile(regex_pattern)
        except re.error as e:
            raise ValueError(f"Invalid regex pattern: {e}")
        for r in rows:
            text_val = str(r.get(text_column, ""))
            matches = bool(compiled.search(text_val))
            if (regex_mode == "keep_match" and matches) or (regex_mode == "remove_match" and not matches):
                kept.append(r)
            else:
                rejected.append(r)

    elif method == "random_sample":
        kept = list(rows)  # no filtering, just sampling below

    elif method == "dedup":
        dedup_cols = [c.strip() for c in dedup_columns_str.split(",") if c.strip()] if dedup_columns_str else None
        seen = set()
        for r in rows:
            if dedup_cols:
                key_data = json.dumps({k: r.get(k) for k in dedup_cols}, sort_keys=True)
            else:
                key_data = json.dumps(r, sort_keys=True)
            key_hash = hashlib.md5(key_data.encode()).hexdigest()
            if key_hash not in seen:
                seen.add(key_hash)
                kept.append(r)
            else:
                rejected.append(r)

    elif method == "top_k":
        scored = sorted(rows, key=lambda r: float(r.get(score_column, 0)), reverse=True)
        kept = scored[:top_k]
        rejected = scored[top_k:]

    elif method == "not_empty":
        for r in rows:
            val = r.get(text_column)
            if val is not None and str(val).strip():
                kept.append(r)
            else:
                rejected.append(r)

    elif method == "value_match":
        if not match_values_str:
            raise ValueError("match_values is required for value_match filter method")
        match_set = {v.strip() for v in match_values_str.split(",") if v.strip()}
        for r in rows:
            if str(r.get(text_column, "")) in match_set:
                kept.append(r)
            else:
                rejected.append(r)

    else:
        raise ValueError(f"Unknown filter method: {method}")

    ctx.report_progress(2, 4)

    # Apply post-filter sampling
    if sample_size > 0 and len(kept) > sample_size:
        random.shuffle(kept)
        rejected.extend(kept[sample_size:])
        kept = kept[:sample_size]

    ctx.report_progress(3, 4)

    # Save kept
    out_path = os.path.join(ctx.run_dir, "dataset")
    os.makedirs(out_path, exist_ok=True)
    with open(os.path.join(out_path, "data.json"), "w", encoding="utf-8") as f:
        json.dump(kept, f)

    # Save rejected
    rej_path = os.path.join(ctx.run_dir, "rejected")
    os.makedirs(rej_path, exist_ok=True)
    with open(os.path.join(rej_path, "data.json"), "w", encoding="utf-8") as f:
        json.dump(rejected, f)

    drop_rate = round(1 - len(kept) / max(original_count, 1), 4)
    stats = {
        "original": original_count,
        "kept": len(kept),
        "rejected": len(rejected),
        "drop_rate": drop_rate,
    }

    # Pass through dataset metadata
    if _dataset_meta:
        _dataset_meta["num_rows"] = len(kept)
        ctx.save_output("dataset_meta", _dataset_meta)

    ctx.save_output("dataset", out_path)
    ctx.save_output("rejected", rej_path)
    ctx.save_output("stats", stats)
    ctx.log_metric("original_count", original_count)
    ctx.log_metric("filtered_count", len(kept))
    ctx.log_metric("drop_rate", drop_rate)
    ctx.log_message(f"Kept {len(kept)}/{original_count} rows (rejected {len(rejected)})")
    ctx.report_progress(4, 4)
