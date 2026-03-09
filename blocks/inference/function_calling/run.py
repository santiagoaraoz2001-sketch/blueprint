"""Function Calling — LLM with tool/function definitions for structured actions.

Workflows:
  1. API orchestration: user request -> LLM decides which API to call -> tool_calls output
  2. Data extraction: document + schema tools -> LLM extracts structured fields
  3. Multi-step agent: tool calls fed back for execution -> results returned
  4. Calculator/code: math or code tools -> LLM generates function calls
  5. Search + answer: search tool + user query -> LLM calls search -> answer
  6. Workflow automation: user intent -> LLM picks tools -> automation pipeline
"""

import json
import os


def run(ctx):
    provider = ctx.config.get("provider", "openai")
    model_name = ctx.config.get("model_name", "gpt-4o")
    tools_json = ctx.config.get("tools", "[]")
    tool_choice = ctx.config.get("tool_choice", "auto")
    user_message = ctx.config.get("user_message", "")
    system_prompt = ctx.config.get("system_prompt", "You are a helpful assistant with access to tools.")
    endpoint = ctx.config.get("endpoint", "https://api.openai.com")
    api_key = ctx.config.get("api_key", "")
    temperature = float(ctx.config.get("temperature", 0.3))
    max_tokens = int(ctx.config.get("max_tokens", 1024))
    top_p = float(ctx.config.get("top_p", 1.0))
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

    # Load tool definitions from input or config
    tools = []
    if ctx.inputs.get("tools"):
        tools_data = ctx.load_input("tools")
        if isinstance(tools_data, list):
            tools = tools_data
        elif isinstance(tools_data, str):
            if os.path.isfile(tools_data):
                with open(tools_data, "r") as f:
                    tools = json.load(f)
            else:
                tools = json.loads(tools_data)
        elif isinstance(tools_data, dict):
            tools = tools_data.get("tools", [tools_data])
    if not tools:
        try:
            tools = json.loads(tools_json)
        except (json.JSONDecodeError, ValueError):
            tools = []

    # Load user message from input or config
    if ctx.inputs.get("text"):
        text_data = ctx.load_input("text")
        if isinstance(text_data, str):
            if os.path.isfile(text_data):
                with open(text_data, "r", encoding="utf-8", errors="ignore") as f:
                    user_message = f.read()
            else:
                user_message = text_data

    if not user_message:
        raise ValueError("No user message provided.")

    ctx.log_message(f"Function calling via {provider}/{model_name} with {len(tools)} tools")
    ctx.report_progress(1, 3)

    # Build messages
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": user_message})

    # Call provider with retries
    response_text = ""
    tool_calls = []
    token_usage = {}
    last_error = None

    for attempt in range(max_retries):
        try:
            if provider == "openai":
                response_text, tool_calls, token_usage = _call_openai(endpoint, api_key, model_name, messages, tools, tool_choice, temperature, max_tokens, top_p, ctx)
            elif provider == "anthropic":
                response_text, tool_calls, token_usage = _call_anthropic(endpoint, api_key, model_name, messages, tools, system_prompt, temperature, max_tokens, top_p, ctx)
            elif provider == "ollama":
                response_text, tool_calls, token_usage = _call_ollama(endpoint, model_name, messages, tools, temperature, max_tokens, top_p, ctx)
            else:
                raise ValueError(f"Provider {provider} does not support function calling.")
            last_error = None
            break
        except Exception as e:
            last_error = e
            if attempt < max_retries - 1:
                ctx.log_message(f"Attempt {attempt+1}/{max_retries} failed: {e}")

    if last_error is not None:
        raise last_error

    ctx.report_progress(2, 3)

    # Save response text
    out_path = os.path.join(ctx.run_dir, "response.txt")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(response_text)
    ctx.save_output("response", out_path)

    # Save tool calls
    calls_path = os.path.join(ctx.run_dir, "tool_calls.json")
    with open(calls_path, "w", encoding="utf-8") as f:
        json.dump(tool_calls, f, indent=2)
    ctx.save_output("tool_calls", calls_path)

    # Save metrics
    metrics = {
        "model": model_name,
        "provider": provider,
        "tools_available": len(tools),
        "tool_calls_made": len(tool_calls),
        "response_length": len(response_text),
    }
    metrics.update(token_usage)
    ctx.save_output("metrics", metrics)

    ctx.log_message(f"Response with {len(tool_calls)} tool calls")
    ctx.report_progress(3, 3)


def _call_openai(endpoint, api_key, model, messages, tools, tool_choice, temperature, max_tokens, top_p, ctx):
    import urllib.request

    if not api_key:
        api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        raise ValueError("OpenAI API key required.")

    url = endpoint.rstrip("/")
    if "/v1/" not in url:
        url = f"{url}/v1/chat/completions"

    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if top_p < 1.0:
        payload["top_p"] = top_p
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = tool_choice

    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    })
    ctx.log_message(f"Calling OpenAI at {url}")

    with urllib.request.urlopen(req, timeout=300) as resp:
        result = json.loads(resp.read().decode())

    choice = result["choices"][0]
    message = choice["message"]
    response_text = message.get("content", "") or ""

    tool_calls = []
    if message.get("tool_calls"):
        for tc in message["tool_calls"]:
            tool_calls.append({
                "id": tc.get("id", ""),
                "function": tc["function"]["name"],
                "arguments": json.loads(tc["function"]["arguments"]) if isinstance(tc["function"]["arguments"], str) else tc["function"]["arguments"],
            })

    usage = result.get("usage", {})
    return response_text, tool_calls, {
        "prompt_tokens": usage.get("prompt_tokens", 0),
        "completion_tokens": usage.get("completion_tokens", 0),
        "total_tokens": usage.get("total_tokens", 0),
    }


def _call_anthropic(endpoint, api_key, model, messages, tools, system_prompt, temperature, max_tokens, top_p, ctx):
    import urllib.request

    if not api_key:
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise ValueError("Anthropic API key required.")

    url = endpoint.rstrip("/")
    if not url.endswith("/v1/messages"):
        url = f"{url}/v1/messages"

    api_messages = [m for m in messages if m["role"] != "system"]

    # Convert OpenAI tool format to Anthropic format
    anthropic_tools = []
    for tool in tools:
        if tool.get("type") == "function":
            func = tool["function"]
            anthropic_tools.append({
                "name": func["name"],
                "description": func.get("description", ""),
                "input_schema": func.get("parameters", {"type": "object", "properties": {}}),
            })
        elif "name" in tool:
            anthropic_tools.append(tool)

    payload = {
        "model": model,
        "messages": api_messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if top_p < 1.0:
        payload["top_p"] = top_p
    if system_prompt:
        payload["system"] = system_prompt
    if anthropic_tools:
        payload["tools"] = anthropic_tools

    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={
        "Content-Type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    })
    ctx.log_message(f"Calling Anthropic at {url}")

    with urllib.request.urlopen(req, timeout=300) as resp:
        result = json.loads(resp.read().decode())

    response_text = ""
    tool_calls = []
    for block in result.get("content", []):
        if block["type"] == "text":
            response_text += block["text"]
        elif block["type"] == "tool_use":
            tool_calls.append({
                "id": block.get("id", ""),
                "function": block["name"],
                "arguments": block.get("input", {}),
            })

    usage = result.get("usage", {})
    return response_text, tool_calls, {
        "prompt_tokens": usage.get("input_tokens", 0),
        "completion_tokens": usage.get("output_tokens", 0),
        "total_tokens": usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
    }


def _call_ollama(endpoint, model, messages, tools, temperature, max_tokens, top_p, ctx):
    import urllib.request

    url = f"{endpoint.rstrip('/')}/api/chat"
    payload = {
        "model": model,
        "messages": messages,
        "options": {"temperature": temperature, "num_predict": max_tokens, **({"top_p": top_p} if top_p < 1.0 else {})},
        "stream": False,
    }
    if tools:
        payload["tools"] = tools

    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    ctx.log_message(f"Calling Ollama at {url}")

    with urllib.request.urlopen(req, timeout=300) as resp:
        result = json.loads(resp.read().decode())

    message = result.get("message", {})
    response_text = message.get("content", "") or ""

    tool_calls = []
    for tc in message.get("tool_calls", []):
        func = tc.get("function", {})
        tool_calls.append({
            "function": func.get("name", ""),
            "arguments": func.get("arguments", {}),
        })

    return response_text, tool_calls, {
        "prompt_tokens": result.get("prompt_eval_count", 0),
        "completion_tokens": result.get("eval_count", 0),
        "total_tokens": result.get("prompt_eval_count", 0) + result.get("eval_count", 0),
    }
