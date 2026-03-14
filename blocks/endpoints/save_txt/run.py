"""Save Text — save pipeline data as a plain text file."""

import os

from backend.block_sdk.exceptions import BlockInputError


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
    out_filepath = os.path.join(out_dir, filename)

    if not append_mode and os.path.exists(out_filepath) and not overwrite:
        raise BlockInputError(
            f"File already exists: {out_filepath}. Enable 'Overwrite Existing'.",
            recoverable=True,
        )

    # ---- Step 3: Write file ----
    mode = "a" if append_mode else "w"
    newline_char = "" if line_ending.upper() == "CRLF" else None
    with open(out_filepath, mode, encoding=encoding, newline=newline_char) as f:
        if append_mode:
            f.write("\n")
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
