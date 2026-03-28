"""
Runtime Preparation — shared helper used by both executor and partial executor.

Consolidates the duplicated logic for preparing a node before execution:
block directory resolution, schema loading, timeout/retry extraction,
composite context selection, input validation, and config validation.

Both executor.py and partial_executor.py MUST call prepare_node_runtime()
instead of open-coding this logic to prevent semantic drift.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .schema_validator import load_block_schema, validate_inputs, validate_config
from .composite import CompositeBlockContext
from ..config import ARTIFACTS_DIR

logger = logging.getLogger(__name__)

# Mapping from expected_type_family to Python types
_TYPE_FAMILY_MAP: dict[str, tuple[type, ...]] = {
    "dict": (dict,),
    "str": (str,),
    "list": (list,),
    "path": (str,),  # paths are strings at runtime
    "any": (),  # matches everything
}


@dataclass
class PreparedNode:
    """All resolved metadata needed to execute a single block."""

    node_id: str
    block_type: str
    block_dir: Path
    block_schema: dict
    timeout_seconds: int | None
    max_retries: int
    is_composite: bool
    context_cls: type | None
    cleaned_config: dict[str, Any]
    run_dir: str
    block_version: str | None


def check_input_types(
    block_schema: dict,
    node_inputs: dict[str, Any],
) -> list[str]:
    """Check runtime input types against declared expected_type_family and cardinality.

    Returns a list of warning messages for mismatches.
    In V1, mismatches are logged as warnings (not errors) for backward compatibility.
    """
    warnings: list[str] = []
    declared_inputs = block_schema.get("inputs", [])
    if not isinstance(declared_inputs, list):
        return warnings

    for input_def in declared_inputs:
        if not isinstance(input_def, dict):
            continue

        port_id = input_def.get("id", "")
        if port_id not in node_inputs:
            continue

        value = node_inputs[port_id]
        if value is None:
            continue

        # Type family check
        expected_family = input_def.get("expected_type_family", "any")
        if expected_family and expected_family != "any":
            expected_types = _TYPE_FAMILY_MAP.get(expected_family)
            if expected_types and not isinstance(value, expected_types):
                actual_type = type(value).__name__
                warnings.append(
                    f"Input '{port_id}': expected type family '{expected_family}', "
                    f"got '{actual_type}'"
                )

        # Cardinality check
        expected_card = input_def.get("cardinality", "any")
        if expected_card == "scalar" and isinstance(value, list):
            warnings.append(
                f"Input '{port_id}': expected scalar value, got list "
                f"(length {len(value)})"
            )
        elif expected_card == "list" and not isinstance(value, list):
            warnings.append(
                f"Input '{port_id}': expected list, got {type(value).__name__}"
            )

    return warnings


def apply_multi_input_policy(
    block_schema: dict,
    node_inputs: dict[str, Any],
    multi_counts: dict[str, int],
) -> dict[str, Any]:
    """Apply multi_input aggregation policy for ports with multiple connections.

    Policies:
    - 'aggregate' (default): collect values into a list (already done by input gathering)
    - 'last_write': keep only the last value received
    - 'error': raise if multiple connections to this port

    Returns updated node_inputs dict.
    """
    declared_inputs = block_schema.get("inputs", [])
    if not isinstance(declared_inputs, list):
        return node_inputs

    policy_map: dict[str, str] = {}
    for input_def in declared_inputs:
        if isinstance(input_def, dict):
            port_id = input_def.get("id", "")
            policy_map[port_id] = input_def.get("multi_input", "aggregate")

    result = dict(node_inputs)
    for port_id, count in multi_counts.items():
        if count <= 1:
            continue

        policy = policy_map.get(port_id, "aggregate")

        if policy == "error":
            from ..block_sdk.exceptions import BlockInputError
            raise BlockInputError(
                f"Input port '{port_id}' does not accept multiple connections",
                details=f"Port received {count} connections but multi_input policy is 'error'.",
                recoverable=False,
            )
        elif policy == "last_write":
            value = result.get(port_id)
            if isinstance(value, list) and value:
                result[port_id] = value[-1]

        # 'aggregate' is the default — values are already collected as a list

    return result


def prepare_node_runtime(
    node_id: str,
    block_type: str,
    config: dict[str, Any],
    node_inputs: dict[str, Any],
    run_id: str,
    *,
    find_block_fn,
    resolve_secrets_fn,
    block_aliases: dict[str, str] | None = None,
    safe_block_type_re=None,
) -> PreparedNode:
    """Prepare a node for execution — shared by full and partial executors.

    Steps:
    1. Resolve block directory (with custom block fallback via baseType)
    2. Load block.yaml schema
    3. Extract timeout, max_retries, composite flag
    4. Resolve secrets in config
    5. Validate inputs (presence check)
    6. Validate config (type checking, defaults, bounds) with inputs= parameter
       so connected inputs satisfy mandatory config fields
    7. Return PreparedNode with all resolved metadata

    Raises:
        RuntimeError: if block type cannot be found
    """
    # --- Step 1: Resolve block directory ---
    block_dir = find_block_fn(block_type)

    # Custom block fallback: try baseType
    if block_dir is None:
        base_type = config.get("baseType", "")
        if base_type and safe_block_type_re and safe_block_type_re.match(base_type):
            if block_aliases:
                base_type = block_aliases.get(base_type, base_type)
            block_dir = find_block_fn(base_type)

    if block_dir is None:
        raise RuntimeError(f"Block type '{block_type}' not found. No run.py available.")

    # --- Step 2: Load schema ---
    block_schema = load_block_schema(block_dir)

    # --- Step 3: Extract execution metadata ---
    timeout_seconds = block_schema.get("timeout") if block_schema else None
    max_retries = block_schema.get("max_retries", 0) if block_schema else 0
    is_composite = block_schema.get("composite", False) if block_schema else False
    block_version = block_schema.get("version") if block_schema else None

    # --- Step 4: Resolve secrets ---
    resolved_config = resolve_secrets_fn(config)

    # --- Step 5 & 6: Pre-execution validation ---
    if block_schema:
        validate_inputs(block_schema, node_inputs)
        # Pass inputs= so connected input ports satisfy mandatory config fields
        resolved_config = validate_config(block_schema, resolved_config, inputs=node_inputs)
        # Runtime type checking (warnings only in V1)
        type_warnings = check_input_types(block_schema, node_inputs)
        for warning in type_warnings:
            logger.warning("Node %s: %s", node_id, warning)

    # --- Step 7: Compute run directory ---
    run_dir = str(ARTIFACTS_DIR / run_id / node_id)

    context_cls = CompositeBlockContext if is_composite else None

    return PreparedNode(
        node_id=node_id,
        block_type=block_type,
        block_dir=block_dir,
        block_schema=block_schema,
        timeout_seconds=timeout_seconds,
        max_retries=max_retries,
        is_composite=is_composite,
        context_cls=context_cls,
        cleaned_config=resolved_config,
        run_dir=run_dir,
        block_version=block_version,
    )
