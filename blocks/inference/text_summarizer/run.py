"""Text Summarizer — summarize text using LLM, transformers pipeline, or extractive methods.

Workflows:
  1. Document summary: long doc -> summarize -> concise overview
  2. Meeting notes: transcript -> summarize -> key points
  3. Article digest: news article -> bullet points summary
  4. Research summary: paper text -> abstract-style summary
  5. Content pipeline: scraped pages -> summarize -> newsletter content
"""

import json
import os
import time
import urllib.request


def _load_text(ctx, input_name):
    data = ctx.load_input(input_name)
    if isinstance(data, str):
        if os.path.isfile(data):
            with open(data, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()
        return data
    return str(data) if data is not None else ""


def _call_llm(provider, endpoint, model_name, api_key, system_prompt, user_prompt, temperature=0.5, max_tokens=512):
    """Call LLM for summarization."""
    ep = endpoint.rstrip("/")

    if provider == "ollama":
        url = f"{ep}/api/generate"
        full_prompt = f"{system_prompt}\n\n{user_prompt}" if system_prompt else user_prompt
        payload = json.dumps({"model": model_name, "prompt": full_prompt, "stream": False,
                              "options": {"temperature": temperature, "num_predict": max_tokens}}).encode()
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=300) as resp:
            data = json.loads(resp.read().decode())
            return data.get("response", ""), data.get("eval_count", 0)

    elif provider == "mlx":
        url = f"{ep}/v1/chat/completions"
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_prompt})
        payload = json.dumps({"model": model_name, "messages": messages,
                              "temperature": temperature, "max_tokens": max_tokens}).encode()
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=300) as resp:
            data = json.loads(resp.read().decode())
            tokens = data.get("usage", {}).get("completion_tokens", 0)
            return data["choices"][0]["message"]["content"], tokens

    elif provider == "openai":
        url = f"{ep}/v1/chat/completions" if "openai" not in ep else "https://api.openai.com/v1/chat/completions"
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_prompt})
        payload = json.dumps({"model": model_name, "messages": messages,
                              "temperature": temperature, "max_tokens": max_tokens}).encode()
        req = urllib.request.Request(url, data=payload, headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        })
        with urllib.request.urlopen(req, timeout=300) as resp:
            data = json.loads(resp.read().decode())
            tokens = data.get("usage", {}).get("completion_tokens", 0)
            return data["choices"][0]["message"]["content"], tokens

    elif provider == "anthropic":
        url = "https://api.anthropic.com/v1/messages"
        messages = [{"role": "user", "content": user_prompt}]
        body = {"model": model_name, "messages": messages, "max_tokens": max_tokens, "temperature": temperature}
        if system_prompt:
            body["system"] = system_prompt
        payload = json.dumps(body).encode()
        req = urllib.request.Request(url, data=payload, headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        })
        with urllib.request.urlopen(req, timeout=300) as resp:
            data = json.loads(resp.read().decode())
            tokens = data.get("usage", {}).get("output_tokens", 0)
            content = data.get("content", [{}])
            text = content[0].get("text", "") if content else ""
            return text, tokens

    raise ValueError(f"Unknown provider: {provider}")


def run(ctx):
    method = ctx.config.get("method", "llm")
    max_length = int(ctx.config.get("max_length", 256))
    style = ctx.config.get("style", "concise")
    provider = ctx.config.get("provider", "ollama")
    model_name = ctx.config.get("model_name", "llama3.2")
    endpoint = ctx.config.get("endpoint", "http://localhost:11434")
    api_key = ctx.config.get("api_key", "")
    system_prompt = ctx.config.get("system_prompt", "")
    temperature = float(ctx.config.get("temperature", 0.5))
    max_input_chars = int(ctx.config.get("max_input_chars", 12000))

    # Resolve API keys from environment
    if not api_key:
        if provider == "openai":
            api_key = os.environ.get("OPENAI_API_KEY", "")
        elif provider == "anthropic":
            api_key = os.environ.get("ANTHROPIC_API_KEY", "")

    ctx.report_progress(0, 3)

    text = _load_text(ctx, "text")
    if not text:
        raise ValueError("No input text provided")

    ctx.log_message(f"Summarizing {len(text)} chars (method={method}, style={style})")
    ctx.report_progress(1, 3)

    summary = ""
    tokens_used = 0
    method_used = method
    start_time = time.time()

    # ── LLM-based summarization ──────────────────────────────────
    if method == "llm":
        style_instructions = {
            "concise": "Provide a concise summary in 2-3 sentences.",
            "detailed": "Provide a detailed summary covering all key points.",
            "bullet_points": "Summarize as a bulleted list of key points.",
            "abstract": "Write an abstract-style summary suitable for academic use.",
        }
        style_instr = style_instructions.get(style, style_instructions["concise"])

        if not system_prompt:
            system_prompt = "You are a precise summarization assistant. Summarize the given text accurately."

        truncated_text = text[:max_input_chars]
        if len(text) > max_input_chars:
            ctx.log_message(f"Input truncated from {len(text)} to {max_input_chars} chars (max_input_chars)")
        user_prompt = f"{style_instr}\n\nText to summarize:\n\n{truncated_text}"

        try:
            summary, tokens_used = _call_llm(provider, endpoint, model_name, api_key, system_prompt, user_prompt, temperature, max_length)
            ctx.log_message(f"LLM summarization ({provider}/{model_name})")
        except Exception as e:
            ctx.log_message(f"LLM error: {e} — falling back to extractive")
            method_used = "extractive"
            summary = _extractive_summary(text, max_length, style)

    # ── Transformers pipeline summarization ──────────────────────
    elif method == "transformers":
        try:
            from transformers import pipeline

            model_path = None
            if ctx.inputs.get("model"):
                model_data = ctx.load_input("model")
                if isinstance(model_data, str):
                    model_path = model_data

            summarizer = pipeline(
                "summarization",
                model=model_path or "sshleifer/distilbart-cnn-12-6",
                device=-1,
            )
            input_text = text[:4096]
            result = summarizer(
                input_text,
                max_length=max_length,
                min_length=min(30, max_length // 4),
                do_sample=False,
            )
            summary = result[0]["summary_text"]
            ctx.log_message("Used transformers summarization model")
        except ImportError:
            ctx.log_message("transformers not installed — using extractive fallback")
            method_used = "extractive"
            summary = _extractive_summary(text, max_length, style)
        except Exception as e:
            ctx.log_message(f"Model error: {e} — using extractive fallback")
            method_used = "extractive"
            summary = _extractive_summary(text, max_length, style)

    # ── Extractive summarization ─────────────────────────────────
    else:
        summary = _extractive_summary(text, max_length, style)
        method_used = "extractive"

    elapsed = time.time() - start_time
    ctx.report_progress(2, 3)

    # Apply output format
    output_format = ctx.config.get("output_format", "text")
    save_text = summary
    if output_format == "json":
        from datetime import datetime
        output_obj = {
            "response": summary,
            "model": model_name,
            "provider": provider,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }
        if tokens_used:
            output_obj["usage"] = {"tokens_used": tokens_used}
        save_text = json.dumps(output_obj, indent=2)

    # Save summary
    ext = "json" if output_format == "json" else "txt"
    out_path = os.path.join(ctx.run_dir, f"summary.{ext}")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(save_text)
    ctx.save_output("text", out_path)

    # Save stats
    stats = {
        "input_length": len(text),
        "output_length": len(summary),
        "compression_ratio": round(len(summary) / max(len(text), 1), 4),
        "style": style,
        "method": method_used,
        "elapsed_s": round(elapsed, 2),
    }
    if tokens_used:
        stats["tokens_used"] = tokens_used
    ctx.save_output("metrics", stats)

    ctx.log_metric("compression_ratio", stats["compression_ratio"])
    ctx.log_message(f"Summary: {len(summary)} chars ({stats['compression_ratio']:.1%} of original)")
    ctx.report_progress(3, 3)


def _extractive_summary(text, max_length, style):
    """Simple extractive summarization fallback."""
    sentences = [s.strip() for s in text.replace("\n", ". ").split(". ") if s.strip()]

    if not sentences:
        return text[:max_length * 4]

    if style == "bullet_points":
        selected = sentences[:min(5, len(sentences))]
        result = "\n".join(f"- {s.rstrip('.')}" for s in selected)
    elif style == "detailed":
        result = ". ".join(sentences[:min(8, len(sentences))])
        if not result.endswith("."):
            result += "."
    else:
        result = ". ".join(sentences[:min(3, len(sentences))])
        if not result.endswith("."):
            result += "."

    char_limit = max_length * 4
    if len(result) > char_limit:
        result = result[:char_limit].rsplit(" ", 1)[0] + "..."

    return result
