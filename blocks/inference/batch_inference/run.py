"""Batch Inference — run model inference on every row of a dataset.

Workflows:
  1. Dataset labeling: dataset + LLM -> each row gets a label/response
  2. Bulk translation: dataset with text column -> translated responses
  3. Data augmentation: generate variations for each row
  4. Sentiment analysis: classify sentiment for each text entry
  5. Batch summarization: summarize each document in a collection
  6. Feature extraction: extract structured fields from each row
  7. Quality scoring: score each item in a dataset
"""

import json
import os
import time


def run(ctx):
    dataset_input = ctx.load_input("dataset")

    # Read upstream dataset metadata
    _dataset_meta = {}
    try:
        _meta_input = ctx.load_input("dataset_meta")
        if isinstance(_meta_input, dict):
            _dataset_meta = _meta_input
    except (ValueError, KeyError):
        pass

    # ── Model config: upstream model input takes priority ──────────────
    model_data = {}
    if ctx.inputs.get("model"):
        model_data = ctx.load_input("model")
        if isinstance(model_data, dict):
            ctx.log_message(f"Using connected model: {model_data.get('model_name', 'unknown')}")

    provider = model_data.get("source", model_data.get("backend",
        ctx.config.get("backend", ctx.config.get("provider", "ollama"))))
    model_name = model_data.get("model_name", model_data.get("model_id",
        ctx.config.get("model_name", "")))
    endpoint = model_data.get("endpoint", model_data.get("base_url",
        ctx.config.get("endpoint", "http://localhost:11434")))
    api_key = model_data.get("api_key",
        ctx.config.get("api_key", ""))

    # Config conflict warnings
    if ctx.inputs.get("model") and ctx.config.get("model_name"):
        ctx.log_message(
            f"\u26a0 Config conflict: upstream model='{model_data.get('model_name')}' "
            f"but local config has model_name='{ctx.config.get('model_name')}'. "
            f"Using upstream. Clear local config to remove this warning."
        )

    text_column = _dataset_meta.get("text_column", ctx.config.get("text_column", "text"))
    prompt_template = ctx.config.get("prompt_template", "{text}")
    system_prompt = ctx.config.get("system_prompt", "")
    max_tokens = int(ctx.config.get("max_tokens", 256))
    temperature = float(ctx.config.get("temperature", 0.7))
    batch_delay = float(ctx.config.get("batch_delay", 0.0))
    response_column = ctx.config.get("response_column", "_response")
    dataset_format = ctx.config.get("dataset_format", "json")
    error_handling = ctx.config.get("error_handling", "skip")
    max_rows = int(ctx.config.get("max_rows", 0))
    frequency_penalty = float(ctx.config.get("frequency_penalty", 0.0))
    presence_penalty = float(ctx.config.get("presence_penalty", 0.0))

    if not model_name:
        raise ValueError("model_name is required — set it in config or connect a model input.")

    # Load dataset
    if isinstance(dataset_input, str):
        data_file = os.path.join(dataset_input, "data.json") if os.path.isdir(dataset_input) else dataset_input
        with open(data_file, "r") as f:
            rows = json.load(f)
    elif isinstance(dataset_input, list):
        rows = dataset_input
    else:
        raise ValueError("Invalid dataset input")

    # Limit rows if max_rows is set
    if max_rows > 0 and len(rows) > max_rows:
        ctx.log_message(f"Limiting from {len(rows)} to {max_rows} rows (max_rows)")
        rows = rows[:max_rows]

    ctx.log_message(f"Batch inference: {len(rows)} rows, model={model_name}, provider={provider}")

    results = []
    start_time = time.time()
    errors = 0

    for i, row in enumerate(rows):
        # Build prompt from template
        prompt = prompt_template
        if isinstance(row, dict):
            for key, val in row.items():
                prompt = prompt.replace("{" + key + "}", str(val))
            input_text = row.get(text_column, str(row))
        else:
            input_text = str(row)
            prompt = prompt.replace("{text}", input_text)

        # Call LLM
        try:
            response = _call_llm(provider, endpoint, api_key, model_name, prompt, system_prompt, temperature, max_tokens, frequency_penalty, presence_penalty)
        except Exception as e:
            if error_handling == "stop":
                raise RuntimeError(f"Row {i} failed: {e}")
            response = f"[Error: {e}]"
            errors += 1

        result_row = dict(row) if isinstance(row, dict) else {"input": input_text}
        result_row[response_column] = response
        result_row["_row_index"] = i
        results.append(result_row)

        if (i + 1) % max(1, len(rows) // 10) == 0:
            ctx.log_message(f"  Processed {i+1}/{len(rows)} rows")

        ctx.report_progress(i + 1, len(rows))
        if batch_delay > 0 and i < len(rows) - 1:
            time.sleep(batch_delay)

    elapsed = time.time() - start_time

    # Save results
    out_dir = os.path.join(ctx.run_dir, "dataset")
    os.makedirs(out_dir, exist_ok=True)
    if dataset_format == "jsonl":
        out_path = os.path.join(out_dir, "data.jsonl")
        with open(out_path, "w", encoding="utf-8") as f:
            for row in results:
                f.write(json.dumps(row) + "\n")
    elif dataset_format == "csv":
        import csv
        out_path = os.path.join(out_dir, "data.csv")
        if results:
            keys = list(results[0].keys())
            with open(out_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=keys)
                writer.writeheader()
                writer.writerows(results)
        else:
            with open(out_path, "w") as f:
                f.write("")
    else:
        out_path = os.path.join(out_dir, "data.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)

    ctx.save_output("dataset", out_dir)
    ctx.save_output("metrics", {
        "total_rows": len(results),
        "errors": errors,
        "elapsed_s": round(elapsed, 2),
        "rows_per_second": round(len(results) / max(elapsed, 0.001), 2),
        "model": model_name,
        "provider": provider,
    })
    ctx.log_metric("total_rows", len(results))
    ctx.log_metric("errors", errors)
    ctx.log_metric("elapsed_s", round(elapsed, 2))
    ctx.log_message(f"Batch complete: {len(results)} rows in {elapsed:.2f}s ({errors} errors)")
    ctx.report_progress(1, 1)


def _call_llm(provider, endpoint, api_key, model, prompt, system_prompt, temperature, max_tokens, frequency_penalty, presence_penalty):
    """Call LLM for a single row."""
    import urllib.request

    if provider == "ollama":
        url = f"{endpoint.rstrip('/')}/api/generate"
        options = {"temperature": temperature, "num_predict": max_tokens}
        if frequency_penalty != 0:
            options["frequency_penalty"] = frequency_penalty
        if presence_penalty != 0:
            options["presence_penalty"] = presence_penalty
        payload = {"model": model, "prompt": prompt, "stream": False,
                   "options": options}
        if system_prompt:
            payload["system"] = system_prompt
        data = json.dumps(payload).encode()
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=300) as resp:
            return json.loads(resp.read().decode()).get("response", "")

    elif provider == "mlx":
        try:
            from mlx_lm import load, generate
        except ImportError:
            raise RuntimeError("mlx-lm not installed. Run: pip install mlx-lm")
        model_obj, tokenizer = load(model)
        return generate(model_obj, tokenizer, prompt=prompt, max_tokens=max_tokens, temp=temperature)

    elif provider == "openai":
        if not api_key:
            api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            raise ValueError("OpenAI API key required.")
        url = endpoint.rstrip("/")
        if "/v1/" not in url:
            url = f"{url}/v1/chat/completions"
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        body = {"model": model, "messages": messages,
                "temperature": temperature, "max_tokens": max_tokens}
        if frequency_penalty != 0:
            body["frequency_penalty"] = frequency_penalty
        if presence_penalty != 0:
            body["presence_penalty"] = presence_penalty
        payload = json.dumps(body).encode()
        req = urllib.request.Request(url, data=payload, headers={
            "Content-Type": "application/json", "Authorization": f"Bearer {api_key}"})
        with urllib.request.urlopen(req, timeout=300) as resp:
            return json.loads(resp.read().decode())["choices"][0]["message"]["content"]

    elif provider == "anthropic":
        if not api_key:
            api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            raise ValueError("Anthropic API key required.")
        url = endpoint.rstrip("/")
        if not url.endswith("/v1/messages"):
            url = f"{url}/v1/messages"
        payload = {"model": model, "messages": [{"role": "user", "content": prompt}],
                   "temperature": temperature, "max_tokens": max_tokens}
        if system_prompt:
            payload["system"] = system_prompt
        data = json.dumps(payload).encode()
        req = urllib.request.Request(url, data=data, headers={
            "Content-Type": "application/json", "x-api-key": api_key, "anthropic-version": "2023-06-01"})
        with urllib.request.urlopen(req, timeout=300) as resp:
            return json.loads(resp.read().decode())["content"][0]["text"]

    else:
        raise ValueError(f"Unknown provider: {provider}")
