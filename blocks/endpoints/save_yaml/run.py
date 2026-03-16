"""Save YAML — save pipeline configuration or data as YAML file."""

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
    output_path = ctx.config.get("output_path", "./output").strip()
    filename = ctx.config.get("filename", "config.yaml").strip()
    default_flow_style = ctx.config.get("default_flow_style", False)
    sort_keys = ctx.config.get("sort_keys", False)
    overwrite = ctx.config.get("overwrite_existing", True)
    allow_unicode = ctx.config.get("allow_unicode", True)
    timestamp_filename = ctx.config.get("timestamp_filename", False)
    header_comment = ctx.config.get("header_comment", "").strip()

    ctx.log_message("Save YAML starting")
    ctx.report_progress(0, 3)

    # ── Loop-aware file handling ──
    loop = ctx.get_loop_metadata()
    if isinstance(loop, dict):
        file_mode = loop.get("file_mode", "overwrite")
        iteration = loop.get("iteration", 0)
        ctx.log_message(f"[Loop iter {iteration}] file_mode={file_mode}")
    else:
        file_mode = "overwrite"
        iteration = 0

    # ---- Step 1: Load data ----
    ctx.report_progress(1, 3)
    raw_data = ctx.resolve_as_data("data")
    if not raw_data:
        raise BlockInputError(
            "No input data provided. Connect a 'data' input.",
            recoverable=False,
        )

    data = raw_data
    ctx.log_message(f"Data type: {type(data).__name__}")

    # ---- Step 2: Serialize to YAML ----
    ctx.report_progress(2, 3)
    try:
        import yaml
    except ImportError as e:
        missing = getattr(e, "name", None) or "pyyaml"
        raise BlockDependencyError(
            missing,
            "PyYAML is required for YAML output",
            install_hint="pip install pyyaml",
        )

    content = yaml.dump(
        data,
        default_flow_style=default_flow_style,
        sort_keys=sort_keys,
        allow_unicode=allow_unicode,
        indent=2,
    )

    # ---- Step 3: Write file ----
    if os.path.isabs(output_path):
        out_dir = output_path
    else:
        out_dir = os.path.join(ctx.run_dir, output_path)
    os.makedirs(out_dir, exist_ok=True)

    if not (filename.endswith(".yaml") or filename.endswith(".yml")):
        filename += ".yaml"

    # Apply timestamp to filename
    if timestamp_filename:
        from datetime import datetime
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        base, fext = os.path.splitext(filename)
        filename = f"{base}_{ts}{fext}"

    # Loop versioned: create iteration-specific filename
    if file_mode == "versioned":
        base, fext = os.path.splitext(filename)
        filename = f"{base}_iter{iteration}{fext}"

    out_filepath = os.path.join(out_dir, filename)

    if file_mode != "append" and os.path.exists(out_filepath) and not overwrite:
        raise BlockInputError(
            f"File already exists: {out_filepath}. Enable 'Overwrite Existing'.",
            recoverable=True,
        )

    # Loop append: append YAML documents separated by ---
    if file_mode == "append" and os.path.isfile(out_filepath):
        # Ensure file ends with a newline before appending separator
        with open(out_filepath, "rb") as f:
            f.seek(0, 2)
            needs_newline = False
            if f.tell() > 0:
                f.seek(-1, 2)
                needs_newline = f.read(1) != b"\n"
        with open(out_filepath, "a", encoding="utf-8") as f:
            if needs_newline:
                f.write("\n")
            f.write("---\n")
            f.write(content)
    else:
        with open(out_filepath, "w", encoding="utf-8") as f:
            if header_comment:
                for line in header_comment.splitlines():
                    f.write(f"# {line}\n")
                f.write("\n")
            f.write(content)

    ctx.report_progress(3, 3)
    file_size = os.path.getsize(out_filepath)
    ctx.log_message(f"Saved YAML to {out_filepath} ({file_size:,} bytes)")

    ctx.save_output("file_path", out_filepath)
    ctx.save_output("summary", {"file_size_bytes": file_size})
    ctx.save_artifact("yaml_output", out_filepath)
    ctx.log_metric("file_size_bytes", float(file_size))

    ctx.log_message("Save YAML complete.")
