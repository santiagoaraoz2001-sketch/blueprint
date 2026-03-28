"""AI-powered Copilot — LLM-backed pipeline explanations, error diagnosis, and variant suggestions.

Uses Ollama (localhost:11434) as the primary inference backend, falling back to MLX
(localhost:8080), then a configurable API endpoint. All methods degrade gracefully
when no inference backend is available.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any

from ..config import OLLAMA_URL, MLX_URL

logger = logging.getLogger("blueprint.copilot.ai")

# System prompt preamble shared across all copilot LLM calls
_SYSTEM_PREAMBLE = """\
You are Blueprint Copilot, a helpful ML pipeline assistant built into the Blueprint \
experiment workbench by Specific Labs. You help users understand their ML pipelines, \
diagnose errors, and suggest improvements.

Key pipeline concepts:
- Pipelines are directed acyclic graphs (DAGs) of blocks connected by typed ports.
- Port types: dataset, text, model, config, metrics, embedding, artifact, agent, llm, any.
- Blocks belong to categories: external, data, model, training, metrics, embedding, \
utilities, agents, interventions, inference, endpoints.
- Config fields have types (string, number, boolean, select) with optional min/max/options.

Keep responses concise and actionable. Use bullet points. Do not hallucinate block names \
or config fields that don't exist in the user's pipeline.
"""


def _try_ollama_generate(prompt: str, system: str, model: str = "llama3.2") -> str | None:
    """Call Ollama /api/generate. Returns response text or None on failure."""
    try:
        payload = json.dumps({
            "model": model,
            "prompt": prompt,
            "system": system,
            "stream": False,
            "options": {"temperature": 0.3, "num_predict": 1024},
        }).encode()
        req = urllib.request.Request(
            f"{OLLAMA_URL}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
            return data.get("response", "")
    except (urllib.error.URLError, OSError, json.JSONDecodeError, KeyError) as e:
        logger.debug("Ollama unavailable: %s", e)
        return None


def _try_mlx_generate(prompt: str, system: str) -> str | None:
    """Call MLX /v1/chat/completions. Returns response text or None on failure."""
    try:
        payload = json.dumps({
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.3,
            "max_tokens": 1024,
        }).encode()
        req = urllib.request.Request(
            f"{MLX_URL}/v1/chat/completions",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
            choices = data.get("choices", [])
            if choices:
                return choices[0].get("message", {}).get("content", "")
            return None
    except (urllib.error.URLError, OSError, json.JSONDecodeError, KeyError) as e:
        logger.debug("MLX unavailable: %s", e)
        return None


def _llm_generate(prompt: str, system: str = _SYSTEM_PREAMBLE) -> str | None:
    """Try Ollama, then MLX, then give up. Returns None if no backend available."""
    result = _try_ollama_generate(prompt, system)
    if result is not None:
        return result
    result = _try_mlx_generate(prompt, system)
    if result is not None:
        return result
    logger.info("No AI inference backend available (tried Ollama + MLX)")
    return None


def _is_ai_available() -> bool:
    """Quick health check — is any inference backend reachable?"""
    # Try Ollama tags endpoint
    try:
        req = urllib.request.Request(f"{OLLAMA_URL}/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=3):
            return True
    except (urllib.error.URLError, OSError):
        pass
    # Try MLX models endpoint
    try:
        req = urllib.request.Request(f"{MLX_URL}/v1/models", method="GET")
        with urllib.request.urlopen(req, timeout=3):
            return True
    except (urllib.error.URLError, OSError):
        pass
    return False


def _summarize_pipeline(nodes: list[dict], edges: list[dict], registry: Any | None) -> str:
    """Build a concise text summary of a pipeline for LLM context."""
    lines = []
    node_map = {n["id"]: n for n in nodes}

    for node in nodes:
        data = node.get("data", {})
        block_type = data.get("type", "")
        label = data.get("label", node.get("id", "?"))
        config = data.get("config", {})
        config_summary = ", ".join(f"{k}={v}" for k, v in list(config.items())[:6])
        category = ""
        if registry and block_type:
            schema = registry.get(block_type) if hasattr(registry, "get") else None
            if schema:
                category = f" [{getattr(schema, 'category', '')}]"
        lines.append(f"- {label} (type={block_type}{category}): {config_summary or 'no config'}")

    lines.append("\nConnections:")
    for edge in edges:
        src_label = node_map.get(edge.get("source", ""), {}).get("data", {}).get("label", edge.get("source", "?"))
        tgt_label = node_map.get(edge.get("target", ""), {}).get("data", {}).get("label", edge.get("target", "?"))
        src_handle = edge.get("sourceHandle", "out")
        tgt_handle = edge.get("targetHandle", "in")
        lines.append(f"  {src_label}.{src_handle} -> {tgt_label}.{tgt_handle}")

    return "\n".join(lines)


def _extract_json_object(text: str) -> dict | None:
    """Extract a JSON object from LLM output, handling common wrapping patterns.

    Handles:
    - Plain JSON
    - Markdown code blocks (```json ... ```, ``` ... ```)
    - Leading/trailing prose around the JSON
    - Multiple JSON objects (takes the first valid one)
    """
    text = text.strip()

    # Strip markdown code fences
    if "```" in text:
        lines = text.split("\n")
        inside_fence = False
        json_lines = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("```"):
                if inside_fence:
                    break  # End of code block
                inside_fence = True
                continue
            if inside_fence:
                json_lines.append(line)
        if json_lines:
            text = "\n".join(json_lines).strip()

    # Try direct parse
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    # Try to find a JSON object in the text using brace matching
    depth = 0
    start = -1
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start >= 0:
                candidate = text[start:i + 1]
                try:
                    parsed = json.loads(candidate)
                    if isinstance(parsed, dict):
                        return parsed
                except json.JSONDecodeError:
                    start = -1
                    continue

    return None


def _build_schema_map(
    nodes: list[dict],
    registry: Any | None,
) -> dict[str, dict[str, dict]]:
    """Build a per-node config field schema lookup.

    Returns: {node_id: {field_key: {"type": str, "options": list, "min": float|None, "max": float|None}}}
    """
    schema_map: dict[str, dict[str, dict]] = {}

    for node in nodes:
        node_id = node.get("id", "")
        block_type = node.get("data", {}).get("type", "")
        if not block_type or not registry:
            continue

        schema = registry.get(block_type) if hasattr(registry, "get") else None
        if schema is None:
            continue

        config_fields = getattr(schema, "config", [])
        if not config_fields:
            continue

        field_map: dict[str, dict] = {}
        for cf in config_fields:
            key = getattr(cf, "key", "")
            if not key:
                continue
            field_map[key] = {
                "type": getattr(cf, "type", "string"),
                "options": list(getattr(cf, "options", [])),
                "min": getattr(cf, "min", None),
                "max": getattr(cf, "max", None),
            }
        if field_map:
            schema_map[node_id] = field_map

    return schema_map


def _format_schema_context(
    schema_map: dict[str, dict[str, dict]],
    nodes: list[dict],
) -> str:
    """Format schema info as context for the LLM prompt."""
    if not schema_map:
        return ""

    node_labels = {n["id"]: n.get("data", {}).get("label", n["id"]) for n in nodes}
    lines = []
    for node_id, fields in schema_map.items():
        label = node_labels.get(node_id, node_id)
        field_descs = []
        for key, meta in fields.items():
            desc = f"{key} ({meta['type']}"
            if meta["options"]:
                desc += f", options: {meta['options'][:8]}"
            if meta["min"] is not None or meta["max"] is not None:
                desc += f", range: [{meta['min']}, {meta['max']}]"
            desc += ")"
            field_descs.append(desc)
        lines.append(f"  {label} (node_id={node_id}): {', '.join(field_descs)}")

    return "\n\nAvailable config fields per block:\n" + "\n".join(lines)


def _validate_variant_suggestions(
    raw: dict,
    valid_node_ids: set[str],
    schema_map: dict[str, dict[str, dict]],
) -> dict[str, dict[str, Any]]:
    """Validate and sanitize AI-suggested config changes against block schemas.

    Rules applied per field:
    1. Reject node_ids that don't exist in the pipeline
    2. If registry schema is available, strip fields not in the schema
    3. Clamp numeric values to [min, max] range if schema defines bounds
    4. Reject enum/select values not in the options list
    5. Coerce types: string→number for numeric fields, etc.
    6. Keep all valid fields; only strip the invalid ones (partial results)
    """
    validated: dict[str, dict[str, Any]] = {}

    for node_id, changes in raw.items():
        if not isinstance(changes, dict):
            continue
        if node_id not in valid_node_ids:
            logger.debug("Stripping unknown node_id from AI suggestions: %s", node_id)
            continue

        field_schemas = schema_map.get(node_id)
        valid_changes: dict[str, Any] = {}

        for field, value in changes.items():
            # If we have schema info, validate against it
            if field_schemas is not None:
                field_meta = field_schemas.get(field)
                if field_meta is None:
                    logger.debug(
                        "Stripping unknown field %s.%s from AI suggestions",
                        node_id, field,
                    )
                    continue

                validated_value = _validate_field_value(value, field_meta)
                if validated_value is not None:
                    valid_changes[field] = validated_value
                else:
                    logger.debug(
                        "Rejected invalid value for %s.%s: %r",
                        node_id, field, value,
                    )
            else:
                # No schema available — accept as-is (graceful degradation)
                valid_changes[field] = value

        if valid_changes:
            validated[node_id] = valid_changes

    return validated


def _validate_field_value(value: Any, meta: dict) -> Any | None:
    """Validate and coerce a single field value against its schema.

    Returns the validated (possibly coerced/clamped) value, or None if invalid.
    """
    ftype = meta.get("type", "string")
    options = meta.get("options", [])
    fmin = meta.get("min")
    fmax = meta.get("max")

    # Select/enum fields: value must be in the options list
    if ftype in ("select", "multiselect") and options:
        str_val = str(value)
        if str_val in options:
            return str_val
        # Try case-insensitive match
        lower_map = {o.lower(): o for o in options}
        if str_val.lower() in lower_map:
            return lower_map[str_val.lower()]
        logger.debug("Value %r not in options %s", value, options[:8])
        return None

    # Numeric fields: coerce + clamp
    if ftype in ("integer", "int"):
        try:
            int_val = int(float(value))
        except (ValueError, TypeError):
            return None
        if fmin is not None:
            int_val = max(int_val, int(fmin))
        if fmax is not None:
            int_val = min(int_val, int(fmax))
        return int_val

    if ftype in ("float", "number"):
        try:
            float_val = float(value)
        except (ValueError, TypeError):
            return None
        if fmin is not None:
            float_val = max(float_val, float(fmin))
        if fmax is not None:
            float_val = min(float_val, float(fmax))
        return float_val

    # Boolean fields
    if ftype == "boolean":
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ("true", "1", "yes")
        return bool(value)

    # String / text_area / file_path: accept as string
    if ftype in ("string", "text_area", "file_path"):
        return str(value)

    # Unknown type — accept as-is
    return value


class AICopilot:
    """LLM-backed copilot for pipeline explanation, diagnosis, and suggestions."""

    def explain_pipeline(
        self,
        nodes: list[dict],
        edges: list[dict],
        registry: Any | None = None,
    ) -> str | None:
        """Ask the LLM to explain a pipeline step-by-step in plain language.

        Returns a markdown string, or None if no AI backend is available.
        """
        summary = _summarize_pipeline(nodes, edges, registry)
        prompt = (
            "Explain this ML pipeline step by step in plain language. "
            "For each block, describe what it does and how data flows between blocks.\n\n"
            f"Pipeline:\n{summary}"
        )
        return _llm_generate(prompt)

    def diagnose_error(
        self,
        run_id: str,
        error_context: dict[str, Any],
        nodes: list[dict],
        edges: list[dict],
    ) -> str | None:
        """Send error context + pipeline to LLM for diagnosis.

        Args:
            run_id: The failed run's ID.
            error_context: Dict with keys like 'error_type', 'message', 'block_type', 'traceback'.
            nodes: Pipeline nodes.
            edges: Pipeline edges.

        Returns:
            Markdown diagnosis string, or None if no AI backend is available.
        """
        summary = _summarize_pipeline(nodes, edges, None)
        error_text = json.dumps(error_context, indent=2, default=str)
        prompt = (
            f"A pipeline run (ID: {run_id}) failed with this error:\n"
            f"```\n{error_text}\n```\n\n"
            f"Pipeline structure:\n{summary}\n\n"
            "Diagnose the root cause. Suggest specific fixes. "
            "Reference block names and config fields from the pipeline."
        )
        return _llm_generate(prompt)

    def suggest_improvements(
        self,
        nodes: list[dict],
        edges: list[dict],
        run_history: list[dict] | None = None,
    ) -> list[str] | None:
        """Suggest pipeline improvements based on structure and optional run history.

        Returns a list of suggestion strings, or None if no AI backend is available.
        """
        summary = _summarize_pipeline(nodes, edges, None)
        history_text = ""
        if run_history:
            history_lines = []
            for run in run_history[:5]:
                status = run.get("status", "?")
                metrics = run.get("metrics", {})
                history_lines.append(f"  - {status}: {json.dumps(metrics, default=str)}")
            history_text = "\n\nRecent run results:\n" + "\n".join(history_lines)

        prompt = (
            f"Review this ML pipeline and suggest improvements:\n\n"
            f"Pipeline:\n{summary}{history_text}\n\n"
            "Return a numbered list of 3-5 specific, actionable suggestions. "
            "Focus on common ML best practices."
        )
        result = _llm_generate(prompt)
        if result is None:
            return None

        # Parse numbered list from response
        suggestions = []
        for line in result.strip().split("\n"):
            line = line.strip()
            if line and (line[0].isdigit() or line.startswith("-") or line.startswith("*")):
                # Strip leading number/bullet
                cleaned = line.lstrip("0123456789.-*) ").strip()
                if cleaned:
                    suggestions.append(cleaned)
        return suggestions if suggestions else [result]

    def suggest_variant_config(
        self,
        source_pipeline: dict[str, Any],
        user_intent: str,
        registry: Any | None = None,
    ) -> dict[str, Any] | None:
        """Parse natural-language intent and suggest config changes for a variant.

        This method is hardened against LLM output quality issues:
        1. Parses JSON from markdown-wrapped and malformed responses
        2. Validates suggested changes against block config schemas
        3. Clamps numeric values to schema-defined min/max ranges
        4. Rejects enum values not in the schema's options list
        5. Strips fields that don't exist in the block config schema
        6. Retries with a corrective prompt if the first parse fails
        7. Returns partial valid results instead of all-or-nothing None

        Args:
            source_pipeline: The pipeline definition dict (with 'nodes' and 'edges').
            user_intent: Natural language like "same but with a larger model".
            registry: BlockRegistryService for schema metadata.

        Returns:
            Dict of {node_id: {field: new_value}} or None if no AI backend.
        """
        nodes = source_pipeline.get("nodes", [])
        edges = source_pipeline.get("edges", [])
        summary = _summarize_pipeline(nodes, edges, registry)

        # Build config schema context and validation lookup
        schema_map = _build_schema_map(nodes, registry)
        schema_context = _format_schema_context(schema_map, nodes)

        prompt = (
            f"A user wants to create a variant of their ML pipeline.\n"
            f"User intent: \"{user_intent}\"\n\n"
            f"Current pipeline:\n{summary}{schema_context}\n\n"
            "Return a JSON object mapping node_id to an object of config changes. "
            "Only include fields that should change. Use exact node_ids and field keys "
            "from the pipeline above. Example format:\n"
            '{"node_abc": {"learning_rate": 0.0001, "epochs": 10}}\n\n'
            "Return ONLY the JSON object, no explanation."
        )

        # Attempt 1: standard generation
        result = _llm_generate(prompt)
        if result is None:
            return None

        parsed = _extract_json_object(result)

        # Attempt 2: corrective retry if first parse failed
        if parsed is None:
            logger.info("First variant parse failed, retrying with corrective prompt")
            retry_prompt = (
                f"Your previous response was not valid JSON. "
                f"Please return ONLY a JSON object (no markdown, no explanation) "
                f"mapping node_id to config changes for this intent: \"{user_intent}\"\n\n"
                f"Valid node_ids: {[n['id'] for n in nodes]}\n"
                f"Example: " + '{"node_1": {"learning_rate": 0.0001}}'
            )
            retry_result = _llm_generate(retry_prompt)
            if retry_result is not None:
                parsed = _extract_json_object(retry_result)

        if parsed is None:
            return None

        # Validate and sanitize against schemas
        valid_node_ids = {n["id"] for n in nodes}
        validated = _validate_variant_suggestions(parsed, valid_node_ids, schema_map)

        return validated if validated else None

    @staticmethod
    def is_available() -> bool:
        """Check if any AI inference backend is reachable."""
        return _is_ai_available()
