"""Multi-Agent Debate — multiple agents debate a topic to reach consensus.

Uses connected LLM Inference block for all model calls via shared utilities.
"""

import json
import os
import time
import random

from blocks.inference._inference_utils import call_inference

try:
    from backend.block_sdk.exceptions import (
        BlockConfigError, BlockInputError, BlockDataError,
        BlockDependencyError, BlockExecutionError,
    )
except ImportError:
    class BlockConfigError(ValueError):
        def __init__(self, field, message, **kw): super().__init__(message)
    class BlockInputError(ValueError):
        def __init__(self, message, **kw): super().__init__(message)
    class BlockDataError(ValueError):
        pass
    class BlockDependencyError(ImportError):
        def __init__(self, dep, message="", **kw): super().__init__(message or dep)
    class BlockExecutionError(RuntimeError):
        def __init__(self, message, **kw): super().__init__(message)


def run(ctx):
    # ── Config ──────────────────────────────────────────────────────────
    num_agents = int(ctx.config.get("num_agents", 3))
    num_rounds = int(ctx.config.get("num_rounds", 3))
    temperature = float(ctx.config.get("temperature", 0.7))
    max_tokens = int(ctx.config.get("max_tokens", 256))
    debate_format = ctx.config.get("format", "free_form")
    custom_personas_raw = ctx.config.get("custom_personas", "")
    seed = int(ctx.config.get("seed", 42))
    moderator_prompt = ctx.config.get("moderator_prompt", "")

    random.seed(seed)

    # ── Load LLM config from connected block ─────────────────────────
    llm_config = None
    try:
        llm_config = ctx.load_input("llm")
    except (ValueError, Exception):
        pass

    if llm_config and isinstance(llm_config, dict):
        framework = llm_config.get("framework", "ollama")
        model_name = llm_config.get("model", "")
        inf_config = llm_config.get("config", {})
        inf_config["max_tokens"] = max_tokens
        inf_config["temperature"] = temperature
    else:
        framework = ""
        model_name = ""
        inf_config = {}

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

    # ── Check if real inference is available ──────────────────────────
    use_real = bool(llm_config and model_name)
    if not use_real:
        ctx.log_message("Demo mode: no LLM connected or no model specified.")

    # ── Build agent personas ────────────────────────────────────────────
    agents = _build_personas(num_agents, custom_personas_raw)

    # ── Run debate ──────────────────────────────────────────────────────
    debate_log = []

    for round_num in range(num_rounds):
        ctx.log_message(f"\n=== Round {round_num + 1}/{num_rounds} ===")
        round_label = _round_label(debate_format, round_num, num_rounds)

        for agent in agents:
            prev_args = []
            for entry in debate_log[-(num_agents * 2):]:
                if entry["agent"] != agent["name"]:
                    prev_args.append(f"{entry['agent']}: {entry['argument'][:150]}")
            context = "\n".join(prev_args) if prev_args else "This is the opening round."

            if use_real:
                argument = _generate_argument_real(
                    framework, model_name, inf_config,
                    agent, topic, context, round_label, debate_format,
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
        "framework": framework or "demo",
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
    agents = []
    if custom_raw.strip():
        lines = [l.strip() for l in custom_raw.split("\n") if l.strip()]
        for i, line in enumerate(lines[:num_agents]):
            if ":" in line:
                name, style = line.split(":", 1)
                agents.append({"name": name.strip(), "style": style.strip(), "bias": "balanced"})
            else:
                agents.append({"name": line.strip(), "style": "analytical and thoughtful", "bias": "balanced"})
    while len(agents) < num_agents:
        idx = len(agents) % len(DEFAULT_PERSONAS)
        agents.append(dict(DEFAULT_PERSONAS[idx]))
    return agents[:num_agents]


def _round_label(debate_format, round_num, num_rounds):
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


def _generate_argument_real(framework, model_name, inf_config, agent, topic, context, round_label, debate_format):
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
        format_instruction = "\nUse the Socratic method: pose questions that challenge assumptions and lead to deeper understanding."

    prompt = (
        f"You are {agent['name']}, a {agent['style']} debater.\n"
        f"Topic: {topic}\nPrevious arguments:\n{context}\n"
        f"{format_instruction}\n{round_label}: Present your argument (2-3 sentences):"
    )
    try:
        response, _ = call_inference(framework, model_name, prompt, config=inf_config)
        return response
    except Exception as e:
        return f"[Error generating argument: {e}]"


def _generate_argument_demo(agent, topic, context, round_num, num_rounds, debate_format):
    style = agent["style"]
    bias = agent["bias"]
    pro_args = [
        f"From a {style} perspective, there are clear benefits to this approach. Evidence supports positive outcomes in multiple studies.",
        f"Building on the discussion, the practical advantages outweigh the theoretical concerns raised by others.",
        f"After considering all viewpoints, a balanced implementation could address concerns while preserving benefits.",
    ]
    con_args = [
        f"As a {style} thinker, I see significant risks that haven't been addressed. We need to consider unintended consequences.",
        f"While previous arguments have merit, they overlook critical challenges in implementation and potential negative externalities.",
        f"Having heard all sides, caution is warranted. The risks require more thorough analysis before proceeding.",
    ]
    balanced_args = [
        f"Taking a {style} approach, I see valid points from both sides. The key is finding the right balance between innovation and safety.",
        f"The debate has highlighted important tensions. I propose a framework that accommodates both concerns and opportunities.",
        f"In synthesis, the most productive path forward combines elements from all perspectives with appropriate safeguards.",
    ]
    pool = {"pro": pro_args, "con": con_args, "balanced": balanced_args}
    args = pool.get(bias, balanced_args)
    return args[min(round_num, len(args) - 1)]


def _compute_consensus(debate_log, num_rounds):
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
