"""Tests for the dry-run simulator (prompt 4.2)."""

import pytest
from unittest.mock import MagicMock, patch

from backend.engine.dry_run import (
    simulate,
    DryRunResult,
    NodeEstimate,
    TotalEstimate,
    _guess_model_size_b,
    _estimate_training_memory_mb,
)
from backend.engine.planner_models import (
    ExecutionPlan,
    ResolvedNode,
    PlannerResult,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolved_node(
    node_id: str,
    block_type: str,
    config: dict | None = None,
) -> ResolvedNode:
    return ResolvedNode(
        node_id=node_id,
        block_type=block_type,
        block_version="1.0.0",
        resolved_config=config or {},
        config_sources={},
        cache_fingerprint="abc123",
        cache_eligible=True,
        in_loop=False,
        loop_id=None,
    )


def _make_plan(nodes: dict[str, ResolvedNode], order: tuple[str, ...] | None = None) -> ExecutionPlan:
    return ExecutionPlan(
        execution_order=order or tuple(nodes.keys()),
        nodes=nodes,
        loops=(),
        independent_subgraphs=(),
        plan_hash="test",
        warnings=(),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestDryRunDetectsMissingTorch:
    """Task 173: test_dry_run_detects_missing_torch."""

    def test_training_block_no_torch_no_mlx(self):
        """Pipeline with a training block when neither torch nor mlx is available
        should report a blocker."""
        node = _resolved_node("n1", "lora_finetuning", {
            "model_name": "meta-llama/Llama-3.2-3B",
            "batch_size": 4,
            "epochs": 3,
            "prefer_framework": "auto",
        })
        plan = _make_plan({"n1": node})

        capabilities = {
            "torch": False,
            "mlx": False,
            "gpu_memory_mb": 0,
            "system_memory_mb": 16384,
        }

        result = simulate(plan, capabilities)

        assert result.viable is False
        assert len(result.blockers) >= 1
        assert any("PyTorch" in b or "MLX" in b for b in result.blockers)

    def test_training_block_with_torch_available(self):
        """Same training block but torch is available — no blocker."""
        node = _resolved_node("n1", "lora_finetuning", {
            "model_name": "meta-llama/Llama-3.2-3B",
            "prefer_framework": "auto",
        })
        plan = _make_plan({"n1": node})

        capabilities = {
            "torch": True,
            "mlx": False,
            "gpu_memory_mb": 8192,
            "system_memory_mb": 32768,
        }

        result = simulate(plan, capabilities)

        assert result.viable is True
        assert len(result.blockers) == 0

    def test_training_block_prefers_pytorch_but_missing(self):
        """Block explicitly requires pytorch but it's not installed."""
        node = _resolved_node("n1", "lora_finetuning", {
            "prefer_framework": "pytorch",
        })
        plan = _make_plan({"n1": node})

        capabilities = {"torch": False, "mlx": True}

        result = simulate(plan, capabilities)

        assert result.viable is False
        assert any("PyTorch" in b for b in result.blockers)


class TestDryRunEstimatesMemory:
    """Task 173: test_dry_run_estimates_memory."""

    def test_known_model_size_reasonable_estimate(self):
        """Training block with a known 7B model should estimate > 10GB memory."""
        node = _resolved_node("n1", "lora_finetuning", {
            "model_name": "meta-llama/Llama-3.1-7B",
            "batch_size": 4,
            "epochs": 3,
        })
        plan = _make_plan({"n1": node})

        capabilities = {"torch": True, "mlx": False}

        result = simulate(plan, capabilities)

        est = result.per_node_estimates["n1"]
        # 7B * 2 bytes * activation factor → should be well over 10GB
        assert est.estimated_memory_mb >= 10000
        assert est.estimated_duration_class in ("minutes", "hours")

    def test_small_model_less_memory(self):
        """A 125M model should use much less memory than a 7B model."""
        node_small = _resolved_node("n1", "lora_finetuning", {
            "model_name": "gpt2-125m",
            "batch_size": 4,
        })
        node_large = _resolved_node("n2", "lora_finetuning", {
            "model_name": "meta-llama/Llama-3.1-7B",
            "batch_size": 4,
        })
        plan = _make_plan({"n1": node_small, "n2": node_large})
        capabilities = {"torch": True, "mlx": False}

        result = simulate(plan, capabilities)

        assert (
            result.per_node_estimates["n1"].estimated_memory_mb
            < result.per_node_estimates["n2"].estimated_memory_mb
        )

    def test_int4_precision_reduces_memory(self):
        """int4 precision should use less memory than float16."""
        node_fp16 = _resolved_node("fp16", "lora_finetuning", {
            "model_name": "meta-llama/Llama-3.1-7B",
            "precision": "float16",
        })
        node_int4 = _resolved_node("int4", "lora_finetuning", {
            "model_name": "meta-llama/Llama-3.1-7B",
            "precision": "int4",
        })
        plan = _make_plan({"fp16": node_fp16, "int4": node_int4})
        capabilities = {"torch": True, "mlx": False}

        result = simulate(plan, capabilities)

        assert (
            result.per_node_estimates["int4"].estimated_memory_mb
            < result.per_node_estimates["fp16"].estimated_memory_mb
        )

    def test_inference_block_estimates(self):
        """Inference block should produce reasonable memory estimate."""
        node = _resolved_node("n1", "text_generation", {
            "model_name": "meta-llama/Llama-3.1-7B",
            "max_tokens": 2048,
        })
        plan = _make_plan({"n1": node})
        capabilities = {"torch": True, "mlx": False}

        result = simulate(plan, capabilities)

        est = result.per_node_estimates["n1"]
        assert est.estimated_memory_mb > 1000  # 7B model needs several GB
        assert est.confidence == "medium"


class TestDryRunUsesHistory:
    """Task 173: test_dry_run_uses_history."""

    def test_historical_data_improves_confidence(self):
        """When historical run data exists, confidence should be 'high'."""
        node = _resolved_node("n1", "lora_finetuning", {
            "model_name": "meta-llama/Llama-3.1-7B",
        })
        plan = _make_plan({"n1": node})
        capabilities = {"torch": True, "mlx": False}

        run_history = [
            {"block_type": "lora_finetuning", "duration_seconds": 300, "peak_memory_mb": 14000},
            {"block_type": "lora_finetuning", "duration_seconds": 320, "peak_memory_mb": 14200},
            {"block_type": "lora_finetuning", "duration_seconds": 310, "peak_memory_mb": 14100},
        ]

        result = simulate(plan, capabilities, run_history)

        est = result.per_node_estimates["n1"]
        assert est.confidence == "high"
        assert est.estimated_duration_class == "minutes"  # 300s avg → minutes

    def test_no_history_uses_heuristic(self):
        """Without history, confidence should be 'medium' for known block types."""
        node = _resolved_node("n1", "lora_finetuning", {
            "model_name": "meta-llama/Llama-3.1-7B",
        })
        plan = _make_plan({"n1": node})
        capabilities = {"torch": True, "mlx": False}

        result = simulate(plan, capabilities, run_history=None)

        est = result.per_node_estimates["n1"]
        assert est.confidence == "medium"

    def test_history_for_different_block_type_not_used(self):
        """History for a different block type should not affect estimates."""
        node = _resolved_node("n1", "text_generation", {
            "model_name": "meta-llama/Llama-3.1-7B",
        })
        plan = _make_plan({"n1": node})
        capabilities = {"torch": True, "mlx": False}

        run_history = [
            {"block_type": "lora_finetuning", "duration_seconds": 300, "peak_memory_mb": 14000},
        ]

        result = simulate(plan, capabilities, run_history)

        est = result.per_node_estimates["n1"]
        assert est.confidence == "medium"  # Not high — history doesn't match


class TestDryRunOnSimplePipeline:
    """Task 173: test_dry_run_on_simple_pipeline."""

    def test_three_block_dag_viable(self):
        """A simple 3-block DAG (data → model → evaluation) should be viable
        with all estimates present."""
        nodes = {
            "loader": _resolved_node("loader", "csv_loader", {}),
            "gen": _resolved_node("gen", "text_generation", {
                "model_name": "gpt2",
                "max_tokens": 512,
            }),
            "eval": _resolved_node("eval", "perplexity_eval", {
                "model_name": "gpt2",
                "num_samples": 100,
            }),
        }
        plan = _make_plan(nodes, order=("loader", "gen", "eval"))

        capabilities = {
            "torch": True,
            "mlx": False,
            "gpu_memory_mb": 8192,
            "system_memory_mb": 32768,
        }

        result = simulate(plan, capabilities)

        # Viability
        assert result.viable is True
        assert len(result.blockers) == 0

        # All nodes have estimates
        assert len(result.per_node_estimates) == 3
        assert "loader" in result.per_node_estimates
        assert "gen" in result.per_node_estimates
        assert "eval" in result.per_node_estimates

        # Total estimate is present and reasonable
        total = result.total_estimate
        assert total.peak_memory_mb > 0
        assert total.total_artifact_volume_mb >= 0
        assert total.runtime_class in ("seconds", "minutes", "hours")
        assert total.confidence in ("high", "medium", "low")

        # File loader should be fast
        assert result.per_node_estimates["loader"].estimated_duration_class == "seconds"

    def test_empty_plan_viable(self):
        """Empty plan should be viable with zero estimates."""
        plan = _make_plan({}, order=())
        result = simulate(plan, {"torch": True})

        assert result.viable is True
        assert result.total_estimate.peak_memory_mb == 0

    def test_unknown_block_type_low_confidence(self):
        """Completely unknown block type should produce low-confidence estimate."""
        node = _resolved_node("n1", "some_totally_custom_block", {})
        plan = _make_plan({"n1": node})
        result = simulate(plan, {"torch": True})

        assert result.viable is True
        assert result.per_node_estimates["n1"].confidence == "low"


# ---------------------------------------------------------------------------
# Unit tests for internal helpers
# ---------------------------------------------------------------------------

class TestModelSizeGuessing:
    def test_parse_7b_from_name(self):
        assert _guess_model_size_b({"model_name": "meta-llama/Llama-3.1-7B"}) == 7.0

    def test_parse_70b(self):
        assert _guess_model_size_b({"model_name": "meta-llama/Llama-3.1-70B-Instruct"}) == 70.0

    def test_parse_125m(self):
        # gpt2-125m resolves via family registry (0.124) or regex (0.125)
        result = _guess_model_size_b({"model_name": "gpt2-125m"})
        assert result is not None
        assert abs(result - 0.125) < 0.01

    def test_explicit_model_size_b(self):
        assert _guess_model_size_b({"model_size_b": 13.0}) == 13.0

    def test_no_model_info(self):
        assert _guess_model_size_b({}) is None


class TestTrainingMemoryEstimation:
    def test_7b_fp16_reasonable_range(self):
        mem = _estimate_training_memory_mb({
            "model_name": "Llama-7B",
            "batch_size": 4,
            "precision": "float16",
        })
        # 7B * 2 bytes = ~14GB base, with activation overhead → 14-50GB
        assert 10000 < mem < 50000

    def test_3b_int4_less_than_7b_fp16(self):
        mem_small = _estimate_training_memory_mb({
            "model_name": "Llama-3B",
            "batch_size": 4,
            "precision": "int4",
        })
        mem_large = _estimate_training_memory_mb({
            "model_name": "Llama-7B",
            "batch_size": 4,
            "precision": "float16",
        })
        assert mem_small < mem_large
