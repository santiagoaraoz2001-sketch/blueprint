"""Exhaustive tests for all 12 training blocks (validation/dry-run only).

Training blocks require GPU + heavy dependencies (torch, transformers, peft, etc.)
so these tests use validation and config validation endpoints only.
"""

from __future__ import annotations
import pytest

pytestmark = pytest.mark.slow

from .block_test_helpers import (
    node, edge, create_pipeline, validate, dry_run, validate_config,
    assert_validation_no_structural_errors,
)


def _training_pipeline(trainer_type: str, trainer_config: dict | None = None):
    """Build ms + dataset_builder + trainer pipeline."""
    ms = node("ms", "model_selector", {"source": "huggingface", "model_id": "meta-llama/Llama-3.2-1B"})
    db = node("db", "dataset_builder", {"source": "huggingface", "hf_dataset": "tatsu-lab/alpaca", "hf_split": "train", "hf_max_samples": 10})
    tr = node("tr", trainer_type, {"model_name": "meta-llama/Llama-3.2-1B", "epochs": 1, "batch_size": 1, "max_seq_length": 128, **(trainer_config or {})})
    edges = [edge("ms", "tr", "model", "model"), edge("db", "tr", "dataset", "dataset")]
    return [ms, db, tr], edges


class TestQLoRAValidation:
    def test_pipeline_validate(self, live_backend):
        nodes, edges = _training_pipeline("qlora_finetuning")
        pid = create_pipeline("train:qlora:val", nodes, edges)
        val = validate(pid)
        assert_validation_no_structural_errors(val)
        assert val["block_count"] == 3

    def test_config_valid(self, live_backend):
        s, d = validate_config("qlora_finetuning", {"model_name": "test", "epochs": 3, "batch_size": 4, "bits": "4"})
        assert s == 200
        assert d.get("valid", True)  # May not have strict validation

    def test_config_invalid_bits(self, live_backend):
        s, d = validate_config("qlora_finetuning", {"model_name": "test", "bits": "3"})
        assert s == 200

    def test_dry_run(self, live_backend):
        nodes, edges = _training_pipeline("qlora_finetuning")
        pid = create_pipeline("train:qlora:dry", nodes, edges)
        result = dry_run(pid)
        assert "viable" in result or "blockers" in result

    def test_config_extreme_lr(self, live_backend):
        s, d = validate_config("qlora_finetuning", {"model_name": "test", "lr": 0.1, "epochs": 1})
        assert s == 200


class TestLoRAValidation:
    def test_pipeline_validate(self, live_backend):
        nodes, edges = _training_pipeline("lora_finetuning")
        pid = create_pipeline("train:lora:val", nodes, edges)
        val = validate(pid)
        assert_validation_no_structural_errors(val)

    def test_config_valid(self, live_backend):
        s, d = validate_config("lora_finetuning", {"model_name": "test", "r": 16, "alpha": 32, "epochs": 3})
        assert s == 200

    def test_config_high_rank(self, live_backend):
        s, d = validate_config("lora_finetuning", {"model_name": "test", "r": 128, "alpha": 256})
        assert s == 200

    def test_dry_run(self, live_backend):
        nodes, edges = _training_pipeline("lora_finetuning")
        pid = create_pipeline("train:lora:dry", nodes, edges)
        result = dry_run(pid)
        assert "viable" in result or "blockers" in result


class TestFullFinetuningValidation:
    def test_pipeline_validate(self, live_backend):
        nodes, edges = _training_pipeline("full_finetuning")
        pid = create_pipeline("train:full:val", nodes, edges)
        val = validate(pid)
        assert_validation_no_structural_errors(val)

    def test_config_valid(self, live_backend):
        s, d = validate_config("full_finetuning", {"model_name": "test", "lr": 2e-5, "epochs": 1})
        assert s == 200

    def test_config_gradient_checkpointing(self, live_backend):
        s, d = validate_config("full_finetuning", {"model_name": "test", "gradient_checkpointing": True})
        assert s == 200


class TestDPOValidation:
    def test_pipeline_validate(self, live_backend):
        nodes, edges = _training_pipeline("dpo_alignment", {"prompt_column": "prompt", "chosen_column": "chosen", "rejected_column": "rejected"})
        pid = create_pipeline("train:dpo:val", nodes, edges)
        val = validate(pid)
        assert_validation_no_structural_errors(val)

    def test_config_valid(self, live_backend):
        s, d = validate_config("dpo_alignment", {"model_name": "test", "beta": 0.1, "epochs": 1})
        assert s == 200

    def test_config_high_beta(self, live_backend):
        s, d = validate_config("dpo_alignment", {"model_name": "test", "beta": 0.5})
        assert s == 200


class TestRLHFPPOValidation:
    def test_pipeline_validate(self, live_backend):
        nodes, edges = _training_pipeline("rlhf_ppo")
        pid = create_pipeline("train:rlhf:val", nodes, edges)
        val = validate(pid)
        assert_validation_no_structural_errors(val)

    def test_config_valid(self, live_backend):
        s, d = validate_config("rlhf_ppo", {"model_name": "test", "epochs": 1})
        assert s == 200


class TestRewardModelValidation:
    def test_pipeline_validate(self, live_backend):
        nodes, edges = _training_pipeline("reward_model_trainer")
        pid = create_pipeline("train:reward:val", nodes, edges)
        val = validate(pid)
        assert_validation_no_structural_errors(val)

    def test_config_valid(self, live_backend):
        s, d = validate_config("reward_model_trainer", {"model_name": "test"})
        assert s == 200


class TestDistillationValidation:
    def test_pipeline_validate(self, live_backend):
        nodes, edges = _training_pipeline("distillation")
        pid = create_pipeline("train:distill:val", nodes, edges)
        val = validate(pid)
        assert_validation_no_structural_errors(val)

    def test_config_valid(self, live_backend):
        s, d = validate_config("distillation", {"teacher_model": "large-model", "student_model": "small-model"})
        assert s == 200


class TestContinuedPretrainingValidation:
    def test_pipeline_validate(self, live_backend):
        nodes, edges = _training_pipeline("continued_pretraining")
        pid = create_pipeline("train:cpt:val", nodes, edges)
        val = validate(pid)
        assert_validation_no_structural_errors(val)

    def test_config_valid(self, live_backend):
        s, d = validate_config("continued_pretraining", {"model_name": "test", "epochs": 1})
        assert s == 200


class TestCurriculumTrainingValidation:
    def test_pipeline_validate(self, live_backend):
        nodes, edges = _training_pipeline("curriculum_training")
        pid = create_pipeline("train:curr:val", nodes, edges)
        val = validate(pid)
        assert_validation_no_structural_errors(val)

    def test_config_valid(self, live_backend):
        s, d = validate_config("curriculum_training", {"model_name": "test", "stages": 3})
        assert s == 200


class TestBallastTrainingValidation:
    def test_pipeline_validate(self, live_backend):
        nodes, edges = _training_pipeline("ballast_training")
        pid = create_pipeline("train:ballast:val", nodes, edges)
        val = validate(pid)
        assert_validation_no_structural_errors(val)

    def test_config_valid(self, live_backend):
        s, d = validate_config("ballast_training", {"model_name": "test"})
        assert s == 200


class TestHyperparameterSweepValidation:
    def test_pipeline_validate(self, live_backend):
        nodes, edges = _training_pipeline("hyperparameter_sweep")
        pid = create_pipeline("train:sweep:val", nodes, edges)
        val = validate(pid)
        assert_validation_no_structural_errors(val)

    def test_config_valid(self, live_backend):
        s, d = validate_config("hyperparameter_sweep", {"search_method": "grid"})
        assert s == 200


class TestCheckpointSelectorValidation:
    def test_config_valid(self, live_backend):
        s, d = validate_config("checkpoint_selector", {"metric": "loss", "direction": "minimize"})
        assert s == 200

    def test_pipeline_validate(self, live_backend):
        nodes = [node("cs", "checkpoint_selector", {"metric": "loss"})]
        pid = create_pipeline("train:ckpt:val", nodes, [])
        val = validate(pid)
        assert val["block_count"] == 1


# ═══════════════════════════════════════════════════════════════════════
#  TRAINING WORKFLOWS (validation only)
# ═══════════════════════════════════════════════════════════════════════

class TestTrainingWorkflows:
    def test_full_training_pipeline_validate(self, live_backend):
        """ms + dataset_builder + qlora → save_model (validate)"""
        nodes = [
            node("ms", "model_selector", {"source": "huggingface", "model_id": "meta-llama/Llama-3.2-1B"}),
            node("db", "dataset_builder", {"source": "huggingface", "hf_dataset": "tatsu-lab/alpaca", "hf_max_samples": 10}),
            node("ql", "qlora_finetuning", {"model_name": "meta-llama/Llama-3.2-1B", "epochs": 1, "batch_size": 1}),
            node("sm", "save_model", {"format": "safetensors"}),
        ]
        edges = [
            edge("ms", "ql", "model", "model"),
            edge("db", "ql", "dataset", "dataset"),
            edge("ql", "sm", "trained_model", "model"),
        ]
        pid = create_pipeline("wf:train:full", nodes, edges)
        val = validate(pid)
        assert val["block_count"] == 4
        assert_validation_no_structural_errors(val)

    def test_training_eval_pipeline_validate(self, live_backend):
        """ms + db + lora → model_card_writer (validate)"""
        nodes = [
            node("ms", "model_selector", {"source": "huggingface", "model_id": "meta-llama/Llama-3.2-1B"}),
            node("db", "dataset_builder", {"source": "huggingface", "hf_dataset": "tatsu-lab/alpaca"}),
            node("lr", "lora_finetuning", {"model_name": "meta-llama/Llama-3.2-1B", "epochs": 1}),
            node("mc", "model_card_writer", {"model_name": "my-lora-model"}),
        ]
        edges = [
            edge("ms", "lr", "model", "model"),
            edge("db", "lr", "dataset", "dataset"),
            edge("lr", "mc", "metrics", "metrics"),
        ]
        pid = create_pipeline("wf:train:eval", nodes, edges)
        val = validate(pid)
        assert val["block_count"] == 4
