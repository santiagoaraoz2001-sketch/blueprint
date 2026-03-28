"""Copilot Rule Engine — rule-based pipeline linting that runs on every graph change.

Evaluates pipeline graphs against 8 built-in rules and returns structured alerts.
Must complete in <50ms for real-time feedback on graph edits.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, asdict
from typing import Any

from .model_catalog import get_model_catalog

logger = logging.getLogger("blueprint.copilot.rules")

# ── Well-known training block categories/types ──────────────────────
_TRAINING_CATEGORIES = {"training"}
_TRAINING_TYPES = {
    "fine_tune", "lora_fine_tune", "qlora_fine_tune", "full_fine_tune",
    "train", "trainer", "sft_trainer", "dpo_trainer", "reward_model_trainer",
}
_EVALUATION_CATEGORIES = {"metrics"}
_EVALUATION_TYPES = {
    "evaluate", "evaluator", "benchmark", "perplexity", "bleu_score",
    "rouge_score", "human_eval", "mmlu", "lm_eval",
}
_INFERENCE_CATEGORIES = {"inference", "endpoints"}
_INFERENCE_TYPES = {
    "inference", "text_generation", "chat_completion", "generate",
    "serve", "deploy",
}
_OUTPUT_TYPES = {
    "save_model", "export", "push_to_hub", "save_dataset",
    "write_file", "artifact_export",
}


@dataclass
class Alert:
    """A single copilot alert produced by a rule."""
    id: str
    severity: str  # 'info' | 'warning' | 'error'
    title: str
    message: str
    affected_node_id: str | None
    suggested_action: str | None
    auto_dismissible: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _get_node_config(node: dict) -> dict[str, Any]:
    """Extract the config dict from a pipeline node."""
    data = node.get("data", {})
    return data.get("config", {})


def _get_node_type(node: dict) -> str:
    return node.get("data", {}).get("type", "")


def _get_node_label(node: dict) -> str:
    return node.get("data", {}).get("label", node.get("id", "unknown"))


def _get_node_category(node: dict, registry) -> str:
    """Get the category for a node from the registry."""
    block_type = _get_node_type(node)
    if not block_type or registry is None:
        return ""
    schema = registry.get(block_type) if hasattr(registry, "get") else None
    if schema is None:
        return ""
    return getattr(schema, "category", "")


def _is_training_node(node: dict, registry) -> bool:
    block_type = _get_node_type(node)
    category = _get_node_category(node, registry)
    return category in _TRAINING_CATEGORIES or block_type in _TRAINING_TYPES


def _is_evaluation_node(node: dict, registry) -> bool:
    block_type = _get_node_type(node)
    category = _get_node_category(node, registry)
    return category in _EVALUATION_CATEGORIES or block_type in _EVALUATION_TYPES


def _is_inference_node(node: dict, registry) -> bool:
    block_type = _get_node_type(node)
    category = _get_node_category(node, registry)
    return category in _INFERENCE_CATEGORIES or block_type in _INFERENCE_TYPES


def _is_output_node(node: dict, registry) -> bool:
    block_type = _get_node_type(node)
    return block_type in _OUTPUT_TYPES


def _estimate_model_params(config: dict) -> float | None:
    """Estimate model parameter count (in billions) from config.

    Resolution order (via ModelCatalog):
    1. Explicit config keys: model_params_b, num_parameters
    2. YAML catalog regex match against model_name / model / base_model
    3. Heuristic extraction: parse "7b", "70b", "350m" from name
    """
    catalog = get_model_catalog()
    info = catalog.lookup_from_config(config)
    return info.params_b if info else None


def _get_model_context(config: dict) -> int | None:
    """Get model context window size from config or catalog."""
    catalog = get_model_catalog()
    return catalog.get_context_from_config(config)


# ── Visual-only node types to skip ──────────────────────────────────
_VISUAL_NODE_TYPES = {"groupNode", "stickyNote"}


class RuleEngine:
    """Evaluates pipeline graphs against built-in rules.

    All rules are pure functions over the graph structure — no I/O, no AI.
    The full evaluate() call must complete in <50ms.
    """

    def evaluate(
        self,
        nodes: list[dict],
        edges: list[dict],
        capabilities: dict[str, Any] | None = None,
        registry: Any | None = None,
    ) -> list[Alert]:
        """Run all rules and return a list of alerts sorted by severity.

        Args:
            nodes: Pipeline node dicts (React Flow format).
            edges: Pipeline edge dicts (React Flow format).
            capabilities: System capabilities dict, e.g. {"available_memory_gb": 16}.
            registry: BlockRegistryService instance (or None).

        Returns:
            List of Alert instances, sorted error > warning > info.
        """
        start = time.monotonic()
        caps = capabilities or {}
        alerts: list[Alert] = []

        # Filter to real block nodes
        block_nodes = [
            n for n in nodes
            if n.get("type") not in _VISUAL_NODE_TYPES
            and _get_node_type(n)
        ]

        alerts.extend(self._rule_oom_prediction(block_nodes, caps, registry))
        alerts.extend(self._rule_missing_evaluation(block_nodes, edges, registry))
        alerts.extend(self._rule_disconnected_required_port(block_nodes, edges, registry))
        alerts.extend(self._rule_config_range(block_nodes, registry))
        alerts.extend(self._rule_incompatible_block_version(block_nodes, registry))
        alerts.extend(self._rule_missing_dependency(block_nodes, registry))
        alerts.extend(self._rule_no_output_block(block_nodes, registry))
        alerts.extend(self._rule_large_context(block_nodes, registry))

        # Sort: error > warning > info
        severity_order = {"error": 0, "warning": 1, "info": 2}
        alerts.sort(key=lambda a: severity_order.get(a.severity, 3))

        elapsed_ms = (time.monotonic() - start) * 1000
        if elapsed_ms > 50:
            logger.warning("Rule evaluation took %.1fms (target <50ms)", elapsed_ms)

        return alerts

    # ── Rule 1: OOM Prediction ───────────────────────────────────────

    def _rule_oom_prediction(
        self,
        nodes: list[dict],
        caps: dict[str, Any],
        registry: Any,
    ) -> list[Alert]:
        available_gb = caps.get("available_memory_gb")
        if available_gb is None:
            return []

        alerts = []
        available_bytes = available_gb * (1024 ** 3)

        for node in nodes:
            if not _is_training_node(node, registry):
                continue

            config = _get_node_config(node)
            params_b = _estimate_model_params(config)
            if params_b is None:
                continue

            batch_size = int(config.get("batch_size", config.get("per_device_train_batch_size", 1)))
            grad_accum = int(config.get("gradient_accumulation_steps", 1))
            bytes_per_param = 4 if config.get("dtype", "float32") == "float32" else 2

            # Adam optimizer: ~3x model params (weights + momentum + variance)
            overhead_factor = 3
            estimated_bytes = (
                params_b * 1e9 * bytes_per_param * overhead_factor
                + params_b * 1e9 * bytes_per_param * batch_size * 0.1  # activation estimate
            )

            estimated_gb = estimated_bytes / (1024 ** 3)

            if estimated_bytes > available_bytes:
                alerts.append(Alert(
                    id=f"oom-{node['id']}",
                    severity="error",
                    title="Predicted Out of Memory",
                    message=(
                        f"Training '{_get_node_label(node)}' with "
                        f"{params_b:.1f}B params, batch_size={batch_size}, "
                        f"grad_accum={grad_accum} is estimated to need "
                        f"~{estimated_gb:.1f} GB, but only {available_gb:.1f} GB "
                        f"is available."
                    ),
                    affected_node_id=node["id"],
                    suggested_action=(
                        f"Reduce batch_size, enable gradient checkpointing, "
                        f"use LoRA/QLoRA, or switch to a smaller model."
                    ),
                    auto_dismissible=False,
                ))

        return alerts

    # ── Rule 2: Missing Evaluation ───────────────────────────────────

    def _rule_missing_evaluation(
        self,
        nodes: list[dict],
        edges: list[dict],
        registry: Any,
    ) -> list[Alert]:
        training_nodes = [n for n in nodes if _is_training_node(n, registry)]
        if not training_nodes:
            return []

        eval_nodes = [n for n in nodes if _is_evaluation_node(n, registry)]
        if eval_nodes:
            return []

        # Check if any training node has a downstream evaluation
        training_ids = {n["id"] for n in training_nodes}
        # Build adjacency for downstream check
        downstream: dict[str, set[str]] = {}
        for edge in edges:
            src = edge.get("source", "")
            tgt = edge.get("target", "")
            downstream.setdefault(src, set()).add(tgt)

        # BFS from training nodes
        visited: set[str] = set()
        queue = list(training_ids)
        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)
            for child in downstream.get(current, set()):
                queue.append(child)

        # If none of the visited downstream nodes are evaluation, warn
        node_map = {n["id"]: n for n in nodes}
        for nid in visited - training_ids:
            node = node_map.get(nid)
            if node and _is_evaluation_node(node, registry):
                return []

        return [Alert(
            id="missing-eval",
            severity="warning",
            title="No Evaluation After Training",
            message=(
                "This pipeline has training blocks but no evaluation block. "
                "Add an evaluation step to measure model quality."
            ),
            affected_node_id=training_nodes[0]["id"],
            suggested_action="Add a benchmark or evaluation block after training.",
            auto_dismissible=True,
        )]

    # ── Rule 3: Disconnected Required Port ───────────────────────────

    def _rule_disconnected_required_port(
        self,
        nodes: list[dict],
        edges: list[dict],
        registry: Any,
    ) -> list[Alert]:
        if registry is None:
            return []

        # Build set of connected input ports: {(node_id, port_id)}
        connected: set[tuple[str, str]] = set()
        for edge in edges:
            tgt = edge.get("target", "")
            tgt_handle = edge.get("targetHandle", "")
            if tgt and tgt_handle:
                connected.add((tgt, tgt_handle))

        alerts = []
        for node in nodes:
            block_type = _get_node_type(node)
            schema = registry.get(block_type) if block_type else None
            if schema is None:
                continue

            inputs = getattr(schema, "inputs", [])
            for inp in inputs:
                port_id = getattr(inp, "id", "")
                required = getattr(inp, "required", False)
                if required and (node["id"], port_id) not in connected:
                    alerts.append(Alert(
                        id=f"disconnected-{node['id']}-{port_id}",
                        severity="error",
                        title="Required Port Not Connected",
                        message=(
                            f"Required input '{port_id}' on "
                            f"'{_get_node_label(node)}' is not connected."
                        ),
                        affected_node_id=node["id"],
                        suggested_action=f"Connect a compatible block to the '{port_id}' input.",
                        auto_dismissible=False,
                    ))

        return alerts

    # ── Rule 4: Config Range Warning ─────────────────────────────────

    def _rule_config_range(
        self,
        nodes: list[dict],
        registry: Any,
    ) -> list[Alert]:
        alerts = []
        for node in nodes:
            config = _get_node_config(node)
            lr = config.get("learning_rate") or config.get("lr")
            if lr is not None:
                try:
                    lr_val = float(lr)
                    if lr_val > 0.01:
                        alerts.append(Alert(
                            id=f"high-lr-{node['id']}",
                            severity="warning",
                            title="High Learning Rate",
                            message=(
                                f"Learning rate {lr_val} on '{_get_node_label(node)}' "
                                f"is unusually high (>0.01). This may cause training instability."
                            ),
                            affected_node_id=node["id"],
                            suggested_action="Try a learning rate between 1e-5 and 1e-3.",
                            auto_dismissible=True,
                        ))
                except (ValueError, TypeError):
                    pass
        return alerts

    # ── Rule 5: Incompatible Block Version ───────────────────────────

    def _rule_incompatible_block_version(
        self,
        nodes: list[dict],
        registry: Any,
    ) -> list[Alert]:
        if registry is None:
            return []

        alerts = []
        for node in nodes:
            block_type = _get_node_type(node)
            schema = registry.get(block_type) if block_type else None
            if schema is None:
                continue

            node_version = node.get("data", {}).get("version")
            registry_version = getattr(schema, "version", None)

            if node_version and registry_version and node_version != registry_version:
                # Only warn if major version differs
                try:
                    node_major = int(str(node_version).split(".")[0])
                    reg_major = int(str(registry_version).split(".")[0])
                    if node_major != reg_major:
                        alerts.append(Alert(
                            id=f"version-{node['id']}",
                            severity="warning",
                            title="Block Version Mismatch",
                            message=(
                                f"'{_get_node_label(node)}' uses version {node_version} "
                                f"but the installed version is {registry_version}."
                            ),
                            affected_node_id=node["id"],
                            suggested_action="Update the block or check for breaking changes.",
                            auto_dismissible=True,
                        ))
                except (ValueError, IndexError):
                    pass

        return alerts

    # ── Rule 6: Missing Dependency ───────────────────────────────────

    def _rule_missing_dependency(
        self,
        nodes: list[dict],
        registry: Any,
    ) -> list[Alert]:
        if registry is None:
            return []

        alerts = []
        for node in nodes:
            block_type = _get_node_type(node)
            if not block_type:
                continue

            schema = registry.get(block_type)
            if schema is not None:
                continue

            # Block type not found in registry — likely missing dependency
            alerts.append(Alert(
                id=f"missing-dep-{node['id']}",
                severity="error",
                title="Missing Block Type",
                message=(
                    f"Block type '{block_type}' on '{_get_node_label(node)}' "
                    f"is not in the registry. The block may not be installed."
                ),
                affected_node_id=node["id"],
                suggested_action=f"Install the block: check the marketplace or add it to blocks/.",
                auto_dismissible=False,
            ))

        return alerts

    # ── Rule 7: No Output Block ──────────────────────────────────────

    def _rule_no_output_block(
        self,
        nodes: list[dict],
        registry: Any,
    ) -> list[Alert]:
        if not nodes:
            return []

        has_output = any(_is_output_node(n, registry) for n in nodes)
        if has_output:
            return []

        # Check for terminal nodes (nodes with no outgoing edges are implicit outputs)
        # This is just informational
        return [Alert(
            id="no-output",
            severity="info",
            title="No Output Block",
            message=(
                "This pipeline has no explicit output block (save, export, push). "
                "Results will only be available in the run artifacts."
            ),
            affected_node_id=None,
            suggested_action="Add a save or export block to persist results.",
            auto_dismissible=True,
        )]

    # ── Rule 8: Large Context Warning ────────────────────────────────

    def _rule_large_context(
        self,
        nodes: list[dict],
        registry: Any,
    ) -> list[Alert]:
        alerts = []
        for node in nodes:
            config = _get_node_config(node)
            max_tokens = config.get("max_tokens") or config.get("max_new_tokens")
            if max_tokens is None:
                continue

            try:
                max_tok = int(max_tokens)
            except (ValueError, TypeError):
                continue

            model_ctx = _get_model_context(config)
            if model_ctx and max_tok > model_ctx:
                alerts.append(Alert(
                    id=f"large-ctx-{node['id']}",
                    severity="warning",
                    title="Exceeds Model Context Window",
                    message=(
                        f"max_tokens={max_tok} on '{_get_node_label(node)}' "
                        f"exceeds the model's context window of {model_ctx} tokens."
                    ),
                    affected_node_id=node["id"],
                    suggested_action=f"Reduce max_tokens to {model_ctx} or use a model with a larger context.",
                    auto_dismissible=True,
                ))

        return alerts


# ── Variant Field Highlighting (rule-based, no AI) ──────────────────

# Fields most commonly varied for each pipeline archetype
VARIANT_FIELD_HINTS: dict[str, list[str]] = {
    "training": ["model_name", "learning_rate", "lr", "epochs", "num_train_epochs", "batch_size", "per_device_train_batch_size"],
    "inference": ["model_name", "model", "temperature", "max_tokens", "max_new_tokens", "top_p"],
    "evaluation": ["model_name", "model", "benchmark", "dataset", "num_samples"],
}


def get_variant_field_hints(nodes: list[dict], registry: Any | None = None) -> dict[str, list[str]]:
    """Return per-node field highlights for clone-as-variant.

    Returns a dict of {node_id: [field_key, ...]} indicating which config
    fields are most commonly varied for that node's archetype.
    Works without AI — pure rule-based.
    """
    hints: dict[str, list[str]] = {}

    for node in nodes:
        if node.get("type") in _VISUAL_NODE_TYPES:
            continue

        config = _get_node_config(node)
        if not config:
            continue

        archetype: str | None = None
        if _is_training_node(node, registry):
            archetype = "training"
        elif _is_inference_node(node, registry):
            archetype = "inference"
        elif _is_evaluation_node(node, registry):
            archetype = "evaluation"

        if archetype is None:
            continue

        suggested_fields = VARIANT_FIELD_HINTS.get(archetype, [])
        # Only include fields that actually exist in the node's config
        present = [f for f in suggested_fields if f in config]
        if present:
            hints[node["id"]] = present

    return hints
