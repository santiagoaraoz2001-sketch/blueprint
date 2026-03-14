"""Block config validator — validates config against block.yaml schema.

Checks types, applies defaults, enforces bounds (min/max), and validates
select options before a block runs.

Supported config types (from block.yaml):
    string, text_area, file_path — validated as str
    integer                      — validated as int (bool rejected)
    float                        — validated as int or float (bool rejected)
    boolean                      — validated as bool or string "true"/"false"
    select                       — validated as str against options list
"""

from typing import Any

from .exceptions import BlockConfigError

# Config types that are treated as free-form text
_STRING_TYPES = frozenset({"string", "text_area", "file_path"})


def validate_and_apply_defaults(config: dict, schema: dict) -> dict:
    """Validate config values against block.yaml schema and apply defaults.

    Args:
        config: User-provided config dict.
        schema: The 'config' section from block.yaml.

    Returns:
        A new config dict with defaults applied and values validated.

    Raises:
        BlockConfigError: On type mismatch, out-of-bounds, or invalid option.
    """
    result = dict(config)

    for field_name, field_spec in schema.items():
        if not isinstance(field_spec, dict):
            continue

        field_type = field_spec.get("type", "string")

        # Apply default if missing or empty string (but not False or 0)
        if field_name not in result or result[field_name] is None or result[field_name] == "":
            if "default" in field_spec:
                result[field_name] = field_spec["default"]

        value = result.get(field_name)

        # Skip validation for missing optional fields
        if value is None or value == "":
            continue

        # Type checking
        _validate_type(field_name, value, field_type)

        # Bounds checking for numeric types
        if field_type in ("integer", "float"):
            _validate_bounds(field_name, value, field_spec)

        # Select option validation
        if field_type == "select":
            _validate_select(field_name, value, field_spec)

    return result


def _validate_type(field_name: str, value: Any, field_type: str) -> None:
    """Check that value matches the declared config type.

    Important: Python ``bool`` is a subclass of ``int``, so we must check
    for ``bool`` first to prevent ``True``/``False`` from passing as integers.
    """
    if field_type == "integer":
        # Reject booleans — isinstance(True, int) is True in Python
        if isinstance(value, bool):
            raise BlockConfigError(
                field_name,
                f"'{field_name}' must be an integer, got bool: {value!r}",
            )
        if isinstance(value, int):
            return
        if isinstance(value, float):
            # Accept floats that are whole numbers (e.g. 5.0 from YAML)
            if value != int(value):
                raise BlockConfigError(
                    field_name,
                    f"'{field_name}' must be an integer, got float: {value!r}",
                )
            return
        # Try to parse string representation
        if isinstance(value, str):
            try:
                int(value)
                return
            except ValueError:
                pass
        raise BlockConfigError(
            field_name,
            f"'{field_name}' must be an integer, got {type(value).__name__}: {value!r}",
        )

    elif field_type == "float":
        # Reject booleans
        if isinstance(value, bool):
            raise BlockConfigError(
                field_name,
                f"'{field_name}' must be a number, got bool: {value!r}",
            )
        if isinstance(value, (int, float)):
            return
        if isinstance(value, str):
            try:
                float(value)
                return
            except ValueError:
                pass
        raise BlockConfigError(
            field_name,
            f"'{field_name}' must be a number, got {type(value).__name__}: {value!r}",
        )

    elif field_type == "boolean":
        if isinstance(value, bool):
            return
        if isinstance(value, str) and value.lower() in ("true", "false"):
            return
        raise BlockConfigError(
            field_name,
            f"'{field_name}' must be a boolean, got {type(value).__name__}: {value!r}",
        )

    elif field_type == "select":
        if not isinstance(value, str):
            raise BlockConfigError(
                field_name,
                f"'{field_name}' must be a string for select, "
                f"got {type(value).__name__}: {value!r}",
            )

    elif field_type in _STRING_TYPES:
        if not isinstance(value, str):
            raise BlockConfigError(
                field_name,
                f"'{field_name}' must be a string, "
                f"got {type(value).__name__}: {value!r}",
            )


def _validate_bounds(field_name: str, value: Any, field_spec: dict) -> None:
    """Check min/max bounds for numeric fields."""
    try:
        numeric_val = float(value)
    except (ValueError, TypeError):
        return  # Type error already caught by _validate_type

    min_val = field_spec.get("min")
    max_val = field_spec.get("max")

    if min_val is not None and numeric_val < float(min_val):
        raise BlockConfigError(
            field_name,
            f"'{field_name}' value {value} is below minimum {min_val}",
        )
    if max_val is not None and numeric_val > float(max_val):
        raise BlockConfigError(
            field_name,
            f"'{field_name}' value {value} is above maximum {max_val}",
        )


def _validate_select(field_name: str, value: Any, field_spec: dict) -> None:
    """Check that value is one of the allowed options."""
    options = field_spec.get("options", [])
    if options and str(value) not in [str(o) for o in options]:
        raise BlockConfigError(
            field_name,
            f"'{field_name}' value {value!r} not in allowed options: {options}",
        )
