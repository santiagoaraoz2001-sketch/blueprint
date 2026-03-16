"""Shared validation utilities for merge blocks.

Validates that model identifiers are compatible with mergekit before
attempting a merge. mergekit requires HuggingFace model IDs (org/name)
or local paths containing safetensors/bin model weights.
"""

import os

try:
    from backend.block_sdk.exceptions import BlockConfigError
except ImportError:
    class BlockConfigError(ValueError):
        def __init__(self, field, message, **kw):
            super().__init__(message)


def _validate_model_for_merge(model_name: str, model_info: dict, ctx, port_label: str = "model") -> str:
    """Validate and resolve a model identifier for merging with mergekit.

    mergekit requires HuggingFace model IDs (org/name) or local paths
    containing safetensors/bin model weights.  Ollama tags, MLX model IDs,
    and GGUF files are incompatible and must be caught early.

    Returns the (possibly resolved) model name, or raises BlockConfigError.
    """
    if not model_name or not isinstance(model_name, str):
        return model_name

    source = ""
    if isinstance(model_info, dict):
        source = model_info.get("source", model_info.get("backend", ""))

    # Try resolver first (forward-compatible with _model_resolver)
    try:
        from blocks.inference._model_resolver import resolve_for_merge
        resolved_id, warnings = resolve_for_merge(model_name, source or "auto")
        for w in warnings:
            ctx.log_message(f"\u26a0\ufe0f {w}")
        if resolved_id:
            return resolved_id
    except ImportError:
        pass

    # ── Ollama models ──
    # Detected by source metadata or by Ollama-style tag pattern (name:tag).
    # Ollama tags look like "llama3.2", "mistral:7b", "codellama:13b-instruct".
    # HuggingFace IDs always contain "/" (org/model), local paths would exist
    # on disk, so the "/" and os.path.exists checks avoid false positives.
    _has_slash = "/" in model_name
    _is_local = os.path.exists(model_name)
    _looks_like_ollama_tag = (
        not _has_slash
        and not _is_local
        and ":" in model_name
        and not model_name.endswith(".gguf")
    )

    if (source == "ollama" or _looks_like_ollama_tag) and not _has_slash and not _is_local:
        raise BlockConfigError(
            port_label,
            f"Ollama model '{model_name}' cannot be used directly for merging. "
            f"mergekit requires HuggingFace model IDs (e.g., 'meta-llama/Llama-3.2-1B') "
            f"or local paths to model directories with safetensors weights.\n\n"
            f"Provide the equivalent HuggingFace model ID in the block configuration.",
        )

    # ── MLX models ──
    # MLX-format models (typically from mlx-community/*) may lack the
    # safetensors/bin weights that mergekit needs.  Warn but don't block,
    # because some MLX repos do ship safetensors alongside the MLX weights.
    if source == "mlx":
        ctx.log_message(
            f"\u26a0\ufe0f {port_label}: MLX model '{model_name}' may not be compatible "
            f"with mergekit. mergekit requires models with safetensors weights. "
            f"If the merge fails, provide a standard HuggingFace model ID instead."
        )

    # ── GGUF files ──
    # GGUF is a single-file quantised format; mergekit cannot merge them.
    if model_name.endswith(".gguf") or "GGUF" in model_name.upper():
        raise BlockConfigError(
            port_label,
            f"GGUF model '{model_name}' cannot be merged. "
            f"mergekit requires full-precision HuggingFace models with "
            f"safetensors weights, not quantised GGUF files.",
        )

    return model_name


def _load_model_info(ctx, *input_ids):
    """Load raw model info dict from the first available input port.

    Returns the upstream output dictionary (which may contain ``source``,
    ``backend``, ``path``, etc.) or an empty dict when no matching port
    is connected.
    """
    for input_id in input_ids:
        if input_id is None:
            continue
        try:
            info = ctx.load_input(input_id)
            if isinstance(info, dict):
                return info
        except (ValueError, Exception):
            pass
    return {}
