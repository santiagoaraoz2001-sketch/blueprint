"""Pipeline Validator — pre-run validation without executing blocks."""

from dataclasses import dataclass, field
from typing import Any

from .block_registry import is_known_block, get_block_types, get_block_config_schema
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

# Port type compatibility matrix (mirrors frontend isPortCompatible)
# SOURCE → CAN CONNECT TO (must match frontend block-registry-types.ts COMPAT)
COMPAT = {
    ("any", "any"), ("dataset", "dataset"), ("text", "text"), ("model", "model"),
    ("config", "config"), ("metrics", "metrics"), ("embedding", "embedding"),
    ("artifact", "artifact"), ("agent", "agent"), ("llm", "llm"),
    # Cross-type coercions
    ("dataset", "text"), ("text", "dataset"),
    # REMOVED: ("text", "config"), ("config", "text") — no more text↔config
    ("config", "text"),  # config→text still allowed (config can serialize to text)
    ("config", "llm"), ("model", "llm"),  # config/model → llm (agent inputs)
    ("llm", "model"), ("llm", "config"),  # llm → model/config (backward compat)
    ("metrics", "dataset"), ("metrics", "text"),
    ("embedding", "dataset"),
    ("artifact", "text"),
}

# Backward-compat aliases for old port type names
_PORT_TYPE_ALIASES = {
    "llm_config": "llm",
}

def _port_compatible(src_type: str, tgt_type: str) -> bool:
    src_type = _PORT_TYPE_ALIASES.get(src_type, src_type)
    tgt_type = _PORT_TYPE_ALIASES.get(tgt_type, tgt_type)
    if src_type == "any" or tgt_type == "any":
        return True
    return (src_type, tgt_type) in COMPAT

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

    # ── 2. Check for cycles (DFS) ──
    adjacency: dict[str, list[str]] = {nid: [] for nid in node_map}
    for edge in edges:
        src = edge.get("source", "")
        tgt = edge.get("target", "")
        if src in adjacency:
            adjacency[src].append(tgt)

    # DFS cycle detection
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {nid: WHITE for nid in node_map}

    def dfs(node_id: str) -> bool:
        color[node_id] = GRAY
        for neighbor in adjacency.get(node_id, []):
            if color.get(neighbor) == GRAY:
                return True  # cycle found
            if color.get(neighbor) == WHITE:
                if dfs(neighbor):
                    return True
        color[node_id] = BLACK
        return False

    for nid in node_map:
        if color[nid] == WHITE:
            if dfs(nid):
                report.errors.append("Pipeline contains a cycle — blocks cannot have circular dependencies")
                report.valid = False
                break

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
        node_data = node.get("data", {})
        # Check both regular inputs and side inputs for required connections
        all_target_ports = node_data.get("inputs", []) + node_data.get("side_inputs", [])
        for in_port in all_target_ports:
            if in_port.get("required", False) and (nid, in_port.get("id")) not in connected_target_handles:
                node_label = node_data.get("label", nid)
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

        for in_port in tgt_data.get("inputs", []) + tgt_data.get("side_inputs", []):
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
            tgt_data = node_map[tgt].get("data", {})
            tgt_inputs = [p.get("id") for p in tgt_data.get("inputs", [])]
            tgt_side_inputs = [p.get("id") for p in tgt_data.get("side_inputs", [])]
            tgt_all_inputs = tgt_inputs + tgt_side_inputs
            if tgt_handle and tgt_all_inputs and tgt_handle not in tgt_all_inputs:
                tgt_label = tgt_data.get("label", tgt)
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
