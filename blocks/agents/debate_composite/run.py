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


def run(ctx):
    topic = ctx.inputs.get("input", "") or ctx.config.get("topic", "")
    model = ctx.config.get("model_name", "")
    rounds = ctx.config.get("rounds", 3)

    if not topic:
        from backend.block_sdk.exceptions import BlockInputError
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
        f"Debate composite: {rounds} round(s) with model={model or 'default'}, "
        f"sub-blocks={ctx.sub_block_count}"
    )
    ctx.log_metric("rounds_completed", rounds)
    ctx.log_metric("sub_blocks_created", ctx.sub_block_count)
    ctx.report_progress(1, 1)

    # Save a placeholder for consensus — the sub-pipeline's actual output
    # will overwrite this once execution completes.
    ctx.save_output("consensus", "")
