"""Artifact Viewer — inspect and generate a manifest for an artifact."""

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
    display_mode = ctx.config.get("display_mode", "preview")
    auto_open = ctx.config.get("auto_open", True)

    ctx.report_progress(0, 1)

    artifact_data = ctx.load_input("artifact")
    if artifact_data is None:
        raise BlockInputError("No artifact input received", recoverable=False)

    # Determine artifact type and info
    artifact_info = {
        "type": "unknown",
        "size": 0,
        "preview": "",
        "display_mode": display_mode,
        "auto_open": auto_open,
    }

    if isinstance(artifact_data, str):
        if os.path.isfile(artifact_data):
            file_size = os.path.getsize(artifact_data)
            ext = os.path.splitext(artifact_data)[1].lower()
            artifact_info["type"] = ext.lstrip(".") or "file"
            artifact_info["size"] = file_size
            artifact_info["path"] = artifact_data
            artifact_info["filename"] = os.path.basename(artifact_data)

            # Generate preview for text-based files
            text_exts = {".txt", ".json", ".csv", ".yaml", ".yml", ".md", ".py", ".log", ".xml", ".html"}
            if ext in text_exts and file_size < 100_000:
                with open(artifact_data, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read(2000)
                artifact_info["preview"] = content
                ctx.log_message(f"Text artifact: {os.path.basename(artifact_data)} ({file_size:,} bytes)")
            else:
                artifact_info["preview"] = f"[Binary file: {file_size:,} bytes]"
                ctx.log_message(f"Binary artifact: {os.path.basename(artifact_data)} ({file_size:,} bytes)")
        else:
            # Raw string content
            artifact_info["type"] = "text"
            artifact_info["size"] = len(artifact_data)
            artifact_info["preview"] = artifact_data[:2000]
            ctx.log_message(f"Text artifact: {len(artifact_data)} chars")
    elif isinstance(artifact_data, dict):
        content = json.dumps(artifact_data, indent=2, default=str)
        artifact_info["type"] = "json"
        artifact_info["size"] = len(content)
        artifact_info["preview"] = content[:2000]
        ctx.log_message(f"JSON artifact: {len(artifact_data)} keys")
    elif isinstance(artifact_data, list):
        content = json.dumps(artifact_data, indent=2, default=str)
        artifact_info["type"] = "json_array"
        artifact_info["size"] = len(content)
        artifact_info["preview"] = content[:2000]
        ctx.log_message(f"Array artifact: {len(artifact_data)} items")
    else:
        artifact_info["type"] = type(artifact_data).__name__
        artifact_info["preview"] = str(artifact_data)[:2000]

    out_path = os.path.join(ctx.run_dir, "artifact_manifest.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(artifact_info, f, indent=2, default=str)

    ctx.save_output("summary", out_path)
    ctx.log_metric("artifact_count", 1)
    ctx.log_metric("total_size_bytes", artifact_info["size"])
    ctx.log_message(f"Artifact manifest created: {artifact_info['type']} ({artifact_info['size']:,} bytes)")
    ctx.report_progress(1, 1)
