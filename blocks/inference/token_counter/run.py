"""Token Counter — count and estimate tokens for text.

Workflows:
  1. Cost estimation: text -> token count -> cost calculation
  2. Context window check: text -> count -> fits in model context?
  3. Prompt optimization: draft prompt -> count -> trim to fit
  4. Dataset analysis: text column -> token distribution stats
  5. Chunking preparation: text -> count -> plan chunk boundaries
"""

import json
import os


def run(ctx):
    tokenizer_type = ctx.config.get("tokenizer", "auto")
    model_name = ctx.config.get("model_name", "gpt-4o")
    context_window = int(ctx.config.get("context_window", 0))
    output_cost_per_1k = float(ctx.config.get("output_cost_per_1k_tokens", 0))

    ctx.report_progress(0, 3)

    # Load text
    text = ""
    if ctx.inputs.get("text"):
        data = ctx.load_input("text")
        if isinstance(data, str):
            if os.path.isfile(data):
                with open(data, "r", encoding="utf-8", errors="ignore") as f:
                    text = f.read()
            else:
                text = data
        elif isinstance(data, dict):
            text = json.dumps(data)
        elif isinstance(data, list):
            text = json.dumps(data)

    if not text:
        raise ValueError("No input text to count tokens for")

    ctx.log_message(f"Counting tokens: {len(text)} chars, tokenizer={tokenizer_type}")
    ctx.report_progress(1, 3)

    token_count = 0
    method_used = "estimate"

    # Try tiktoken
    if tokenizer_type in ("auto", "tiktoken"):
        try:
            import tiktoken
            try:
                enc = tiktoken.encoding_for_model(model_name)
            except KeyError:
                enc = tiktoken.get_encoding("cl100k_base")
            tokens = enc.encode(text)
            token_count = len(tokens)
            method_used = "tiktoken"
            ctx.log_message(f"Used tiktoken ({enc.name})")
            ctx.log_metric("simulation_mode", 0.0)
        except ImportError:
            if tokenizer_type == "tiktoken":
                ctx.log_message("tiktoken not installed. Run: pip install tiktoken")

    # Try transformers tokenizer
    if method_used == "estimate" and tokenizer_type in ("auto", "transformers"):
        try:
            from transformers import AutoTokenizer
        except ImportError as e:
            from backend.block_sdk.exceptions import BlockDependencyError
            missing = str(e).split("'")[-2] if "'" in str(e) else str(e)
            raise BlockDependencyError(
                missing,
                f"Required library not installed: {e}",
                install_hint="pip install transformers",
            )
        try:
            tokenizer = AutoTokenizer.from_pretrained(model_name)
            tokens = tokenizer.encode(text)
            token_count = len(tokens)
            method_used = "transformers"
            ctx.log_message(f"Used transformers tokenizer for {model_name}")
            ctx.log_metric("simulation_mode", 0.0)
        except OSError:
            pass

    # Fallback: estimation
    if method_used == "estimate":
        token_count = max(1, len(text) // 4)
        method_used = "char_estimate"
        ctx.log_message("⚠️ SIMULATION MODE: No tokenizer library available. Using character-based estimation (~4 chars/token). Install tiktoken or transformers for accurate counts.")
        ctx.log_metric("simulation_mode", 1.0)

    ctx.report_progress(2, 3)

    word_count = len(text.split())
    line_count = text.count("\n") + 1
    cost_per_1k = float(ctx.config.get("cost_per_1k_tokens", 0))
    estimated_cost = round(token_count / 1000 * cost_per_1k, 6) if cost_per_1k > 0 else None

    counts = {
        "token_count": token_count,
        "char_count": len(text),
        "word_count": word_count,
        "line_count": line_count,
        "method": method_used,
        "model": model_name,
        "chars_per_token": round(len(text) / max(token_count, 1), 2),
    }
    if estimated_cost is not None:
        counts["estimated_cost"] = estimated_cost
        counts["cost_per_1k_tokens"] = cost_per_1k

    if context_window > 0:
        counts["context_window"] = context_window
        counts["fits_in_context"] = token_count <= context_window
        counts["context_utilization"] = round(token_count / context_window, 4)

    if output_cost_per_1k > 0:
        counts["output_cost_per_1k_tokens"] = output_cost_per_1k

    ctx.save_output("metrics", counts)

    # Build dataset row for chaining
    dataset_row = {
        "text": text[:500],
        "token_count": token_count,
        "character_count": len(text),
        "word_count": word_count,
        "line_count": line_count,
        "chars_per_token": counts["chars_per_token"],
        "method": method_used,
        "model": model_name,
    }
    if estimated_cost is not None:
        dataset_row["estimated_cost"] = estimated_cost
    if context_window > 0:
        dataset_row["fits_in_context"] = counts["fits_in_context"]
        dataset_row["context_utilization"] = counts["context_utilization"]

    results = [dataset_row]
    dataset_format = ctx.config.get("dataset_format", "json")
    if dataset_format == "jsonl":
        ds_path = os.path.join(ctx.run_dir, "results.jsonl")
        with open(ds_path, "w", encoding="utf-8") as f:
            for row in results:
                f.write(json.dumps(row) + "\n")
    elif dataset_format == "csv":
        import csv as _csv
        ds_path = os.path.join(ctx.run_dir, "results.csv")
        if results:
            keys = list(results[0].keys())
            with open(ds_path, "w", newline="", encoding="utf-8") as f:
                writer = _csv.DictWriter(f, fieldnames=keys)
                writer.writeheader()
                writer.writerows(results)
        else:
            with open(ds_path, "w") as f:
                f.write("")
    else:
        ds_path = os.path.join(ctx.run_dir, "results.json")
        with open(ds_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)
    ctx.save_output("dataset", ds_path)

    breakdown = (
        f"Tokens: {token_count:,}\n"
        f"Characters: {len(text):,}\n"
        f"Words: {word_count:,}\n"
        f"Lines: {line_count:,}\n"
        f"Chars/Token: {counts['chars_per_token']}\n"
        f"Method: {method_used}"
    )
    out_path = os.path.join(ctx.run_dir, "breakdown.txt")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(breakdown)
    ctx.save_output("text", out_path)

    ctx.log_metric("token_count", token_count)
    ctx.log_metric("char_count", len(text))
    ctx.log_message(f"Token count: {token_count:,} ({method_used})")
    ctx.report_progress(3, 3)
