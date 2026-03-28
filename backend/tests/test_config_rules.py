"""Tests for declarative cross-field config validation (config_rules.py)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.engine.config_rules import evaluate_rule, evaluate_rules


# ── Numeric operators ─────────────────────────────────────────

class TestNumericOperators:
    def test_lte_passes(self):
        rule = {"fields": ["batch_size"], "op": "lte", "value": 32, "message": "Too big", "severity": "warning"}
        result = evaluate_rule(rule, {"batch_size": 16})
        assert result.passed

    def test_lte_fails(self):
        rule = {"fields": ["batch_size"], "op": "lte", "value": 32, "message": "Too big", "severity": "warning"}
        result = evaluate_rule(rule, {"batch_size": 64})
        assert not result.passed
        assert result.message == "Too big"

    def test_gte_passes(self):
        rule = {"fields": ["alpha"], "op": "gte", "value": 1, "message": "Too small", "severity": "error"}
        result = evaluate_rule(rule, {"alpha": 16})
        assert result.passed

    def test_gte_fails(self):
        rule = {"fields": ["alpha"], "op": "gte", "value": 1, "message": "Too small", "severity": "error"}
        result = evaluate_rule(rule, {"alpha": 0})
        assert not result.passed
        assert result.severity == "error"

    def test_lt(self):
        rule = {"fields": ["lr"], "op": "lt", "value": 0.01, "message": "lr too high", "severity": "warning"}
        assert evaluate_rule(rule, {"lr": 0.001}).passed
        assert not evaluate_rule(rule, {"lr": 0.01}).passed

    def test_gt(self):
        rule = {"fields": ["epochs"], "op": "gt", "value": 0, "message": "Need at least 1 epoch", "severity": "error"}
        assert evaluate_rule(rule, {"epochs": 3}).passed
        assert not evaluate_rule(rule, {"epochs": 0}).passed

    def test_eq(self):
        rule = {"fields": ["r"], "op": "eq", "value": 16, "message": "r must be 16", "severity": "warning"}
        assert evaluate_rule(rule, {"r": 16}).passed
        assert not evaluate_rule(rule, {"r": 8}).passed

    def test_neq(self):
        rule = {"fields": ["dropout"], "op": "neq", "value": 0, "message": "Use nonzero dropout", "severity": "warning"}
        assert evaluate_rule(rule, {"dropout": 0.1}).passed
        assert not evaluate_rule(rule, {"dropout": 0}).passed


# ── Multi-field operators ─────────────────────────────────────

class TestMultiFieldOperators:
    def test_product_lte_passes(self):
        rule = {
            "fields": ["batch_size", "grad_accum"],
            "op": "product_lte",
            "value": 32,
            "message": "Effective batch too big",
            "severity": "warning",
        }
        result = evaluate_rule(rule, {"batch_size": 4, "grad_accum": 8})
        assert result.passed

    def test_product_lte_fails(self):
        rule = {
            "fields": ["batch_size", "grad_accum"],
            "op": "product_lte",
            "value": 32,
            "message": "Effective batch too big",
            "severity": "warning",
        }
        result = evaluate_rule(rule, {"batch_size": 8, "grad_accum": 8})
        assert not result.passed

    def test_sum_lte_passes(self):
        rule = {
            "fields": ["train_split", "eval_split"],
            "op": "sum_lte",
            "value": 1.0,
            "message": "Splits exceed 100%",
            "severity": "error",
        }
        result = evaluate_rule(rule, {"train_split": 0.8, "eval_split": 0.2})
        assert result.passed

    def test_sum_lte_fails(self):
        rule = {
            "fields": ["train_split", "eval_split"],
            "op": "sum_lte",
            "value": 1.0,
            "message": "Splits exceed 100%",
            "severity": "error",
        }
        result = evaluate_rule(rule, {"train_split": 0.8, "eval_split": 0.3})
        assert not result.passed


# ── required_if operator ──────────────────────────────────────

class TestRequiredIf:
    def test_condition_met_and_field_present(self):
        rule = {
            "fields": ["gradient_checkpointing"],
            "op": "required_if",
            "condition_field": "use_lora",
            "condition_value": True,
            "message": "Required when use_lora is enabled",
            "severity": "error",
        }
        result = evaluate_rule(rule, {"use_lora": True, "gradient_checkpointing": True})
        assert result.passed

    def test_condition_met_and_field_missing(self):
        rule = {
            "fields": ["gradient_checkpointing"],
            "op": "required_if",
            "condition_field": "use_lora",
            "condition_value": True,
            "message": "Required when use_lora is enabled",
            "severity": "error",
        }
        result = evaluate_rule(rule, {"use_lora": True})
        assert not result.passed

    def test_condition_not_met(self):
        rule = {
            "fields": ["gradient_checkpointing"],
            "op": "required_if",
            "condition_field": "use_lora",
            "condition_value": True,
            "message": "Required when use_lora is enabled",
            "severity": "error",
        }
        result = evaluate_rule(rule, {"use_lora": False})
        assert result.passed


# ── Edge cases ────────────────────────────────────────────────

class TestEdgeCases:
    def test_missing_field_skips_validation(self):
        """If a referenced field is absent, the rule passes (can't evaluate)."""
        rule = {"fields": ["batch_size"], "op": "lte", "value": 32, "message": "Too big", "severity": "warning"}
        result = evaluate_rule(rule, {})
        assert result.passed

    def test_empty_string_field_skips(self):
        rule = {"fields": ["batch_size"], "op": "lte", "value": 32, "message": "Too big", "severity": "warning"}
        result = evaluate_rule(rule, {"batch_size": ""})
        assert result.passed

    def test_non_numeric_field_skips(self):
        rule = {"fields": ["model_name"], "op": "lte", "value": 100, "message": "Bad", "severity": "warning"}
        result = evaluate_rule(rule, {"model_name": "llama-3"})
        assert result.passed

    def test_unknown_operator_skips(self):
        rule = {"fields": ["x"], "op": "bogus_op", "value": 1, "message": "Unknown", "severity": "warning"}
        result = evaluate_rule(rule, {"x": 5})
        assert result.passed


# ── evaluate_rules batch ──────────────────────────────────────

class TestEvaluateRules:
    def test_returns_only_failures(self):
        rules = [
            {"fields": ["batch_size"], "op": "lte", "value": 32, "message": "Batch too big", "severity": "warning"},
            {"fields": ["lr"], "op": "lte", "value": 0.001, "message": "LR too high", "severity": "warning"},
        ]
        config = {"batch_size": 16, "lr": 0.01}
        failures = evaluate_rules(rules, config)
        assert len(failures) == 1
        assert failures[0].message == "LR too high"

    def test_all_pass_returns_empty(self):
        rules = [
            {"fields": ["batch_size"], "op": "lte", "value": 32, "message": "Too big", "severity": "warning"},
        ]
        failures = evaluate_rules(rules, {"batch_size": 4})
        assert failures == []

    def test_empty_rules(self):
        assert evaluate_rules([], {"anything": 42}) == []

    def test_to_dict(self):
        rule = {"fields": ["x"], "op": "lte", "value": 5, "message": "Over", "severity": "error"}
        result = evaluate_rule(rule, {"x": 10})
        d = result.to_dict()
        assert d["passed"] is False
        assert d["fields"] == ["x"]
        assert d["severity"] == "error"
