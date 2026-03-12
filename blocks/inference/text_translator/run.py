"""Text Translator — translate text between languages using LLM or transformers.

Workflows:
  1. Content localization: English docs -> translate -> Spanish/French/etc
  2. Multilingual support: user messages -> detect language -> translate -> English
  3. Batch translation: dataset of texts -> translate all -> localized dataset
  4. Quality check: source -> translate -> back-translate -> compare
  5. Subtitle translation: transcript segments -> translate -> localized subtitles
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


LANG_NAMES = {
    "auto": "Auto-detect", "en": "English", "es": "Spanish", "fr": "French",
    "de": "German", "zh": "Chinese", "ja": "Japanese", "ko": "Korean",
    "pt": "Portuguese", "ar": "Arabic", "hi": "Hindi",
}


def _call_llm(provider, endpoint, model_name, api_key, system_prompt, user_prompt):
    """Call LLM for translation."""
    ep = endpoint.rstrip("/")

    if provider == "ollama":
        url = f"{ep}/api/generate"
        full_prompt = f"{system_prompt}\n\n{user_prompt}" if system_prompt else user_prompt
        payload = json.dumps({"model": model_name, "prompt": full_prompt, "stream": False}).encode()
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
        payload = json.dumps({"model": model_name, "messages": messages}).encode()
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
        payload = json.dumps({"model": model_name, "messages": messages}).encode()
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
        body = {"model": model_name, "messages": messages, "max_tokens": 4096}
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
    source_lang = ctx.config.get("source_lang", "auto")
    target_lang = ctx.config.get("target_lang", "en")
    provider = ctx.config.get("backend", "ollama")
    model_name = ctx.config.get("model_name", "llama3.2")
    endpoint = ctx.config.get("endpoint", "http://localhost:11434")
    api_key = ctx.config.get("api_key", "")
    formality = ctx.config.get("formality", "default")
    preserve_formatting = ctx.config.get("preserve_formatting", True)
    if isinstance(preserve_formatting, str):
        preserve_formatting = preserve_formatting.lower() in ("true", "1", "yes")
    glossary = ctx.config.get("glossary", "")
    max_input_chars = int(ctx.config.get("max_input_chars", 12000))

    # Resolve API keys
    if not api_key:
        if provider == "openai":
            api_key = os.environ.get("OPENAI_API_KEY", "")
        elif provider == "anthropic":
            api_key = os.environ.get("ANTHROPIC_API_KEY", "")

    ctx.report_progress(0, 3)

    text = _load_text(ctx, "text")
    if not text:
        raise ValueError("No input text provided")

    src_name = LANG_NAMES.get(source_lang, source_lang)
    tgt_name = LANG_NAMES.get(target_lang, target_lang)
    ctx.log_message(f"Translating {len(text)} chars: {src_name} -> {tgt_name} (method={method})")
    ctx.report_progress(1, 3)

    translated = ""
    tokens_used = 0
    method_used = method
    start_time = time.time()

    # ── LLM-based translation ────────────────────────────────────
    if method == "llm":
        source_instruction = f"from {src_name}" if source_lang != "auto" else ""
        formality_instruction = f" Use a {formality} tone." if formality != "default" else ""
        formatting_instruction = " Preserve the original formatting, line breaks, and structure." if preserve_formatting else ""
        if glossary:
            glossary_instruction = f" Use this glossary for specific terms: {glossary}"
        else:
            glossary_instruction = ""
        system_prompt = (
            f"You are a professional translator. Translate the following text "
            f"{source_instruction} to {tgt_name}.{formality_instruction}{formatting_instruction}{glossary_instruction} "
            f"Provide ONLY the translation, no explanations or notes."
        )
        if len(text) > max_input_chars:
            ctx.log_message(f"Input text truncated from {len(text)} to {max_input_chars} chars")
        user_prompt = text[:max_input_chars]

        try:
            translated, tokens_used = _call_llm(
                provider, endpoint, model_name, api_key, system_prompt, user_prompt
            )
            ctx.log_message(f"LLM translation ({provider}/{model_name})")
        except Exception as e:
            ctx.log_message(f"LLM error: {e} — falling back to transformers")
            method_used = "transformers_fallback"
            translated = _transformers_translate(ctx, text, source_lang, target_lang)

    # ── Transformers-based translation ───────────────────────────
    elif method == "transformers":
        translated = _transformers_translate(ctx, text, source_lang, target_lang)
        method_used = "transformers"

    else:
        ctx.log_message(f"Unknown method '{method}' — using LLM")
        method_used = "llm"
        source_instruction = f"from {src_name}" if source_lang != "auto" else ""
        if glossary:
            glossary_instruction = f" Use this glossary for specific terms: {glossary}"
        else:
            glossary_instruction = ""
        system_prompt = f"Translate {source_instruction} to {tgt_name}.{glossary_instruction} Output ONLY the translation."
        if len(text) > max_input_chars:
            ctx.log_message(f"Input text truncated from {len(text)} to {max_input_chars} chars")
        try:
            translated, tokens_used = _call_llm(
                provider, endpoint, model_name, api_key, system_prompt, text[:max_input_chars]
            )
        except Exception as e:
            ctx.log_message(f"LLM error: {e}")
            translated = text

    elapsed = time.time() - start_time
    ctx.report_progress(2, 3)

    # Apply output format
    output_format = ctx.config.get("output_format", "text")
    save_text = translated
    if output_format == "json":
        from datetime import datetime
        output_obj = {
            "response": translated,
            "model": model_name,
            "provider": provider,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }
        if tokens_used:
            output_obj["usage"] = {"tokens_used": tokens_used}
        save_text = json.dumps(output_obj, indent=2)

    # Save translated text
    ext = "json" if output_format == "json" else "txt"
    out_path = os.path.join(ctx.run_dir, f"translated.{ext}")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(save_text)
    ctx.save_output("text", out_path)

    # Save metrics
    stats = {
        "input_length": len(text),
        "output_length": len(translated),
        "source_lang": source_lang,
        "target_lang": target_lang,
        "method": method_used,
        "elapsed_s": round(elapsed, 2),
        "length_ratio": round(len(translated) / max(len(text), 1), 4),
    }
    if tokens_used:
        stats["tokens_used"] = tokens_used
    ctx.save_output("metrics", stats)

    ctx.log_metric("output_length", len(translated))
    ctx.log_metric("elapsed_s", round(elapsed, 2))
    ctx.log_message(f"Translation complete: {len(translated)} chars in {elapsed:.1f}s")
    ctx.report_progress(3, 3)


def _transformers_translate(ctx, text, source_lang, target_lang):
    """Translate using Helsinki-NLP MarianMT models via transformers."""
    try:
        from transformers import pipeline

        model_path = None
        if ctx.inputs.get("model"):
            model_data = ctx.load_input("model")
            if isinstance(model_data, str):
                model_path = model_data

        if not model_path:
            src = source_lang if source_lang != "auto" else "en"
            model_path = f"Helsinki-NLP/opus-mt-{src}-{target_lang}"

        translator = pipeline("translation", model=model_path, device=-1)

        chunks = [text[i:i + 512] for i in range(0, len(text), 512)]
        parts = []
        for i, chunk in enumerate(chunks):
            result = translator(chunk)
            parts.append(result[0]["translation_text"])
            ctx.report_progress(1 + (i + 1) / max(len(chunks), 1), 3)

        translated = " ".join(parts)
        ctx.log_message("Used transformers translation model")
        return translated

    except ImportError:
        ctx.log_message("transformers not installed — returning original text")
        return text
    except Exception as e:
        ctx.log_message(f"Translation model error: {e} — returning original text")
        return text
