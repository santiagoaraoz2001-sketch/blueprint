"""MLX Model — load a model using Apple MLX framework."""

import json
import os


def run(ctx):
    model_name = ctx.config.get("model_name", "mlx-community/Llama-3.2-1B-Instruct-4bit")
    ctx.log_message(f"Loading MLX model: {model_name}")

    try:
        from mlx_lm import load
        ctx.log_message("mlx-lm found. Loading model and tokenizer...")
        model, tokenizer = load(model_name)

        # Get model info
        param_count = sum(p.size for p in model.parameters()) if hasattr(model, 'parameters') else 0
        ctx.log_message(f"Model loaded successfully. Parameters: {param_count:,}")

        model_ref = {
            "source": "mlx",
            "model_name": model_name,
            "loaded": True,
            "parameters": param_count,
            "framework": "mlx-lm",
        }
        ctx.log_metric("parameters", param_count)

    except ImportError:
        ctx.log_message("⚠ DEMO MODE: 'mlx-lm' not installed. Install: pip install mlx-lm")
        ctx.log_message("Returning mock model reference.")
        model_ref = {
            "source": "mlx",
            "model_name": model_name,
            "loaded": False,
            "demo_mode": True,
            "framework": "mlx-lm",
            "install_hint": "pip install mlx-lm",
        }
    except Exception as e:
        ctx.log_message(f"Error loading model: {e}")
        model_ref = {
            "source": "mlx",
            "model_name": model_name,
            "loaded": False,
            "error": str(e),
            "framework": "mlx-lm",
        }

    ctx.save_output("model", model_ref)
    ctx.report_progress(1, 1)
