"""
Debate Composite — multi-agent debate built from composable sub-blocks.

Instead of a monolithic implementation, this block defines a sub-pipeline
of llm_inference blocks wired together:

    Round N:  pessimist + optimist  →  judge
              (context from prior judge feeds into next round)

The CompositeBlockContext handles sub-pipeline execution automatically.
The parent block's inputs (llm config, topic) are injected into root
child blocks by the composite executor.
"""

import json
import os

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
    topic = ctx.inputs.get("input", "") or ctx.config.get("topic", "")
    model = ctx.config.get("model_name", "")
    rounds = ctx.config.get("rounds", 3)

    # ── Load LLM config — accept llm port OR model port ───────────────
    llm_source = ""  # track where model came from for logging

    # Try llm port first (preferred — contains framework + config)
    try:
        llm_data = ctx.load_input("llm")
        if isinstance(llm_data, dict):
            if "framework" in llm_data:
                model = model or llm_data.get("model", "")
                if model:
                    llm_source = f"{llm_data.get('framework', 'unknown')} via llm port"
            elif "model_name" in llm_data or "model_id" in llm_data:
                model = model or llm_data.get("model_name", llm_data.get("model_id", ""))
                if model:
                    llm_source = f"{llm_data.get('source', 'unknown')} via llm port"
    except (ValueError, Exception):
        pass

    # Try model port as fallback (direct model_selector connection)
    if not model:
        try:
            model_data = ctx.load_input("model")
            if isinstance(model_data, dict):
                model = model_data.get("model_name", model_data.get("model_id", ""))
                if model:
                    llm_source = f"{model_data.get('source', 'unknown')} via model port"
            elif isinstance(model_data, str):
                model = model_data
                if model:
                    llm_source = "model port (string)"
        except (ValueError, Exception):
            pass

    if not model and not llm_source:
        llm_source = "config" if ctx.config.get("model_name") else "none"

    if not topic:
        raise BlockInputError(
            "No debate topic provided",
            details="Connect a text source to the 'input' port or set 'topic' in config.",
            recoverable=False,
        )

    # Build a sub-pipeline for each round of debate.
    # Each round: pessimist and optimist respond, then judge synthesizes.
    #
    # Child blocks are llm_inference blocks. Their interface:
    #   Config:  user_input, system_prompt, model_name, ...
    #   Inputs:  prompt (text), context (any), model (config)
    #   Outputs: response (text/file), metadata (metrics), llm_config (config)
    prev_judge_id = None

    for r in range(rounds):
        pessimist_id = f"pessimist_r{r}"
        optimist_id = f"optimist_r{r}"
        judge_id = f"judge_r{r}"

        round_label = f"[Round {r + 1}/{rounds}]"
        if r == 0:
            prior_context = "This is the first round of debate."
        else:
            prior_context = (
                "Consider the judge's prior synthesis and refine your position."
            )

        ctx.add_sub_block(pessimist_id, "llm_inference", {
            "model_name": model,
            "system_prompt": (
                "You are a critical pessimist. Find flaws, risks, and downsides "
                "in every argument. Be thorough but fair."
            ),
            "user_input": f"{round_label} {prior_context}\nTopic: {topic}",
        })

        ctx.add_sub_block(optimist_id, "llm_inference", {
            "model_name": model,
            "system_prompt": (
                "You are an enthusiastic optimist. Find the best interpretation, "
                "opportunities, and upsides of every argument. Be constructive."
            ),
            "user_input": f"{round_label} {prior_context}\nTopic: {topic}",
        })

        ctx.add_sub_block(judge_id, "llm_inference", {
            "model_name": model,
            "system_prompt": (
                "You are a neutral judge. Synthesize the pessimist and optimist "
                "views into a balanced assessment. Identify areas of agreement "
                "and remaining disagreements."
            ),
            "user_input": (
                f"{round_label} Synthesize the following perspectives on: {topic}"
            ),
        })

        # Wire pessimist + optimist responses → judge context.
        # llm_inference outputs "response" and accepts "context" input.
        ctx.add_sub_edge(pessimist_id, judge_id, "response", "context")
        ctx.add_sub_edge(optimist_id, judge_id, "response", "context")

        # Chain rounds: previous judge's response → current debaters' context
        if prev_judge_id:
            ctx.add_sub_edge(prev_judge_id, pessimist_id, "response", "context")
            ctx.add_sub_edge(prev_judge_id, optimist_id, "response", "context")

        prev_judge_id = judge_id

    ctx.log_message(
        f"Debate composite: {rounds} round(s) with model={model or 'default'} "
        f"(source={llm_source}), sub-blocks={ctx.sub_block_count}"
    )
    if not model:
        ctx.log_message("No model connected. Sub-blocks will use auto-detection or demo mode. "
                        "Connect a Model Selector or LLM Inference block for real output.")
    ctx.log_metric("rounds_completed", rounds)
    ctx.log_metric("sub_blocks_created", ctx.sub_block_count)

    # Save a placeholder for consensus — the sub-pipeline's actual output
    # will overwrite this once execution completes.
    ctx.save_output("consensus", "")

    # ── Save debate log as dataset ──
    debate_entries = []
    for r in range(rounds):
        debate_entries.append({
            "round": r + 1,
            "pessimist": f"pessimist_r{r}",
            "optimist": f"optimist_r{r}",
            "judge": f"judge_r{r}",
        })
    log_path = os.path.join(ctx.run_dir, "debate_log")
    os.makedirs(log_path, exist_ok=True)
    with open(os.path.join(log_path, "data.json"), "w") as f:
        json.dump(debate_entries, f, indent=2)
    ctx.save_output("dataset", log_path)

    # ── Save metrics ──
    ctx.save_output("metrics", {
        "rounds": rounds,
        "agents": 3,  # pessimist + optimist + judge per round
        "sub_blocks": ctx.sub_block_count,
        "model": model or "default",
        "demo_mode": not bool(model),
    })

    # ── Passthrough LLM config for agent chaining ──
    llm_config = None
    try:
        llm_config = ctx.inputs.get("llm")
    except (ValueError, Exception):
        pass

    if llm_config:
        ctx.save_output("llm_config", llm_config)
    else:
        ctx.save_output("llm_config", {
            "framework": "demo",
            "model": model or "demo",
            "config": {},
            "demo_mode": not bool(model),
        })

    ctx.report_progress(1, 1)
