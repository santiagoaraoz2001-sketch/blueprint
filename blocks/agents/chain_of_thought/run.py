"""Chain of Thought — multi-step LLM reasoning with prompt chaining."""

import json
import os
import time
from collections import Counter


def run(ctx):
    # ── Config ──────────────────────────────────────────────────────────
    num_steps = int(ctx.config.get("num_steps", 3))
    temperature = float(ctx.config.get("temperature", 0.3))
    max_tokens = int(ctx.config.get("max_tokens", 512))
    self_consistency = int(ctx.config.get("self_consistency", 1))
    custom_steps_raw = ctx.config.get("custom_steps", "")
    output_mode = ctx.config.get("output_mode", "full_chain")
    provider = ctx.config.get("provider", "ollama")
    endpoint = ctx.config.get("endpoint", "http://localhost:11434")

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

    # ── Load input ──────────────────────────────────────────────────────
    input_text = ""
    try:
        data = ctx.load_input("input")
        if isinstance(data, str):
            input_text = data if not os.path.isfile(data) else open(data).read()
        elif isinstance(data, dict):
            input_text = data.get("text", data.get("prompt", json.dumps(data)))
        elif isinstance(data, list):
            input_text = "\n".join(
                item.get("text", str(item)) if isinstance(item, dict) else str(item)
                for item in data
            )
    except (ValueError, Exception):
        input_text = ctx.config.get(
            "input_text", "What are the key benefits of renewable energy?"
        )
        ctx.log_message("No input connected. Using config/default text.")

    ctx.log_message(f"Chain of Thought: {num_steps} steps, {self_consistency} sample(s)")
    ctx.log_message(f"Input: {input_text[:100]}...")

    # ── Check model availability ────────────────────────────────────────
    use_real = _check_provider(provider, model_name, endpoint)
    if not use_real:
        ctx.log_message("Demo mode: simulating reasoning chain.")

    # ── Build step prompts ──────────────────────────────────────────────
    custom_prompts = [
        line.strip()
        for line in custom_steps_raw.split("\n")
        if line.strip()
    ] if custom_steps_raw.strip() else []

    if custom_prompts:
        step_prompts = custom_prompts[:num_steps]
        while len(step_prompts) < num_steps:
            step_prompts.append(
                "Step {step_num} — Continue:\nRefine based on previous analysis.\n\n"
                "Previous: {previous}\n\nRefined:"
            )
    else:
        step_prompts = _default_step_prompts(num_steps)

    # ── Run chains (self-consistency) ───────────────────────────────────
    all_chains = []
    total_steps = self_consistency * num_steps
    progress_count = 0

    for sample_idx in range(self_consistency):
        if self_consistency > 1:
            ctx.log_message(f"\n=== Sample {sample_idx + 1}/{self_consistency} ===")

        steps = []
        previous = input_text

        for i in range(num_steps):
            prompt = step_prompts[i]
            prompt = prompt.replace("{input}", input_text)
            prompt = prompt.replace("{previous}", previous)
            prompt = prompt.replace("{step_num}", str(i + 1))
            for j, step in enumerate(steps):
                prompt = prompt.replace(f"{{step_{j + 1}}}", step["response"])

            ctx.log_message(f"  Step {i + 1}/{num_steps}")

            if use_real:
                try:
                    response = _call_model(
                        provider, endpoint, model_name, prompt,
                        temperature, max_tokens,
                    )
                except Exception as e:
                    response = f"[Error: {e}]"
            else:
                response = _simulate_step(i, num_steps, input_text)
                time.sleep(0.15)

            steps.append({
                "step": i + 1,
                "prompt": prompt[:200] + ("..." if len(prompt) > 200 else ""),
                "response": response,
                "tokens_approx": len(response.split()),
            })
            previous = response

            progress_count += 1
            ctx.report_progress(progress_count, total_steps)
            ctx.log_message(f"    Response: {response[:120]}...")

        all_chains.append({
            "sample": sample_idx + 1,
            "steps": steps,
            "final_answer": steps[-1]["response"] if steps else "",
        })

    # ── Select final answer ─────────────────────────────────────────────
    if self_consistency > 1:
        final_answer = _majority_vote(all_chains)
        ctx.log_message(f"Self-consistency: selected answer via majority vote")
    else:
        final_answer = all_chains[0]["final_answer"]

    # ── Flatten all steps for dataset output ────────────────────────────
    all_steps = []
    for chain in all_chains:
        for step in chain["steps"]:
            record = dict(step)
            record["sample"] = chain["sample"]
            all_steps.append(record)

    # ── Build text output based on output_mode ──────────────────────────
    if output_mode == "final_only":
        output_text = final_answer
    else:
        chain_parts = []
        for chain in all_chains:
            if self_consistency > 1:
                chain_parts.append(f"## Sample {chain['sample']}")
            for step in chain["steps"]:
                chain_parts.append(f"### Step {step['step']}\n{step['response']}")
        chain_parts.append(f"### Final Answer\n{final_answer}")
        output_text = "\n\n".join(chain_parts)

    # ── Apply output format ─────────────────────────────────────────────
    output_format = ctx.config.get("output_format", "markdown")
    if output_format == "json":
        output_text = json.dumps({
            "steps": all_steps,
            "final_answer": final_answer,
            "metadata": {
                "num_steps": num_steps,
                "self_consistency": self_consistency,
                "output_mode": output_mode,
                "model": model_name or "demo",
            },
        }, indent=2)
    elif output_format == "plain":
        output_text = output_text.replace("### ", "").replace("## ", "")

    # ── Save outputs ────────────────────────────────────────────────────
    out_path = os.path.join(ctx.run_dir, "response.txt")
    with open(out_path, "w") as f:
        f.write(output_text)
    ctx.save_output("response", out_path)

    steps_dir = os.path.join(ctx.run_dir, "dataset")
    os.makedirs(steps_dir, exist_ok=True)
    with open(os.path.join(steps_dir, "data.json"), "w") as f:
        json.dump(all_steps, f, indent=2)
    ctx.save_output("dataset", steps_dir)

    total_tokens = sum(s["tokens_approx"] for s in all_steps)
    metrics = {
        "num_steps": num_steps,
        "self_consistency_samples": self_consistency,
        "total_tokens": total_tokens,
        "model": model_name or "demo",
        "provider": provider,
        "demo_mode": not use_real,
    }
    ctx.save_output("metrics", metrics)
    for k, v in metrics.items():
        if isinstance(v, (int, float)):
            ctx.log_metric(k, v)

    ctx.log_message(f"Chain of thought complete: {num_steps} steps, {total_tokens} tokens")
    ctx.report_progress(1, 1)


# ── Helpers ─────────────────────────────────────────────────────────────


def _default_step_prompts(num_steps):
    """Build default CoT step prompts."""
    prompts = [
        (
            "Step 1 — Understand the problem:\n"
            "Analyze the following question and break it down into key components.\n\n"
            "Question: {input}\n\nAnalysis:"
        ),
        (
            "Step 2 — Gather evidence:\n"
            "Based on the analysis below, identify key facts and evidence.\n\n"
            "Previous analysis: {previous}\n\nEvidence:"
        ),
        (
            "Step 3 — Synthesize and conclude:\n"
            "Based on the analysis and evidence, provide a comprehensive answer.\n\n"
            "Analysis: {step_1}\nEvidence: {step_2}\n\nFinal Answer:"
        ),
    ]
    for i in range(3, num_steps):
        prompts.append(
            f"Step {i + 1} — Refine:\n"
            f"Refine the previous answer with additional depth and nuance.\n\n"
            f"Previous: {{previous}}\n\nRefined:"
        )
    return prompts


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


def _call_model(provider, endpoint, model, prompt, temperature, max_tokens):
    """Call the configured LLM provider."""
    import urllib.request

    if provider == "ollama":
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
            "messages": [{"role": "user", "content": prompt}],
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
        payload = json.dumps({
            "model": model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
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


def _simulate_step(step_idx, num_steps, input_text):
    """Generate plausible demo reasoning for a step."""
    preview = input_text[:50].replace("\n", " ")
    demos = [
        (
            f"The question asks about '{preview}...'. Key components include: "
            f"1) Understanding the core concept, 2) Identifying relevant factors, "
            f"3) Evaluating implications. This requires examining multiple perspectives."
        ),
        (
            f"Based on the analysis, key evidence includes: "
            f"Multiple studies support the main premise. Historical data shows "
            f"consistent patterns. Expert consensus aligns with the evidence."
        ),
        (
            f"Synthesizing the analysis and evidence: The answer to '{preview}...' "
            f"involves interconnected factors. The evidence supports a comprehensive "
            f"understanding that accounts for theoretical foundations and practical implications."
        ),
    ]
    return demos[min(step_idx, len(demos) - 1)]


def _majority_vote(chains):
    """Select the most common final answer across chains (by keyword overlap)."""
    answers = [c["final_answer"] for c in chains]
    if len(answers) <= 1:
        return answers[0] if answers else ""

    # Use keyword-based similarity: pick the answer most similar to all others
    def keywords(text):
        return set(text.lower().split())

    best_idx = 0
    best_score = -1
    for i, ans_i in enumerate(answers):
        kw_i = keywords(ans_i)
        score = sum(
            len(kw_i & keywords(ans_j)) for j, ans_j in enumerate(answers) if j != i
        )
        if score > best_score:
            best_score = score
            best_idx = i

    return answers[best_idx]
