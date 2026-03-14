"""A/B Split Test — route data to two paths for comparison testing."""

import json
import os
import random
import hashlib


def _deterministic_bucket(item, index, split_ratio, seed):
    """Assign an item to bucket A or B using a deterministic hash.

    This ensures the same item always goes to the same bucket across runs
    (given the same seed), which is important for reproducibility.
    """
    item_repr = f"{seed}:{index}:{json.dumps(item, sort_keys=True, default=str)[:200]}"
    hash_val = int(hashlib.sha256(item_repr.encode("utf-8")).hexdigest()[:8], 16)
    return "A" if (hash_val % 10000) / 10000.0 < split_ratio else "B"


def run(ctx):
    split_ratio = float(ctx.config.get("split_ratio", 0.5))
    random_seed = int(ctx.config.get("random_seed", 42))
    split_method = ctx.config.get("split_method", "random")
    label_a = ctx.config.get("label_a", "A")
    label_b = ctx.config.get("label_b", "B")
    stratify_by = ctx.config.get("stratify_by", "").strip()

    ctx.log_message(f"A/B Split Test: ratio={split_ratio} ({label_a}/{label_b}), "
                    f"method={split_method}, seed={random_seed}")
    ctx.report_progress(0, 3)

    # ---- Step 1: Load data ----
    ctx.report_progress(1, 3)
    raw_data = ctx.resolve_as_data("data")
    if not raw_data:
        raise ValueError("No data provided. Connect a 'data' input.")
    data = raw_data

    # ---- Step 2: Split data ----
    ctx.report_progress(2, 3)

    if isinstance(data, list):
        # List data: split items between A and B
        rng = random.Random(random_seed)
        path_a = []
        path_b = []

        # Stratified split: split proportionally within each group defined by a column
        if stratify_by and data and isinstance(data[0], dict):
            groups = {}
            for item in data:
                key = str(item.get(stratify_by, "__none__"))
                groups.setdefault(key, []).append(item)

            ctx.log_message(f"Stratified by '{stratify_by}': {len(groups)} groups")
            for group_key, group_items in groups.items():
                group_rng = random.Random(random_seed + hash(group_key))
                indices = list(range(len(group_items)))
                group_rng.shuffle(indices)
                split_index = max(1, int(len(indices) * split_ratio)) if len(indices) > 1 else 1
                for i in indices[:split_index]:
                    path_a.append(group_items[i])
                for i in indices[split_index:]:
                    path_b.append(group_items[i])
        elif split_method == "sequential":
            # First N% goes to A, rest to B
            split_index = int(len(data) * split_ratio)
            path_a = data[:split_index]
            path_b = data[split_index:]
        elif split_method == "deterministic":
            # Hash-based deterministic split
            for i, item in enumerate(data):
                bucket = _deterministic_bucket(item, i, split_ratio, random_seed)
                if bucket == "A":
                    path_a.append(item)
                else:
                    path_b.append(item)
        else:
            # Random shuffle split (default)
            indices = list(range(len(data)))
            rng.shuffle(indices)
            split_index = int(len(indices) * split_ratio)
            path_a = [data[i] for i in indices[:split_index]]
            path_b = [data[i] for i in indices[split_index:]]

        ctx.log_message(f"Split {len(data)} items: {label_a}={len(path_a)}, {label_b}={len(path_b)}")

    elif isinstance(data, dict):
        # Dict data: split keys between A and B
        rng = random.Random(random_seed)
        keys = list(data.keys())
        rng.shuffle(keys)
        split_index = int(len(keys) * split_ratio)
        path_a = {k: data[k] for k in keys[:split_index]}
        path_b = {k: data[k] for k in keys[split_index:]}
        ctx.log_message(f"Split {len(keys)} keys: {label_a}={len(path_a)}, {label_b}={len(path_b)}")

    else:
        # Non-collection data: send full copy to both paths
        path_a = data
        path_b = data
        ctx.log_message(f"Non-collection data: full copy sent to both {label_a} and {label_b}")

    # ---- Step 3: Save outputs ----
    ctx.report_progress(3, 3)

    ctx.save_output("path_a", path_a)
    ctx.save_output("path_b", path_b)

    # Comparison metadata
    comparison = {
        "split_ratio": split_ratio,
        "split_method": split_method,
        "random_seed": random_seed,
        "label_a": label_a,
        "label_b": label_b,
        "count_a": len(path_a) if isinstance(path_a, (list, dict)) else 1,
        "count_b": len(path_b) if isinstance(path_b, (list, dict)) else 1,
        "total_items": len(data) if isinstance(data, (list, dict)) else 1,
    }

    comparison_path = os.path.join(ctx.run_dir, "split_comparison.json")
    with open(comparison_path, "w", encoding="utf-8") as f:
        json.dump(comparison, f, indent=2, default=str)

    ctx.save_output("comparison", comparison)
    ctx.save_artifact("split_comparison", comparison_path)

    ctx.log_metric("count_a", comparison["count_a"])
    ctx.log_metric("count_b", comparison["count_b"])
    ctx.log_metric("actual_ratio", comparison["count_a"] / max(comparison["count_a"] + comparison["count_b"], 1))

    ctx.log_message("A/B Split Test complete.")
