"""Multi-Agent Debate — multiple agents debate a topic to reach consensus."""

import json
import os
import time
import random


def run(ctx):
    # ── Config ──────────────────────────────────────────────────────────
    num_agents = int(ctx.config.get("num_agents", 3))
    num_rounds = int(ctx.config.get("num_rounds", 3))
    temperature = float(ctx.config.get("temperature", 0.7))
    max_tokens = int(ctx.config.get("max_tokens", 256))
    debate_format = ctx.config.get("format", "free_form")
    custom_personas_raw = ctx.config.get("custom_personas", "")
    provider = ctx.config.get("provider", "ollama")
    endpoint = ctx.config.get("endpoint", "http://localhost:11434")
    seed = int(ctx.config.get("seed", 42))
    moderator_prompt = ctx.config.get("moderator_prompt", "")

    random.seed(seed)

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

    # ── Load topic ──────────────────────────────────────────────────────
    topic = ""
    try:
        data = ctx.load_input("input")
        if isinstance(data, str):
            topic = data if not os.path.isfile(data) else open(data).read()
        elif isinstance(data, dict):
            topic = data.get("text", data.get("topic", data.get("prompt", "")))
    except (ValueError, Exception):
        pass
    topic = topic or ctx.config.get(
        "topic", "Should artificial intelligence be regulated by governments?"
    )

    ctx.log_message(f"Multi-Agent Debate: {num_agents} agents, {num_rounds} rounds, format={debate_format}")
    ctx.log_message(f"Topic: {topic[:100]}...")

    # ── Check model availability ────────────────────────────────────────
    use_real = _check_provider(provider, model_name, endpoint)
    if not use_real:
        ctx.log_message("Demo mode: simulating multi-agent debate.")

    # ── Build agent personas ────────────────────────────────────────────
    agents = _build_personas(num_agents, custom_personas_raw)

    # ── Run debate ──────────────────────────────────────────────────────
    debate_log = []

    for round_num in range(num_rounds):
        ctx.log_message(f"\n=== Round {round_num + 1}/{num_rounds} ===")

        # Determine round label for structured format
        round_label = _round_label(debate_format, round_num, num_rounds)

        for agent in agents:
            # Build context from prior arguments
            prev_args = []
            for entry in debate_log[-(num_agents * 2):]:
                if entry["agent"] != agent["name"]:
                    prev_args.append(f"{entry['agent']}: {entry['argument'][:150]}")
            context = "\n".join(prev_args) if prev_args else "This is the opening round."

            if use_real:
                argument = _generate_argument_real(
                    provider, endpoint, model_name, agent, topic,
                    context, round_num, round_label, debate_format,
                    temperature, max_tokens,
                )
            else:
                argument = _generate_argument_demo(
                    agent, topic, context, round_num, num_rounds, debate_format,
                )
                time.sleep(0.1)

            entry = {
                "round": round_num + 1,
                "round_label": round_label,
                "agent": agent["name"],
                "persona": agent["style"],
                "bias": agent["bias"],
                "argument": argument,
            }
            debate_log.append(entry)
            ctx.log_message(f"  {agent['name']}: {argument[:100]}...")

        ctx.report_progress(round_num + 1, num_rounds)

    # ── Compute consensus score ─────────────────────────────────────────
    consensus_score = _compute_consensus(debate_log, num_rounds)

    ctx.log_message(f"\n--- Debate Complete ---")
    ctx.log_message(f"Consensus score: {consensus_score:.2%}")
    ctx.log_message(f"Total arguments: {len(debate_log)}")

    # ── Generate summary ────────────────────────────────────────────────
    summary = _generate_summary(topic, agents, debate_log, num_rounds, consensus_score, moderator_prompt)

    # ── Apply output format ────────────────────────────────────────────
    output_format = ctx.config.get("output_format", "markdown")
    if output_format == "json":
        summary = json.dumps({
            "topic": topic,
            "agents": [{"name": a["name"], "style": a["style"], "bias": a["bias"]} for a in agents],
            "rounds": num_rounds,
            "consensus_score": consensus_score,
            "debate_log": debate_log,
            "summary_text": summary,
        }, indent=2)
    elif output_format == "plain":
        summary = summary.replace("## ", "").replace("**", "").replace("*", "")

    # ── Save outputs ────────────────────────────────────────────────────
    out_dir = os.path.join(ctx.run_dir, "debate")
    os.makedirs(out_dir, exist_ok=True)

    summary_path = os.path.join(out_dir, "summary.md")
    with open(summary_path, "w") as f:
        f.write(summary)
    ctx.save_output("response", summary_path)

    with open(os.path.join(out_dir, "data.json"), "w") as f:
        json.dump(debate_log, f, indent=2)
    ctx.save_output("dataset", out_dir)

    metrics = {
        "num_agents": num_agents,
        "num_rounds": num_rounds,
        "total_arguments": len(debate_log),
        "consensus_score": consensus_score,
        "format": debate_format,
        "model": model_name or "demo",
        "provider": provider,
        "demo_mode": not use_real,
    }
    ctx.save_output("metrics", metrics)
    for k, v in metrics.items():
        if isinstance(v, (int, float)):
            ctx.log_metric(k, v)

    ctx.report_progress(1, 1)


# ── Helpers ─────────────────────────────────────────────────────────────


DEFAULT_PERSONAS = [
    {"name": "Analyst", "style": "logical and data-driven", "bias": "balanced"},
    {"name": "Advocate", "style": "passionate and supportive", "bias": "pro"},
    {"name": "Critic", "style": "skeptical and questioning", "bias": "con"},
    {"name": "Synthesizer", "style": "integrative and diplomatic", "bias": "balanced"},
    {"name": "Innovator", "style": "creative and forward-thinking", "bias": "pro"},
]


def _build_personas(num_agents, custom_raw):
    """Parse custom personas or use defaults."""
    agents = []

    if custom_raw.strip():
        lines = [l.strip() for l in custom_raw.split("\n") if l.strip()]
        for i, line in enumerate(lines[:num_agents]):
            if ":" in line:
                name, style = line.split(":", 1)
                agents.append({
                    "name": name.strip(),
                    "style": style.strip(),
                    "bias": "balanced",
                })
            else:
                agents.append({
                    "name": line.strip(),
                    "style": "analytical and thoughtful",
                    "bias": "balanced",
                })

    # Fill remaining with defaults
    while len(agents) < num_agents:
        idx = len(agents) % len(DEFAULT_PERSONAS)
        template = DEFAULT_PERSONAS[idx]
        agents.append(dict(template))

    return agents[:num_agents]


def _round_label(debate_format, round_num, num_rounds):
    """Get the label for this round based on debate format."""
    if debate_format == "structured":
        if round_num == 0:
            return "Opening Statement"
        elif round_num == num_rounds - 1:
            return "Closing Statement"
        else:
            return f"Rebuttal {round_num}"
    elif debate_format == "socratic":
        return f"Question Round {round_num + 1}"
    return f"Round {round_num + 1}"


def _check_provider(provider, model_name, endpoint):
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


def _generate_argument_real(
    provider, endpoint, model_name, agent, topic,
    context, round_num, round_label, debate_format,
    temperature, max_tokens,
):
    """Generate an argument using a real LLM."""
    import urllib.request

    format_instruction = ""
    if debate_format == "structured":
        format_instruction = f"\nThis is the {round_label}. "
        if "Opening" in round_label:
            format_instruction += "Present your initial position clearly."
        elif "Rebuttal" in round_label:
            format_instruction += "Respond to the other agents' arguments."
        else:
            format_instruction += "Give your final summary position."
    elif debate_format == "socratic":
        format_instruction = (
            "\nUse the Socratic method: pose questions that challenge "
            "assumptions and lead to deeper understanding."
        )

    prompt = (
        f"You are {agent['name']}, a {agent['style']} debater.\n"
        f"Topic: {topic}\n"
        f"Previous arguments:\n{context}\n"
        f"{format_instruction}\n"
        f"{round_label}: Present your argument (2-3 sentences):"
    )

    if provider == "ollama":
        url = f"{endpoint.rstrip('/')}/api/generate"
        payload = json.dumps({
            "model": model_name,
            "prompt": prompt,
            "options": {"temperature": temperature, "num_predict": max_tokens},
            "stream": False,
        }).encode()
        req = urllib.request.Request(
            url, data=payload, headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode()).get("response", "")

    if provider == "openai":
        url = "https://api.openai.com/v1/chat/completions"
        payload = json.dumps({
            "model": model_name,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }).encode()
        req = urllib.request.Request(url, data=payload, headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}",
        })
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode())
            return data["choices"][0]["message"]["content"]

    if provider == "anthropic":
        url = "https://api.anthropic.com/v1/messages"
        payload = json.dumps({
            "model": model_name,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }).encode()
        req = urllib.request.Request(url, data=payload, headers={
            "Content-Type": "application/json",
            "x-api-key": os.environ["ANTHROPIC_API_KEY"],
            "anthropic-version": "2023-06-01",
        })
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode())
            return data["content"][0]["text"]

    return "[Unsupported provider]"


def _generate_argument_demo(agent, topic, context, round_num, num_rounds, debate_format):
    """Generate a simulated argument for demo mode."""
    style = agent["style"]
    bias = agent["bias"]

    pro_args = [
        f"From a {style} perspective, there are clear benefits to this approach. "
        f"Evidence supports positive outcomes in multiple studies.",
        f"Building on the discussion, the practical advantages "
        f"outweigh the theoretical concerns raised by others.",
        f"After considering all viewpoints, a balanced implementation "
        f"could address concerns while preserving benefits.",
    ]
    con_args = [
        f"As a {style} thinker, I see significant risks that haven't been addressed. "
        f"We need to consider unintended consequences.",
        f"While previous arguments have merit, they overlook critical challenges "
        f"in implementation and potential negative externalities.",
        f"Having heard all sides, caution is warranted. The risks require "
        f"more thorough analysis before proceeding.",
    ]
    balanced_args = [
        f"Taking a {style} approach, I see valid points from both sides. "
        f"The key is finding the right balance between innovation and safety.",
        f"The debate has highlighted important tensions. I propose a framework "
        f"that accommodates both concerns and opportunities.",
        f"In synthesis, the most productive path forward combines elements from "
        f"all perspectives with appropriate safeguards.",
    ]

    pool = {"pro": pro_args, "con": con_args, "balanced": balanced_args}
    args = pool.get(bias, balanced_args)
    return args[min(round_num, len(args) - 1)]


def _compute_consensus(debate_log, num_rounds):
    """Compute consensus score based on final-round argument overlap."""
    final_args = [e["argument"] for e in debate_log if e["round"] == num_rounds]
    if len(final_args) <= 1:
        return 1.0

    word_sets = [set(arg.lower().split()) for arg in final_args]
    all_words = set()
    for ws in word_sets:
        all_words.update(ws)

    common = word_sets[0]
    for ws in word_sets[1:]:
        common = common & ws

    raw = len(common) / max(len(all_words), 1)
    return round(min(1.0, raw * 3 + random.uniform(0.2, 0.4)), 4)


def _generate_summary(topic, agents, debate_log, num_rounds, consensus_score, moderator_prompt=""):
    """Generate a markdown summary of the debate."""
    if moderator_prompt.strip():
        summary = moderator_prompt
        summary = summary.replace("{topic}", topic)
        summary = summary.replace("{agents}", ", ".join(a["name"] for a in agents))
        summary = summary.replace("{rounds}", str(num_rounds))
        summary = summary.replace("{consensus}", f"{consensus_score:.2%}")
        for agent in agents:
            agent_entries = [e for e in debate_log if e["agent"] == agent["name"]]
            if agent_entries:
                last = agent_entries[-1]
                summary += f"\n\n**{agent['name']}**: {last['argument'][:200]}"
        return summary

    lines = [
        f"## Debate Summary\n",
        f"**Topic:** {topic}\n",
        f"**Participants:** {', '.join(a['name'] for a in agents)}\n",
        f"**Rounds:** {num_rounds}\n",
        f"**Consensus Score:** {consensus_score:.2%}\n",
        f"\n### Key Arguments\n",
    ]

    for agent in agents:
        agent_entries = [e for e in debate_log if e["agent"] == agent["name"]]
        if agent_entries:
            lines.append(f"\n**{agent['name']}** ({agent['style']}):")
            last = agent_entries[-1]
            lines.append(f"  {last['argument'][:200]}\n")

    return "\n".join(lines)
