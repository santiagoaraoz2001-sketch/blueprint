"""Save Model — save model weights or checkpoint to disk."""

import json
import os
import shutil

from backend.block_sdk.exceptions import BlockInputError


def run(ctx):
    output_path = ctx.config.get("output_path", "./output").strip()
    filename = ctx.config.get("filename", "model").strip()
    fmt = ctx.config.get("format", "safetensors").lower().strip()
    quantize = ctx.config.get("quantize", "none").lower().strip()
    save_config = ctx.config.get("save_config", True)
    save_tokenizer = ctx.config.get("save_tokenizer", True)
    overwrite = ctx.config.get("overwrite_existing", True)

    ctx.log_message(f"Save Model starting (format={fmt})")
    ctx.report_progress(0, 4)

    # ---- Step 1: Load model data ----
    ctx.report_progress(1, 4)
    model_info = ctx.resolve_model_info("model")
    if not model_info:
        raise BlockInputError(
            "No model data provided. Connect a 'model' input.",
            recoverable=False,
        )

    # Determine model type from resolve_model_info output
    # resolve_model_info returns dict with: model_name, model_id, source, backend, and optionally path
    model_path = model_info.get("path", model_info.get("model_id", ""))
    has_local_path = isinstance(model_path, str) and os.path.exists(model_path)
    ctx.log_message(f"Model input: {model_info.get('model_name', 'unknown')} (source={model_info.get('source', 'unknown')})")

    # ---- Step 2: Resolve output directory ----
    ctx.report_progress(2, 4)
    if os.path.isabs(output_path):
        out_dir = os.path.join(output_path, filename)
    else:
        out_dir = os.path.join(ctx.run_dir, output_path, filename)

    if os.path.exists(out_dir) and not overwrite:
        raise BlockInputError(
            f"Model directory already exists: {out_dir}. Enable 'Overwrite Existing'.",
            recoverable=True,
        )

    os.makedirs(out_dir, exist_ok=True)

    # ---- Step 3: Save model ----
    ctx.report_progress(3, 4)
    saved_files = []

    if has_local_path:
        src_path = model_path

        if os.path.isdir(src_path):
            # Copy model directory contents
            for item in os.listdir(src_path):
                src_item = os.path.join(src_path, item)
                dst_item = os.path.join(out_dir, item)

                # Filter based on config
                if not save_config and item == "config.json":
                    continue
                if not save_tokenizer and item.startswith("tokenizer"):
                    continue

                if os.path.isfile(src_item):
                    shutil.copy2(src_item, dst_item)
                    saved_files.append(item)
                elif os.path.isdir(src_item):
                    if os.path.exists(dst_item):
                        shutil.rmtree(dst_item)
                    shutil.copytree(src_item, dst_item)
                    saved_files.append(item + "/")

            ctx.log_message(f"Copied {len(saved_files)} items from {src_path}")

        elif os.path.isfile(src_path):
            # Single file — copy it
            dst = os.path.join(out_dir, os.path.basename(src_path))
            shutil.copy2(src_path, dst)
            saved_files.append(os.path.basename(src_path))
            ctx.log_message(f"Copied model file: {os.path.basename(src_path)}")

    else:
        # Save model metadata/config as JSON
        meta_path = os.path.join(out_dir, "model_info.json")
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(model_info, f, indent=2, default=str)
        saved_files.append("model_info.json")
        ctx.log_message("Saved model metadata as JSON")

        # If there's a nested path reference, try to copy
        for key in ["model_path", "path", "checkpoint_path", "weights_path"]:
            nested_path = model_info.get(key, "")
            if isinstance(nested_path, str) and os.path.exists(nested_path):
                if os.path.isdir(nested_path):
                    for item in os.listdir(nested_path):
                        src_item = os.path.join(nested_path, item)
                        if os.path.isfile(src_item):
                            shutil.copy2(src_item, os.path.join(out_dir, item))
                            saved_files.append(item)
                elif os.path.isfile(nested_path):
                    dst = os.path.join(out_dir, os.path.basename(nested_path))
                    shutil.copy2(nested_path, dst)
                    saved_files.append(os.path.basename(nested_path))
                ctx.log_message(f"Also copied files from {key}: {nested_path}")
                break

    # Save format metadata
    format_meta = {
        "format": fmt,
        "quantize": quantize,
        "saved_files": saved_files,
        "save_config": save_config,
        "save_tokenizer": save_tokenizer,
    }
    if model_info.get("metadata"):
        format_meta["model_metadata"] = model_info["metadata"]

    meta_path = os.path.join(out_dir, "save_info.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(format_meta, f, indent=2, default=str)

    # ---- Step 4: Finalize ----
    ctx.report_progress(4, 4)
    total_size = sum(
        os.path.getsize(os.path.join(dp, fn))
        for dp, _, fns in os.walk(out_dir, followlinks=False)
        for fn in fns
    )
    ctx.log_message(f"Model saved to {out_dir} ({total_size:,} bytes, {len(saved_files)} files)")

    ctx.save_output("file_path", out_dir)
    ctx.save_output("summary", {
        "total_size_bytes": total_size,
        "files_saved": len(saved_files),
        "format": fmt,
        "quantize": quantize,
    })
    # Save artifact for the metadata file so it appears in the artifact registry
    save_info_path = os.path.join(out_dir, "save_info.json")
    if os.path.isfile(save_info_path):
        ctx.save_artifact("model_save_info", save_info_path)
    ctx.log_metric("file_size_bytes", float(total_size))
    ctx.log_metric("files_saved", float(len(saved_files)))

    ctx.log_message("Save Model complete.")
