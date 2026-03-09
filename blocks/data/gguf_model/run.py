"""GGUF Model — load a GGUF model using llama-cpp-python."""

import json
import os


def run(ctx):
    model_path = ctx.config.get("model_path", "")
    n_ctx = int(ctx.config.get("n_ctx", 2048))
    n_gpu_layers = int(ctx.config.get("n_gpu_layers", 0))

    if not model_path:
        ctx.log_message("No model_path configured. Using placeholder reference.")
        model_path = "model.gguf"

    ctx.log_message(f"Loading GGUF model: {model_path}")
    ctx.log_message(f"Context length: {n_ctx}, GPU layers: {n_gpu_layers}")

    try:
        from llama_cpp import Llama
        ctx.log_message("llama-cpp-python found. Loading model...")

        if not os.path.isfile(model_path):
            raise FileNotFoundError(f"GGUF file not found: {model_path}")

        llm = Llama(model_path=model_path, n_ctx=n_ctx, n_gpu_layers=n_gpu_layers, verbose=False)
        metadata = llm.metadata if hasattr(llm, 'metadata') else {}
        n_params = metadata.get("general.parameter_count", 0)

        ctx.log_message(f"Model loaded successfully.")

        model_ref = {
            "source": "gguf",
            "model_path": model_path,
            "loaded": True,
            "n_ctx": n_ctx,
            "n_gpu_layers": n_gpu_layers,
            "parameters": n_params,
            "framework": "llama-cpp-python",
        }
        ctx.log_metric("n_ctx", n_ctx)

    except ImportError:
        ctx.log_message("⚠ DEMO MODE: 'llama-cpp-python' not installed. Install: pip install llama-cpp-python")
        ctx.log_message("Returning mock model reference.")
        model_ref = {
            "source": "gguf",
            "model_path": model_path,
            "loaded": False,
            "demo_mode": True,
            "n_ctx": n_ctx,
            "n_gpu_layers": n_gpu_layers,
            "framework": "llama-cpp-python",
            "install_hint": "pip install llama-cpp-python",
        }
    except Exception as e:
        ctx.log_message(f"Error loading GGUF model: {e}")
        model_ref = {
            "source": "gguf",
            "model_path": model_path,
            "loaded": False,
            "error": str(e),
            "framework": "llama-cpp-python",
        }

    ctx.save_output("model", model_ref)
    ctx.report_progress(1, 1)
