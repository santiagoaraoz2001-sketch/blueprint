"""Ollama Model — validate Ollama connection and return model reference."""

import json


def run(ctx):
    model_name = ctx.config.get("model_name", "llama3.2")
    endpoint = ctx.config.get("endpoint", "http://localhost:11434")

    ctx.log_message(f"Connecting to Ollama at {endpoint}")
    ctx.log_message(f"Requested model: {model_name}")

    available_models = []
    ollama_connected = False

    try:
        import urllib.request
        url = f"{endpoint.rstrip('/')}/api/tags"
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            models_list = data.get("models", [])
            available_models = [m.get("name", "") for m in models_list]
            ollama_connected = True
            ctx.log_message(f"Ollama connected. {len(available_models)} models available.")
    except Exception as e:
        ctx.log_message(f"Could not connect to Ollama at {endpoint}: {e}")
        ctx.log_message("Returning model reference anyway (Ollama may be started later).")

    # Check if requested model is available
    if ollama_connected and available_models:
        matched = [m for m in available_models if model_name in m]
        if matched:
            ctx.log_message(f"Model '{model_name}' found: {matched[0]}")
        else:
            ctx.log_message(f"Model '{model_name}' not found. Available: {', '.join(available_models[:10])}")
            ctx.log_message(f"You can pull it with: ollama pull {model_name}")

    model_ref = {
        "source": "ollama",
        "model_name": model_name,
        "endpoint": endpoint,
        "connected": ollama_connected,
        "available_models": available_models[:20],
    }

    ctx.save_output("model", model_ref)
    ctx.log_metric("ollama_connected", 1 if ollama_connected else 0)
    ctx.log_metric("available_models_count", len(available_models))
    ctx.report_progress(1, 1)
