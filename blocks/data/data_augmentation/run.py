"""Data Augmentation — apply text augmentation strategies to expand a dataset."""

import json
import os
import random
from collections import Counter, defaultdict


# ── Rule-based strategies (no model needed) ────────────────────────

_SYNONYMS = {
    "good": ["great", "excellent", "fine", "nice", "wonderful"],
    "bad": ["poor", "terrible", "awful", "dreadful", "horrible"],
    "big": ["large", "huge", "enormous", "massive", "vast"],
    "small": ["tiny", "little", "miniature", "compact", "minute"],
    "fast": ["quick", "rapid", "swift", "speedy", "hasty"],
    "slow": ["sluggish", "gradual", "unhurried", "leisurely", "delayed"],
    "happy": ["joyful", "pleased", "delighted", "glad", "cheerful"],
    "sad": ["unhappy", "sorrowful", "gloomy", "downcast", "melancholy"],
    "important": ["significant", "crucial", "vital", "essential", "critical"],
    "easy": ["simple", "straightforward", "effortless", "basic", "uncomplicated"],
    "hard": ["difficult", "tough", "challenging", "demanding", "arduous"],
}


def _synonym_swap(text, n_swaps=2):
    words = text.split()
    if len(words) < 2:
        return text
    indices = list(range(len(words)))
    random.shuffle(indices)
    swaps_done = 0
    for idx in indices:
        word_lower = words[idx].lower().strip(".,!?;:")
        if word_lower in _SYNONYMS:
            replacement = random.choice(_SYNONYMS[word_lower])
            if words[idx][0].isupper():
                replacement = replacement.capitalize()
            words[idx] = replacement
            swaps_done += 1
            if swaps_done >= n_swaps:
                break
    return " ".join(words)


def _random_insertion(text, n_inserts=1):
    words = text.split()
    if not words:
        return text
    filler_words = ["also", "very", "quite", "rather", "indeed", "certainly", "actually"]
    for _ in range(n_inserts):
        pos = random.randint(0, len(words))
        words.insert(pos, random.choice(filler_words))
    return " ".join(words)


def _random_deletion(text, p=0.1):
    words = text.split()
    if len(words) <= 2:
        return text
    remaining = [w for w in words if random.random() > p]
    return " ".join(remaining) if remaining else " ".join(words[:2])


def _random_swap(text, n_swaps=1):
    words = text.split()
    if len(words) < 2:
        return text
    for _ in range(n_swaps):
        i, j = random.sample(range(len(words)), 2)
        words[i], words[j] = words[j], words[i]
    return " ".join(words)


def _char_noise(text, p=0.02):
    chars = list(text)
    for i in range(len(chars)):
        if random.random() < p and chars[i].isalpha():
            chars[i] = random.choice("abcdefghijklmnopqrstuvwxyz")
    return "".join(chars)


_RULE_STRATEGIES = {
    "synonym_swap": _synonym_swap,
    "random_insertion": _random_insertion,
    "random_deletion": _random_deletion,
    "random_swap": _random_swap,
    "char_noise": _char_noise,
}

# Strategies that require a model
_MODEL_STRATEGIES = {"paraphrase", "back_translate", "contextual_insert"}


# ── Model-backed helpers ───────────────────────────────────────────

def _resolve_model(model_ref):
    """Extract model_name, provider, endpoint from a model input (str or dict)."""
    if isinstance(model_ref, dict):
        model_name = model_ref.get("model_name", model_ref.get("model_id", ""))
        provider = model_ref.get("backend", model_ref.get("provider", "ollama"))
        endpoint = model_ref.get("base_url", model_ref.get("endpoint", "http://localhost:11434"))
        return model_name, provider, endpoint
    # Plain string — treat as model name for default provider
    return str(model_ref), "ollama", "http://localhost:11434"


def _call_ollama(endpoint, model_name, prompt, max_tokens):
    """Call Ollama's /api/generate endpoint."""
    import urllib.request
    payload = json.dumps({
        "model": model_name,
        "prompt": prompt,
        "stream": False,
        "options": {"num_predict": max_tokens},
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{endpoint.rstrip('/')}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    return result.get("response", "").strip()


def _call_transformers(model_name, prompt, max_tokens):
    """Call a local HuggingFace transformers model."""
    try:
        from transformers import pipeline as hf_pipeline
    except ImportError as e:
        from backend.block_sdk.exceptions import BlockDependencyError
        missing = str(e).split("'")[-2] if "'" in str(e) else str(e)
        raise BlockDependencyError(
            missing,
            f"Required library not installed: {e}",
            install_hint="pip install transformers",
        )
    generator = hf_pipeline("text-generation", model=model_name, device=-1)
    out = generator(prompt, max_new_tokens=max_tokens, num_return_sequences=1, truncation=True)
    return out[0]["generated_text"].replace(prompt, "").strip()


def _call_model(model_name, provider, endpoint, prompt, max_tokens):
    """Route model call to the appropriate provider."""
    if provider == "transformers":
        return _call_transformers(model_name, prompt, max_tokens)
    # Default: Ollama (works for ollama, also usable as generic OpenAI-compat)
    return _call_ollama(endpoint, model_name, prompt, max_tokens)


def _augment_with_model(text, strategy, model_name, provider, endpoint,
                        augment_prompt, max_tokens, corpus_phrases):
    """Apply a model-backed augmentation strategy to a single text."""
    if strategy == "paraphrase":
        if augment_prompt:
            prompt = augment_prompt.replace("{text}", text)
        else:
            prompt = f"Paraphrase the following text. Output ONLY the paraphrased version, nothing else.\n\nText: {text}\n\nParaphrase:"
        result = _call_model(model_name, provider, endpoint, prompt, max_tokens)
        return result if result else text

    elif strategy == "back_translate":
        if augment_prompt:
            prompt = augment_prompt.replace("{text}", text)
        else:
            prompt = (
                f"Translate this text to French, then translate it back to English. "
                f"Output ONLY the final English version.\n\nText: {text}\n\nBack-translated:"
            )
        result = _call_model(model_name, provider, endpoint, prompt, max_tokens)
        return result if result else text

    elif strategy == "contextual_insert":
        if corpus_phrases:
            # Pick a random phrase from the corpus and ask the model to blend it
            phrase = random.choice(corpus_phrases)
            if augment_prompt:
                prompt = augment_prompt.replace("{text}", text).replace("{phrase}", phrase)
            else:
                prompt = (
                    f"Rewrite the following text, naturally incorporating this concept: \"{phrase}\". "
                    f"Output ONLY the rewritten text.\n\nOriginal: {text}\n\nRewritten:"
                )
        else:
            if augment_prompt:
                prompt = augment_prompt.replace("{text}", text)
            else:
                prompt = (
                    f"Rewrite the following text with additional contextual detail. "
                    f"Output ONLY the rewritten text.\n\nText: {text}\n\nRewritten:"
                )
        result = _call_model(model_name, provider, endpoint, prompt, max_tokens)
        return result if result else text

    return text


# ── Main ───────────────────────────────────────────────────────────

def run(ctx):
    dataset_path = ctx.load_input("dataset")

    # Read upstream dataset metadata
    _dataset_meta = {}
    try:
        _meta_input = ctx.load_input("dataset_meta")
        if isinstance(_meta_input, dict):
            _dataset_meta = _meta_input
    except (ValueError, KeyError):
        pass

    strategy = ctx.config.get("strategy", "synonym_swap")
    augment_factor = int(ctx.config.get("augment_factor", 2))
    text_column = _dataset_meta.get("text_column", ctx.config.get("text_column", "text"))
    seed = int(ctx.config.get("seed") or _dataset_meta.get("seed", 42))
    preserve_labels = ctx.config.get("preserve_labels", True)
    balance_column = ctx.config.get("balance_column", "")
    augment_prompt = ctx.config.get("augment_prompt", "")
    provider = ctx.config.get("provider", "ollama")
    endpoint = ctx.config.get("endpoint", "http://localhost:11434")
    max_tokens = int(ctx.config.get("max_tokens", 256))
    add_metadata = ctx.config.get("add_metadata", True)

    # Optional model input
    try:
        model_ref = ctx.load_input("model")
    except ValueError:
        model_ref = None

    # Optional prompt input (overrides augment_prompt config)
    try:
        prompt_input = ctx.load_input("prompt")
        if prompt_input:
            if isinstance(prompt_input, str) and os.path.isfile(prompt_input):
                with open(prompt_input, "r", encoding="utf-8") as f:
                    augment_prompt = f.read()
            else:
                augment_prompt = str(prompt_input)
            ctx.log_message(f"Using prompt input: {len(augment_prompt)} chars")
    except ValueError:
        pass

    # Optional corpus input (web scraping or supplementary data)
    corpus_phrases = []
    try:
        corpus_path = ctx.load_input("corpus")
        if corpus_path:
            corpus_file = os.path.join(corpus_path, "data.json") if os.path.isdir(corpus_path) else corpus_path
            if os.path.isfile(corpus_file):
                with open(corpus_file, "r", encoding="utf-8") as f:
                    corpus_data = json.load(f)
                # Extract text phrases from corpus rows
                for row in corpus_data:
                    if isinstance(row, dict):
                        txt = row.get(text_column, row.get("text", row.get("content", "")))
                        if isinstance(txt, str) and len(txt) > 5:
                            # Split into sentence-level phrases
                            for sent in txt.split(". "):
                                s = sent.strip()
                                if 5 < len(s) < 200:
                                    corpus_phrases.append(s)
                    elif isinstance(row, str) and len(row) > 5:
                        corpus_phrases.append(row)
                ctx.log_message(f"Loaded {len(corpus_phrases)} phrases from corpus")
    except ValueError:
        pass

    random.seed(seed)

    # Resolve model for model-backed strategies
    model_name, model_provider, model_endpoint = None, provider, endpoint

    if model_ref:
        model_name, model_provider, model_endpoint = _resolve_model(model_ref)
        # Config overrides if explicitly set
        if provider != "ollama":
            model_provider = provider
        if endpoint != "http://localhost:11434":
            model_endpoint = endpoint
        ctx.log_message(f"Model: {model_name} via {model_provider} at {model_endpoint}")

    # Load dataset
    data_file = os.path.join(dataset_path, "data.json") if os.path.isdir(dataset_path) else dataset_path
    if not os.path.isfile(data_file):
        raise FileNotFoundError(f"Dataset not found at: {dataset_path}")

    with open(data_file, "r", encoding="utf-8") as f:
        rows = json.load(f)

    if not isinstance(rows, list):
        raise ValueError("Dataset must be a JSON array")

    original_count = len(rows)
    # Support comma-separated multi-strategy for diversity
    strategies = [s.strip() for s in strategy.split(",") if s.strip()]
    if not strategies:
        strategies = ["synonym_swap"]
    multi_strategy = len(strategies) > 1

    ctx.log_message(f"Loaded {original_count} rows. Strategy: {'+'.join(strategies)}, Factor: {augment_factor}x")

    # Build augmentation function (randomly picks from pool if multi-strategy)
    def fn(text):
        chosen = random.choice(strategies) if multi_strategy else strategies[0]
        if chosen in _MODEL_STRATEGIES:
            return _augment_with_model(
                text, chosen, model_name, model_provider, model_endpoint,
                augment_prompt, max_tokens, corpus_phrases,
            )
        rule_fn = _RULE_STRATEGIES.get(chosen)
        if rule_fn is None:
            ctx.log_message(f"Unknown strategy '{chosen}', defaulting to synonym_swap")
            rule_fn = _synonym_swap
        return rule_fn(text)

    # Validate: if any strategy requires a model, ensure model is available
    has_model_strategies = any(s in _MODEL_STRATEGIES for s in strategies)
    if has_model_strategies and not model_name:
        model_strategies = [s for s in strategies if s in _MODEL_STRATEGIES]
        raise ValueError(
            f"Strategies {model_strategies} require a model input. "
            f"Connect a model block or use only rule-based strategies."
        )

    augmented = list(rows)  # keep originals
    base_rounds = max(augment_factor - 1, 0)

    # Class-balanced augmentation
    if balance_column and rows and balance_column in rows[0]:
        class_counts = Counter(r.get(balance_column) for r in rows)
        max_class_count = max(class_counts.values())
        ctx.log_message(f"Balancing by '{balance_column}': {len(class_counts)} classes, max={max_class_count}")

        target_per_class = max_class_count * augment_factor
        class_rows = defaultdict(list)
        for r in rows:
            class_rows[r.get(balance_column)].append(r)

        aug_count = 0
        for label, c_rows in class_rows.items():
            needed = target_per_class - len(c_rows)
            for i in range(max(needed, 0)):
                row = c_rows[i % len(c_rows)]
                new_row = dict(row)
                if text_column in new_row and isinstance(new_row[text_column], str):
                    new_row[text_column] = fn(new_row[text_column])
                if add_metadata:
                    new_row["_augmented"] = True
                    new_row["_aug_strategy"] = strategy
                augmented.append(new_row)
                aug_count += 1
            ctx.report_progress(list(class_rows.keys()).index(label) + 1, len(class_rows))
        ctx.log_message(f"Class-balanced: added {aug_count} augmented rows")
    else:
        for factor_idx in range(base_rounds):
            for row_idx, row in enumerate(rows):
                new_row = dict(row)
                if text_column in new_row and isinstance(new_row[text_column], str):
                    new_row[text_column] = fn(new_row[text_column])
                else:
                    for key, val in new_row.items():
                        if isinstance(val, str) and len(val) > 10:
                            new_row[key] = fn(val)
                            break
                if add_metadata:
                    new_row["_augmented"] = True
                    new_row["_aug_strategy"] = "+".join(strategies) if multi_strategy else strategy
                augmented.append(new_row)
            ctx.report_progress(factor_idx + 1, max(base_rounds, 1))

    ctx.log_message(f"Augmented: {original_count} -> {len(augmented)} rows ({augment_factor}x)")

    # Save
    out_dir = os.path.join(ctx.run_dir, "dataset")
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "data.json"), "w", encoding="utf-8") as f:
        json.dump(augmented, f, indent=2)

    stats = {
        "original_rows": original_count,
        "augmented_rows": len(augmented),
        "strategy": strategy,
        "augment_factor": augment_factor,
        "model_backed": has_model_strategies,
        "corpus_phrases": len(corpus_phrases),
    }

    # Pass through dataset metadata
    if _dataset_meta:
        _dataset_meta["num_rows"] = len(augmented)
        ctx.save_output("dataset_meta", _dataset_meta)

    ctx.save_output("dataset", out_dir)
    ctx.save_output("metrics", stats)
    ctx.log_metric("original_rows", original_count)
    ctx.log_metric("augmented_rows", len(augmented))
    ctx.log_metric("augment_factor", augment_factor)
    ctx.report_progress(1, 1)
