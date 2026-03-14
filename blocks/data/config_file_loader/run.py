"""Config File Loader — read a JSON, YAML, or TOML config file from disk with optional schema validation."""

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
    file_path = ctx.config.get("file_path", "")
    fmt = ctx.config.get("format", "auto")
    validate_schema = ctx.config.get("validate_schema", False)
    schema_path = ctx.config.get("schema_path", "")

    # Normalize booleans
    if isinstance(validate_schema, str):
        validate_schema = validate_schema.lower() in ("true", "1", "yes")

    if not file_path:
        raise BlockConfigError("file_path", "No file_path configured")

    file_path = os.path.expanduser(file_path)
    if not os.path.isfile(file_path):
        raise BlockInputError(f"Config file not found: {file_path}", details="Check that the upstream block produced output", recoverable=False)

    ctx.log_message(f"Loading config from {os.path.basename(file_path)}")
    ctx.report_progress(0, 1)

    with open(file_path, "r", encoding="utf-8") as f:
        raw = f.read()

    ext = os.path.splitext(file_path)[1].lower()
    if fmt == "auto":
        fmt = {
            ".json": "json",
            ".yaml": "yaml",
            ".yml": "yaml",
            ".toml": "toml",
        }.get(ext, "json")
        ctx.log_message(f"Auto-detected format: {fmt}")

    parsed = None

    if fmt == "json":
        parsed = json.loads(raw)
        ctx.log_message("Parsed as JSON")
    elif fmt in ("yaml", "yml"):
        try:
            import yaml
            parsed = yaml.safe_load(raw)
            ctx.log_message("Parsed as YAML")
        except ImportError:
            raise BlockDependencyError("pyyaml", install_hint="pip install pyyaml")
    elif fmt == "toml":
        try:
            import tomllib
            parsed = tomllib.loads(raw)
        except ImportError:
            try:
                import tomli
                parsed = tomli.loads(raw)
            except ImportError:
                raise BlockDependencyError("tomli", install_hint="pip install tomli")
        ctx.log_message("Parsed as TOML")
    else:
        parsed = json.loads(raw)

    # Optional schema validation
    if validate_schema and schema_path:
        schema_path = os.path.expanduser(schema_path)
        if os.path.isfile(schema_path):
            try:
                import jsonschema

                with open(schema_path, "r", encoding="utf-8") as f:
                    schema = json.load(f)

                try:
                    jsonschema.validate(instance=parsed, schema=schema)
                    ctx.log_message("Schema validation passed")
                except jsonschema.ValidationError as e:
                    ctx.log_message(f"WARNING: Schema validation failed: {e.message}")
                    ctx.log_message(f"  Path: {'.'.join(str(p) for p in e.path)}" if e.path else "")
                except jsonschema.SchemaError as e:
                    ctx.log_message(f"WARNING: Invalid JSON schema: {e.message}")

            except ImportError:
                ctx.log_message("WARNING: jsonschema not installed. Install with: pip install jsonschema")
        else:
            ctx.log_message(f"WARNING: Schema file not found: {schema_path}")

    out_path = os.path.join(ctx.run_dir, "config.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(parsed, f, indent=2, default=str)

    key_count = len(parsed) if isinstance(parsed, dict) else "N/A"
    ctx.log_message(f"Config loaded: {key_count} top-level keys")
    ctx.log_metric("key_count", len(parsed) if isinstance(parsed, dict) else 0)
    ctx.report_progress(1, 1)
    ctx.save_output("config", out_path)
