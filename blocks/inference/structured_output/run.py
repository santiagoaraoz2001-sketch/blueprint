"""Structured Output — generate JSON/structured data from LLM using a schema.

Workflows:
  1. Data extraction: document + schema -> structured JSON fields
  2. Form filling: unstructured text -> structured form data
  3. API response generation: user query -> JSON API response format
  4. Entity extraction: text -> entities with types and values
  5. Config generation: requirements -> JSON config file
  6. Resume parsing: resume text + schema -> structured profile
  7. Survey analysis: free-text responses -> categorized JSON
"""

import json
import os
import re


def run(ctx):
    provider = ctx.config.get("provider", "ollama")
    model_name = ctx.config.get("model_name", "llama3.2")
    output_schema = ctx.config.get("output_schema", '{"name": "string"}')
    user_prompt = ctx.config.get("user_prompt", "")
    system_prompt = ctx.config.get("system_prompt", "")
    strict_mode = ctx.config.get("strict_mode", True)
    if isinstance(strict_mode, str):
        strict_mode = strict_mode.lower() in ("true", "1", "yes")
    endpoint = ctx.config.get("endpoint", "http://localhost:11434")
    api_key = ctx.config.get("api_key", "")
    temperature = float(ctx.config.get("temperature", 0.3))
    max_tokens = int(ctx.config.get("max_tokens", 1024))
    max_retries = int(ctx.config.get("max_retries", 1))

    # Override from connected model input
    if ctx.inputs.get("model"):
        model_data = ctx.load_input("model")
        if isinstance(model_data, dict):
            model_name = model_data.get("model_name", model_data.get("model_id", model_name))
            provider = model_data.get("backend", model_data.get("provider", provider))
            endpoint = model_data.get("base_url", model_data.get("endpoint", endpoint))
            api_key = model_data.get("api_key", api_key)

    ctx.report_progress(0, 3)

    # Load schema from input or config
    if ctx.inputs.get("schema"):
        schema_data = ctx.load_input("schema")
        if isinstance(schema_data, dict):
            output_schema = json.dumps(schema_data)
        elif isinstance(schema_data, str):
            if os.path.isfile(schema_data):
                with open(schema_data, "r") as f:
                    output_schema = f.read()
            else:
                output_schema = schema_data

    # Load user prompt from input or config
    if ctx.inputs.get("text"):
        text_data = ctx.load_input("text")
        if isinstance(text_data, str):
            if os.path.isfile(text_data):
                with open(text_data, "r", encoding="utf-8", errors="ignore") as f:
                    user_prompt = f.read()
            else:
                user_prompt = text_data

    if not user_prompt:
        raise ValueError("No user prompt provided.")

    # Build system instruction for structured output
    schema_instruction = (
        f"You must respond with valid JSON matching this schema:\n{output_schema}\n\n"
        "Respond ONLY with JSON, no other text or explanation."
    )
    full_system = f"{system_prompt}\n\n{schema_instruction}" if system_prompt else schema_instruction

    ctx.log_message(f"Structured output via {provider}/{model_name}")
    ctx.report_progress(1, 3)

    # Call LLM with retry on JSON parse failure
    parsed_json = None
    raw_response = ""
    for attempt in range(max_retries):
        raw_response = _call_llm(provider, endpoint, api_key, model_name, user_prompt, full_system, temperature, max_tokens, ctx)

        # Parse JSON from response
        try:
            parsed_json = json.loads(raw_response)
            break
        except json.JSONDecodeError:
            # Try to extract JSON from markdown code blocks or embedded JSON
            json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', raw_response)
            if json_match:
                try:
                    parsed_json = json.loads(json_match.group(1))
                    break
                except json.JSONDecodeError:
                    pass
            if parsed_json is None:
                # Try to find JSON object in the text
                json_match = re.search(r'\{[\s\S]*\}', raw_response)
                if json_match:
                    try:
                        parsed_json = json.loads(json_match.group())
                        break
                    except json.JSONDecodeError:
                        pass

        if parsed_json is None and attempt < max_retries - 1:
            ctx.log_message(f"JSON parse failed (attempt {attempt + 1}/{max_retries}), retrying...")

    if parsed_json is None and strict_mode:
        raise ValueError(f"Failed to parse JSON after {max_retries} attempts: {raw_response[:200]}")

    ctx.report_progress(2, 3)

    # Save structured data
    if parsed_json is not None:
        data_path = os.path.join(ctx.run_dir, "output.json")
        with open(data_path, "w", encoding="utf-8") as f:
            json.dump(parsed_json, f, indent=2)
        ctx.save_output("data", data_path)
        result_text = json.dumps(parsed_json, indent=2)
    else:
        result_text = raw_response
        ctx.save_output("data", raw_response)

    # Save raw text
    out_path = os.path.join(ctx.run_dir, "output_text.txt")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(result_text)
    ctx.save_output("text", out_path)

    # Save metrics
    ctx.save_output("metrics", {
        "valid_json": parsed_json is not None,
        "output_length": len(result_text),
        "model": model_name,
        "provider": provider,
    })

    ctx.log_message(f"Structured output: {'valid JSON' if parsed_json else 'parse failed'}, {len(result_text)} chars")
    ctx.report_progress(3, 3)


def _call_llm(provider, endpoint, api_key, model, prompt, system_prompt, temperature, max_tokens, ctx):
    import urllib.request

    if provider == "ollama":
        url = f"{endpoint.rstrip('/')}/api/chat"
        payload = json.dumps({
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            "options": {"temperature": temperature, "num_predict": max_tokens},
            "stream": False,
            "format": "json",
        }).encode()
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=300) as resp:
            return json.loads(resp.read().decode()).get("message", {}).get("content", "")

    elif provider == "openai":
        if not api_key:
            api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            raise ValueError("OpenAI API key required.")
        url = endpoint.rstrip("/")
        if "/v1/" not in url:
            url = f"{url}/v1/chat/completions"
        payload = json.dumps({
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            "temperature": temperature, "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }).encode()
        req = urllib.request.Request(url, data=payload, headers={
            "Content-Type": "application/json", "Authorization": f"Bearer {api_key}",
        })
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
        payload = json.dumps({
            "model": model,
            "system": system_prompt,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature, "max_tokens": max_tokens,
        }).encode()
        req = urllib.request.Request(url, data=payload, headers={
            "Content-Type": "application/json", "x-api-key": api_key, "anthropic-version": "2023-06-01",
        })
        with urllib.request.urlopen(req, timeout=300) as resp:
            return json.loads(resp.read().decode())["content"][0]["text"]

    else:
        raise ValueError(f"Unknown provider: {provider}")
