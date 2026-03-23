"""Discovers locally available ML frameworks and their downloaded models."""

import glob
import os
import time
from typing import Any

_cache: dict[str, Any] = {"result": None, "timestamp": 0.0}
_CACHE_TTL = 30.0  # seconds


def discover_frameworks() -> list[dict]:
    """Returns available frameworks with their status.

    Results are cached for 30 seconds to avoid repeated filesystem scanning.
    """
    now = time.time()
    if _cache["result"] is not None and (now - _cache["timestamp"]) < _CACHE_TTL:
        return _cache["result"]

    frameworks = []

    # ── Ollama ───────────────────────────────────────────────────────
    from ..utils.model_scanner import detect_ollama_models

    ollama_detected = detect_ollama_models()
    ollama_models = [m["name"] for m in ollama_detected]
    # Consider Ollama "available" if we found any models (even via CLI)
    frameworks.append({
        "id": "ollama",
        "name": "Ollama",
        "available": len(ollama_models) > 0,
        "models": ollama_models,
        "default_config": {
            "max_tokens": 2048,
            "temperature": 0.7,
            "supports_system_prompt": True,
            "supports_chat": True,
            "supports_streaming": True,
        },
    })

    # ── MLX (Apple Silicon) ─────────────────────────────────────────
    try:
        import mlx  # noqa: F401 — just check availability

        mlx_cache = os.path.expanduser("~/.cache/huggingface/hub")
        mlx_models = []
        if os.path.isdir(mlx_cache):
            for model_dir in glob.glob(f"{mlx_cache}/models--*"):
                name = model_dir.split("models--")[1].replace("--", "/")
                snapshots = glob.glob(f"{model_dir}/snapshots/*/weights.npz") + \
                            glob.glob(f"{model_dir}/snapshots/*/model*.safetensors")
                if snapshots:
                    mlx_models.append(name)
        frameworks.append({
            "id": "mlx",
            "name": "MLX (Apple Silicon)",
            "available": True,
            "models": mlx_models,
            "default_config": {
                "max_tokens": 100,
                "temperature": 0.0,
                "supports_system_prompt": False,
                "supports_chat": False,
                "supports_streaming": True,
            },
        })
    except ImportError:
        frameworks.append({
            "id": "mlx",
            "name": "MLX",
            "available": False,
            "models": [],
            "default_config": {
                "max_tokens": 100,
                "temperature": 0.0,
                "supports_system_prompt": False,
                "supports_chat": False,
                "supports_streaming": True,
            },
        })

    # ── PyTorch / Transformers ──────────────────────────────────────
    try:
        import torch

        hf_cache = os.path.expanduser("~/.cache/huggingface/hub")
        pt_models = []
        if os.path.isdir(hf_cache):
            for model_dir in glob.glob(f"{hf_cache}/models--*"):
                name = model_dir.split("models--")[1].replace("--", "/")
                snapshots = glob.glob(f"{model_dir}/snapshots/*/pytorch_model*.bin") + \
                            glob.glob(f"{model_dir}/snapshots/*/model*.safetensors")
                if snapshots:
                    pt_models.append(name)
        gpu_available = torch.cuda.is_available() or (
            hasattr(torch.backends, "mps") and torch.backends.mps.is_available()
        )
        frameworks.append({
            "id": "pytorch",
            "name": "PyTorch/Transformers",
            "available": True,
            "models": pt_models,
            "gpu": gpu_available,
            "default_config": {
                "max_tokens": 512,
                "temperature": 0.7,
                "supports_system_prompt": True,
                "supports_chat": True,
                "supports_streaming": True,
            },
        })
    except ImportError:
        frameworks.append({
            "id": "pytorch",
            "name": "PyTorch",
            "available": False,
            "models": [],
            "default_config": {
                "max_tokens": 512,
                "temperature": 0.7,
                "supports_system_prompt": True,
                "supports_chat": True,
                "supports_streaming": True,
            },
        })

    _cache["result"] = frameworks
    _cache["timestamp"] = now
    return frameworks


def invalidate_cache():
    """Force cache invalidation (e.g. after installing a new model)."""
    _cache["result"] = None
    _cache["timestamp"] = 0.0
