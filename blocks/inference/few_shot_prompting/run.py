"""Few-Shot Prompting — in-context learning with example-based prompting.

Workflows:
  1. Classification: labeled examples + query -> LLM classifies new input
  2. Translation: example pairs + text -> LLM translates in same style
  3. Data extraction: example extractions + new doc -> structured output
  4. Code generation: example code snippets + task -> generated code
  5. Style transfer: example rewrites + text -> rewritten in target style
  6. Q&A: example Q&A pairs + new question -> answer
  7. Summarization: example summaries + new text -> summary in same format
"""

import json
import os
import random


def run(ctx):
    provider = ctx.config.get("backend", "ollama")
    model_name = ctx.config.get("model_name", "llama3.2")
    num_examples = int(ctx.config.get("num_examples", 3))
    input_column = ctx.config.get("input_column", "input")
    output_column = ctx.config.get("output_column", "output")
    selection_strategy = ctx.config.get("selection_strategy", "sequential")
    prompt_prefix = ctx.config.get("prompt_prefix", "Here are some examples:\n\n")
    prompt_suffix = ctx.config.get("prompt_suffix", "\n\nNow respond to the following:\n")
    example_format = ctx.config.get("example_format", "Input: {input}\nOutput: {output}")
    query = ctx.config.get("query", "")
    endpoint = ctx.config.get("endpoint", "http://localhost:11434")
    api_key = ctx.config.get("api_key", "")
    temperature = float(ctx.config.get("temperature", 0.5))
    max_tokens = int(ctx.config.get("max_tokens", 512))
    system_prompt = ctx.config.get("system_prompt", "")
    example_separator = ctx.config.get("example_separator", "\n\n")
    frequency_penalty = float(ctx.config.get("frequency_penalty", 0.0))
    presence_penalty = float(ctx.config.get("presence_penalty", 0.0))

    # Override from connected model input
    if ctx.inputs.get("model"):
        model_data = ctx.load_input("model")
        if isinstance(model_data, dict):
            model_name = model_data.get("model_name", model_data.get("model_id", model_name))
            provider = model_data.get("backend", model_data.get("provider", provider))
            endpoint = model_data.get("base_url", model_data.get("endpoint", endpoint))
            api_key = model_data.get("api_key", api_key)

    ctx.report_progress(0, 4)

    # Load examples dataset
    examples = []
    if ctx.inputs.get("dataset"):
        data = ctx.load_input("dataset")
        examples = _load_examples(data)
    ctx.log_message(f"Loaded {len(examples)} examples")

    # Load query from input or config
    if ctx.inputs.get("text"):
        text_data = ctx.load_input("text")
        if isinstance(text_data, str):
            if os.path.isfile(text_data):
                with open(text_data, "r", encoding="utf-8", errors="ignore") as f:
                    query = f.read()
            else:
                query = text_data

    if not query:
        raise ValueError("No query provided. Set query config or connect a text input.")

    ctx.report_progress(1, 4)

    # Select examples
    if selection_strategy == "random" and len(examples) > num_examples:
        selected = random.sample(examples, num_examples)
    else:
        selected = examples[:num_examples]

    ctx.log_message(f"Selected {len(selected)} examples ({selection_strategy})")
    ctx.report_progress(2, 4)

    # Build the few-shot prompt
    example_blocks = []
    for ex in selected:
        block = example_format
        for key, val in ex.items():
            block = block.replace("{" + key + "}", str(val))
        block = block.replace("{input}", str(ex.get(input_column, "")))
        block = block.replace("{output}", str(ex.get(output_column, "")))
        example_blocks.append(block)

    assembled_prompt = prompt_prefix + example_separator.join(example_blocks) + prompt_suffix + query

    # Save assembled prompt
    prompt_path = os.path.join(ctx.run_dir, "assembled_prompt.txt")
    with open(prompt_path, "w", encoding="utf-8") as f:
        f.write(assembled_prompt)
    ctx.save_output("prompt", prompt_path)

    ctx.log_message(f"Assembled prompt: {len(assembled_prompt)} chars")

    # Call LLM
    response_text, token_usage = _call_llm(provider, endpoint, api_key, model_name, assembled_prompt, system_prompt, temperature, max_tokens, frequency_penalty, presence_penalty, ctx)

    ctx.report_progress(3, 4)

    # Apply output format
    output_format = ctx.config.get("output_format", "text")
    save_text = response_text
    if output_format == "json":
        from datetime import datetime
        output_obj = {
            "response": response_text,
            "model": model_name,
            "provider": provider,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }
        if token_usage:
            output_obj["usage"] = token_usage
        save_text = json.dumps(output_obj, indent=2)

    # Save response
    ext = "json" if output_format == "json" else "txt"
    out_path = os.path.join(ctx.run_dir, f"response.{ext}")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(save_text)
    ctx.save_output("response", out_path)

    # Save metrics
    metrics = {
        "examples_used": len(selected),
        "examples_available": len(examples),
        "strategy": selection_strategy,
        "prompt_length": len(assembled_prompt),
        "response_length": len(response_text),
        "model": model_name,
        "provider": provider,
    }
    metrics.update(token_usage)
    ctx.save_output("metrics", metrics)

    ctx.log_message(f"Response: {len(response_text)} chars using {len(selected)} examples")
    ctx.report_progress(4, 4)


def _load_examples(data):
    """Load examples from various input formats."""
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, str):
        path = data
        if os.path.isdir(path):
            path = os.path.join(path, "data.json")
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            try:
                parsed = json.loads(content)
                if isinstance(parsed, list):
                    return [row for row in parsed if isinstance(row, dict)]
            except (json.JSONDecodeError, ValueError):
                pass
    return []


def _call_llm(provider, endpoint, api_key, model, prompt, system_prompt, temperature, max_tokens, frequency_penalty, presence_penalty, ctx):
    """Call LLM with the assembled few-shot prompt."""
    import urllib.request

    if provider == "ollama":
        url = f"{endpoint.rstrip('/')}/api/generate"
        options = {"temperature": temperature, "num_predict": max_tokens}
        if frequency_penalty != 0:
            options["frequency_penalty"] = frequency_penalty
        if presence_penalty != 0:
            options["presence_penalty"] = presence_penalty
        payload = {
            "model": model, "prompt": prompt,
            "options": options,
            "stream": False,
        }
        if system_prompt:
            payload["system"] = system_prompt
        data = json.dumps(payload).encode()
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=300) as resp:
            result = json.loads(resp.read().decode())
            return result.get("response", ""), {
                "prompt_tokens": result.get("prompt_eval_count", 0),
                "completion_tokens": result.get("eval_count", 0),
                "total_tokens": result.get("prompt_eval_count", 0) + result.get("eval_count", 0),
            }

    elif provider == "mlx":
        try:
            from mlx_lm import load, generate
        except ImportError:
            raise RuntimeError("mlx-lm not installed. Run: pip install mlx-lm")
        model_obj, tokenizer = load(model)
        text = generate(model_obj, tokenizer, prompt=prompt, max_tokens=max_tokens, temp=temperature)
        return text, {}

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
        body = {
            "model": model,
            "messages": messages,
            "temperature": temperature, "max_tokens": max_tokens,
        }
        if frequency_penalty != 0:
            body["frequency_penalty"] = frequency_penalty
        if presence_penalty != 0:
            body["presence_penalty"] = presence_penalty
        payload = json.dumps(body).encode()
        req = urllib.request.Request(url, data=payload, headers={
            "Content-Type": "application/json", "Authorization": f"Bearer {api_key}",
        })
        with urllib.request.urlopen(req, timeout=300) as resp:
            result = json.loads(resp.read().decode())
            usage = result.get("usage", {})
            return result["choices"][0]["message"]["content"], {
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
            }

    elif provider == "anthropic":
        if not api_key:
            api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            raise ValueError("Anthropic API key required.")
        url = endpoint.rstrip("/")
        if not url.endswith("/v1/messages"):
            url = f"{url}/v1/messages"
        body = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature, "max_tokens": max_tokens,
        }
        if system_prompt:
            body["system"] = system_prompt
        payload = json.dumps(body).encode()
        req = urllib.request.Request(url, data=payload, headers={
            "Content-Type": "application/json", "x-api-key": api_key, "anthropic-version": "2023-06-01",
        })
        with urllib.request.urlopen(req, timeout=300) as resp:
            result = json.loads(resp.read().decode())
            usage = result.get("usage", {})
            return result["content"][0]["text"], {
                "prompt_tokens": usage.get("input_tokens", 0),
                "completion_tokens": usage.get("output_tokens", 0),
                "total_tokens": usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
            }

    else:
        raise ValueError(f"Unknown provider: {provider}")
