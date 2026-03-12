"""Vision Inference — image understanding with multimodal LLMs.

Workflows:
  1. Image description: image -> GPT-4o -> detailed description
  2. OCR/text extraction: document image -> LLM -> extracted text
  3. Visual Q&A: image + question -> LLM -> answer
  4. Image classification: image + categories -> LLM -> label
  5. Chart/graph analysis: chart image -> LLM -> data interpretation
  6. Accessibility: image -> LLM -> alt-text generation
  7. Content moderation: image -> LLM -> safety assessment
"""

import base64
import json
import os


def run(ctx):
    provider = ctx.config.get("backend", "openai")
    model_name = ctx.config.get("model_name", "gpt-4o")
    prompt = ctx.config.get("prompt", "Describe this image in detail.")
    image_path = ctx.config.get("image_path", "")
    endpoint = ctx.config.get("endpoint", "https://api.openai.com")
    api_key = ctx.config.get("api_key", "")
    max_tokens = int(ctx.config.get("max_tokens", 1024))
    temperature = float(ctx.config.get("temperature", 0.5))
    detail = ctx.config.get("detail", "auto")
    system_prompt = ctx.config.get("system_prompt", "")
    resize_max = int(ctx.config.get("resize_max", 0))

    # Override from connected model input
    if ctx.inputs.get("model"):
        model_data = ctx.load_input("model")
        if isinstance(model_data, dict):
            model_name = model_data.get("model_name", model_data.get("model_id", model_name))
            provider = model_data.get("backend", model_data.get("provider", provider))
            endpoint = model_data.get("base_url", model_data.get("endpoint", endpoint))
            api_key = model_data.get("api_key", api_key)

    ctx.report_progress(0, 3)

    # Load image from input or config
    if ctx.inputs.get("image"):
        img_data = ctx.load_input("image")
        if isinstance(img_data, str) and os.path.isfile(img_data):
            image_path = img_data
        elif isinstance(img_data, dict) and img_data.get("path"):
            image_path = img_data["path"]

    # Load additional context
    additional_context = ""
    if ctx.inputs.get("text"):
        text_data = ctx.load_input("text")
        if isinstance(text_data, str):
            if os.path.isfile(text_data):
                with open(text_data, "r", encoding="utf-8", errors="ignore") as f:
                    additional_context = f.read()
            else:
                additional_context = text_data

    if additional_context:
        prompt = f"{prompt}\n\nAdditional context:\n{additional_context}"

    if not image_path or not os.path.isfile(image_path):
        raise ValueError(f"Image file not found: {image_path or '(none provided)'}")

    ctx.log_message(f"Vision inference via {provider}/{model_name}")
    ctx.log_message(f"Image: {os.path.basename(image_path)}")
    ctx.report_progress(1, 3)

    # Resize image if configured
    if resize_max > 0:
        try:
            from PIL import Image
            import io
            img = Image.open(image_path)
            if max(img.size) > resize_max:
                ratio = resize_max / max(img.size)
                new_size = (int(img.width * ratio), int(img.height * ratio))
                img = img.resize(new_size, Image.LANCZOS)
                buf = io.BytesIO()
                fmt = "PNG" if image_path.lower().endswith(".png") else "JPEG"
                img.save(buf, format=fmt)
                image_bytes = buf.getvalue()
                ctx.log_message(f"Resized image to {new_size[0]}x{new_size[1]}")
            else:
                with open(image_path, "rb") as f:
                    image_bytes = f.read()
        except ImportError:
            ctx.log_message("Pillow not installed for resize. Using original image.")
            with open(image_path, "rb") as f:
                image_bytes = f.read()
    else:
        with open(image_path, "rb") as f:
            image_bytes = f.read()

    # Encode image
    image_b64 = base64.b64encode(image_bytes).decode("utf-8")

    # Detect MIME type
    ext = os.path.splitext(image_path)[1].lower()
    mime_types = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                  ".gif": "image/gif", ".webp": "image/webp"}
    mime_type = mime_types.get(ext, "image/png")

    # Call vision API
    response_text = ""
    token_usage = {}

    if provider == "openai":
        response_text, token_usage = _call_openai_vision(endpoint, api_key, model_name, prompt, system_prompt, image_b64, mime_type, detail, temperature, max_tokens, ctx)
    elif provider == "anthropic":
        response_text, token_usage = _call_anthropic_vision(endpoint, api_key, model_name, prompt, system_prompt, image_b64, mime_type, temperature, max_tokens, ctx)
    elif provider == "ollama":
        response_text, token_usage = _call_ollama_vision(endpoint, model_name, prompt, system_prompt, image_b64, temperature, max_tokens, ctx)
    else:
        raise ValueError(f"Provider {provider} does not support vision.")

    ctx.report_progress(2, 3)

    # Save response
    out_path = os.path.join(ctx.run_dir, "response.txt")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(response_text)
    ctx.save_output("response", out_path)

    # Save metrics
    metrics = {
        "model": model_name,
        "provider": provider,
        "image_size_bytes": len(image_bytes),
        "response_length": len(response_text),
    }
    metrics.update(token_usage)
    ctx.save_output("metrics", metrics)

    ctx.log_message(f"Response: {len(response_text)} chars")
    ctx.report_progress(3, 3)


def _call_openai_vision(endpoint, api_key, model, prompt, system_prompt, image_b64, mime_type, detail, temperature, max_tokens, ctx):
    import urllib.request

    if not api_key:
        api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        raise ValueError("OpenAI API key required for vision.")

    url = endpoint.rstrip("/")
    if "/v1/" not in url:
        url = f"{url}/v1/chat/completions"

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({
        "role": "user",
        "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {
                "url": f"data:{mime_type};base64,{image_b64}",
                "detail": detail,
            }},
        ],
    })

    payload = json.dumps({
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }).encode()

    req = urllib.request.Request(url, data=payload, headers={
        "Content-Type": "application/json", "Authorization": f"Bearer {api_key}",
    })
    ctx.log_message(f"Calling OpenAI Vision at {url}")

    with urllib.request.urlopen(req, timeout=300) as resp:
        result = json.loads(resp.read().decode())
        text = result["choices"][0]["message"]["content"]
        usage = result.get("usage", {})
        return text, {
            "prompt_tokens": usage.get("prompt_tokens", 0),
            "completion_tokens": usage.get("completion_tokens", 0),
            "total_tokens": usage.get("total_tokens", 0),
        }


def _call_anthropic_vision(endpoint, api_key, model, prompt, system_prompt, image_b64, mime_type, temperature, max_tokens, ctx):
    import urllib.request

    if not api_key:
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise ValueError("Anthropic API key required for vision.")

    url = endpoint.rstrip("/")
    if not url.endswith("/v1/messages"):
        url = f"{url}/v1/messages"

    body = {
        "model": model,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "image", "source": {
                    "type": "base64",
                    "media_type": mime_type,
                    "data": image_b64,
                }},
                {"type": "text", "text": prompt},
            ],
        }],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if system_prompt:
        body["system"] = system_prompt
    payload = json.dumps(body).encode()

    req = urllib.request.Request(url, data=payload, headers={
        "Content-Type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    })
    ctx.log_message(f"Calling Anthropic Vision at {url}")

    with urllib.request.urlopen(req, timeout=300) as resp:
        result = json.loads(resp.read().decode())
        text = result["content"][0]["text"]
        usage = result.get("usage", {})
        return text, {
            "prompt_tokens": usage.get("input_tokens", 0),
            "completion_tokens": usage.get("output_tokens", 0),
            "total_tokens": usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
        }


def _call_ollama_vision(endpoint, model, prompt, system_prompt, image_b64, temperature, max_tokens, ctx):
    import urllib.request

    url = f"{endpoint.rstrip('/')}/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "images": [image_b64],
        "options": {"temperature": temperature, "num_predict": max_tokens},
        "stream": False,
    }
    if system_prompt:
        payload["system"] = system_prompt
    payload = json.dumps(payload).encode()

    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    ctx.log_message(f"Calling Ollama Vision at {url}")

    with urllib.request.urlopen(req, timeout=300) as resp:
        result = json.loads(resp.read().decode())
        return result.get("response", ""), {
            "prompt_tokens": result.get("prompt_eval_count", 0),
            "completion_tokens": result.get("eval_count", 0),
            "total_tokens": result.get("prompt_eval_count", 0) + result.get("eval_count", 0),
        }
