"""Agent Text Bridge — extract text from structured agent output."""

import json
import os

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


def run(ctx):
    # ── Config ──────────────────────────────────────────────────────────
    extract_field = ctx.config.get("extract_field", "final_answer")
    fallback_fields_raw = ctx.config.get("fallback_fields", "response,output,text,code,answer")
    separator = ctx.config.get("separator", "\n---\n")
    max_length = int(ctx.config.get("max_length", 0))

    fallback_fields = [
        f.strip() for f in fallback_fields_raw.split(",") if f.strip()
    ]

    ctx.report_progress(0, 3)

    # ── Load agent output ───────────────────────────────────────────────
    agent_data = _load_data(ctx, "agent")
    if agent_data is None:
        raise BlockInputError("No agent output received on 'agent' input port.", recoverable=False)

    ctx.log_message(f"Agent data type: {type(agent_data).__name__}")
    ctx.report_progress(1, 3)

    # ── Load task context (optional) ────────────────────────────────────
    dataset = _load_data(ctx, "dataset")
    ctx.report_progress(2, 3)

    # ── Extract the target field ────────────────────────────────────────
    if isinstance(agent_data, dict):
        extracted = _extract_from_dict(agent_data, extract_field, fallback_fields)
    elif isinstance(agent_data, list):
        parts = []
        for item in agent_data:
            if isinstance(item, dict):
                parts.append(_extract_from_dict(item, extract_field, fallback_fields))
            else:
                parts.append(str(item))
        extracted = separator.join(parts)
    else:
        extracted = str(agent_data)

    if max_length > 0 and len(extracted) > max_length:
        extracted = extracted[:max_length] + "..."
        ctx.log_message(f"Truncated to {max_length} chars")

    ctx.log_message(f"Extracted '{extract_field}': {len(extracted)} chars")

    # ── Apply output format ─────────────────────────────────────────────
    output_format = ctx.config.get("output_format", "raw")
    if output_format == "markdown":
        output_content = (
            f"## Extracted Agent Output\n\n"
            f"**Field:** {extract_field}\n"
            f"**Length:** {len(extracted)} chars\n\n---\n\n{extracted}"
        )
    elif output_format == "json":
        output_content = json.dumps({
            "extracted_text": extracted,
            "extract_field": extract_field,
            "source_type": type(agent_data).__name__,
            "length": len(extracted),
        }, indent=2)
    else:
        output_content = extracted

    # ── Save extracted text ─────────────────────────────────────────────
    text_path = os.path.join(ctx.run_dir, "agent_output.txt")
    with open(text_path, "w", encoding="utf-8") as f:
        f.write(output_content)
    ctx.save_output("text", text_path)

    # ── Save full responses as dataset ──────────────────────────────────
    ds_dir = os.path.join(ctx.run_dir, "dataset")
    os.makedirs(ds_dir, exist_ok=True)
    full_record = {
        "agent_data": agent_data,
        "dataset": dataset,
        "extracted_text": extracted,
        "extract_field": extract_field,
    }
    with open(os.path.join(ds_dir, "data.json"), "w", encoding="utf-8") as f:
        json.dump([full_record], f, indent=2, default=str)
    ctx.save_output("output_dataset", ds_dir)

    # ── Save metrics ────────────────────────────────────────────────────
    metrics = {
        "extracted_length": len(extracted),
        "extract_field": extract_field,
        "agent_data_type": type(agent_data).__name__,
        "num_results": len(agent_data) if isinstance(agent_data, list) else 1,
    }
    ctx.save_output("metrics", metrics)
    for k, v in metrics.items():
        if isinstance(v, (int, float)):
            ctx.log_metric(k, v)

    ctx.report_progress(3, 3)


# ── Helpers ─────────────────────────────────────────────────────────────


def _load_data(ctx, input_name):
    """Load input data, handling files, directories, and raw values."""
    try:
        data = ctx.load_input(input_name)
    except (ValueError, Exception):
        return None

    if isinstance(data, str):
        if os.path.isdir(data):
            data_file = os.path.join(data, "data.json")
            if os.path.isfile(data_file):
                with open(data_file, "r", encoding="utf-8", errors="ignore") as f:
                    try:
                        return json.load(f)
                    except json.JSONDecodeError:
                        return f.read()
        elif os.path.isfile(data):
            with open(data, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            try:
                return json.loads(content)
            except (json.JSONDecodeError, ValueError):
                return content

    return data


def _extract_from_dict(d, primary_field, fallback_fields):
    """Extract a text value from a dict, trying primary then fallback fields."""
    # Try primary field
    if primary_field in d:
        return str(d[primary_field])

    # Try fallback fields in order
    for field in fallback_fields:
        if field in d:
            return str(d[field])

    # Last resort: serialize the whole dict
    return json.dumps(d, indent=2, default=str)
