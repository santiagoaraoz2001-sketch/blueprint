"""Loop Controller — orchestrates iterative pipeline execution.

The actual loop iteration is handled by the executor. This run.py handles
initial seed data loading and final result assembly.
"""

import json
import os

_DEFAULT_ITERATIONS = 10


def run(ctx):
    """Called once BEFORE the loop starts (setup) and once AFTER (teardown).

    The executor calls this in two phases:
    - Phase 1 (pre-loop): Load seed data, validate config
    - Phase 2 (post-loop): Assemble final results
    """
    phase = ctx.config.get("_executor_phase", "setup")

    if phase == "setup":
        _setup(ctx)
    elif phase == "teardown":
        _teardown(ctx)


def _setup(ctx):
    """Load seed data and emit to body output."""
    seed_data = None
    try:
        seed_data = ctx.load_input("input")
    except Exception as e:
        ctx.log_message(f"No seed data loaded ({type(e).__name__}: {e})")

    iterations = int(ctx.config.get("iterations", _DEFAULT_ITERATIONS))
    ctx.log_message(f"Loop Controller: {iterations} iterations planned")
    ctx.log_message(f"  File mode: {ctx.config.get('file_mode', 'append')}")
    ctx.log_message(f"  Context: {ctx.config.get('context_management', 'clear')}")

    # Pass seed data to body output
    if seed_data is not None:
        ctx.save_output("body", seed_data)

    ctx.report_progress(0, iterations)


def _teardown(ctx):
    """Assemble final results after all iterations complete."""
    # The executor accumulates results and passes them via _accumulated_results
    accumulated = ctx.config.get("_accumulated_results", [])
    iterations_done = ctx.config.get("_iterations_completed", 0)
    early_stopped = ctx.config.get("_early_stopped", False)

    # Save accumulated results as dataset
    result_path = os.path.join(ctx.run_dir, "results")
    os.makedirs(result_path, exist_ok=True)
    with open(os.path.join(result_path, "data.json"), "w", encoding="utf-8") as f:
        json.dump(accumulated if isinstance(accumulated, list) else [accumulated], f, indent=2, default=str)

    ctx.save_output("result", result_path)
    ctx.save_output("metrics", {
        "iterations_completed": iterations_done,
        "iterations_planned": int(ctx.config.get("iterations", _DEFAULT_ITERATIONS)),
        "early_stopped": early_stopped,
        "file_mode": ctx.config.get("file_mode", "append"),
    })

    ctx.log_metric("iterations_completed", iterations_done)
    ctx.log_message(f"Loop complete: {iterations_done} iterations" +
                     (" (early stopped)" if early_stopped else ""))
    ctx.report_progress(1, 1)
