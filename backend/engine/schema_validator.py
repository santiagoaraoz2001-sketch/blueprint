"""
Schema Validator — validates block inputs and config against block.yaml.

Called by the executor BEFORE loading and running a block.
"""

import math
import logging

import yaml
from pathlib import Path
from typing import Any

from ..block_sdk.exceptions import BlockInputError, BlockConfigError

logger = logging.getLogger(__name__)


def load_block_schema(block_dir: Path) -> dict:
    """Load and parse block.yaml from a block directory.

    Returns an empty dict if the file doesn't exist or can't be parsed,
    which disables validation (backward compat).
    """
    schema_path = block_dir / "block.yaml"
    if not schema_path.exists():
        return {}
    try:
        with open(schema_path, "r") as f:
            schema = yaml.safe_load(f)
        return schema if isinstance(schema, dict) else {}
    except yaml.YAMLError as e:
        logger.warning("Failed to parse %s: %s", schema_path, e)
        return {}


def validate_inputs(schema: dict, inputs: dict[str, Any]) -> None:
    """
    Validate that all required inputs are present and have correct types.

    Raises BlockInputError if validation fails.
    """
    declared_inputs = schema.get("inputs", [])
    if not isinstance(declared_inputs, list):
        return

    for input_def in declared_inputs:
        if not isinstance(input_def, dict):
            continue

        input_id = input_def.get("id", "")
        required = input_def.get("required", False)
        expected_type = input_def.get("data_type", "any")

        if required and input_id not in inputs:
            raise BlockInputError(
                f"Required input '{input_def.get('label', input_id)}' is not connected",
                details=f"Connect a {expected_type} source to the '{input_id}' input port.",
                recoverable=False,
            )

        if input_id in inputs and inputs[input_id] is None and required:
            raise BlockInputError(
                f"Required input '{input_def.get('label', input_id)}' received empty data",
                details="The upstream block produced no output for this port.",
                recoverable=False,
            )


def validate_config(
    schema: dict,
    config: dict[str, Any],
    inputs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Validate config values against block.yaml schema.

    - Checks types (string, integer, float, boolean)
    - Enforces min/max bounds
    - Applies defaults for missing keys
    - Returns cleaned config with defaults applied

    Args:
        schema: The full block.yaml schema dict.
        config: User-supplied config values.
        inputs: Runtime inputs dict (optional). When provided, mandatory
            config fields are skipped if the corresponding input port
            already supplies a value.

    Raises BlockConfigError if validation fails.
    """
    config_schema = schema.get("config", {})
    if not isinstance(config_schema, dict):
        return dict(config)

    # Build a set of input port IDs that have data, so we can skip mandatory
    # checks for config fields that are satisfied by a connected input port.
    _config_to_port: dict[str, str] = {
        "model_name": "model",
        "model_id": "model",
        "dataset_name": "dataset",
        "file_path": "dataset",
        "directory_path": "dataset",
        "teacher_model": "teacher",
        "student_model": "student",
        "reward_model": "reward_model",
        "checkpoint_dir": "model",
        "url": "config",
    }

    def _input_provides(field_name: str) -> bool:
        """Return True if a connected input port supplies this config field."""
        if inputs is None:
            return False
        port_id = _config_to_port.get(field_name)
        if not port_id:
            return False
        return port_id in inputs and inputs[port_id] is not None

    cleaned = dict(config)  # Start with user config

    for field_name, field_def in config_schema.items():
        if not isinstance(field_def, dict):
            continue

        field_type = field_def.get("type", "string")
        default = field_def.get("default")
        label = field_def.get("label", field_name)

        # Check mandatory fields — skip if an input port provides the value
        value = cleaned.get(field_name)
        if field_def.get("mandatory") and (value is None or (isinstance(value, str) and value == "")):
            if default is None and not _input_provides(field_name):
                raise BlockConfigError(
                    field_name,
                    f"'{label}' is required — set a value or connect the input port",
                    recoverable=False,
                )

        # Apply default if missing or empty string
        if value is None or (isinstance(value, str) and value == ""):
            if field_name not in cleaned or (isinstance(value, str) and value == ""):
                if default is not None:
                    cleaned[field_name] = default
                continue  # Don't validate missing optional fields
            continue

        # Type validation
        if field_type == "integer":
            if isinstance(value, bool):
                raise BlockConfigError(
                    field_name,
                    f"'{label}' must be an integer, got boolean",
                    recoverable=False,
                )
            try:
                cleaned[field_name] = int(value)
            except (ValueError, TypeError):
                raise BlockConfigError(
                    field_name,
                    f"'{label}' must be an integer, got '{value}'",
                    recoverable=False,
                )

        elif field_type == "float":
            if isinstance(value, bool):
                raise BlockConfigError(
                    field_name,
                    f"'{label}' must be a number, got boolean",
                    recoverable=False,
                )
            try:
                float_val = float(value)
            except (ValueError, TypeError):
                raise BlockConfigError(
                    field_name,
                    f"'{label}' must be a number, got '{value}'",
                    recoverable=False,
                )
            if math.isnan(float_val) or math.isinf(float_val):
                raise BlockConfigError(
                    field_name,
                    f"'{label}' must be a finite number, got '{value}'",
                    recoverable=False,
                )
            cleaned[field_name] = float_val

        elif field_type == "boolean":
            if isinstance(value, str):
                cleaned[field_name] = value.lower() in ("true", "1", "yes")
            else:
                cleaned[field_name] = bool(value)

        elif field_type == "select":
            options = field_def.get("options", [])
            if isinstance(options, list) and options and value not in options:
                raise BlockConfigError(
                    field_name,
                    f"'{label}' must be one of {options}, got '{value}'",
                    recoverable=False,
                )

        # Bounds validation (applies to int and float)
        if field_type in ("integer", "float"):
            val = cleaned[field_name]
            min_val = field_def.get("min")
            max_val = field_def.get("max")
            if min_val is not None and val < min_val:
                raise BlockConfigError(
                    field_name,
                    f"'{label}' must be >= {min_val}, got {val}",
                    recoverable=False,
                )
            if max_val is not None and val > max_val:
                raise BlockConfigError(
                    field_name,
                    f"'{label}' must be <= {max_val}, got {val}",
                    recoverable=False,
                )

    return cleaned


def validate_block(block_dir: Path, inputs: dict, config: dict) -> dict:
    """
    Full pre-execution validation. Returns cleaned config with defaults applied.

    Raises BlockInputError or BlockConfigError on failure.
    """
    schema = load_block_schema(block_dir)
    if not schema:
        return config  # No schema, pass through

    validate_inputs(schema, inputs)
    return validate_config(schema, config, inputs=inputs)
