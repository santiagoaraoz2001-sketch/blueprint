"""Agentic Review Loop — LLM-as-judge iterative refinement until quality threshold is met."""

import json
import os
import re
import urllib.request
import urllib.error
from datetime import datetime, timezone


def _call_ollama(base_url, model_name, prompt, ctx, temperature=0.1, system_prompt=""):
    """Call Ollama API for judging."""
    url = f"{base_url}/api/generate"
    body = {
        "model": model_name,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": temperature},
    }
    if system_prompt:
        body["system"] = system_prompt
    payload = json.dumps(body).encode("utf-8")

    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            result = json.loads(response.read().decode("utf-8"))
            return result.get("response", "")
    except Exception as e:
        ctx.log_message(f"Ollama call failed: {e}")
        return None


def _call_openai(api_key, model_name, prompt, ctx, temperature=0.1, system_prompt=""):
    """Call OpenAI API for judging."""
    url = "https://api.openai.com/v1/chat/completions"
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    payload = json.dumps({
        "model": model_name or "gpt-4o-mini",
        "messages": messages,
        "temperature": temperature,
        "max_tokens": 1024,
    }).encode("utf-8")

    req = urllib.request.Request(url, data=payload, headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    })
    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            result = json.loads(response.read().decode("utf-8"))
            return result["choices"][0]["message"]["content"]
    except Exception as e:
        ctx.log_message(f"OpenAI call failed: {e}")
        return None


def _call_anthropic(api_key, model_name, prompt, ctx, temperature=0.1, system_prompt=""):
    """Call Anthropic API for judging."""
    url = "https://api.anthropic.com/v1/messages"
    body = {
        "model": model_name or "claude-sonnet-4-20250514",
        "max_tokens": 1024,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system_prompt:
        body["system"] = system_prompt
    if temperature > 0:
        body["temperature"] = temperature
    payload = json.dumps(body).encode("utf-8")

    req = urllib.request.Request(url, data=payload, headers={
        "Content-Type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    })
    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            result = json.loads(response.read().decode("utf-8"))
            return result["content"][0]["text"]
    except Exception as e:
        ctx.log_message(f"Anthropic call failed: {e}")
        return None


def _call_judge(provider, model_name, api_key, base_url, prompt, ctx, temperature=0.1, system_prompt=""):
    """Dispatch to the appropriate LLM provider."""
    if provider == "ollama":
        return _call_ollama(base_url or "http://localhost:11434", model_name or "llama3.2", prompt, ctx, temperature=temperature, system_prompt=system_prompt)
    elif provider == "openai":
        if not api_key:
            api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            ctx.log_message("WARNING: No OpenAI API key provided")
            return None
        return _call_openai(api_key, model_name, prompt, ctx, temperature=temperature, system_prompt=system_prompt)
    elif provider == "anthropic":
        if not api_key:
            api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            ctx.log_message("WARNING: No Anthropic API key provided")
            return None
        return _call_anthropic(api_key, model_name, prompt, ctx, temperature=temperature, system_prompt=system_prompt)
    else:
        ctx.log_message(f"Unknown provider: {provider}")
        return None


def _extract_score(response_text):
    """Extract a numeric score (0-1) from the judge's response.

    Looks for patterns like:
      - "Score: 0.85"
      - "0.85/1.0"
      - "85/100"
      - Just a decimal number on its own line
    """
    if not response_text:
        return None

    # Pattern: "score: X.XX" or "Score: X.XX"
    match = re.search(r'[Ss]core:\s*([\d.]+)', response_text)
    if match:
        val = float(match.group(1))
        return val if val <= 1.0 else val / 100.0

    # Pattern: X/100
    match = re.search(r'(\d+(?:\.\d+)?)\s*/\s*100', response_text)
    if match:
        return float(match.group(1)) / 100.0

    # Pattern: X.XX/1 or X.XX/1.0
    match = re.search(r'([\d.]+)\s*/\s*1(?:\.0)?(?:\s|$)', response_text)
    if match:
        val = float(match.group(1))
        if val <= 1.0:
            return val

    # Last resort: find any decimal between 0 and 1
    matches = re.findall(r'\b(0\.\d+|1\.0|0|1)\b', response_text)
    if matches:
        return float(matches[-1])

    return None


def run(ctx):
    max_iterations = int(ctx.config.get("max_iterations", 3))
    quality_threshold = float(ctx.config.get("quality_threshold", 0.8))
    judge_prompt = ctx.config.get("judge_prompt", "Evaluate the quality of this output on a scale of 0-1.")
    rubric_scoring = ctx.config.get("rubric_scoring", "").strip()
    model_provider = ctx.config.get("model_provider", "ollama")
    model_name = ctx.config.get("model_name", "")
    api_key = ctx.config.get("api_key", "").strip()
    base_url = ctx.config.get("base_url", "http://localhost:11434").strip()
    refinement_prompt = ctx.config.get("refinement_prompt",
        "The previous output scored {score}. Here is the judge's feedback:\n{feedback}\n\n"
        "Please improve the output to address the feedback. Original output:\n{output}")
    system_prompt = ctx.config.get("system_prompt", "").strip()
    temperature = float(ctx.config.get("temperature", 0.1))
    early_stop_patience = int(ctx.config.get("early_stop_patience", 0))
    save_all_iterations = ctx.config.get("save_all_iterations", False)
    output_format = ctx.config.get("output_format", "text").lower().strip()

    # ---- Load optional model input (overrides config if connected) ----
    try:
        model_input = ctx.resolve_model_info("model")
        if model_input:
            model_info = model_input
            if isinstance(model_info, dict):
                if model_info.get("provider") and not model_provider:
                    model_provider = model_info["provider"]
                if model_info.get("model_name") and not model_name:
                    model_name = model_info["model_name"]
                if model_info.get("model_id") and not model_name:
                    model_name = model_info["model_id"]
                if model_info.get("api_key") and not api_key:
                    api_key = model_info["api_key"]
                if model_info.get("base_url") and not base_url:
                    base_url = model_info["base_url"]
                ctx.log_message(f"Model input connected: overriding with {model_info.get('provider', '')}/{model_info.get('model_name', model_info.get('model_id', ''))}")
    except (ValueError, Exception):
        pass

    ctx.log_message(f"Agentic Review Loop: max_iter={max_iterations}, threshold={quality_threshold}")
    ctx.log_message(f"Judge: {model_provider}/{model_name or '(default)'}")
    ctx.report_progress(0, max_iterations + 1)

    # ---- Load input data ----
    raw_data = ctx.resolve_as_data("data")
    if not raw_data:
        raise ValueError("No data provided. Connect a 'data' input.")
    current_output = raw_data

    # Convert to string for LLM processing
    if not isinstance(current_output, str):
        current_output_str = json.dumps(current_output, indent=2, default=str)
    else:
        current_output_str = current_output

    iteration_log = []
    final_score = 0.0
    best_output = current_output_str
    best_score = 0.0
    no_improve_count = 0
    prev_score = -1.0

    for iteration in range(1, max_iterations + 1):
        ctx.report_progress(iteration, max_iterations + 1)
        ctx.log_message(f"--- Iteration {iteration}/{max_iterations} ---")

        # Build judge prompt
        full_judge_prompt = judge_prompt
        if rubric_scoring:
            full_judge_prompt += f"\n\nScoring rubric:\n{rubric_scoring}"
        full_judge_prompt += (
            f"\n\nOutput to evaluate:\n{current_output_str[:4000]}"
            f"\n\nRespond with your evaluation and end with 'Score: X.XX' where X.XX is between 0 and 1."
        )

        # Call judge
        judge_response = _call_judge(model_provider, model_name, api_key, base_url, full_judge_prompt, ctx,
                                     temperature=temperature, system_prompt=system_prompt)
        if judge_response is None:
            ctx.log_message(f"Judge call failed on iteration {iteration} — stopping")
            break

        score = _extract_score(judge_response)
        if score is None:
            ctx.log_message(f"Could not extract score from judge response — defaulting to 0.5")
            score = 0.5

        ctx.log_message(f"Iteration {iteration} score: {score:.3f} (threshold: {quality_threshold})")
        ctx.log_metric(f"iteration_{iteration}_score", score)

        iteration_record = {
            "iteration": iteration,
            "score": score,
            "judge_feedback": judge_response[:1000],
            "output_preview": current_output_str[:500],
        }
        if save_all_iterations:
            iteration_record["full_output"] = current_output_str
        iteration_log.append(iteration_record)

        if score > best_score:
            best_score = score
            best_output = current_output_str

        final_score = score

        # Check if we've met the threshold
        if score >= quality_threshold:
            ctx.log_message(f"Quality threshold met at iteration {iteration}! ({score:.3f} >= {quality_threshold})")
            break

        # Early stop: if score hasn't improved for `early_stop_patience` consecutive iterations
        if early_stop_patience > 0:
            if score <= prev_score + 1e-6:
                no_improve_count += 1
                if no_improve_count >= early_stop_patience:
                    ctx.log_message(f"Early stop: score has not improved for {early_stop_patience} iterations")
                    break
            else:
                no_improve_count = 0
        prev_score = score

        # Not at threshold yet — request refinement
        if iteration < max_iterations:
            refine_prompt = refinement_prompt.replace("{score}", f"{score:.3f}")
            refine_prompt = refine_prompt.replace("{feedback}", judge_response[:2000])
            refine_prompt = refine_prompt.replace("{output}", current_output_str[:3000])

            refined = _call_judge(model_provider, model_name, api_key, base_url, refine_prompt, ctx,
                                  temperature=temperature, system_prompt=system_prompt)
            if refined:
                current_output_str = refined
                ctx.log_message(f"Output refined for next iteration")
            else:
                ctx.log_message("Refinement call failed — keeping current output")

    # ---- Produce outputs ----
    ctx.report_progress(max_iterations + 1, max_iterations + 1)

    passed = final_score >= quality_threshold
    score_report = {
        "final_score": final_score,
        "best_score": best_score,
        "quality_threshold": quality_threshold,
        "passed": passed,
        "iterations_used": len(iteration_log),
        "max_iterations": max_iterations,
        "iteration_log": iteration_log,
    }

    report_path = os.path.join(ctx.run_dir, "review_loop_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(score_report, f, indent=2, default=str, ensure_ascii=False)

    # Use best output (highest scoring iteration)
    final_output = best_output
    if output_format == "json":
        try:
            final_output = json.loads(best_output)
            ctx.log_message("Output parsed as JSON")
        except (json.JSONDecodeError, ValueError):
            ctx.log_message("Output is not valid JSON — returning as text")
    ctx.save_output("refined_output", final_output)
    ctx.save_output("score_report", score_report)
    ctx.save_artifact("review_loop_report", report_path)

    ctx.log_metric("final_score", final_score)
    ctx.log_metric("best_score", best_score)
    ctx.log_metric("iterations_used", len(iteration_log))
    ctx.log_metric("passed", 1.0 if passed else 0.0)

    if passed:
        ctx.log_message(f"PASSED: final score {final_score:.3f} >= {quality_threshold}")
    else:
        ctx.log_message(f"DID NOT PASS: best score {best_score:.3f} < {quality_threshold} after {len(iteration_log)} iterations")

    ctx.log_message("Agentic Review Loop complete.")
