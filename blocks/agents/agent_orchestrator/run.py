"""Agent Orchestrator — multi-step agent workflow with tool use and reasoning."""

import json
import os
import time


def run(ctx):
    # ── Config ──────────────────────────────────────────────────────────
    max_steps = int(ctx.config.get("max_steps", 10))
    strategy = ctx.config.get("strategy", "sequential")
    system_prompt = ctx.config.get(
        "system_prompt",
        "You are a helpful assistant that breaks down tasks into steps "
        "and uses tools when needed. Think step by step.",
    )
    temperature = float(ctx.config.get("temperature", 0.3))
    max_tokens = int(ctx.config.get("max_tokens", 1024))
    provider = ctx.config.get("provider", "ollama")
    endpoint = ctx.config.get("endpoint", "http://localhost:11434")
    stop_phrase = ctx.config.get("stop_phrase", "FINAL ANSWER:")
    output_format = ctx.config.get("output_format", "plain")

    # ── Load model info ─────────────────────────────────────────────────
    model_name = ctx.config.get("model_name", "")
    try:
        model_info = ctx.load_input("model")
        if isinstance(model_info, dict):
            model_name = model_name or model_info.get(
                "model_name", model_info.get("model_id", "")
            )
            provider = model_info.get("source", provider)
            endpoint = model_info.get("endpoint", endpoint)
    except (ValueError, Exception):
        pass

    # ── Load task input ─────────────────────────────────────────────────
    input_text = ""
    try:
        data = ctx.load_input("input")
        if isinstance(data, str):
            input_text = data if not os.path.isfile(data) else open(data).read()
        elif isinstance(data, dict):
            input_text = data.get("text", data.get("prompt", json.dumps(data)))
        elif isinstance(data, list):
            input_text = "\n".join(
                item.get("text", item.get("prompt", str(item)))
                if isinstance(item, dict)
                else str(item)
                for item in data
            )
    except (ValueError, Exception):
        input_text = ctx.config.get(
            "task",
            "Analyze the pros and cons of renewable energy sources.",
        )

    # ── Load tools ──────────────────────────────────────────────────────
    tools = []
    tool_schemas = []
    try:
        tools_data = ctx.load_input("tools")
        if isinstance(tools_data, dict):
            tools = tools_data.get("tools", [])
            tool_schemas = tools_data.get("function_schemas", [])
        elif isinstance(tools_data, list):
            tools = tools_data
    except (ValueError, Exception):
        pass

    # ── Load memory context ─────────────────────────────────────────────
    memory_context = ""
    try:
        mem_data = ctx.load_input("memory")
        if isinstance(mem_data, dict):
            mem_entries = []
            for k, v in mem_data.items():
                if isinstance(v, dict) and "value" in v:
                    mem_entries.append(f"- {k}: {v['value']}")
                elif k not in ("tools", "function_schemas", "count", "timestamp"):
                    mem_entries.append(f"- {k}: {v}")
            if mem_entries:
                memory_context = "\n\nRelevant memory:\n" + "\n".join(mem_entries)
    except (ValueError, Exception):
        pass

    ctx.log_message(f"Agent Orchestrator: strategy={strategy}, max_steps={max_steps}")
    ctx.log_message(f"Task: {input_text[:100]}...")
    ctx.log_message(f"Available tools: {len(tools)}")

    # ── Check model availability ────────────────────────────────────────
    use_real = _check_provider(provider, model_name, endpoint)

    if not use_real:
        ctx.log_message("Demo mode: simulating agent orchestration.")

    # ── Build initial conversation ──────────────────────────────────────
    full_system = system_prompt
    if tools:
        tool_names = [t.get("name", "unknown") for t in tools]
        full_system += f"\n\nYou have access to these tools: {', '.join(tool_names)}"
        full_system += "\nTo use a tool, write: TOOL_CALL: tool_name(arguments)"
    if memory_context:
        full_system += memory_context

    if strategy == "react":
        full_system += (
            "\n\nUse the ReAct framework: "
            "Thought → Action → Observation for each step. "
            f"When done, write '{stop_phrase}' followed by your answer."
        )
    elif strategy == "plan_and_execute":
        full_system += (
            "\n\nFirst, create a numbered plan. Then execute each step. "
            f"When done, write '{stop_phrase}' followed by your answer."
        )
    else:
        full_system += (
            f"\n\nWork through this step by step. "
            f"When done, write '{stop_phrase}' followed by your answer."
        )

    conversation = [
        {"role": "system", "content": full_system},
        {"role": "user", "content": input_text},
    ]

    # ── Agent loop ──────────────────────────────────────────────────────
    steps = []
    final_answer = ""
    total_tokens = 0

    for step_num in range(max_steps):
        ctx.log_message(f"\n--- Step {step_num + 1}/{max_steps} ---")

        if use_real:
            try:
                response = _call_model(
                    provider, endpoint, model_name, conversation,
                    temperature, max_tokens,
                )
            except Exception as e:
                ctx.log_message(f"Model error: {e}")
                response = f"[Error calling model: {e}]"
        else:
            response = _simulate_step(
                step_num, max_steps, input_text, strategy, tools, stop_phrase,
            )
            time.sleep(0.2)

        approx_tokens = len(response.split())
        total_tokens += approx_tokens

        conversation.append({"role": "assistant", "content": response})
        step_record = {
            "step": step_num + 1,
            "response": response,
            "tokens_approx": approx_tokens,
            "strategy": strategy,
        }

        # Detect tool calls in response
        if "TOOL_CALL:" in response and tools:
            tool_result = _execute_tool_call(response, tools)
            step_record["tool_call"] = True
            step_record["tool_result"] = tool_result
            conversation.append({"role": "user", "content": f"Tool result: {tool_result}"})

        steps.append(step_record)
        ctx.log_message(f"Response: {response[:150]}...")
        ctx.report_progress(step_num + 1, max_steps)

        # Check for completion signal
        if stop_phrase.lower() in response.lower():
            idx = response.lower().index(stop_phrase.lower())
            final_answer = response[idx + len(stop_phrase):].strip()
            if not final_answer:
                final_answer = response
            ctx.log_message("Agent signaled completion.")
            break

        # Also check natural conclusion phrases
        if any(p in response.lower() for p in ["in conclusion", "to summarize", "final answer"]):
            if step_num >= 1:  # Allow at least 2 steps
                final_answer = response
                ctx.log_message("Agent reached natural conclusion.")
                break

    if not final_answer:
        final_answer = steps[-1]["response"] if steps else "No response generated."

    # ── Apply output format ──────────────────────────────────────────────
    if output_format == "json":
        final_answer = json.dumps({
            "response": final_answer,
            "steps": len(steps),
            "strategy": strategy,
            "model": model_name or "demo",
        }, indent=2)
    elif output_format == "markdown":
        final_answer = (
            f"## Agent Response\n\n{final_answer}\n\n---\n"
            f"*Strategy: {strategy} | Steps: {len(steps)}*"
        )

    # ── Save outputs ────────────────────────────────────────────────────
    out_path = os.path.join(ctx.run_dir, "response.txt")
    with open(out_path, "w") as f:
        f.write(final_answer)
    ctx.save_output("response", out_path)

    steps_dir = os.path.join(ctx.run_dir, "dataset")
    os.makedirs(steps_dir, exist_ok=True)
    with open(os.path.join(steps_dir, "data.json"), "w") as f:
        json.dump(steps, f, indent=2)
    ctx.save_output("dataset", steps_dir)

    metrics = {
        "total_steps": len(steps),
        "total_tokens": total_tokens,
        "model": model_name or "demo",
        "provider": provider,
        "strategy": strategy,
        "tools_available": len(tools),
        "demo_mode": not use_real,
    }
    ctx.save_output("metrics", metrics)
    for k, v in metrics.items():
        if isinstance(v, (int, float)):
            ctx.log_metric(k, v)

    ctx.log_message(f"Agent complete: {len(steps)} steps, {total_tokens} tokens")
    ctx.report_progress(1, 1)


# ── Helpers ─────────────────────────────────────────────────────────────


def _check_provider(provider, model_name, endpoint):
    """Check if an LLM provider is reachable."""
    if not model_name:
        return False
    if provider == "ollama":
        try:
            import urllib.request
            with urllib.request.urlopen(f"{endpoint.rstrip('/')}/api/tags", timeout=5):
                return True
        except Exception:
            return False
    if provider == "openai":
        return bool(os.environ.get("OPENAI_API_KEY"))
    if provider == "anthropic":
        return bool(os.environ.get("ANTHROPIC_API_KEY"))
    return False


def _call_model(provider, endpoint, model, messages, temperature, max_tokens):
    """Dispatch to the correct provider API."""
    import urllib.request

    if provider == "ollama":
        prompt = "\n".join(f"{m['role'].upper()}: {m['content']}" for m in messages)
        url = f"{endpoint.rstrip('/')}/api/generate"
        payload = json.dumps({
            "model": model,
            "prompt": prompt,
            "options": {"temperature": temperature, "num_predict": max_tokens},
            "stream": False,
        }).encode()
        req = urllib.request.Request(
            url, data=payload, headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode()).get("response", "")

    if provider == "openai":
        url = "https://api.openai.com/v1/chat/completions"
        payload = json.dumps({
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }).encode()
        req = urllib.request.Request(url, data=payload, headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}",
        })
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode())
            return data["choices"][0]["message"]["content"]

    if provider == "anthropic":
        url = "https://api.anthropic.com/v1/messages"
        api_msgs = [m for m in messages if m["role"] != "system"]
        system_text = next(
            (m["content"] for m in messages if m["role"] == "system"), "",
        )
        payload = json.dumps({
            "model": model,
            "max_tokens": max_tokens,
            "system": system_text,
            "messages": api_msgs,
        }).encode()
        req = urllib.request.Request(url, data=payload, headers={
            "Content-Type": "application/json",
            "x-api-key": os.environ["ANTHROPIC_API_KEY"],
            "anthropic-version": "2023-06-01",
        })
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode())
            return data["content"][0]["text"]

    raise ValueError(f"Unsupported provider: {provider}")


def _simulate_step(step_num, max_steps, input_text, strategy, tools, stop_phrase):
    """Generate a plausible demo response for a given step."""
    task_preview = input_text[:60].replace("\n", " ")

    if strategy == "react":
        if step_num == 0:
            return (
                f"Thought: I need to analyze the task: '{task_preview}...'\n"
                f"Action: Break down the key components.\n"
                f"Observation: The task involves multiple aspects that need systematic analysis."
            )
        if step_num == max_steps - 1 or step_num >= 2:
            return (
                f"Thought: I have gathered enough information.\n"
                f"{stop_phrase} Based on my analysis of '{task_preview}...', "
                f"the key findings are: (1) Multiple factors support a nuanced view. "
                f"(2) Evidence points to balanced considerations. "
                f"(3) Practical implications should guide decision-making."
            )
        return (
            f"Thought: I need to examine aspect {step_num + 1}.\n"
            f"Action: Analyze supporting evidence for component {step_num + 1}.\n"
            f"Observation: Found relevant factors that inform the analysis."
        )

    if strategy == "plan_and_execute":
        if step_num == 0:
            return (
                f"Plan for '{task_preview}...':\n"
                f"1. Identify the core question\n"
                f"2. Gather relevant evidence\n"
                f"3. Analyze from multiple perspectives\n"
                f"4. Synthesize findings\n\n"
                f"Executing step 1: The core question centers on {task_preview}..."
            )
        if step_num == max_steps - 1 or step_num >= 2:
            return (
                f"Executing final step — synthesis:\n\n"
                f"{stop_phrase} After systematic analysis, the answer to "
                f"'{task_preview}...' is: A balanced approach considering all perspectives "
                f"provides the most comprehensive understanding. Key takeaways include "
                f"practical considerations and evidence-based reasoning."
            )
        return f"Executing step {step_num + 1}: Analyzing component {step_num + 1} in detail."

    # sequential (default)
    if step_num == 0:
        tool_note = ""
        if tools:
            names = [t.get("name", "?") for t in tools[:3]]
            tool_note = f"\nI have tools available: {', '.join(names)}."
        return (
            f"I'll analyze this task step by step.{tool_note}\n\n"
            f"Understanding: The task requires me to {task_preview}...\n\n"
            f"Plan:\n1. Break down the key aspects\n2. Analyze each component\n"
            f"3. Synthesize findings\n\nLet me start."
        )
    if step_num == max_steps - 1 or step_num >= 2:
        return (
            f"{stop_phrase} After analyzing '{task_preview}...', here are the "
            f"key findings:\n\n1. The analysis reveals multiple important factors.\n"
            f"2. Evidence supports a nuanced understanding.\n"
            f"3. Practical implications should be considered.\n\n"
            f"A balanced approach provides the most comprehensive answer."
        )
    return (
        f"Step {step_num + 1} — Analysis:\n\n"
        f"Continuing from the previous step.\n"
        f"Key observations:\n"
        f"- Factor {step_num + 1}: Important consideration identified\n"
        f"- Supporting evidence has been evaluated\n"
        f"- Moving to the next phase of analysis"
    )


def _execute_tool_call(response, tools):
    """Parse and simulate a tool call from the agent's response."""
    try:
        idx = response.index("TOOL_CALL:")
        call_str = response[idx + len("TOOL_CALL:"):].strip().split("\n")[0]
        tool_name = call_str.split("(")[0].strip()

        available = {t["name"] for t in tools}
        if tool_name in available:
            return f"[Tool '{tool_name}' executed successfully. Result: simulated output]"
        return f"[Tool '{tool_name}' not found in registry]"
    except (ValueError, IndexError):
        return "[Could not parse tool call]"
