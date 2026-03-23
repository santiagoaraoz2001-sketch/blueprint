"""Quantize Model — apply quantization to reduce model size and improve inference speed.

Workflows:
  1. Model compression: large model -> quantize -> smaller deployable model
  2. Edge deployment: full model -> 4-bit quantize -> mobile/edge device
  3. Cost reduction: cloud model -> quantize -> cheaper inference
  4. Speed optimization: model -> quantize -> faster throughput
  5. Quality evaluation: model -> quantize -> benchmark accuracy loss
"""

import json
import os
import time

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
    method = ctx.config.get("method", "gptq")
    bits = int(ctx.config.get("bits", 4))
    model_name = ctx.config.get("model_name", "")
    group_size = int(ctx.config.get("group_size", 128))
    dataset_name = ctx.config.get("calibration_dataset", "c4")
    compute_dtype = ctx.config.get("compute_dtype", "float16")

    # Try to get model from input
    if ctx.inputs.get("model"):
        try:
            model_info = ctx.load_input("model")
            if isinstance(model_info, dict):
                model_name = model_name or model_info.get("model_name", model_info.get("model_id", ""))
            elif isinstance(model_info, str):
                model_name = model_name or model_info
        except Exception:
            pass

    if not model_name:
        raise BlockConfigError("model_name", "model_name is required — provide via config or model input port")

    # Validate bits vs method compatibility
    if method == "bitsandbytes" and bits not in (4, 8):
        ctx.log_message(
            f"WARNING: BitsAndBytes only supports 4-bit and 8-bit quantization. "
            f"Requested {bits}-bit will be clamped to 4-bit."
        )
        bits = 4

    # Warn on extreme quantization settings
    if bits <= 2:
        ctx.log_message(
            "WARNING: 2-bit quantization causes significant quality degradation. "
            "Expect noticeable accuracy loss — only use for size-constrained deployments. "
            "Consider 4-bit as the best quality/size tradeoff."
        )
    elif bits == 3:
        ctx.log_message(
            "NOTE: 3-bit quantization is experimental and may produce inconsistent results. "
            "4-bit is recommended for most use cases."
        )

    ctx.log_message(f"Quantizing model: {model_name}")
    ctx.log_message(f"Method: {method}, Bits: {bits}, Group size: {group_size}")
    ctx.report_progress(1, 4)

    start_time = time.time()

    # ── GPTQ quantization ────────────────────────────────────────
    if method == "gptq":
        try:
            from auto_gptq import AutoGPTQForCausalLM, BaseQuantizeConfig
            from transformers import AutoTokenizer

            ctx.log_message("Loading model for GPTQ quantization...")
            ctx.log_message(f"Calibration dataset: {dataset_name}")
            ctx.report_progress(2, 4)

            tokenizer = AutoTokenizer.from_pretrained(model_name)
            quantize_config = BaseQuantizeConfig(bits=bits, group_size=group_size)
            model = AutoGPTQForCausalLM.from_pretrained(model_name, quantize_config)

            ctx.log_message("Running quantization (this may take a while)...")
            ctx.report_progress(3, 4)

            # Load calibration data
            calib_examples = None
            try:
                from datasets import load_dataset
                calib_ds = load_dataset(dataset_name, split="train[:128]")
                calib_examples = [tokenizer(row["text"], return_tensors="pt", truncation=True, max_length=512) for row in calib_ds if "text" in row]
                ctx.log_message(f"Loaded {len(calib_examples)} calibration examples from '{dataset_name}'")
            except Exception as e:
                ctx.log_message(f"Could not load calibration dataset '{dataset_name}': {e}")

            if calib_examples:
                model.quantize(tokenizer, examples=calib_examples)
            else:
                model.quantize(tokenizer)

            out_path = os.path.join(ctx.run_dir, "quantized_model")
            model.save_quantized(out_path)
            tokenizer.save_pretrained(out_path)

            elapsed = time.time() - start_time
            # Branch: GPTQ quantization succeeded
            ctx.save_output("quantized_model", {
                "source": "gptq", "path": out_path,
                "model_name": model_name, "bits": bits,
            })
            # Branch: GPTQ quantization succeeded
            ctx.save_output("metrics", {
                "method": "gptq", "bits": bits, "group_size": group_size,
                "calibration_dataset": dataset_name, "elapsed_s": round(elapsed, 2),
            })
            ctx.log_metric("elapsed_s", round(elapsed, 2))
            ctx.log_message(f"GPTQ quantization complete in {elapsed:.1f}s")
            ctx.report_progress(4, 4)
            return

        except ImportError as e:
            from backend.block_sdk.exceptions import BlockDependencyError
            missing = str(e).split("'")[-2] if "'" in str(e) else str(e)
            raise BlockDependencyError(
                missing,
                f"Required library not installed: {e}",
                install_hint="pip install auto-gptq transformers",
            )

    # ── BitsAndBytes quantization ────────────────────────────────
    elif method == "bitsandbytes":
        try:
            from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

            ctx.log_message("Loading model with bitsandbytes quantization...")
            ctx.report_progress(2, 4)

            import torch
            dtype_map = {"float16": torch.float16, "bfloat16": torch.bfloat16, "float32": torch.float32}
            torch_dtype = dtype_map.get(compute_dtype, torch.float16)
            bnb_config = BitsAndBytesConfig(
                load_in_4bit=(bits == 4),
                load_in_8bit=(bits == 8),
                bnb_4bit_compute_dtype=torch_dtype,
            )
            model = AutoModelForCausalLM.from_pretrained(
                model_name, quantization_config=bnb_config
            )
            ctx.report_progress(3, 4)

            out_path = os.path.join(ctx.run_dir, "quantized_model")
            model.save_pretrained(out_path)

            try:
                tokenizer = AutoTokenizer.from_pretrained(model_name)
                tokenizer.save_pretrained(out_path)
            except Exception:
                pass

            elapsed = time.time() - start_time
            # Branch: BitsAndBytes quantization succeeded
            ctx.save_output("quantized_model", {
                "source": "bitsandbytes", "path": out_path,
                "model_name": model_name, "bits": bits,
            })
            # Branch: BitsAndBytes quantization succeeded
            ctx.save_output("metrics", {
                "method": "bitsandbytes", "bits": bits,
                "elapsed_s": round(elapsed, 2),
            })
            ctx.log_metric("elapsed_s", round(elapsed, 2))
            ctx.log_message(f"BitsAndBytes quantization complete in {elapsed:.1f}s")
            ctx.report_progress(4, 4)
            return

        except ImportError as e:
            from backend.block_sdk.exceptions import BlockDependencyError
            missing = str(e).split("'")[-2] if "'" in str(e) else str(e)
            raise BlockDependencyError(
                missing,
                f"Required library not installed: {e}",
                install_hint="pip install bitsandbytes torch transformers",
            )

    # ── AWQ quantization ─────────────────────────────────────────
    elif method == "awq":
        try:
            from awq import AutoAWQForCausalLM
            from transformers import AutoTokenizer

            ctx.log_message("Loading model for AWQ quantization...")
            ctx.report_progress(2, 4)

            model = AutoAWQForCausalLM.from_pretrained(model_name)
            tokenizer = AutoTokenizer.from_pretrained(model_name)

            quant_config = {"zero_point": True, "q_group_size": group_size, "w_bit": bits}
            ctx.log_message("Running AWQ quantization...")
            ctx.report_progress(3, 4)
            model.quantize(tokenizer, quant_config=quant_config)

            out_path = os.path.join(ctx.run_dir, "quantized_model")
            model.save_quantized(out_path)
            tokenizer.save_pretrained(out_path)

            elapsed = time.time() - start_time
            # Branch: AWQ quantization succeeded
            ctx.save_output("quantized_model", {
                "source": "awq", "path": out_path,
                "model_name": model_name, "bits": bits,
            })
            # Branch: AWQ quantization succeeded
            ctx.save_output("metrics", {
                "method": "awq", "bits": bits, "group_size": group_size,
                "elapsed_s": round(elapsed, 2),
            })
            ctx.log_metric("elapsed_s", round(elapsed, 2))
            ctx.log_message(f"AWQ quantization complete in {elapsed:.1f}s")
            ctx.report_progress(4, 4)
            return

        except ImportError as e:
            from backend.block_sdk.exceptions import BlockDependencyError
            missing = str(e).split("'")[-2] if "'" in str(e) else str(e)
            raise BlockDependencyError(
                missing,
                f"Required library not installed: {e}",
                install_hint="pip install autoawq transformers",
            )

    else:
        ctx.log_message(f"Method '{method}' — running in estimation mode.")

    # ── Estimation mode (no quantization library available) ──────
    ctx.report_progress(2, 4)
    ctx.log_message("Running size estimation (no quantization library available)...")

    # Estimate model sizes based on typical parameter counts
    param_estimates = {
        "7b": 7e9, "13b": 13e9, "70b": 70e9,
        "1b": 1e9, "3b": 3e9, "8b": 8e9,
    }
    param_count = 7e9
    model_lower = model_name.lower()
    for key, count in param_estimates.items():
        if key in model_lower:
            param_count = count
            break

    original_size_gb = (param_count * 2) / (1024**3)  # FP16
    quantized_size_gb = (param_count * bits / 8) / (1024**3)
    compression_ratio = original_size_gb / max(quantized_size_gb, 0.01)

    ctx.report_progress(3, 4)

    out_path = os.path.join(ctx.run_dir, "quantized_model")
    os.makedirs(out_path, exist_ok=True)
    with open(os.path.join(out_path, "config.json"), "w") as f:
        json.dump({
            "base_model": model_name,
            "quantization_method": method,
            "bits": bits,
            "group_size": group_size,
            "estimation_only": True,
        }, f, indent=2)

    elapsed = time.time() - start_time
    # Branch: estimation fallback — no real quantization
    ctx.save_output("quantized_model", {
        "source": method,
        "path": out_path,
        "model_name": model_name,
        "bits": bits,
        "estimation_only": True,
    })
    # Branch: estimation fallback — no real quantization
    ctx.save_output("metrics", {
        "method": method,
        "bits": bits,
        "group_size": group_size,
        "estimated_params": param_count,
        "original_size_gb": round(original_size_gb, 2),
        "quantized_size_gb": round(quantized_size_gb, 2),
        "compression_ratio": round(compression_ratio, 2),
        "elapsed_s": round(elapsed, 2),
        "estimation_only": True,
    })
    ctx.log_metric("compression_ratio", round(compression_ratio, 2))
    ctx.log_metric("elapsed_s", round(elapsed, 2))
    ctx.log_message(
        f"Estimated: {original_size_gb:.1f}GB -> {quantized_size_gb:.1f}GB "
        f"({compression_ratio:.1f}x compression at {bits}-bit)"
    )
    ctx.log_message("Install a quantization library for real quantization:")
    ctx.log_message("  GPTQ: pip install auto-gptq")
    ctx.log_message("  BitsAndBytes: pip install bitsandbytes")
    ctx.log_message("  AWQ: pip install autoawq")
    ctx.report_progress(4, 4)
