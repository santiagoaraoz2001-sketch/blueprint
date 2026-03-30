"""Exhaustive tests for all 5 merge blocks (validation only — need GPU + models)."""

from __future__ import annotations
import pytest

pytestmark = pytest.mark.slow

from .block_test_helpers import node, edge, create_pipeline, validate, validate_config, assert_validation_no_structural_errors


def _merge_pipeline(merge_type: str, extra_config: dict | None = None):
    ms_a = node("ms_a", "model_selector", {"source": "huggingface", "model_id": "meta-llama/Llama-3.2-1B"})
    ms_b = node("ms_b", "model_selector", {"source": "huggingface", "model_id": "meta-llama/Llama-3.2-1B"})
    merger = node("m", merge_type, {"output_path": "/tmp/merged", **(extra_config or {})})
    edges = [edge("ms_a", "m", "model", "model_a"), edge("ms_b", "m", "model", "model_b")]
    return [ms_a, ms_b, merger], edges


class TestMergekitMerge:
    def test_validate(self, live_backend):
        nodes, edges = _merge_pipeline("mergekit_merge", {"method": "slerp", "weight": 0.5})
        pid = create_pipeline("merge:mk:val", nodes, edges)
        val = validate(pid)
        assert_validation_no_structural_errors(val)
        assert val["block_count"] == 3

    def test_config(self, live_backend):
        s, d = validate_config("mergekit_merge", {"method": "slerp", "weight": 0.5})
        assert s == 200

    def test_config_ties(self, live_backend):
        s, d = validate_config("mergekit_merge", {"method": "ties", "density": 0.5})
        assert s == 200


class TestTIESMerge:
    def test_validate(self, live_backend):
        nodes, edges = _merge_pipeline("ties_merge")
        pid = create_pipeline("merge:ties:val", nodes, edges)
        val = validate(pid)
        assert_validation_no_structural_errors(val)

    def test_config(self, live_backend):
        s, d = validate_config("ties_merge", {"density": 0.5, "weight": 0.7})
        assert s == 200


class TestDAREMerge:
    def test_validate(self, live_backend):
        nodes, edges = _merge_pipeline("dare_merge")
        pid = create_pipeline("merge:dare:val", nodes, edges)
        val = validate(pid)
        assert_validation_no_structural_errors(val)

    def test_config(self, live_backend):
        s, d = validate_config("dare_merge", {"drop_rate": 0.1, "rescale": True})
        assert s == 200


class TestSLERPMerge:
    def test_validate(self, live_backend):
        nodes, edges = _merge_pipeline("slerp_merge")
        pid = create_pipeline("merge:slerp:val", nodes, edges)
        val = validate(pid)
        assert_validation_no_structural_errors(val)

    def test_config(self, live_backend):
        s, d = validate_config("slerp_merge", {"weight": 0.5})
        assert s == 200


class TestFrankenmerge:
    def test_validate(self, live_backend):
        nodes, edges = _merge_pipeline("frankenmerge")
        pid = create_pipeline("merge:frank:val", nodes, edges)
        val = validate(pid)
        assert_validation_no_structural_errors(val)

    def test_config(self, live_backend):
        s, d = validate_config("frankenmerge", {"layer_ranges": "0-16:A,16-32:B"})
        assert s == 200


class TestMergeWorkflows:
    def test_merge_to_save_validate(self, live_backend):
        ms_a = node("ms_a", "model_selector", {"source": "huggingface", "model_id": "meta-llama/Llama-3.2-1B"})
        ms_b = node("ms_b", "model_selector", {"source": "huggingface", "model_id": "meta-llama/Llama-3.2-1B"})
        merger = node("m", "slerp_merge", {"weight": 0.5})
        save = node("sm", "save_model", {"format": "safetensors"})
        edges = [
            edge("ms_a", "m", "model", "model_a"),
            edge("ms_b", "m", "model", "model_b"),
            edge("m", "sm", "merged_model", "model"),
        ]
        pid = create_pipeline("wf:merge:save", [ms_a, ms_b, merger, save], edges)
        val = validate(pid)
        assert val["block_count"] == 4
