"""Declarative cross-field config validation engine.

Evaluates a closed set of operators against block config values.
No eval(), no arbitrary code — just simple comparisons and arithmetic.
"""

from __future__ import annotations

import math
from typing import Any


# ── Operator registry ─────────────────────────────────────────

def _op_lte(values: list[float], threshold: float) -> bool:
    """Single field <= value."""
    return values[0] <= threshold


def _op_gte(values: list[float], threshold: float) -> bool:
    return values[0] >= threshold


def _op_lt(values: list[float], threshold: float) -> bool:
    return values[0] < threshold


def _op_gt(values: list[float], threshold: float) -> bool:
    return values[0] > threshold


def _op_eq(values: list[float], threshold: float) -> bool:
    return values[0] == threshold


def _op_neq(values: list[float], threshold: float) -> bool:
    return values[0] != threshold


def _op_product_lte(values: list[float], threshold: float) -> bool:
    """Product of all field values <= threshold."""
    product = 1.0
    for v in values:
        product *= v
    return product <= threshold


def _op_sum_lte(values: list[float], threshold: float) -> bool:
    """Sum of all field values <= threshold."""
    return sum(values) <= threshold


_OPERATORS: dict[str, Any] = {
    "lte": _op_lte,
    "gte": _op_gte,
    "lt": _op_lt,
    "gt": _op_gt,
    "eq": _op_eq,
    "neq": _op_neq,
    "product_lte": _op_product_lte,
    "sum_lte": _op_sum_lte,
}


# ── Rule model ────────────────────────────────────────────────

class ValidationResult:
    """Result of evaluating a single validation rule."""
    __slots__ = ("fields", "message", "severity", "passed")

    def __init__(self, fields: list[str], message: str, severity: str, passed: bool):
        self.fields = fields
        self.message = message
        self.severity = severity
        self.passed = passed

    def to_dict(self) -> dict[str, Any]:
        return {
            "fields": self.fields,
            "message": self.message,
            "severity": self.severity,
            "passed": self.passed,
        }


def evaluate_rule(rule: dict[str, Any], config: dict[str, Any]) -> ValidationResult:
    """Evaluate a single declarative validation rule against a config dict.

    Rule format:
        {
            "fields": ["batch_size", "gradient_accumulation_steps"],
            "op": "product_lte",
            "value": 32,
            "message": "Effective batch size may cause memory issues",
            "severity": "warning"
        }

    Special case — ``required_if``:
        {
            "fields": ["gradient_checkpointing"],
            "op": "required_if",
            "condition_field": "use_lora",
            "condition_value": true,
            "message": "gradient_checkpointing is required when use_lora is enabled",
            "severity": "error"
        }
    """
    fields: list[str] = rule.get("fields", [])
    op: str = rule.get("op", "")
    message: str = rule.get("message", "Validation failed")
    severity: str = rule.get("severity", "warning")

    # Handle required_if specially
    if op == "required_if":
        condition_field = rule.get("condition_field", "")
        condition_value = rule.get("condition_value")
        if config.get(condition_field) == condition_value:
            # The condition is met — check that the target fields are non-empty
            for field in fields:
                val = config.get(field)
                if val is None or val == "" or val is False:
                    return ValidationResult(fields, message, severity, passed=False)
        return ValidationResult(fields, message, severity, passed=True)

    # Standard numeric operators
    func = _OPERATORS.get(op)
    if func is None:
        # Unknown operator — skip silently
        return ValidationResult(fields, f"Unknown operator: {op}", "warning", passed=True)

    # Gather numeric values for all referenced fields
    values: list[float] = []
    for field in fields:
        raw = config.get(field)
        if raw is None or raw == "":
            # Missing field — can't evaluate, treat as passed
            return ValidationResult(fields, message, severity, passed=True)
        try:
            values.append(float(raw))
        except (TypeError, ValueError):
            return ValidationResult(fields, message, severity, passed=True)

    threshold = rule.get("value", 0)
    try:
        threshold = float(threshold)
    except (TypeError, ValueError):
        return ValidationResult(fields, message, severity, passed=True)

    passed = func(values, threshold)
    return ValidationResult(fields, message, severity, passed=passed)


def evaluate_rules(rules: list[dict[str, Any]], config: dict[str, Any]) -> list[ValidationResult]:
    """Evaluate all rules and return only the ones that FAILED."""
    results: list[ValidationResult] = []
    for rule in rules:
        result = evaluate_rule(rule, config)
        if not result.passed:
            results.append(result)
    return results
