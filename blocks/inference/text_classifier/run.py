"""Text Classifier — classify text using LLM, zero-shot transformers, few-shot, or keyword rules.

Workflows:
  1. Sentiment analysis: reviews -> classify -> positive/negative/neutral
  2. Content moderation: user posts -> classify -> safe/unsafe/review
  3. Intent detection: support tickets -> classify -> billing/technical/general
  4. Topic labeling: articles -> classify -> categories
  5. Spam filtering: emails -> classify -> spam/ham
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


def _call_llm(provider, endpoint, model_name, api_key, system_prompt, user_prompt):
    """Call LLM for classification."""
    ep = endpoint.rstrip("/")

    if provider == "ollama":
        url = f"{ep}/api/generate"
        full_prompt = f"{system_prompt}\n\n{user_prompt}" if system_prompt else user_prompt
        payload = json.dumps({"model": model_name, "prompt": full_prompt, "stream": False}).encode()
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=300) as resp:
            data = json.loads(resp.read().decode())
            return data.get("response", "")

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
            return data["choices"][0]["message"]["content"]

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
            return data["choices"][0]["message"]["content"]

    elif provider == "anthropic":
        url = "https://api.anthropic.com/v1/messages"
        messages = [{"role": "user", "content": user_prompt}]
        body = {"model": model_name, "messages": messages, "max_tokens": 1024}
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
            content = data.get("content", [{}])
            return content[0].get("text", "") if content else ""

    raise ValueError(f"Unknown provider: {provider}")


def run(ctx):
    categories_str = ctx.config.get("categories", "positive,negative,neutral")
    method = ctx.config.get("method", "llm")
    provider = ctx.config.get("backend", ctx.config.get("provider", "ollama"))
    model_name = ctx.config.get("model_name", "llama3.2")
    endpoint = ctx.config.get("endpoint", "http://localhost:11434")
    api_key = ctx.config.get("api_key", "")
    input_column = ctx.config.get("input_column", "text")
    label_column = ctx.config.get("label_column", "label")
    num_examples = int(ctx.config.get("num_examples", 5))
    multi_label = ctx.config.get("multi_label", False)
    if isinstance(multi_label, str):
        multi_label = multi_label.lower() in ("true", "1", "yes")
    confidence_threshold = float(ctx.config.get("confidence_threshold", 0.5))
    classification_instructions = ctx.config.get("classification_instructions", "")
    output_format = ctx.config.get("output_format", "text")

    # Resolve API keys
    if not api_key:
        if provider == "openai":
            api_key = os.environ.get("OPENAI_API_KEY", "")
        elif provider == "anthropic":
            api_key = os.environ.get("ANTHROPIC_API_KEY", "")

    categories = [c.strip() for c in categories_str.split(",") if c.strip()]
    if not categories:
        raise ValueError("No categories configured")

    ctx.report_progress(0, 3)

    text = _load_text(ctx, "text")
    if not text:
        raise ValueError("No input text provided")

    ctx.log_message(f"Classifying {len(text)} chars into {len(categories)} categories ({method})")
    ctx.report_progress(1, 3)

    scores = {}
    start_time = time.time()
    method_used = method

    # ── LLM-based classification ─────────────────────────────────
    if method == "llm":
        categories_list = ", ".join(categories)
        if multi_label:
            system_prompt = (
                f"You are a text classifier. Classify the given text into ALL applicable categories from: {categories_list}.\n"
                f"Respond with ONLY a JSON object: {{\"labels\": [\"<cat1>\", \"<cat2>\"], \"confidences\": [<0-1>, <0-1>]}}\n"
                f"Do not include any other text."
            )
        else:
            system_prompt = (
                f"You are a text classifier. Classify the given text into exactly one of these categories: {categories_list}.\n"
                f"Respond with ONLY a JSON object in this format: {{\"label\": \"<category>\", \"confidence\": <0-1>}}\n"
                f"Do not include any other text."
            )
        if classification_instructions:
            system_prompt += f"\n\nAdditional instructions: {classification_instructions}"
        user_prompt = f"Classify this text:\n\n{text[:8000]}"

        try:
            response = _call_llm(provider, endpoint, model_name, api_key, system_prompt, user_prompt)
            scores = _parse_llm_classification(response, categories)
            ctx.log_message(f"LLM classification ({provider}/{model_name})")
        except Exception as e:
            ctx.log_message(f"LLM error: {e} — falling back to keyword")
            method_used = "keyword"
            scores = _keyword_classify(text, categories)

    # ── Zero-shot transformers classification ────────────────────
    elif method == "zero_shot":
        try:
            from transformers import pipeline

            model_path = None
            if ctx.inputs.get("model"):
                model_data = ctx.load_input("model")
                if isinstance(model_data, str):
                    model_path = model_data

            classifier = pipeline(
                "zero-shot-classification",
                model=model_path or "facebook/bart-large-mnli",
                device=-1,
            )
            result = classifier(text[:10000], categories)
            for label, score in zip(result["labels"], result["scores"]):
                scores[label] = round(score, 4)
            ctx.log_message("Used transformers zero-shot classification")
        except ImportError:
            ctx.log_message("transformers not installed — using keyword fallback")
            method_used = "keyword"
            scores = _keyword_classify(text, categories)
        except Exception as e:
            ctx.log_message(f"Model error: {e} — using keyword fallback")
            method_used = "keyword"
            scores = _keyword_classify(text, categories)

    # ── Few-shot LLM classification ──────────────────────────────
    elif method == "few_shot":
        examples_text = ""
        if ctx.inputs.get("dataset"):
            try:
                ds_path = ctx.load_input("dataset")
                data_file = os.path.join(ds_path, "data.json") if os.path.isdir(ds_path) else ds_path
                with open(data_file, "r", encoding="utf-8") as f:
                    examples = json.load(f)
                examples = examples[:num_examples]
                example_lines = []
                for ex in examples:
                    if isinstance(ex, dict):
                        ex_text = str(ex.get(input_column, ""))
                        ex_label = str(ex.get(label_column, ""))
                        if ex_text and ex_label:
                            example_lines.append(f"Text: {ex_text}\nCategory: {ex_label}")
                examples_text = "\n\n".join(example_lines)
                ctx.log_message(f"Loaded {len(example_lines)} few-shot examples")
            except Exception as e:
                ctx.log_message(f"Could not load examples: {e}")

        categories_list = ", ".join(categories)
        system_prompt = (
            f"You are a text classifier. Classify text into one of: {categories_list}.\n"
            f"Respond with ONLY a JSON object: {{\"label\": \"<category>\", \"confidence\": <0-1>}}"
        )
        if classification_instructions:
            system_prompt += f"\n\nAdditional instructions: {classification_instructions}"

        if examples_text:
            user_prompt = f"Examples:\n\n{examples_text}\n\nNow classify this text:\n\n{text[:8000]}"
        else:
            user_prompt = f"Classify this text:\n\n{text[:8000]}"

        try:
            response = _call_llm(provider, endpoint, model_name, api_key, system_prompt, user_prompt)
            scores = _parse_llm_classification(response, categories)
            ctx.log_message(f"Few-shot LLM classification ({provider}/{model_name})")
        except Exception as e:
            ctx.log_message(f"LLM error: {e} — falling back to keyword")
            method_used = "keyword"
            scores = _keyword_classify(text, categories)

    # ── Keyword-based classification ─────────────────────────────
    else:
        scores = _keyword_classify(text, categories)
        method_used = "keyword"

    elapsed = time.time() - start_time
    ctx.report_progress(2, 3)

    # Determine best classification
    if multi_label:
        labels_above = {k: v for k, v in scores.items() if v >= confidence_threshold}
        best_label = ", ".join(labels_above.keys()) if labels_above else (max(scores, key=scores.get) if scores else categories[0])
    else:
        best_label = max(scores, key=scores.get) if scores else categories[0]

    # Save classification result
    result = {
        "label": best_label,
        "confidence": scores.get(best_label, 0),
        "all_scores": scores,
        "text_length": len(text),
        "method": method_used,
        "elapsed_s": round(elapsed, 2),
    }

    if output_format == "json":
        from datetime import datetime
        result["model"] = model_name
        result["provider"] = provider
        result["categories"] = categories
        result["multi_label"] = multi_label
        result["timestamp"] = datetime.now().isoformat()

    text_path = os.path.join(ctx.run_dir, "classification.json")
    with open(text_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    ctx.save_output("text", text_path)

    ctx.save_output("metrics", scores)

    ctx.log_metric("confidence", scores.get(best_label, 0))
    ctx.log_message(f"Classification: {best_label} ({scores.get(best_label, 0):.2%})")
    ctx.report_progress(3, 3)


def _parse_llm_classification(response, categories):
    """Parse LLM classification response into scores dict."""
    import re

    scores = {}
    response = response.strip()

    # Try parsing JSON
    json_match = re.search(r'\{[^}]+\}', response)
    if json_match:
        try:
            parsed = json.loads(json_match.group())
            label = parsed.get("label", parsed.get("category", ""))
            confidence = float(parsed.get("confidence", parsed.get("score", 0.9)))

            # Find closest matching category
            label_lower = label.lower()
            matched = None
            for cat in categories:
                if cat.lower() == label_lower or cat.lower() in label_lower or label_lower in cat.lower():
                    matched = cat
                    break
            if not matched:
                matched = label if label in categories else categories[0]

            for cat in categories:
                scores[cat] = round(confidence, 4) if cat == matched else round((1 - confidence) / max(len(categories) - 1, 1), 4)
            return scores
        except (json.JSONDecodeError, ValueError):
            pass

    # Fallback: look for category name in response
    response_lower = response.lower()
    for cat in categories:
        if cat.lower() in response_lower:
            for c in categories:
                scores[c] = 0.9 if c == cat else round(0.1 / max(len(categories) - 1, 1), 4)
            return scores

    # Default uniform
    uniform = round(1.0 / len(categories), 4)
    return {c: uniform for c in categories}


def _keyword_classify(text, categories):
    """Simple keyword-based classification fallback."""
    text_lower = text.lower()
    scores = {}
    for cat in categories:
        count = text_lower.count(cat.lower())
        scores[cat] = count / max(len(text_lower.split()), 1)

    total = sum(scores.values())
    if total > 0:
        scores = {k: round(v / total, 4) for k, v in scores.items()}
    else:
        uniform = round(1.0 / len(categories), 4)
        scores = {k: uniform for k in categories}

    return scores
