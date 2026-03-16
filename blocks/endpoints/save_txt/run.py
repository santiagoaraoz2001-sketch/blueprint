"""Save Text — save pipeline data as a plain text file."""

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
    filename = ctx.config.get("filename", "output.txt").strip()
    encoding = ctx.config.get("encoding", "utf-8")
    append_mode = ctx.config.get("append_mode", False)
    overwrite = ctx.config.get("overwrite_existing", True)
    separator = ctx.config.get("separator", "\\n")
    max_length = int(ctx.config.get("max_length", 0))
    line_ending = ctx.config.get("line_ending", "LF")
    prefix = ctx.config.get("prefix", "")
    suffix = ctx.config.get("suffix", "")
    trim_whitespace = ctx.config.get("trim_whitespace", False)

    # Unescape separator
    separator = separator.replace("\\n", "\n").replace("\\t", "\t")

    ctx.log_message("Save Text starting")
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

    # ---- Step 1: Load and convert data ----
    ctx.report_progress(1, 3)
    raw_data = ctx.resolve_as_text("text")
    if not raw_data:
        raise BlockInputError(
            "No input data provided. Connect a 'text' input.",
            recoverable=False,
        )

    content = raw_data
    original_length = len(content)

    # Trim whitespace from each line if requested
    if trim_whitespace:
        content = "\n".join(line.strip() for line in content.splitlines())

    if max_length > 0 and len(content) > max_length:
        content = content[:max_length]
        ctx.log_message(f"Truncated from {original_length:,} to {max_length:,} characters")

    # Apply prefix/suffix
    if prefix:
        content = prefix + "\n" + content
    if suffix:
        content = content + "\n" + suffix

    # Apply line ending
    if line_ending.upper() == "CRLF":
        content = content.replace("\r\n", "\n").replace("\n", "\r\n")

    ctx.log_message(f"Text content: {len(content):,} characters")

    # ---- Step 2: Resolve path ----
    ctx.report_progress(2, 3)
    if os.path.isabs(output_path):
        out_dir = output_path
    else:
        out_dir = os.path.join(ctx.run_dir, output_path)
    os.makedirs(out_dir, exist_ok=True)

    if not filename.endswith(".txt"):
        filename += ".txt"

    # Loop versioned: create iteration-specific filename
    if file_mode == "versioned":
        base = filename.rsplit(".", 1)[0]
        filename = f"{base}_iter{iteration}.txt"

    out_filepath = os.path.join(out_dir, filename)

    # Loop append overrides the block's own append_mode
    effective_append = append_mode or (file_mode == "append")

    if not effective_append and os.path.exists(out_filepath) and not overwrite:
        raise BlockInputError(
            f"File already exists: {out_filepath}. Enable 'Overwrite Existing'.",
            recoverable=True,
        )

    # ---- Step 3: Write file ----
    newline_char = "" if line_ending.upper() == "CRLF" else None

    if effective_append and os.path.isfile(out_filepath):
        # Check if existing file needs a trailing newline before we append
        needs_separator = False
        with open(out_filepath, "rb") as f:
            f.seek(0, 2)
            if f.tell() > 0:
                f.seek(-1, 2)
                needs_separator = f.read(1) != b"\n"
        with open(out_filepath, "a", encoding=encoding, newline=newline_char) as f:
            if needs_separator:
                f.write("\n")
            f.write(content)
    else:
        with open(out_filepath, "w", encoding=encoding, newline=newline_char) as f:
            f.write(content)

    ctx.report_progress(3, 3)
    file_size = os.path.getsize(out_filepath)
    ctx.log_message(f"Saved to {out_filepath} ({file_size:,} bytes)")

    ctx.save_output("file_path", out_filepath)
    ctx.save_output("summary", {
        "characters": len(content),
        "file_size_bytes": file_size,
        "append_mode": append_mode,
    })
    ctx.save_artifact("text_output", out_filepath)
    ctx.log_metric("characters_saved", float(len(content)))
    ctx.log_metric("file_size_bytes", float(file_size))

    ctx.log_message("Save Text complete.")
