"""Shared validation for training blocks — validates model identifiers before training."""

import os


def _validate_model_for_training(model_name, model_info, ctx, field_name="model_name"):
    """Validate and potentially resolve a model identifier for training.

    Args:
        model_name: The model identifier to validate
        model_info: The full model info dict from the model input port
        ctx: Block context for logging
        field_name: Config field name for error reporting (e.g. "teacher_model",
            "reward_model"). Defaults to "model_name".

    Returns:
        Validated/resolved model name suitable for from_pretrained()

    Raises:
        BlockConfigError: If model cannot be used for training
    """
    try:
        from backend.block_sdk.exceptions import BlockConfigError
    except ImportError:
        class BlockConfigError(ValueError):
            def __init__(self, field, message, **kw): super().__init__(message)

    if not model_name:
        return model_name

    source = ""
    if isinstance(model_info, dict):
        source = model_info.get("source", model_info.get("backend", ""))

    # Check 1: Ollama model tag (no slash, looks like a tag)
    if source == "ollama" or (
        "/" not in model_name and not os.path.exists(model_name)
    ):
        try:
            from blocks.inference._model_resolver import resolve_for_training
            resolved_id, framework, warnings = resolve_for_training(
                model_name, source or "auto"
            )
            for w in warnings:
                ctx.log_message(f"\u26a0\ufe0f {w}")
            if resolved_id and resolved_id != model_name:
                ctx.log_message(
                    f"Resolved '{model_name}' \u2192 '{resolved_id}' for training"
                )
                return resolved_id
            elif not resolved_id:
                raise BlockConfigError(
                    field_name,
                    f"Cannot use Ollama model '{model_name}' for training. "
                    f"Training requires a HuggingFace model ID "
                    f"(e.g., 'meta-llama/Llama-3.2-1B') or a local model path."
                    f"\n\nOptions:\n"
                    f"  1. Set {field_name} in config to a HuggingFace ID\n"
                    f"  2. Connect a HuggingFace model loader instead of "
                    f"model_selector\n"
                    f"  3. Download the model locally and provide the path",
                )
        except ImportError:
            # _model_resolver not available — use heuristic
            if source == "ollama":
                raise BlockConfigError(
                    field_name,
                    f"Ollama model '{model_name}' cannot be used directly for "
                    f"training. Training requires a HuggingFace model ID "
                    f"(e.g., 'meta-llama/Llama-3.2-1B') or a local model path. "
                    f"Set {field_name} in the block config.",
                )
        except BlockConfigError:
            raise
        except Exception as exc:
            # _model_resolver exists but failed at runtime — log and continue
            # with heuristic checks rather than crashing the block
            ctx.log_message(
                f"Model resolver failed for '{model_name}': {exc}"
            )
            if source == "ollama":
                raise BlockConfigError(
                    field_name,
                    f"Ollama model '{model_name}' cannot be used directly for "
                    f"training. Training requires a HuggingFace model ID "
                    f"(e.g., 'meta-llama/Llama-3.2-1B') or a local model path. "
                    f"Set {field_name} in the block config.",
                )

    # Check 2: GGUF file (quantized — can't train)
    name_lower = model_name.lower()
    if name_lower.endswith(".gguf") or "-gguf" in name_lower or "/gguf" in name_lower:
        raise BlockConfigError(
            field_name,
            f"GGUF model '{model_name}' is quantized and cannot be used for "
            f"training. Use the original full-precision model from HuggingFace "
            f"instead.",
        )

    # Check 3: MLX model — may need different handling
    if "mlx-community" in name_lower or source == "mlx":
        ctx.log_message(
            f"MLX model detected: '{model_name}'. "
            f"This block uses PyTorch for training. "
            f"The model will be loaded via HuggingFace."
        )
        # MLX community models ARE HuggingFace repos, so from_pretrained()
        # usually works. But quantized MLX models may not load correctly.
        if "-4bit" in name_lower or "-8bit" in name_lower:
            ctx.log_message(
                "\u26a0\ufe0f Quantized MLX model detected. PyTorch may not load "
                "quantized weights. Consider using the non-quantized "
                "HuggingFace variant."
            )

    return model_name
