"""Guardrails — content filtering and safety layer for LLM outputs.

Workflows:
  1. Output safety: LLM response -> guardrails -> filtered response
  2. Input validation: user prompt -> guardrails -> sanitized prompt
  3. PII redaction: text with personal info -> redacted text
  4. Content moderation: user content -> flag/block inappropriate material
  5. Compliance filter: responses -> ensure no restricted content
  6. Pipeline safety: insert between any blocks for content checks
"""

import json
import os
import re

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


# PII detection patterns
PII_PATTERNS = {
    "email": r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
    "phone": r'\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b',
    "ssn": r'\b\d{3}-\d{2}-\d{4}\b',
    "credit_card": r'\b(?:\d{4}[-\s]?){3}\d{4}\b',
    "ip_address": r'\b(?:\d{1,3}\.){3}\d{1,3}\b',
}

# Toxicity/profanity word lists (basic — production should use a model)
TOXICITY_INDICATORS = [
    "hate", "kill", "murder", "violent", "abuse", "racist", "sexist",
    "threat", "harass", "assault", "slur", "extremist",
]

SELF_HARM_INDICATORS = [
    "suicide", "self-harm", "cut myself", "end my life", "hurt myself",
]


def run(ctx):
    categories_str = ctx.config.get("categories", "toxicity,pii,bias")
    threshold = float(ctx.config.get("threshold", 0.5))
    action = ctx.config.get("action", "flag")
    custom_banned_str = ctx.config.get("custom_banned_words", "")
    pii_types_str = ctx.config.get("pii_types", "email,phone,ssn,credit_card,ip_address")
    redaction_string = ctx.config.get("redaction_string", "")
    fail_on_flag = ctx.config.get("fail_on_flag", False)
    if isinstance(fail_on_flag, str):
        fail_on_flag = fail_on_flag.lower() in ("true", "1", "yes")
    output_format = ctx.config.get("output_format", "text")

    categories = [c.strip() for c in categories_str.split(",") if c.strip()]
    pii_types = [p.strip() for p in pii_types_str.split(",") if p.strip()]
    custom_banned = [w.strip().lower() for w in custom_banned_str.split("\n") if w.strip()]

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

    if not text:
        raise BlockInputError("No input text to filter", recoverable=False)

    ctx.log_message(f"Guardrails: checking {len(categories)} categories, action={action}")
    ctx.report_progress(1, 3)

    # Score each category
    scores = {}
    details = {}
    filtered_text = text
    text_lower = text.lower()

    for cat in categories:
        if cat == "pii":
            pii_found = {}
            total_pii = 0
            for pii_type in pii_types:
                pattern = PII_PATTERNS.get(pii_type)
                if pattern:
                    matches = re.findall(pattern, text)
                    if matches:
                        pii_found[pii_type] = len(matches)
                        total_pii += len(matches)
                        if action == "redact":
                            replacement = redaction_string if redaction_string else f"[{pii_type.upper()}_REDACTED]"
                            filtered_text = re.sub(pattern, replacement, filtered_text)

            scores[cat] = min(total_pii * 0.3, 1.0)
            details[cat] = pii_found

        elif cat == "toxicity":
            found_words = [w for w in TOXICITY_INDICATORS if w in text_lower]
            found_words += [w for w in custom_banned if w in text_lower]
            scores[cat] = min(len(found_words) * 0.2, 1.0)
            details[cat] = {"found": found_words}

        elif cat == "profanity":
            # Basic profanity check using custom banned words
            found = [w for w in custom_banned if w in text_lower]
            scores[cat] = min(len(found) * 0.3, 1.0)
            details[cat] = {"found": found}

        elif cat == "bias":
            # Check for demographic terms used in potentially biased context
            bias_terms = ["always", "never", "all", "none", "every"]
            demographic_terms = ["women", "men", "race", "gender", "religion", "ethnic"]
            bias_count = 0
            for bt in bias_terms:
                for dt in demographic_terms:
                    if bt in text_lower and dt in text_lower:
                        bias_count += 1
            scores[cat] = min(bias_count * 0.15, 1.0)
            details[cat] = {"bias_indicator_count": bias_count}

        elif cat == "self_harm":
            found_phrases = [p for p in SELF_HARM_INDICATORS if p in text_lower]
            scores[cat] = min(len(found_phrases) * 0.5, 1.0)
            details[cat] = {"found": found_phrases}

        else:
            scores[cat] = 0.0
            details[cat] = {}

    ctx.report_progress(2, 3)

    # Apply action
    flagged = {k: v for k, v in scores.items() if v >= threshold}

    if flagged:
        ctx.log_message(f"Flagged categories: {list(flagged.keys())}")

        if action == "block":
            filtered_text = "[BLOCKED] Content flagged for: " + ", ".join(flagged.keys())
        elif action == "flag":
            warning = f"[WARNING: Flagged for {', '.join(flagged.keys())}]\n\n"
            filtered_text = warning + filtered_text
        elif action == "redact":
            # PII redaction already applied above; for other categories, no text change
            pass
        # passthrough: no modification
    else:
        ctx.log_message("All safety checks passed")

    # Raise error if fail_on_flag is enabled and content was flagged
    flagged_categories = list(flagged.keys())
    if fail_on_flag and flagged_categories:
        raise BlockExecutionError(f"Content flagged: {', '.join(flagged_categories)}")

    # Save filtered text
    if output_format == "json":
        from datetime import datetime
        json_result = {
            "result": "flagged" if flagged else "safe",
            "filtered_text": filtered_text,
            "flags": list(flagged.keys()),
            "scores": scores,
            "details": details,
            "action_taken": action if flagged else "none",
            "model": "rule-based",
            "provider": "built-in",
            "timestamp": datetime.now().isoformat(),
        }
        out_path = os.path.join(ctx.run_dir, "filtered.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(json_result, f, indent=2)
    else:
        out_path = os.path.join(ctx.run_dir, "filtered.txt")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(filtered_text)
    ctx.save_output("text", out_path)

    # Save safety metrics
    safety_report = {
        "scores": scores,
        "details": details,
        "flagged": list(flagged.keys()),
        "action_taken": action if flagged else "none",
        "threshold": threshold,
        "text_modified": filtered_text != text,
    }
    ctx.save_output("metrics", safety_report)

    for cat, score in scores.items():
        ctx.log_metric(f"safety_{cat}", round(score, 4))

    ctx.report_progress(3, 3)
