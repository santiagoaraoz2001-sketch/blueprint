"""Dataset Builder — all-in-one dataset preparation for training pipelines.

Loads from HuggingFace Hub (with auto-detection), local files, or upstream blocks.
Transforms via column mapping and Python scripts. Formats for any training task.
Validates output schema against target training blocks.

Pipeline stages:
  1. Load  →  2. Column Map  →  3. Script Transform  →  4. Format Convert
  →  5. Filter  →  6. Shuffle & Split  →  7. Validate & Save
"""

import csv
import hashlib
import json
import math
import os
import random
import re
import traceback

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


# ---------------------------------------------------------------------------
# Schema requirements for each training block type
# ---------------------------------------------------------------------------
TRAINING_SCHEMAS = {
    "lora_finetuning":       {"required": ["text"]},
    "qlora_finetuning":      {"required": ["text"]},
    "full_finetuning":       {"required": ["text"]},
    "dpo_alignment":         {"required": ["chosen", "rejected"], "optional": ["prompt"]},
    "reward_model_trainer":  {"required": ["chosen", "rejected"], "optional": ["prompt"]},
    "rlhf_ppo":              {"required_any": ["query", "prompt", "text"]},
    "distillation":          {"required_any": ["text", "content"]},
    "continued_pretraining": {"required": ["text"]},
}

# Map training_format → default target block for auto-detection
FORMAT_TO_TARGET = {
    "instruction":      "lora_finetuning",
    "chat":             "lora_finetuning",
    "completion":       "continued_pretraining",
    "preference_pairs": "dpo_alignment",
    "rlhf_prompts":     "rlhf_ppo",
}

# Column name patterns for auto-detection (ordered by priority)
COLUMN_PATTERNS = {
    "instruction": ["instruction", "prompt", "query", "question", "input_text", "input"],
    "output":      ["output", "response", "answer", "completion", "target", "assistant"],
    "chosen":      ["chosen", "preferred", "positive", "accepted", "chosen_response"],
    "rejected":    ["rejected", "dispreferred", "negative", "declined", "rejected_response"],
    "text":        ["text", "content", "document", "passage", "body"],
    "messages":    ["messages", "conversation", "turns", "dialogue"],
    "prompt":      ["prompt", "query", "question", "context", "instruction"],
}

# Minimum recommended rows per training task
MIN_ROWS_RECOMMENDATION = {
    "lora_finetuning": 100,
    "qlora_finetuning": 100,
    "full_finetuning": 500,
    "dpo_alignment": 200,
    "reward_model_trainer": 200,
    "rlhf_ppo": 100,
    "distillation": 500,
    "continued_pretraining": 1000,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_bool(val):
    """Normalize a config value to boolean."""
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.lower() in ("true", "1", "yes")
    return bool(val)


def _to_int(val, default=0):
    """Safely convert a config value to int."""
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


def _to_float(val, default=0.0):
    """Safely convert a config value to float."""
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def _detect_column(rows, pattern_key):
    """Find a column matching known patterns for a given role. Returns None if no match."""
    if not rows or not rows[0]:
        return None
    keys = set(rows[0].keys())
    for candidate in COLUMN_PATTERNS.get(pattern_key, []):
        if candidate in keys:
            return candidate
    return None


def _detect_primary_text_column(rows):
    """Detect the primary text column for filtering purposes."""
    if not rows or not rows[0]:
        return "text"
    keys = list(rows[0].keys())
    for candidate in ["text", "query", "chosen", "instruction", "content", "prompt"]:
        if candidate in keys:
            return candidate
    return keys[0]


def _suggest_training_format(columns, ctx):
    """Log suggestions for training_format based on detected columns."""
    col_set = set(columns)
    suggestions = []
    if "chosen" in col_set and "rejected" in col_set:
        suggestions.append("preference_pairs (found 'chosen' and 'rejected' columns)")
    if "messages" in col_set:
        suggestions.append("chat (found 'messages' column)")
    if "instruction" in col_set and "output" in col_set:
        suggestions.append("instruction (found 'instruction' and 'output' columns)")
    if "text" in col_set and not suggestions:
        suggestions.append("completion (found 'text' column)")

    if suggestions:
        ctx.log_message(f"Suggested training_format: {', '.join(suggestions)}")
    else:
        ctx.log_message(f"No standard training format detected from columns: {columns}. "
                        "Set training_format manually or use a transform script to prepare columns.")


# ---------------------------------------------------------------------------
# Stage 1: Data loading
# ---------------------------------------------------------------------------

def _load_upstream(ctx):
    """Load from connected dataset input."""
    try:
        raw = ctx.load_input("dataset")
    except (ValueError, KeyError):
        raw = None

    if raw is None:
        raise BlockInputError(
            "No dataset connected. Connect an upstream dataset block or switch source to 'huggingface' or 'local_file'.",
            details="The 'upstream' source requires a dataset input connection",
            recoverable=True,
        )

    # Resolve to list of dicts
    if isinstance(raw, list):
        if raw and isinstance(raw[0], dict):
            ctx.log_message(f"Loaded {len(raw)} rows from upstream (direct list)")
            return raw
        elif raw:
            raise BlockDataError(
                f"Upstream dataset contains {type(raw[0]).__name__} items instead of dicts. "
                "Each row must be a JSON object (dict)."
            )
        return raw

    if isinstance(raw, str):
        path = raw
        if os.path.isdir(path):
            data_file = os.path.join(path, "data.json")
            if not os.path.isfile(data_file):
                # Try any .json file in directory
                json_files = [f for f in os.listdir(path) if f.endswith(".json")]
                if json_files:
                    data_file = os.path.join(path, json_files[0])
                    ctx.log_message(f"Using {json_files[0]} from dataset directory")
                else:
                    raise BlockDataError(
                        f"No data.json found in upstream dataset directory: {path}. "
                        f"Contents: {os.listdir(path)[:10]}"
                    )
            path = data_file

        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                content = f.read().strip()
            if not content:
                raise BlockDataError(f"Upstream dataset file is empty: {path}")
            if content.startswith("["):
                rows = json.loads(content)
            else:
                # JSONL
                rows = [json.loads(line) for line in content.splitlines() if line.strip()]
            ctx.log_message(f"Loaded {len(rows)} rows from upstream file")
            return rows
        else:
            raise BlockDataError(f"Upstream dataset path not found: {path}")

    if isinstance(raw, dict):
        ctx.log_message("Upstream provided a single dict — wrapping as 1-row dataset")
        return [raw]

    raise BlockDataError(
        f"Cannot interpret upstream dataset (type={type(raw).__name__}). "
        "Expected a list of dicts, a file path, or a directory."
    )


def _load_huggingface(ctx, cfg):
    """Load from HuggingFace Hub with auto-detection of configs and splits."""
    hf_dataset = cfg.get("hf_dataset", "").strip()
    if not hf_dataset:
        raise BlockConfigError(
            "hf_dataset",
            "HF Dataset Name is required when source is 'huggingface'. "
            "Provide a dataset identifier like 'tatsu-lab/alpaca' or 'Anthropic/hh-rlhf'."
        )

    try:
        from datasets import load_dataset
    except ImportError:
        raise BlockDependencyError(
            "datasets",
            "The 'datasets' library is required for HuggingFace loading. "
            "Install it with: pip install datasets",
            install_hint="pip install datasets",
        )

    hf_subset = cfg.get("hf_subset", "").strip()
    hf_split = cfg.get("hf_split", "train")
    hf_token = cfg.get("hf_token", "").strip() or None
    hf_streaming = _to_bool(cfg.get("hf_streaming", False))
    hf_max_samples = _to_int(cfg.get("hf_max_samples", 0))

    # Auto-detect available configs and splits
    try:
        from datasets import get_dataset_config_names, get_dataset_split_names
        configs = get_dataset_config_names(hf_dataset, token=hf_token)
        if configs and configs != ["default"]:
            ctx.log_message(f"Available subsets: {configs}")
            if not hf_subset:
                ctx.log_message(f"Using default subset. Set hf_subset to one of the above if needed.")
        splits = get_dataset_split_names(hf_dataset, config_name=hf_subset or None, token=hf_token)
        ctx.log_message(f"Available splits: {splits}")
        if hf_split != "all" and hf_split not in splits:
            available = ", ".join(splits)
            ctx.log_message(f"WARNING: Requested split '{hf_split}' not found. Available: {available}. Falling back to first available.")
            hf_split = splits[0] if splits else "train"
    except Exception as e:
        ctx.log_message(f"Could not auto-detect subsets/splits for '{hf_dataset}': {e}. Proceeding with configured values.")

    ctx.log_message(f"Loading '{hf_dataset}' (split={hf_split}, subset={hf_subset or 'default'}, streaming={hf_streaming})")

    load_kwargs = {"path": hf_dataset, "streaming": hf_streaming}
    if hf_subset:
        load_kwargs["name"] = hf_subset
    if hf_split and hf_split != "all":
        load_kwargs["split"] = hf_split
    if hf_token:
        load_kwargs["token"] = hf_token

    try:
        ds = load_dataset(**load_kwargs)
    except Exception as e:
        raise BlockExecutionError(
            f"Failed to load HuggingFace dataset '{hf_dataset}': {e}. "
            f"Check the dataset name, subset ('{hf_subset}'), and split ('{hf_split}') are correct."
        )

    # Handle split='all' → DatasetDict
    if hf_split == "all":
        try:
            from datasets import concatenate_datasets
            split_names = list(ds.keys())
            ctx.log_message(f"Concatenating {len(split_names)} splits: {split_names}")
            ds = concatenate_datasets(list(ds.values()))
        except Exception as e:
            raise BlockExecutionError(f"Failed to concatenate splits: {e}")

    if hf_streaming:
        rows = []
        limit = hf_max_samples if hf_max_samples > 0 else float("inf")
        log_interval = min(5000, max(100, hf_max_samples // 10)) if hf_max_samples > 0 else 5000
        for i, example in enumerate(ds):
            if i >= limit:
                break
            rows.append(dict(example))
            if (i + 1) % log_interval == 0:
                ctx.log_message(f"  Streamed {i + 1} rows...")
                if hf_max_samples > 0:
                    ctx.report_progress(min(i + 1, hf_max_samples), hf_max_samples)
    else:
        total = len(ds)
        if hf_max_samples > 0 and hf_max_samples < total:
            ds = ds.select(range(hf_max_samples))
            ctx.log_message(f"Selected first {hf_max_samples} of {total} rows")
        rows = [dict(row) for row in ds]

    ctx.log_message(f"Loaded {len(rows)} rows from HuggingFace")
    if rows:
        col_names = list(rows[0].keys())
        ctx.log_message(f"Columns: {col_names}")
        _suggest_training_format(col_names, ctx)
    else:
        ctx.log_message("WARNING: Dataset is empty — no rows loaded")

    return rows


def _load_local_file(ctx, cfg):
    """Load from a local file on disk."""
    file_path = cfg.get("file_path", "").strip()
    if not file_path:
        raise BlockConfigError(
            "file_path",
            "File Path is required when source is 'local_file'. "
            "Provide an absolute or relative path to a CSV, JSON, JSONL, TSV, or Parquet file."
        )

    file_path = os.path.expanduser(file_path)
    if not os.path.exists(file_path):
        raise BlockInputError(
            f"File not found: {file_path}",
            details="Check the file path is correct and the file exists",
            recoverable=True,
        )

    fmt = cfg.get("file_format", "auto")
    encoding = cfg.get("file_encoding", "utf-8") or "utf-8"

    if fmt == "auto":
        ext = os.path.splitext(file_path)[1].lower()
        fmt = {
            ".csv": "csv", ".tsv": "tsv", ".json": "json",
            ".jsonl": "jsonl", ".parquet": "parquet",
        }.get(ext, "csv")
        ctx.log_message(f"Auto-detected format: {fmt} (from extension '{ext}')")

    file_size = os.path.getsize(file_path)
    ctx.log_message(f"Loading {file_path} ({fmt}, {file_size / 1024:.1f} KB, encoding={encoding})")

    rows = []

    if fmt in ("csv", "tsv"):
        sep = "\t" if fmt == "tsv" else ","
        try:
            with open(file_path, "r", encoding=encoding) as f:
                reader = csv.DictReader(f, delimiter=sep)
                for i, row in enumerate(reader):
                    rows.append(dict(row))
                    if (i + 1) % 50000 == 0:
                        ctx.log_message(f"  Read {i + 1} rows...")
        except UnicodeDecodeError as e:
            raise BlockDataError(
                f"Encoding error reading {file_path} with encoding='{encoding}': {e}. "
                "Try setting file_encoding to 'latin-1' or 'cp1252'."
            )

    elif fmt in ("json", "jsonl"):
        try:
            with open(file_path, "r", encoding=encoding) as f:
                content = f.read().strip()
        except UnicodeDecodeError as e:
            raise BlockDataError(
                f"Encoding error reading {file_path} with encoding='{encoding}': {e}. "
                "Try setting file_encoding to 'latin-1' or 'cp1252'."
            )

        if not content:
            raise BlockDataError(f"File is empty: {file_path}")

        if content.startswith("["):
            try:
                rows = json.loads(content)
                if not isinstance(rows, list):
                    rows = [rows]
            except json.JSONDecodeError as e:
                raise BlockDataError(f"Invalid JSON in {file_path}: {e}")
        else:
            # JSONL
            for line_num, line in enumerate(content.splitlines(), 1):
                line = line.strip()
                if line:
                    try:
                        rows.append(json.loads(line))
                    except json.JSONDecodeError as e:
                        raise BlockDataError(f"Invalid JSON on line {line_num} of {file_path}: {e}")

    elif fmt == "parquet":
        try:
            import pandas as pd
        except ImportError:
            raise BlockDependencyError(
                "pandas",
                "The 'pandas' and 'pyarrow' libraries are required for Parquet files. "
                "Install with: pip install pandas pyarrow",
                install_hint="pip install pandas pyarrow",
            )
        try:
            df = pd.read_parquet(file_path)
            rows = df.to_dict(orient="records")
        except Exception as e:
            raise BlockDataError(f"Failed to read Parquet file {file_path}: {e}")

    else:
        raise BlockConfigError("file_format", f"Unsupported format: '{fmt}'. Use csv, tsv, json, jsonl, or parquet.")

    ctx.log_message(f"Loaded {len(rows)} rows from local file")
    if rows:
        ctx.log_message(f"Columns: {list(rows[0].keys())}")
    return rows


# ---------------------------------------------------------------------------
# Stage 2: Column mapping
# ---------------------------------------------------------------------------

def _apply_column_mapping(rows, mapping_json, keep_columns_str, ctx):
    """Rename columns and optionally filter to keep_columns."""
    if not rows:
        return rows

    # Parse rename map
    rename_map = {}
    if mapping_json and mapping_json.strip():
        try:
            parsed = json.loads(mapping_json)
        except json.JSONDecodeError as e:
            raise BlockConfigError("column_mapping", f"Invalid JSON in column_mapping: {e}")

        if not isinstance(parsed, dict):
            raise BlockConfigError("column_mapping", f"column_mapping must be a JSON object (got {type(parsed).__name__})")

        # Validate all keys and values are strings
        for k, v in parsed.items():
            if not isinstance(k, str) or not isinstance(v, str):
                raise BlockConfigError("column_mapping", f"All keys and values must be strings. Got: {k!r} → {v!r}")
        rename_map = parsed

    if rename_map:
        available = set(rows[0].keys())
        missing = [k for k in rename_map if k not in available]
        if missing:
            ctx.log_message(f"WARNING: column_mapping references columns not in data: {missing}. Available: {sorted(available)}")

        applied = {k: v for k, v in rename_map.items() if k in available}
        if applied:
            rows = [{rename_map.get(k, k): v for k, v in row.items()} for row in rows]
            ctx.log_message(f"Renamed {len(applied)} column(s): {applied}")

    # Keep only specified columns
    if keep_columns_str and keep_columns_str.strip():
        cols = [c.strip() for c in keep_columns_str.split(",") if c.strip()]
        if cols:
            available = set(rows[0].keys()) if rows else set()
            valid = [c for c in cols if c in available]
            missing = [c for c in cols if c not in available]
            if missing:
                ctx.log_message(f"WARNING: keep_columns not found (skipped): {missing}. Available: {sorted(available)}")
            if valid:
                rows = [{k: row.get(k) for k in valid} for row in rows]
                ctx.log_message(f"Keeping {len(valid)} column(s): {valid}")
            elif not valid:
                ctx.log_message("WARNING: No valid columns in keep_columns — keeping all columns")

    return rows


# ---------------------------------------------------------------------------
# Stage 3: Script-based transform
# ---------------------------------------------------------------------------

def _build_transform_function(script_text):
    """Compile user's transform script into a callable function in a restricted namespace."""
    # Build the function from user code
    lines = script_text.strip().splitlines()
    func_lines = ["def _transform(row):"]
    for line in lines:
        func_lines.append(f"    {line}")
    # Ensure function always has a body
    if len(func_lines) == 1:
        func_lines.append("    return row")
    func_code = "\n".join(func_lines)

    # Restricted builtins — data-manipulation functions only, no I/O or code execution
    import builtins as _builtins_mod
    _safe_names = [
        # Types & constructors
        "len", "str", "int", "float", "bool", "list", "dict", "tuple", "set",
        "frozenset", "bytes", "bytearray", "complex",
        # Iteration & sequence
        "min", "max", "sum", "sorted", "reversed", "enumerate", "zip", "range",
        "map", "filter", "any", "all",
        # Inspection
        "isinstance", "type", "hasattr", "getattr", "callable", "id", "hash",
        "repr", "format",
        # Math
        "round", "abs", "pow", "divmod",
        # String/char
        "chr", "ord", "hex", "bin", "oct",
        # Constants & exceptions (needed for control flow in user code)
        "True", "False", "None",
        "ValueError", "TypeError", "KeyError", "IndexError", "AttributeError", "Exception",
        "StopIteration",
        # Printing for debug (no-op effectively, but users expect it)
        "print",
    ]
    safe_builtins = {}
    for name in _safe_names:
        val = getattr(_builtins_mod, name, None)
        if val is not None:
            safe_builtins[name] = val

    import datetime as _datetime_mod
    namespace = {
        "__builtins__": safe_builtins,
        "re": re,
        "json": json,
        "math": math,
        "datetime": _datetime_mod,
    }

    try:
        compiled = compile(func_code, "<transform_script>", "exec")
    except SyntaxError as e:
        raise BlockConfigError(
            "transform_script",
            f"Syntax error in transform script at line {e.lineno}: {e.msg}. "
            f"Check your Python syntax."
        )

    exec(compiled, namespace)
    return namespace["_transform"]


def _apply_transform_script(rows, script_text, ctx):
    """Apply user-defined Python transform to each row."""
    if not script_text or not script_text.strip() or not rows:
        return rows

    ctx.log_message("Applying transform script...")
    transform_fn = _build_transform_function(script_text)

    result = []
    errors = 0
    error_types = {}
    total = len(rows)
    log_interval = max(1000, total // 20)  # Log every 5% or 1000 rows

    for i, row in enumerate(rows):
        try:
            out = transform_fn(dict(row))  # Copy to prevent mutation leaking between rows
            if out is None:
                continue  # Row dropped by transform
            if not isinstance(out, dict):
                errors += 1
                err_key = f"returned {type(out).__name__} instead of dict"
                error_types[err_key] = error_types.get(err_key, 0) + 1
                if errors <= 3:
                    ctx.log_message(f"  Transform error row {i}: must return dict or None, got {type(out).__name__}")
                continue
            result.append(out)
        except Exception as e:
            errors += 1
            err_key = type(e).__name__
            error_types[err_key] = error_types.get(err_key, 0) + 1
            if errors <= 5:
                ctx.log_message(f"  Transform error row {i}: {e}")

        if (i + 1) % log_interval == 0:
            ctx.report_progress(i + 1, total)

    if errors:
        error_summary = ", ".join(f"{v}x {k}" for k, v in sorted(error_types.items(), key=lambda x: -x[1]))
        ctx.log_message(f"Transform: {total} input → {len(result)} output ({errors} errors: {error_summary})")
    else:
        dropped = total - len(result)
        ctx.log_message(f"Transform: {total} → {len(result)} rows" + (f" ({dropped} dropped by script)" if dropped else ""))

    return result


# ---------------------------------------------------------------------------
# Stage 4: Training format conversion
# ---------------------------------------------------------------------------

def _validate_template_columns(template, rows, ctx):
    """Check that all {column} placeholders in a template exist in the data."""
    import string
    formatter = string.Formatter()
    try:
        fields = [field_name for _, field_name, _, _ in formatter.parse(template) if field_name]
    except (ValueError, KeyError):
        return  # Can't parse, will fail at format time with a clear error

    if not fields or not rows:
        return

    available = set(rows[0].keys())
    missing = [f for f in fields if f not in available]
    if missing:
        ctx.log_message(
            f"WARNING: Template references columns not in data: {missing}. "
            f"Available columns: {sorted(available)}. "
            f"Template formatting will fail for rows missing these columns."
        )


def _apply_training_format(rows, cfg, ctx):
    """Convert rows to the target training format."""
    fmt = cfg.get("training_format", "none")
    if fmt == "none" or not rows:
        return rows

    ctx.log_message(f"Applying training format: {fmt}")

    if fmt == "instruction":
        template = cfg.get("instruction_template", "### Instruction:\n{instruction}\n\n### Response:\n{output}")
        if not template or not template.strip():
            raise BlockConfigError("instruction_template", "Instruction template is required for 'instruction' format")

        _validate_template_columns(template, rows, ctx)

        result = []
        errors = 0
        for i, row in enumerate(rows):
            try:
                text = template.format_map(row)
                result.append({"text": text})
            except KeyError as e:
                errors += 1
                if errors <= 3:
                    ctx.log_message(
                        f"  Template error row {i}: missing column {e}. "
                        f"Row has: {list(row.keys())}. Template: {template[:80]}..."
                    )
        if errors:
            ctx.log_message(f"Instruction format: {errors} rows failed template formatting (skipped)")
        else:
            ctx.log_message(f"Instruction format: {len(result)} rows formatted")
        return result

    elif fmt == "chat":
        system_prompt = cfg.get("system_prompt", "").strip()
        result = []
        for i, row in enumerate(rows):
            # If row already has 'messages' column (list of role/content dicts), use it
            if "messages" in row and isinstance(row["messages"], (list, str)):
                messages = row["messages"]
                if isinstance(messages, str):
                    try:
                        messages = json.loads(messages)
                    except json.JSONDecodeError:
                        if i == 0:
                            ctx.log_message("WARNING: 'messages' column contains strings, not lists. Attempting JSON parse.")
                        continue

                if not isinstance(messages, list):
                    continue

                if system_prompt and (not messages or messages[0].get("role") != "system"):
                    messages = [{"role": "system", "content": system_prompt}] + messages

                parts = []
                for msg in messages:
                    role = msg.get("role", "user")
                    content = msg.get("content", "")
                    parts.append(f"<|im_start|>{role}\n{content}<|im_end|>")
                result.append({"text": "\n".join(parts)})
            else:
                # Build chat from instruction/output columns
                instr_col = _detect_column([row], "instruction") or "instruction"
                out_col = _detect_column([row], "output") or "output"
                instr = str(row.get(instr_col, ""))
                output = str(row.get(out_col, ""))
                if not instr and not output:
                    if i == 0:
                        ctx.log_message(
                            f"WARNING: No 'messages', '{instr_col}', or '{out_col}' column found. "
                            f"Available: {list(row.keys())}. Chat format may produce empty conversations."
                        )
                    continue
                parts = []
                if system_prompt:
                    parts.append(f"<|im_start|>system\n{system_prompt}<|im_end|>")
                parts.append(f"<|im_start|>user\n{instr}<|im_end|>")
                parts.append(f"<|im_start|>assistant\n{output}<|im_end|>")
                result.append({"text": "\n".join(parts)})

        ctx.log_message(f"Chat format: {len(result)} conversations built" +
                        (f" ({len(rows) - len(result)} skipped)" if len(result) < len(rows) else ""))
        return result

    elif fmt == "completion":
        text_col = cfg.get("text_column", "").strip()
        if not text_col:
            text_col = _detect_column(rows, "text")
        if not text_col:
            # Fall back to first column
            text_col = list(rows[0].keys())[0]
            ctx.log_message(f"No text column detected — using first column: '{text_col}'")
        else:
            ctx.log_message(f"Completion format using column: '{text_col}'")

        if text_col not in rows[0]:
            raise BlockDataError(
                f"Text column '{text_col}' not found in data. "
                f"Available columns: {list(rows[0].keys())}. "
                f"Set text_column explicitly or rename the column using column_mapping."
            )

        result = [{"text": str(row.get(text_col, ""))} for row in rows]
        return result

    elif fmt == "preference_pairs":
        chosen_col = cfg.get("chosen_column", "chosen").strip() or "chosen"
        rejected_col = cfg.get("rejected_column", "rejected").strip() or "rejected"
        prompt_col = cfg.get("prompt_column", "").strip() or _detect_column(rows, "prompt")

        available = set(rows[0].keys())
        if chosen_col not in available:
            raise BlockDataError(
                f"Chosen column '{chosen_col}' not found. Available: {sorted(available)}. "
                f"Set chosen_column to the correct column name."
            )
        if rejected_col not in available:
            raise BlockDataError(
                f"Rejected column '{rejected_col}' not found. Available: {sorted(available)}. "
                f"Set rejected_column to the correct column name."
            )

        result = []
        for row in rows:
            out = {
                "chosen": row.get(chosen_col, ""),
                "rejected": row.get(rejected_col, ""),
            }
            if prompt_col and prompt_col in row:
                out["prompt"] = row[prompt_col]
            result.append(out)

        ctx.log_message(
            f"Preference pairs: {len(result)} rows (chosen='{chosen_col}', rejected='{rejected_col}'"
            + (f", prompt='{prompt_col}'" if prompt_col else "") + ")"
        )
        return result

    elif fmt == "rlhf_prompts":
        prompt_col = cfg.get("prompt_column", "").strip()
        if not prompt_col:
            prompt_col = _detect_column(rows, "prompt")
        if not prompt_col:
            # Try known fallbacks
            available = set(rows[0].keys())
            for fallback in ["query", "prompt", "text", "instruction", "question"]:
                if fallback in available:
                    prompt_col = fallback
                    break
        if not prompt_col:
            prompt_col = list(rows[0].keys())[0]
            ctx.log_message(f"No prompt column detected — using first column: '{prompt_col}'")

        if prompt_col not in rows[0]:
            raise BlockDataError(
                f"Prompt column '{prompt_col}' not found. Available: {list(rows[0].keys())}. "
                f"Set prompt_column explicitly."
            )

        result = [{"query": str(row.get(prompt_col, ""))} for row in rows]
        ctx.log_message(f"RLHF prompts: {len(result)} rows (from column '{prompt_col}' → 'query')")
        return result

    else:
        ctx.log_message(f"WARNING: Unknown training_format '{fmt}' — passing data through unchanged")
        return rows


# ---------------------------------------------------------------------------
# Stage 5: Filtering
# ---------------------------------------------------------------------------

def _apply_filters(rows, cfg, ctx):
    """Filter, deduplicate, and sample rows. Returns (rows, dropped_counts)."""
    if not rows:
        return rows, {}

    original_count = len(rows)
    dropped = {"filter_expr": 0, "min_length": 0, "max_length": 0, "dedup": 0}
    text_col = _detect_primary_text_column(rows)

    # Filter expression (method-based, not eval)
    filter_expr = (cfg.get("filter_expression", "") or "").strip()
    if filter_expr:
        ctx.log_message(f"Applying filter expression on {len(rows)} rows...")

        # Build restricted namespace for eval — minimal, no code execution
        import builtins as _builtins_mod
        safe_eval_builtins = {}
        for name in ["len", "str", "int", "float", "bool", "True", "False", "None",
                      "isinstance", "any", "all", "min", "max", "abs", "round",
                      "sorted", "list", "tuple", "set", "dict"]:
            val = getattr(_builtins_mod, name, None)
            if val is not None:
                safe_eval_builtins[name] = val

        filtered = []
        eval_errors = 0
        for row in rows:
            try:
                keep = eval(filter_expr, {"__builtins__": safe_eval_builtins, "row": row, "re": re})
                if keep:
                    filtered.append(row)
                else:
                    dropped["filter_expr"] += 1
            except Exception as e:
                eval_errors += 1
                dropped["filter_expr"] += 1
                if eval_errors <= 3:
                    ctx.log_message(f"  Filter expression error: {e} (row keys: {list(row.keys())})")

        if eval_errors:
            ctx.log_message(f"Filter expression: {eval_errors} evaluation errors (rows dropped)")
        rows = filtered

    # Min length filter
    min_len = _to_int(cfg.get("min_length", 0))
    if min_len > 0 and rows:
        before = len(rows)
        rows = [r for r in rows if len(str(r.get(text_col, ""))) >= min_len]
        dropped["min_length"] = before - len(rows)
        if dropped["min_length"]:
            ctx.log_message(f"Min length filter ({min_len} chars on '{text_col}'): dropped {dropped['min_length']} rows")

    # Max length filter
    max_len = _to_int(cfg.get("max_length", 0))
    if max_len > 0 and rows:
        before = len(rows)
        rows = [r for r in rows if len(str(r.get(text_col, ""))) <= max_len]
        dropped["max_length"] = before - len(rows)
        if dropped["max_length"]:
            ctx.log_message(f"Max length filter ({max_len} chars on '{text_col}'): dropped {dropped['max_length']} rows")

    # Deduplication
    if _to_bool(cfg.get("deduplicate", False)) and rows:
        seen = set()
        unique = []
        for row in rows:
            h = hashlib.md5(json.dumps(row, sort_keys=True, default=str).encode()).hexdigest()
            if h not in seen:
                seen.add(h)
                unique.append(row)
        dropped["dedup"] = len(rows) - len(unique)
        rows = unique
        if dropped["dedup"]:
            ctx.log_message(f"Deduplication: removed {dropped['dedup']} duplicate rows")

    # Random sample (applied last, before eval split)
    sample_size = _to_int(cfg.get("sample_size", 0))
    if sample_size > 0 and sample_size < len(rows):
        seed = _to_int(cfg.get("seed", 42))
        rng = random.Random(seed)
        rows = rng.sample(rows, sample_size)
        ctx.log_message(f"Sampled {sample_size} rows (seed={seed})")

    total_dropped = sum(dropped.values())
    if total_dropped > 0:
        ctx.log_message(f"Filtering complete: {original_count} → {len(rows)} rows ({total_dropped} dropped)")

    return rows, dropped


# ---------------------------------------------------------------------------
# Stage 6: Shuffle & eval split
# ---------------------------------------------------------------------------

def _shuffle_and_split(rows, cfg, ctx):
    """Shuffle rows and optionally split into train and eval sets."""
    if not rows:
        return rows, []

    shuffle = _to_bool(cfg.get("shuffle", True))
    seed = _to_int(cfg.get("seed", 42))
    eval_ratio = _to_float(cfg.get("eval_split", 0.0))

    data = list(rows)

    if shuffle:
        rng = random.Random(seed)
        rng.shuffle(data)
        ctx.log_message(f"Shuffled {len(data)} rows (seed={seed})")
    elif eval_ratio > 0:
        ctx.log_message(
            "NOTE: eval_split is set but shuffle is disabled. "
            "The eval set will be the last rows in order — ensure your data isn't ordered by label/difficulty."
        )

    if eval_ratio <= 0:
        return data, []

    split_idx = max(1, int(len(data) * (1 - eval_ratio)))
    train = data[:split_idx]
    eval_data = data[split_idx:]
    ctx.log_message(f"Split: {len(train)} train / {len(eval_data)} eval (ratio={eval_ratio})")
    return train, eval_data


# ---------------------------------------------------------------------------
# Stage 7: Schema validation
# ---------------------------------------------------------------------------

def _validate_schema(rows, cfg, ctx):
    """Validate output columns match target training block expectations."""
    if not _to_bool(cfg.get("validate_schema", True)) or not rows:
        return True, []

    target = cfg.get("target_block", "auto")
    if target == "auto":
        fmt = cfg.get("training_format", "none")
        target = FORMAT_TO_TARGET.get(fmt, "")
    if not target or target not in TRAINING_SCHEMAS:
        return True, []

    schema = TRAINING_SCHEMAS[target]
    columns = set(rows[0].keys())
    warnings = []

    # Check required columns
    for col in schema.get("required", []):
        if col not in columns:
            warnings.append(
                f"MISSING required column '{col}' for {target}. "
                f"Available: {sorted(columns)}. "
                f"Use column_mapping or training_format to produce this column."
            )

    # Check required_any (at least one must be present)
    required_any = schema.get("required_any", [])
    if required_any and not any(c in columns for c in required_any):
        warnings.append(
            f"MISSING: need at least one of {required_any} for {target}. "
            f"Available: {sorted(columns)}."
        )

    # Check for empty values in required columns (sample-based for performance)
    check_cols = schema.get("required", []) + [c for c in required_any if c in columns]
    sample = rows[:min(1000, len(rows))]  # Check first 1000 rows
    for col in check_cols:
        if col in columns:
            empty_count = sum(1 for r in sample if not r.get(col))
            if empty_count > 0:
                pct = empty_count / len(sample) * 100
                if pct > 5:
                    warnings.append(
                        f"Column '{col}' has ~{pct:.0f}% empty values "
                        f"({empty_count} of {len(sample)} sampled rows). "
                        "This may cause poor training quality."
                    )

    # Check optional columns — advisory only
    for col in schema.get("optional", []):
        if col not in columns:
            ctx.log_message(f"INFO: Optional column '{col}' not found — {target} will work without it")

    # Row count check with task-specific recommendation
    min_recommended = MIN_ROWS_RECOMMENDATION.get(target, 100)
    if len(rows) < min_recommended:
        warnings.append(
            f"Only {len(rows)} rows — recommended minimum for {target} is {min_recommended}. "
            "Consider adding more training data."
        )

    has_hard_failure = any("MISSING" in w for w in warnings)

    if warnings:
        for w in warnings:
            ctx.log_message(f"Schema validation: {w}")
    else:
        ctx.log_message(f"Schema validation passed for {target}")

    return not has_hard_failure, warnings


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run(ctx):
    source = ctx.config.get("source", "upstream")

    # Build effective config (base config + overrides)
    cfg = dict(ctx.config)

    # Apply config overrides from connected input
    try:
        _ci = ctx.load_input("config")
        if _ci:
            _ov = _ci
            if isinstance(_ci, str) and os.path.isfile(_ci):
                with open(_ci, "r", encoding="utf-8") as f:
                    _ov = json.load(f)
            if isinstance(_ov, dict) and _ov:
                override_keys = list(_ov.keys())
                cfg.update(_ov)
                source = cfg.get("source", source)
                ctx.log_message(f"Applied {len(override_keys)} config override(s): {override_keys}")
    except (ValueError, KeyError):
        pass
    except (json.JSONDecodeError, OSError) as e:
        ctx.log_message(f"WARNING: Could not load config override input: {e}")

    # Inherit metadata hints from upstream (as defaults, not overrides)
    try:
        meta = ctx.load_input("dataset_meta")
        if meta:
            if isinstance(meta, str) and os.path.isfile(meta):
                with open(meta, "r", encoding="utf-8") as f:
                    meta = json.load(f)
            if isinstance(meta, dict):
                if not cfg.get("text_column") and meta.get("text_column"):
                    cfg["text_column"] = meta["text_column"]
                if meta.get("seed") and not ctx.config.get("seed"):
                    cfg["seed"] = meta["seed"]
                if meta.get("columns"):
                    ctx.log_message(f"Upstream columns: {meta['columns']}")
    except (ValueError, KeyError):
        pass
    except (json.JSONDecodeError, OSError) as e:
        ctx.log_message(f"WARNING: Could not load dataset_meta input: {e}")

    total_stages = 7

    # ── Stage 1: Load data ──
    ctx.log_message(f"[1/{total_stages}] Loading data (source: {source})")
    ctx.report_progress(0, total_stages)

    if source == "upstream":
        rows = _load_upstream(ctx)
    elif source == "huggingface":
        rows = _load_huggingface(ctx, cfg)
    elif source == "local_file":
        rows = _load_local_file(ctx, cfg)
    else:
        raise BlockConfigError("source", f"Unknown source: '{source}'. Use 'upstream', 'huggingface', or 'local_file'.")

    if not rows:
        raise BlockDataError("No data loaded — dataset is empty. Check your source configuration.")
    if not isinstance(rows[0], dict):
        raise BlockDataError(
            f"Dataset rows must be dicts (JSON objects), got {type(rows[0]).__name__}. "
            "Check your data format."
        )

    ctx.log_message(f"Loaded {len(rows)} rows, {len(rows[0])} columns: {list(rows[0].keys())}")
    ctx.report_progress(1, total_stages)

    # ── Stage 2: Column mapping ──
    ctx.log_message(f"[2/{total_stages}] Column mapping")
    rows = _apply_column_mapping(
        rows,
        cfg.get("column_mapping", ""),
        cfg.get("keep_columns", ""),
        ctx,
    )
    if not rows:
        raise BlockDataError("All rows lost after column mapping — check column_mapping and keep_columns configuration")
    ctx.report_progress(2, total_stages)

    # ── Stage 3: Script-based transform ──
    ctx.log_message(f"[3/{total_stages}] Script transform")
    rows = _apply_transform_script(rows, cfg.get("transform_script", ""), ctx)
    if not rows:
        raise BlockDataError(
            "All rows were dropped by the transform script. "
            "Ensure your script returns a dict (not None) for rows you want to keep."
        )
    ctx.report_progress(3, total_stages)

    # ── Stage 4: Training format conversion ──
    ctx.log_message(f"[4/{total_stages}] Training format conversion")
    rows = _apply_training_format(rows, cfg, ctx)
    if not rows:
        raise BlockDataError(
            "No rows produced after training format conversion. "
            "Check that your data has the columns required by the selected training_format."
        )
    ctx.report_progress(4, total_stages)

    # ── Stage 5: Filtering ──
    ctx.log_message(f"[5/{total_stages}] Filtering")
    rows, dropped_counts = _apply_filters(rows, cfg, ctx)
    if not rows:
        raise BlockDataError(
            "All rows were dropped by filters. "
            "Check min_length, max_length, filter_expression, and deduplicate settings."
        )
    ctx.report_progress(5, total_stages)

    # ── Stage 6: Shuffle & eval split ──
    ctx.log_message(f"[6/{total_stages}] Shuffle & split")
    train_rows, eval_rows = _shuffle_and_split(rows, cfg, ctx)
    ctx.report_progress(6, total_stages)

    # ── Stage 7: Validate & save ──
    ctx.log_message(f"[7/{total_stages}] Validate & save")
    schema_valid, validation_warnings = _validate_schema(train_rows, cfg, ctx)

    # Raise on hard failures (missing required columns) — only if validation is enabled
    if _to_bool(cfg.get("validate_schema", True)):
        hard_failures = [w for w in validation_warnings if "MISSING" in w]
        if hard_failures:
            raise BlockDataError(
                "Schema validation failed:\n" + "\n".join(f"  - {w}" for w in hard_failures)
            )

    # Save train dataset
    out_path = os.path.join(ctx.run_dir, "dataset")
    os.makedirs(out_path, exist_ok=True)
    with open(os.path.join(out_path, "data.json"), "w", encoding="utf-8") as f:
        json.dump(train_rows, f, default=str, ensure_ascii=False)
    ctx.save_output("dataset", out_path)

    # Save eval dataset if split was applied
    eval_row_count = 0
    if eval_rows:
        eval_path = os.path.join(ctx.run_dir, "eval_dataset")
        os.makedirs(eval_path, exist_ok=True)
        with open(os.path.join(eval_path, "data.json"), "w", encoding="utf-8") as f:
            json.dump(eval_rows, f, default=str, ensure_ascii=False)
        ctx.save_output("eval_dataset", eval_path)
        eval_row_count = len(eval_rows)

    # Determine text column for metadata
    col_names = list(train_rows[0].keys()) if train_rows else []
    text_col = _detect_primary_text_column(train_rows)

    # Resolve target block for metadata
    fmt_applied = cfg.get("training_format", "none")
    target_block = cfg.get("target_block", "auto")
    if target_block == "auto":
        target_block = FORMAT_TO_TARGET.get(fmt_applied, "")

    # Save dataset_meta
    seed = _to_int(cfg.get("seed", 42))
    shuffle = _to_bool(cfg.get("shuffle", True))
    ctx.save_output("dataset_meta", {
        "text_column": text_col,
        "columns": col_names,
        "num_rows": len(train_rows),
        "eval_rows": eval_row_count,
        "seed": seed,
        "shuffle": shuffle,
        "source": source,
        "training_format": fmt_applied,
        "target_block": target_block,
        "schema_valid": schema_valid,
        "validation_warnings": validation_warnings,
    })

    # Save metrics
    metrics = {
        "source": source,
        "row_count": len(train_rows),
        "eval_row_count": eval_row_count,
        "columns": col_names,
        "column_count": len(col_names),
        "format_applied": fmt_applied,
        "target_block": target_block or "none",
        "validation_result": "passed" if schema_valid else "warnings",
        "validation_warnings": validation_warnings,
        "dropped_rows": dropped_counts,
        "total_dropped": sum(dropped_counts.values()),
    }
    metrics_path = os.path.join(ctx.run_dir, "metrics.json")
    with open(metrics_path, "w") as f:
        json.dump(metrics, f, indent=2)
    ctx.save_output("metrics", metrics_path)

    # Log metrics for tracking
    ctx.log_metric("row_count", len(train_rows))
    ctx.log_metric("eval_row_count", eval_row_count)
    ctx.log_metric("column_count", len(col_names))
    ctx.log_metric("total_dropped", sum(dropped_counts.values()))
    if not schema_valid:
        ctx.log_metric("schema_warnings", len(validation_warnings))

    # Final summary
    summary_parts = [f"{len(train_rows)} train rows"]
    if eval_row_count:
        summary_parts.append(f"{eval_row_count} eval rows")
    summary_parts.append(f"format={fmt_applied}")
    if target_block:
        summary_parts.append(f"target={target_block}")
    summary_parts.append(f"valid={'yes' if schema_valid else 'warnings'}")
    ctx.log_message(f"Dataset ready: {' | '.join(summary_parts)}")
    ctx.report_progress(total_stages, total_stages)
