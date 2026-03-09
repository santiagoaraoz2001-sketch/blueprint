"""HuggingFace Dataset Loader — downloads or streams a dataset from HuggingFace Hub."""

import json
import os
import time


def run(ctx):
    dataset_name = ctx.config.get("dataset_name", "")
    subset = ctx.config.get("subset", "")
    split = ctx.config.get("split", "train")
    max_samples = int(ctx.config.get("max_samples", 0))
    streaming = ctx.config.get("streaming", False)
    revision = ctx.config.get("revision", "main")
    trust_remote_code = ctx.config.get("trust_remote_code", False)
    columns = ctx.config.get("columns", "")
    token = ctx.config.get("token", "")
    cache_dir = ctx.config.get("cache_dir", "")
    shuffle = ctx.config.get("shuffle", False)
    seed = int(ctx.config.get("seed", 42))
    sample_percent = float(ctx.config.get("sample_percent", 0))
    output_format = ctx.config.get("output_format", "json")

    # Apply overrides from connected config input
    try:
        _ci = ctx.load_input("config")
        if _ci:
            _ov = json.load(open(_ci)) if isinstance(_ci, str) and os.path.isfile(_ci) else (_ci if isinstance(_ci, dict) else {})
            if isinstance(_ov, dict) and _ov:
                ctx.log_message(f"Applying {len(_ov)} config override(s) from input")
                dataset_name = _ov.get("dataset_name", dataset_name)
                subset = _ov.get("subset", subset)
                split = _ov.get("split", split)
                max_samples = int(_ov.get("max_samples", max_samples))
                columns = _ov.get("columns", columns)
                token = _ov.get("token", token)
                revision = _ov.get("revision", revision)
    except (ValueError, KeyError):
        pass

    if not dataset_name:
        raise ValueError("dataset_name is required — provide a HuggingFace dataset identifier (e.g. 'imdb', 'squad')")

    # Normalize booleans from string config values
    if isinstance(streaming, str):
        streaming = streaming.lower() in ("true", "1", "yes")
    if isinstance(trust_remote_code, str):
        trust_remote_code = trust_remote_code.lower() in ("true", "1", "yes")
    if isinstance(shuffle, str):
        shuffle = shuffle.lower() in ("true", "1", "yes")

    ctx.log_message(f"Loading dataset '{dataset_name}' (split={split}, subset={subset or 'default'})")
    if streaming:
        ctx.log_message("Streaming mode enabled")

    row_count = 0
    col_count = 0
    col_names = []

    try:
        from datasets import load_dataset

        # Build kwargs
        load_kwargs = {
            "path": dataset_name,
            "revision": revision or "main",
            "trust_remote_code": trust_remote_code,
            "streaming": streaming,
        }

        # Subset maps to the 'name' parameter
        if subset:
            load_kwargs["name"] = subset

        # Split handling — 'all' loads all splits
        if split and split != "all":
            load_kwargs["split"] = split

        # Token for private datasets
        if token:
            load_kwargs["token"] = token

        # Custom cache directory (large datasets benefit from dedicated cache)
        if cache_dir:
            load_kwargs["cache_dir"] = os.path.expanduser(cache_dir)
            ctx.log_message(f"Using custom cache: {cache_dir}")

        ds = load_dataset(**load_kwargs)

        # If split='all', we get a DatasetDict — concatenate all splits
        if split == "all":
            from datasets import concatenate_datasets
            all_splits = list(ds.values())
            ctx.log_message(f"Concatenating {len(all_splits)} splits: {list(ds.keys())}")
            ds = concatenate_datasets(all_splits)

        out_path = os.path.join(ctx.run_dir, "dataset")
        os.makedirs(out_path, exist_ok=True)

        if streaming:
            # Streaming mode: iterate and collect rows, save as JSON
            if shuffle:
                ds = ds.shuffle(seed=seed, buffer_size=10000)
                ctx.log_message(f"Streaming with shuffle (seed={seed}, buffer=10000)")

            # Compute effective limit from percentage if set
            if sample_percent > 0 and hasattr(ds, "info") and ds.info and ds.info.splits:
                split_info = ds.info.splits.get(split)
                if split_info and split_info.num_examples:
                    max_samples = int(split_info.num_examples * sample_percent / 100)
                    ctx.log_message(f"Sampling {sample_percent}% → {max_samples} rows (estimated from split info)")

            rows = []
            ctx.log_message("Streaming rows...")
            limit = max_samples if max_samples > 0 else float("inf")
            for i, example in enumerate(ds):
                if i >= limit:
                    break
                rows.append(example)
                if (i + 1) % 1000 == 0:
                    ctx.log_message(f"  Streamed {i + 1} rows...")
                    if max_samples > 0:
                        ctx.report_progress(min(i + 1, max_samples), max_samples)

            # Apply column filtering
            if columns:
                col_list = [c.strip() for c in columns.split(",") if c.strip()]
                if col_list:
                    rows = [{k: row.get(k) for k in col_list if k in row} for row in rows]
                    ctx.log_message(f"Filtered to columns: {col_list}")

            with open(os.path.join(out_path, "data.json"), "w") as f:
                json.dump(rows, f)

            row_count = len(rows)
            col_names = list(rows[0].keys()) if rows else []
            col_count = len(col_names)
            ctx.log_message(f"Streamed {row_count} rows")
            ctx.log_metric("row_count", row_count)

        else:
            # Standard mode: load into memory
            # Compute effective sample count from percentage if set
            if sample_percent > 0:
                effective_max = int(len(ds) * sample_percent / 100)
                ctx.log_message(f"Sampling {sample_percent}% → {effective_max} rows from {len(ds)}")
                max_samples = effective_max

            if shuffle:
                ds = ds.shuffle(seed=seed)
                ctx.log_message(f"Shuffled dataset (seed={seed})")

            if max_samples and max_samples > 0:
                ds = ds.select(range(min(max_samples, len(ds))))

            # Apply column filtering
            if columns:
                col_list = [c.strip() for c in columns.split(",") if c.strip()]
                if col_list:
                    available_cols = ds.column_names
                    valid_cols = [c for c in col_list if c in available_cols]
                    if valid_cols:
                        cols_to_remove = [c for c in available_cols if c not in valid_cols]
                        if cols_to_remove:
                            ds = ds.remove_columns(cols_to_remove)
                        ctx.log_message(f"Filtered to columns: {valid_cols}")
                    else:
                        ctx.log_message(f"WARNING: None of the requested columns {col_list} found. Available: {available_cols}")

            row_count = len(ds)
            col_names = ds.column_names if hasattr(ds, "column_names") else []
            col_count = len(col_names)

            # Save based on output_format
            if output_format == "native":
                ds.save_to_disk(out_path)
                ctx.log_message(f"Saved in HuggingFace native format (Arrow)")
            else:
                # JSON: convert to list of dicts for pipeline consistency
                rows = [dict(row) for row in ds]
                with open(os.path.join(out_path, "data.json"), "w") as f:
                    json.dump(rows, f, default=str)
                ctx.log_message(f"Saved as JSON ({row_count} rows)")

            ctx.log_message(f"Loaded {row_count} rows")
            ctx.log_metric("row_count", row_count)
            if col_names:
                ctx.log_message(f"Columns: {col_names}")
                ctx.log_metric("column_count", col_count)

        ctx.report_progress(1, 1)
        ctx.save_output("dataset", out_path)

    except ImportError:
        # Fallback: simulate loading for demo purposes
        ctx.log_message("'datasets' library not installed — running in demo mode")
        ctx.log_message("Install with: pip install datasets")
        total_steps = 10
        for i in range(total_steps):
            time.sleep(0.2)
            ctx.report_progress(i + 1, total_steps)

        out_path = os.path.join(ctx.run_dir, "dataset")
        os.makedirs(out_path, exist_ok=True)

        demo_data = [{"text": f"Sample {j}", "label": j % 2} for j in range(100)]

        # Apply column filtering to demo data
        if columns:
            col_list = [c.strip() for c in columns.split(",") if c.strip()]
            if col_list:
                demo_data = [{k: row.get(k) for k in col_list if k in row} for row in demo_data]

        if max_samples and max_samples > 0:
            demo_data = demo_data[:max_samples]

        with open(os.path.join(out_path, "data.json"), "w") as f:
            json.dump(demo_data, f)

        row_count = len(demo_data)
        col_names = list(demo_data[0].keys()) if demo_data else []
        col_count = len(col_names)
        ctx.log_metric("row_count", row_count)
        ctx.log_message(f"Demo: generated {row_count} rows")
        ctx.save_output("dataset", out_path)

    # Save metrics output
    _metrics = {
        "dataset_name": dataset_name,
        "split": split,
        "row_count": row_count,
        "column_count": col_count,
        "columns": col_names,
        "streaming": streaming,
        "output_format": output_format,
    }
    _mp = os.path.join(ctx.run_dir, "metrics.json")
    with open(_mp, "w") as f:
        json.dump(_metrics, f, indent=2)
    ctx.save_output("metrics", _mp)
