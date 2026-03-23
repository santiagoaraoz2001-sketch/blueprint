"""Text Concatenator — combine multiple text inputs into a single output."""

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


def _resolve_text(data):
    """Resolve a loaded input to text, handling file paths and raw strings."""
    if data is None:
        return ""
    if isinstance(data, str):
        if os.path.isfile(data):
            with open(data, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()
        return data
    return str(data)


def run(ctx):
    separator = ctx.config.get("separator", "\n\n")
    template = ctx.config.get("template", "{text_a}{separator}{text_b}")
    trim_whitespace = ctx.config.get("trim_whitespace", True)
    skip_empty = ctx.config.get("skip_empty", True)
    prefix = ctx.config.get("prefix", "")
    suffix = ctx.config.get("suffix", "")
    max_length = int(ctx.config.get("max_length", 0))

    ctx.report_progress(0, 1)

    text_a = _resolve_text(ctx.load_input("text_a"))
    text_b = _resolve_text(ctx.load_input("text_b"))
    try:
        text_c = _resolve_text(ctx.load_input("text_c"))
    except ValueError:
        text_c = ""

    if trim_whitespace:
        text_a = text_a.strip()
        text_b = text_b.strip()
        text_c = text_c.strip()

    ctx.log_message(f"Text A: {len(text_a)} chars | Text B: {len(text_b)} chars | Text C: {len(text_c)} chars")

    # Auto-expand template if text_c is connected and template doesn't reference it
    if text_c and "{text_c}" not in template:
        template = template + "{separator}{text_c}"
        ctx.log_message("Auto-appended {text_c} to template since Text C is connected")

    # Handle skip_empty: remove placeholders for empty inputs
    if skip_empty:
        if not text_a:
            template = template.replace("{text_a}{separator}", "").replace("{separator}{text_a}", "").replace("{text_a}", "")
        if not text_b:
            template = template.replace("{text_b}{separator}", "").replace("{separator}{text_b}", "").replace("{text_b}", "")
        if not text_c:
            template = template.replace("{text_c}{separator}", "").replace("{separator}{text_c}", "").replace("{text_c}", "")

    # Apply template
    result = template
    result = result.replace("{text_a}", text_a)
    result = result.replace("{text_b}", text_b)
    result = result.replace("{text_c}", text_c)
    result = result.replace("{separator}", separator)

    if trim_whitespace:
        result = result.strip()

    # Apply prefix/suffix (prompt assembly workflow)
    if prefix:
        result = prefix + result
    if suffix:
        result = result + suffix

    # Truncate to max_length if set (prompt size guard)
    if max_length > 0 and len(result) > max_length:
        ctx.log_message(f"Truncating output from {len(result)} to {max_length} chars")
        result = result[:max_length]

    out_path = os.path.join(ctx.run_dir, "concatenated.txt")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(result)

    input_count = sum(1 for t in (text_a, text_b, text_c) if t)
    ctx.log_metric("input_count", input_count)
    ctx.log_metric("output_length", len(result))
    ctx.log_metric("char_count", len(text_a) + len(text_b) + len(text_c))

    ctx.log_message(f"Combined output: {len(result)} chars")
    ctx.report_progress(1, 1)
    ctx.save_output("text", out_path)
