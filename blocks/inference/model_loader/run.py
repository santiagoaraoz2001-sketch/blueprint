"""Model Loader — load and configure a model reference for downstream inference blocks.

Workflows:
  1. Local model setup: configure Ollama model -> connect to LLM inference
  2. Cloud model setup: set API key + model name -> downstream blocks
  3. Model validation: check model availability before pipeline runs
  4. Multi-model pipelines: multiple loaders -> different inference blocks
  5. Provider switching: change backend without editing downstream blocks
"""

import json
import os
import time


def run(ctx):
    model_name = ctx.config.get("model_name", "llama3.2")
    backend = ctx.config.get("backend", "ollama")
    base_url = ctx.config.get("base_url", "http://localhost:11434")
    api_key = ctx.config.get("api_key", "")
    validate = ctx.config.get("validate", True)

    ctx.log_message(f"Loading model: {model_name}")
    ctx.log_message(f"Backend: {backend}, URL: {base_url}")
    ctx.report_progress(1, 3)

    loaded = False
    error_msg = ""
    start_time = time.time()

    # Validate model reachability
    if validate:
        ctx.log_message("Validating model connection...")
        ctx.report_progress(2, 3)
        try:
            if backend == "ollama":
                import urllib.request
                url = f"{base_url.rstrip('/')}/api/tags"
                req = urllib.request.Request(url)
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = json.loads(resp.read().decode())
                    models = [m.get("name", "") for m in data.get("models", [])]
                    # Check if model name matches (with or without :latest tag)
                    found = any(
                        model_name in m or m.startswith(model_name.split(":")[0])
                        for m in models
                    )
                    if found:
                        loaded = True
                        ctx.log_message(f"Model '{model_name}' found in Ollama")
                    else:
                        loaded = True  # Server is reachable, model may be pulled on demand
                        ctx.log_message(
                            f"Model '{model_name}' not in local list, "
                            f"but Ollama is reachable (may pull on demand)"
                        )

            elif backend == "openai":
                import urllib.request
                url = f"{base_url.rstrip('/')}/v1/models"
                headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=10) as resp:
                    loaded = True
                    ctx.log_message("OpenAI API reachable")

            elif backend == "anthropic":
                # Anthropic doesn't have a models list endpoint, just validate key format
                if api_key:
                    loaded = True
                    ctx.log_message("Anthropic API key provided")
                else:
                    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
                    if api_key:
                        loaded = True
                        ctx.log_message("Anthropic API key found in environment")
                    else:
                        error_msg = "No Anthropic API key provided"
                        ctx.log_message(f"WARNING: {error_msg}")

            elif backend == "mlx":
                loaded = True
                ctx.log_message("MLX backend selected (validated at inference time)")

            else:
                loaded = True
                ctx.log_message(f"Backend '{backend}' — no validation available")

        except Exception as e:
            error_msg = str(e)
            ctx.log_message(f"Validation failed: {error_msg}")
    else:
        loaded = True
        ctx.log_message("Skipping validation (validate=false)")

    elapsed = time.time() - start_time

    model_config = {
        "model_name": model_name,
        "backend": backend,
        "base_url": base_url,
        "model_id": model_name,
        "api_key": api_key,
        "source": backend,
        "endpoint": base_url,
    }

    ctx.save_output("model", model_config)

    metrics = {
        "model_name": model_name,
        "backend": backend,
        "base_url": base_url,
        "loaded": loaded,
        "elapsed_s": round(elapsed, 3),
    }
    if error_msg:
        metrics["error"] = error_msg

    ctx.save_output("metrics", metrics)
    ctx.log_metric("loaded", loaded)
    ctx.log_metric("elapsed_s", round(elapsed, 3))
    ctx.log_message(f"Model config ready: {model_name} ({backend})")
    ctx.report_progress(3, 3)
