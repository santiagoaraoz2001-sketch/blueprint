"""Tests for the Copilot rule engine, AI service, and API endpoints."""

from __future__ import annotations

import sys
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.services.copilot_rules import RuleEngine, Alert, get_variant_field_hints
from backend.services.copilot_ai import AICopilot


# ── Helpers ──────────────────────────────────────────────────────────

def _make_node(
    node_id: str,
    block_type: str,
    config: dict | None = None,
    label: str | None = None,
    category: str = "",
    version: str | None = None,
) -> dict:
    """Create a minimal pipeline node dict."""
    data: dict = {
        "type": block_type,
        "label": label or block_type,
        "config": config or {},
    }
    if version:
        data["version"] = version
    return {"id": node_id, "type": "blockNode", "data": data, "position": {"x": 0, "y": 0}}


def _make_edge(source: str, target: str, src_handle: str = "output", tgt_handle: str = "input") -> dict:
    return {
        "id": f"{source}-{target}",
        "source": source,
        "target": target,
        "sourceHandle": src_handle,
        "targetHandle": tgt_handle,
    }


class _FakeSchema:
    """Minimal schema stub for registry mocking."""
    def __init__(self, block_type: str, category: str, version: str = "1.0.0",
                 inputs: list | None = None, config: list | None = None):
        self.block_type = block_type
        self.category = category
        self.version = version
        self.inputs = inputs or []
        self.config = config or []


class _FakePort:
    def __init__(self, port_id: str, required: bool = False):
        self.id = port_id
        self.required = required


class _FakeConfigField:
    def __init__(self, key: str, ftype: str = "string", options: list | None = None,
                 fmin: float | None = None, fmax: float | None = None):
        self.key = key
        self.type = ftype
        self.options = options or []
        self.min = fmin
        self.max = fmax


class _FakeRegistry:
    """Minimal registry stub for rule engine tests."""
    def __init__(self, blocks: dict[str, _FakeSchema] | None = None):
        self._blocks = blocks or {}

    def get(self, block_type: str) -> _FakeSchema | None:
        return self._blocks.get(block_type)


# ── Test 1: OOM Rule Triggers ────────────────────────────────────────

class TestOOMRule:
    def test_oom_rule_triggers(self):
        """OOM rule fires when estimated memory exceeds available memory."""
        engine = RuleEngine()
        registry = _FakeRegistry({
            "fine_tune": _FakeSchema("fine_tune", "training"),
        })

        nodes = [
            _make_node("n1", "fine_tune", config={
                "model_name": "llama-7b",
                "batch_size": 8,
                "gradient_accumulation_steps": 4,
                "dtype": "float32",
            }),
        ]
        edges: list = []
        capabilities = {"available_memory_gb": 8}

        alerts = engine.evaluate(nodes, edges, capabilities, registry)

        oom_alerts = [a for a in alerts if a.id.startswith("oom-")]
        assert len(oom_alerts) == 1
        alert = oom_alerts[0]
        assert alert.severity == "error"
        assert "7.0B" in alert.message
        assert "batch_size=8" in alert.message
        assert alert.affected_node_id == "n1"

    def test_oom_no_trigger_with_enough_memory(self):
        """OOM rule does not fire when memory is sufficient."""
        engine = RuleEngine()
        registry = _FakeRegistry({
            "fine_tune": _FakeSchema("fine_tune", "training"),
        })

        nodes = [
            _make_node("n1", "fine_tune", config={
                "model_name": "gpt2",  # 0.117B params — tiny
                "batch_size": 1,
            }),
        ]
        capabilities = {"available_memory_gb": 64}

        alerts = engine.evaluate(nodes, [], capabilities, registry)
        oom_alerts = [a for a in alerts if a.id.startswith("oom-")]
        assert len(oom_alerts) == 0


# ── Test 2: Missing Evaluation Detected ──────────────────────────────

class TestMissingEvaluation:
    def test_missing_eval_detected(self):
        """Warning fires when training block exists without downstream evaluation."""
        engine = RuleEngine()
        registry = _FakeRegistry({
            "fine_tune": _FakeSchema("fine_tune", "training"),
            "save_model": _FakeSchema("save_model", "utilities"),
        })

        nodes = [
            _make_node("n1", "fine_tune"),
            _make_node("n2", "save_model"),
        ]
        edges = [_make_edge("n1", "n2")]

        alerts = engine.evaluate(nodes, edges, registry=registry)

        eval_alerts = [a for a in alerts if a.id == "missing-eval"]
        assert len(eval_alerts) == 1
        assert eval_alerts[0].severity == "warning"

    def test_no_warning_when_eval_present(self):
        """No warning when evaluation block follows training."""
        engine = RuleEngine()
        registry = _FakeRegistry({
            "fine_tune": _FakeSchema("fine_tune", "training"),
            "evaluate": _FakeSchema("evaluate", "metrics"),
        })

        nodes = [
            _make_node("n1", "fine_tune"),
            _make_node("n2", "evaluate"),
        ]
        edges = [_make_edge("n1", "n2")]

        alerts = engine.evaluate(nodes, edges, registry=registry)
        eval_alerts = [a for a in alerts if a.id == "missing-eval"]
        assert len(eval_alerts) == 0


# ── Test 3: Rule Engine Under 50ms ───────────────────────────────────

class TestPerformance:
    def test_rule_engine_under_50ms(self):
        """evaluate() completes within 50ms for a moderately sized pipeline."""
        engine = RuleEngine()
        registry = _FakeRegistry({
            f"block_{i}": _FakeSchema(f"block_{i}", "data")
            for i in range(50)
        })

        # 50 nodes, 49 edges (linear chain)
        nodes = [
            _make_node(f"n{i}", f"block_{i}", config={
                "learning_rate": 0.001,
                "batch_size": 16,
            })
            for i in range(50)
        ]
        edges = [_make_edge(f"n{i}", f"n{i+1}") for i in range(49)]

        # Warm up
        engine.evaluate(nodes, edges, registry=registry)

        # Timed run
        start = time.monotonic()
        engine.evaluate(nodes, edges, registry=registry)
        elapsed_ms = (time.monotonic() - start) * 1000

        assert elapsed_ms < 50, f"Rule evaluation took {elapsed_ms:.1f}ms (limit: 50ms)"


# ── Test 4: AI Explain Returns Response (Mocked) ────────────────────

class TestAIExplain:
    @patch("backend.services.copilot_ai._try_ollama_generate")
    def test_explain_returns_response(self, mock_ollama):
        """explain_pipeline returns LLM response when Ollama is available."""
        mock_ollama.return_value = "This pipeline loads data, fine-tunes a model, and evaluates it."

        copilot = AICopilot()
        nodes = [
            _make_node("n1", "load_dataset", label="Load Data"),
            _make_node("n2", "fine_tune", label="Fine-Tune"),
            _make_node("n3", "evaluate", label="Evaluate"),
        ]
        edges = [_make_edge("n1", "n2"), _make_edge("n2", "n3")]

        result = copilot.explain_pipeline(nodes, edges)

        assert result is not None
        assert "pipeline" in result.lower() or "data" in result.lower()
        mock_ollama.assert_called_once()


# ── Test 5: No AI Graceful Degradation ───────────────────────────────

class TestGracefulDegradation:
    @patch("backend.services.copilot_ai._try_ollama_generate", return_value=None)
    @patch("backend.services.copilot_ai._try_mlx_generate", return_value=None)
    def test_no_ai_graceful_degradation(self, mock_mlx, mock_ollama):
        """AI methods return None when no inference backend is available."""
        copilot = AICopilot()

        nodes = [_make_node("n1", "fine_tune")]
        edges: list = []

        # explain_pipeline returns None
        result = copilot.explain_pipeline(nodes, edges)
        assert result is None

        # diagnose_error returns None
        result = copilot.diagnose_error("run-1", {"error": "test"}, nodes, edges)
        assert result is None

        # suggest_improvements returns None
        result = copilot.suggest_improvements(nodes, edges)
        assert result is None

        # suggest_variant_config returns None
        result = copilot.suggest_variant_config(
            {"nodes": nodes, "edges": edges}, "try larger model"
        )
        assert result is None


# ── Test 6: AI Suggest Variant Returns Config Changes ────────────────

class TestSuggestVariant:
    @patch("backend.services.copilot_ai._try_ollama_generate")
    def test_suggest_variant_returns_config_changes(self, mock_ollama):
        """suggest_variant_config returns structured config diff from LLM."""
        mock_ollama.return_value = '{"n1": {"model_name": "llama-13b", "learning_rate": 0.0001}}'

        copilot = AICopilot()
        pipeline = {
            "nodes": [
                _make_node("n1", "fine_tune", config={
                    "model_name": "llama-7b",
                    "learning_rate": 0.001,
                    "epochs": 3,
                }),
            ],
            "edges": [],
        }

        result = copilot.suggest_variant_config(pipeline, "same but with a larger model")

        assert result is not None
        assert isinstance(result, dict)
        assert "n1" in result
        assert result["n1"]["model_name"] == "llama-13b"
        assert result["n1"]["learning_rate"] == 0.0001

    @patch("backend.services.copilot_ai._try_ollama_generate")
    def test_suggest_variant_handles_markdown_wrapped_json(self, mock_ollama):
        """Parses JSON even when LLM wraps it in markdown code blocks."""
        mock_ollama.return_value = '```json\n{"n1": {"epochs": 10}}\n```'

        copilot = AICopilot()
        pipeline = {
            "nodes": [_make_node("n1", "fine_tune", config={"epochs": 3})],
            "edges": [],
        }

        result = copilot.suggest_variant_config(pipeline, "more epochs")
        assert result is not None
        assert result["n1"]["epochs"] == 10


# ── Test 7: Rule-Based Field Highlighting ────────────────────────────

class TestFieldHighlighting:
    def test_rule_based_field_highlighting(self):
        """Training pipeline highlights lr/epochs/model without any AI."""
        registry = _FakeRegistry({
            "fine_tune": _FakeSchema("fine_tune", "training"),
        })

        nodes = [
            _make_node("n1", "fine_tune", config={
                "model_name": "llama-7b",
                "learning_rate": 0.001,
                "epochs": 3,
                "batch_size": 8,
                "warmup_steps": 100,
            }),
        ]

        hints = get_variant_field_hints(nodes, registry)

        assert "n1" in hints
        highlighted = hints["n1"]
        assert "model_name" in highlighted
        assert "learning_rate" in highlighted
        assert "epochs" in highlighted
        assert "batch_size" in highlighted
        # warmup_steps is NOT in the common variant fields list
        assert "warmup_steps" not in highlighted

    def test_inference_pipeline_highlights(self):
        """Inference pipeline highlights temperature/max_tokens/model."""
        registry = _FakeRegistry({
            "text_generation": _FakeSchema("text_generation", "inference"),
        })

        nodes = [
            _make_node("n1", "text_generation", config={
                "model_name": "llama-7b",
                "temperature": 0.7,
                "max_tokens": 512,
                "system_prompt": "You are a helpful assistant",
            }),
        ]

        hints = get_variant_field_hints(nodes, registry)

        assert "n1" in hints
        highlighted = hints["n1"]
        assert "model_name" in highlighted
        assert "temperature" in highlighted
        assert "max_tokens" in highlighted
        assert "system_prompt" not in highlighted

    def test_no_hints_for_unknown_archetype(self):
        """Nodes that aren't training/inference/evaluation get no hints."""
        registry = _FakeRegistry({
            "load_csv": _FakeSchema("load_csv", "data"),
        })

        nodes = [
            _make_node("n1", "load_csv", config={"file_path": "/data/train.csv"}),
        ]

        hints = get_variant_field_hints(nodes, registry)
        assert "n1" not in hints


# ── Additional Rule Coverage ─────────────────────────────────────────

class TestAdditionalRules:
    def test_high_learning_rate_warning(self):
        """Config range rule warns on learning_rate > 0.01."""
        engine = RuleEngine()
        nodes = [
            _make_node("n1", "some_block", config={"learning_rate": 0.1}),
        ]
        alerts = engine.evaluate(nodes, [])
        lr_alerts = [a for a in alerts if a.id.startswith("high-lr-")]
        assert len(lr_alerts) == 1
        assert lr_alerts[0].severity == "warning"

    def test_disconnected_required_port(self):
        """Disconnected required port triggers error alert."""
        engine = RuleEngine()
        registry = _FakeRegistry({
            "fine_tune": _FakeSchema(
                "fine_tune", "training",
                inputs=[_FakePort("dataset", required=True)],
            ),
        })

        nodes = [_make_node("n1", "fine_tune")]
        alerts = engine.evaluate(nodes, [], registry=registry)

        disc_alerts = [a for a in alerts if a.id.startswith("disconnected-")]
        assert len(disc_alerts) == 1
        assert disc_alerts[0].severity == "error"
        assert "dataset" in disc_alerts[0].message

    def test_no_output_block_info(self):
        """No output block triggers info-level alert."""
        engine = RuleEngine()
        registry = _FakeRegistry({
            "load_csv": _FakeSchema("load_csv", "data"),
        })
        nodes = [_make_node("n1", "load_csv")]
        alerts = engine.evaluate(nodes, [], registry=registry)

        output_alerts = [a for a in alerts if a.id == "no-output"]
        assert len(output_alerts) == 1
        assert output_alerts[0].severity == "info"

    def test_large_context_warning(self):
        """Large context rule warns when max_tokens exceeds model context."""
        engine = RuleEngine()
        nodes = [
            _make_node("n1", "text_gen", config={
                "model_name": "gpt2",
                "max_tokens": 2048,
            }),
        ]
        alerts = engine.evaluate(nodes, [])
        ctx_alerts = [a for a in alerts if a.id.startswith("large-ctx-")]
        assert len(ctx_alerts) == 1
        assert "1024" in ctx_alerts[0].message  # gpt2 context = 1024
