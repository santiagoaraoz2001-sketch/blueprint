"""Pipeline Validator — pre-run validation without executing blocks."""

from dataclasses import dataclass, field
from typing import Any

from .block_registry import is_known_block, get_block_types, get_block_config_schema
from .executor import _detect_loops
from ..block_sdk.config_validator import (
    validate_and_apply_defaults,
    _validate_type,
    _validate_bounds,
    _validate_select,
)
from ..block_sdk.exceptions import BlockConfigError


@dataclass
class ValidationReport:
    valid: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    estimated_runtime_s: int = 0
    block_count: int = 0
    edge_count: int = 0


# Rough runtime estimates per category (seconds)
CATEGORY_RUNTIME = {
    "external": 5,
    "data": 5,
    "model": 20,
    "inference": 10,
    "training": 120,
    "metrics": 30,
    "embedding": 15,
    "utilities": 5,
    "agents": 15,
    "interventions": 5,
    "endpoints": 3,
}

# Port type compatibility matrix.
# AUTHORITATIVE SOURCE: frontend/src/lib/block-registry-types.ts COMPAT (line 123).
# This dict MUST be kept in exact sync with the frontend.
# SOURCE → set of CAN-CONNECT-TO types.
COMPAT: dict[str, set[str]] = {
    "dataset":   {"dataset", "text", "any"},
    "text":      {"text", "dataset", "any"},
    "model":     {"model", "llm", "any"},
    "config":    {"config", "text", "llm", "any"},
    "metrics":   {"metrics", "dataset", "text", "any"},
    "embedding": {"embedding", "dataset", "any"},
    "artifact":  {"artifact", "text", "any"},
    "agent":     {"agent", "any"},
    "llm":       {"llm", "model", "config", "any"},
    "any":       {"any", "dataset", "text", "model", "config", "metrics",
                  "embedding", "artifact", "agent", "llm"},
}

# Backward-compat aliases for legacy port type names.
# AUTHORITATIVE SOURCE: frontend/src/lib/block-registry-types.ts PORT_TYPE_ALIASES.
_PORT_TYPE_ALIASES: dict[str, str] = {
    "data": "dataset",
    "external": "dataset",
    "training": "model",
    "intervention": "any",
    "checkpoint": "model",
    "optimizer": "config",
    "schedule": "config",
    "api": "dataset",
    "file": "dataset",
    "cloud": "config",
    "llm_config": "llm",
}


def _resolve_port_type(port_type: str) -> str:
    """Resolve legacy port type aliases."""
    return _PORT_TYPE_ALIASES.get(port_type, port_type)


def _port_compatible(src_type: str, tgt_type: str) -> bool:
    """Check if source port type can connect to target port type."""
    src = _resolve_port_type(src_type)
    tgt = _resolve_port_type(tgt_type)
    return tgt in COMPAT.get(src, set())

# Critical config fields that must be set for specific block types
CRITICAL_CONFIG_FIELDS = {
    "llm_inference": ["model_name"],
    "local_file_loader": ["file_path"],
    "huggingface_loader": ["dataset_name"],
    "huggingface_model_loader": ["model_id"],
    "model_selector": ["model_id"],
}


def validate_pipeline(definition: dict) -> ValidationReport:
    """
    Validate a pipeline definition without running any blocks.

    Args:
        definition: Pipeline definition dict with 'nodes' and 'edges' keys.
            nodes: list of {id, type, config, ...}
            edges: list of {source, target, sourceHandle, targetHandle, ...}

    Returns:
        ValidationReport with errors, warnings, and metadata.
    """
    report = ValidationReport()

    nodes = definition.get("nodes", [])
    edges = definition.get("edges", [])

    report.block_count = len(nodes)
    report.edge_count = len(edges)

    if not nodes:
        report.errors.append("Pipeline has no blocks — add at least one block to run")
        report.valid = False
        return report

    # Build lookup maps
    node_map: dict[str, dict] = {}
    for node in nodes:
        nid = node.get("id", "")
        if nid in node_map:
            report.errors.append(f"Duplicate node ID: {nid}")
        node_map[nid] = node

    # ── 1. Check for unknown node types ──
    known_types = get_block_types()
    for node in nodes:
        if node.get("type") in ("groupNode", "stickyNote"):
            continue
        block_type = node.get("data", {}).get("type", node.get("type", ""))
        if block_type and known_types and block_type not in known_types:
            node_label = node.get("data", {}).get("label", node.get("id", "?"))
            report.warnings.append(f"Block '{node_label}' uses unknown type '{block_type}' — it may not have a run.py implementation")

    # ── 2. Check for cycles / legal loops ──
    # Use _detect_loops() which distinguishes legal single-controller loops
    # from illegal cycles. Legal loops are reported as warnings, not errors.
    visual_types = {"groupNode", "stickyNote"}
    exec_nodes = [n for n in nodes if n.get("type") not in visual_types]
    exec_node_ids = {n.get("id") for n in exec_nodes}
    exec_edges = [
        e for e in edges
        if e.get("source") in exec_node_ids and e.get("target") in exec_node_ids
    ]

    try:
        detected_loops = _detect_loops(exec_nodes, exec_edges)
        if detected_loops:
            loop_parts = []
            for lp in detected_loops:
                ctrl_label = node_map.get(lp.controller_id, {}).get(
                    "data", {}
                ).get("label", lp.controller_id)
                loop_parts.append(
                    f"'{ctrl_label}' ({len(lp.body_node_ids)} body block"
                    f"{'s' if len(lp.body_node_ids) != 1 else ''})"
                )
            report.warnings.append(
                f"Pipeline contains {len(detected_loops)} loop(s): "
                + ", ".join(loop_parts)
            )
    except ValueError as exc:
        report.errors.append(str(exc))
        report.valid = False

    # ── 3. Check disconnected nodes & required ports ──
    connected_target_handles = set()
    connected_nodes: set[str] = set()
    for edge in edges:
        connected_nodes.add(edge.get("source", ""))
        connected_nodes.add(edge.get("target", ""))
        connected_target_handles.add((edge.get("target", ""), edge.get("targetHandle", "")))

    if len(nodes) > 1:
        disconnected = [n.get("id", "?") for n in nodes if n.get("id") not in connected_nodes]
        if disconnected:
            # Only warn, don't fail — single unconnected nodes are common during editing
            for did in disconnected:
                node_data = node_map.get(did, {})
                node_label = node_data.get("data", {}).get("label", did)
                report.warnings.append(f"Block '{node_label}' ({did}) is not connected to any other block")
                
    for node in nodes:
        if node.get("type") in ("groupNode", "stickyNote"):
            continue
        nid = node.get("id", "")
        inputs = node.get("data", {}).get("inputs", [])
        for in_port in inputs:
            if in_port.get("required", False) and (nid, in_port.get("id")) not in connected_target_handles:
                node_label = node.get("data", {}).get("label", nid)
                report.errors.append(f"Block '{node_label}' is missing required input: {in_port.get('label', in_port.get('id'))}")
                report.valid = False

    # ── 4. Check edge validity and data types ──
    for edge in edges:
        src = edge.get("source", "")
        tgt = edge.get("target", "")
        if src not in node_map:
            report.errors.append(f"Edge references unknown source node: {src}")
            report.valid = False
            continue
        if tgt not in node_map:
            report.errors.append(f"Edge references unknown target node: {tgt}")
            report.valid = False
            continue
        if src == tgt:
            report.errors.append(f"Self-loop detected on node: {src}")
            report.valid = False
            continue
            
        src_data = node_map[src].get("data", {})
        tgt_data = node_map[tgt].get("data", {})
        src_handle = edge.get("sourceHandle")
        tgt_handle = edge.get("targetHandle")
        
        src_port_type = "any"
        tgt_port_type = "any"
        
        for out_port in src_data.get("outputs", []):
            if out_port.get("id") == src_handle:
                src_port_type = out_port.get("dataType", "any")
                break
                
        for in_port in tgt_data.get("inputs", []):
            if in_port.get("id") == tgt_handle:
                tgt_port_type = in_port.get("dataType", "any")
                break
                
        if not _port_compatible(src_port_type, tgt_port_type):
            src_label = src_data.get("label", src)
            tgt_label = tgt_data.get("label", tgt)
            report.errors.append(f"Incompatible connection: Cannot connect {src_port_type.upper()} ({src_label}) to {tgt_port_type.upper()} ({tgt_label})")
            report.valid = False

    # ── 5. Check required config fields ──
    for node in nodes:
        if node.get("type") == "groupNode" or node.get("type") == "stickyNote":
            continue

        node_config = node.get("data", {}).get("config", {})
        block_type = node.get("data", {}).get("type", node.get("data", {}).get("blockType", ""))
        node_label = node.get("data", {}).get("label", node.get("id", "?"))

        # Critical config fields → error (pipeline won't run without these)
        critical_fields = CRITICAL_CONFIG_FIELDS.get(block_type, [])
        for cf in critical_fields:
            if not node_config.get(cf):
                report.errors.append(f"Block '{node_label}': '{cf}' is required but empty")
                report.valid = False

        # Other potentially important config fields → warning
        for key, value in node_config.items():
            if key in critical_fields:
                continue  # Already handled as error above
            if key in ("dataset_name", "model_path", "base_url") and not value:
                report.warnings.append(f"Block '{node_label}': '{key}' is empty — may be required at runtime")

    # ── 5a. Deep config validation against block.yaml schemas ──
    for node in nodes:
        if node.get("type") in ("groupNode", "stickyNote"):
            continue
        block_type = node.get("data", {}).get("type", node.get("data", {}).get("blockType", ""))
        if not block_type:
            continue

        schema = get_block_config_schema(block_type)
        if not schema:
            continue

        node_config = node.get("data", {}).get("config", {})
        node_label = node.get("data", {}).get("label", node.get("id", "?"))

        # Validate each field independently so all issues get reported
        for field_name, field_spec in schema.items():
            if not isinstance(field_spec, dict):
                continue
            field_type = field_spec.get("type", "string")
            value = node_config.get(field_name)

            # Apply default if missing
            if value is None or value == "":
                if "default" in field_spec:
                    value = field_spec["default"]
            if value is None or value == "":
                continue

            try:
                _validate_type(field_name, value, field_type)
            except BlockConfigError as exc:
                report.warnings.append(f"Block '{node_label}': {exc}")
                continue  # Skip bounds/select if type is wrong

            if field_type in ("integer", "float"):
                try:
                    _validate_bounds(field_name, value, field_spec)
                except BlockConfigError as exc:
                    report.warnings.append(f"Block '{node_label}': {exc}")

            if field_type == "select":
                try:
                    _validate_select(field_name, value, field_spec)
                except BlockConfigError as exc:
                    report.warnings.append(f"Block '{node_label}': {exc}")

    # ── 5b. Check port existence on edges ──
    for edge in edges:
        src = edge.get("source", "")
        tgt = edge.get("target", "")
        src_handle = edge.get("sourceHandle", "")
        tgt_handle = edge.get("targetHandle", "")

        if src in node_map:
            src_outputs = [p.get("id") for p in node_map[src].get("data", {}).get("outputs", [])]
            if src_handle and src_outputs and src_handle not in src_outputs:
                src_label = node_map[src].get("data", {}).get("label", src)
                report.warnings.append(f"Edge from '{src_label}' references non-existent output port '{src_handle}'")

        if tgt in node_map:
            tgt_inputs = [p.get("id") for p in node_map[tgt].get("data", {}).get("inputs", [])]
            if tgt_handle and tgt_inputs and tgt_handle not in tgt_inputs:
                tgt_label = node_map[tgt].get("data", {}).get("label", tgt)
                report.warnings.append(f"Edge to '{tgt_label}' references non-existent input port '{tgt_handle}'")

    # ── 6. Estimate runtime ──
    total_time = 0
    for node in nodes:
        if node.get("type") == "groupNode" or node.get("type") == "stickyNote":
            continue
        category = node.get("data", {}).get("category", "flow")
        total_time += CATEGORY_RUNTIME.get(category, 5)
    report.estimated_runtime_s = total_time

    # ── 7. Final summary ──
    if not report.errors:
        report.valid = True

    return report
