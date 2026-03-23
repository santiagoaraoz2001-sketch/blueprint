"""Config Builder — parse a JSON/YAML config string into a structured object, optionally merging with an upstream config."""

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


def _deep_merge(base, override):
    """Recursively merge override into base. Override values win for scalars, dicts merge deeply, lists concatenate."""
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        elif key in result and isinstance(result[key], list) and isinstance(value, list):
            result[key] = result[key] + value
        else:
            result[key] = value
    return result


def run(ctx):
    json_body = ctx.config.get("json_body", '{"key": "value"}')
    merge_strategy = ctx.config.get("merge_strategy", "replace")

    ctx.log_message("Parsing config body...")
    ctx.report_progress(0, 1)

    # Parse json_body
    parsed = None

    # Try JSON first
    try:
        parsed = json.loads(json_body)
        ctx.log_message("Parsed as JSON")
    except (json.JSONDecodeError, ValueError):
        pass

    # Fallback: try YAML
    if parsed is None:
        try:
            import yaml
            parsed = yaml.safe_load(json_body)
            ctx.log_message("Parsed as YAML")
        except Exception:
            pass

    if parsed is None:
        ctx.log_message("Could not parse as JSON or YAML, treating as raw text")
        parsed = {"raw": json_body}

    # Merge with base_config input if connected
    try:
        base_config_path = ctx.load_input("base_config")
        if base_config_path:
            if isinstance(base_config_path, str) and os.path.isfile(base_config_path):
                with open(base_config_path, "r", encoding="utf-8") as f:
                    base_config = json.load(f)
            elif isinstance(base_config_path, dict):
                base_config = base_config_path
            else:
                base_config = None

            if base_config and isinstance(base_config, dict) and isinstance(parsed, dict):
                if merge_strategy == "deep_merge":
                    parsed = _deep_merge(base_config, parsed)
                    ctx.log_message(f"Deep-merged with base config ({len(base_config)} base keys)")
                else:
                    # Replace: parsed overrides base entirely
                    merged = dict(base_config)
                    merged.update(parsed)
                    parsed = merged
                    ctx.log_message(f"Merged with base config (replace strategy, {len(base_config)} base keys)")
    except (ValueError, KeyError):
        pass  # No base_config input connected

    out_path = os.path.join(ctx.run_dir, "config.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(parsed, f, indent=2, default=str)

    key_count = len(parsed) if isinstance(parsed, dict) else 1
    ctx.log_message(f"Config built with {key_count} top-level keys")
    ctx.log_metric("key_count", key_count)
    ctx.report_progress(1, 1)
    ctx.save_output("config", out_path)
