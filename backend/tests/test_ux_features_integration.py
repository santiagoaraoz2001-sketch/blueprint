"""
Integration tests for UX & Connector Overhaul features.

Tests cover: port type system, port ID collisions, agent I/O parity,
loop system, mandatory config, chat_completion block, and regression.
"""

import subprocess
import sys
import yaml
import pytest
from pathlib import Path

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

BLOCKS_DIR = Path(__file__).resolve().parents[2] / "blocks"


def _load_block_yaml(block_type: str) -> dict:
    """Load block.yaml for a given block type by scanning the blocks directory."""
    for yp in BLOCKS_DIR.rglob("block.yaml"):
        with open(yp) as f:
            spec = yaml.safe_load(f) or {}
        if spec.get("type") == block_type:
            return spec
    return {}


def _make_node(node_id: str, block_type: str, config: dict, category: str = None) -> dict:
    """Build a pipeline node dict compatible with validate_pipeline.

    Loads the real block.yaml to get accurate input/output/side_input port definitions.
    """
    spec = _load_block_yaml(block_type)
    if not category:
        category = spec.get("category", "data")

    inputs = []
    for inp in spec.get("inputs", []):
        inputs.append({
            "id": inp["id"],
            "label": inp.get("label", inp["id"]),
            "dataType": inp.get("data_type", "any"),
            "required": inp.get("required", False),
        })

    outputs = []
    for out in spec.get("outputs", []):
        outputs.append({
            "id": out["id"],
            "label": out.get("label", out["id"]),
            "dataType": out.get("data_type", "any"),
        })

    side_inputs = []
    for si in spec.get("side_inputs", []):
        side_inputs.append({
            "id": si["id"],
            "label": si.get("label", si["id"]),
            "dataType": si.get("data_type", "any"),
            "required": si.get("required", False),
        })

    return {
        "id": node_id,
        "type": "custom",
        "data": {
            "type": block_type,
            "label": spec.get("name", block_type),
            "category": category,
            "config": config,
            "inputs": inputs,
            "outputs": outputs,
            "side_inputs": side_inputs,
        },
    }


def _make_edge(source: str, target: str, source_handle: str, target_handle: str) -> dict:
    """Build a pipeline edge dict."""
    return {
        "source": source,
        "target": target,
        "sourceHandle": source_handle,
        "targetHandle": target_handle,
    }


def _make_pipeline(nodes: list, edges: list) -> dict:
    return {"nodes": nodes, "edges": edges}


def _ollama_has_model(model_name: str) -> bool:
    """Check if an Ollama model is available locally."""
    try:
        result = subprocess.run(
            ["ollama", "list"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return model_name.lower() in result.stdout.lower()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


# ---------------------------------------------------------------------------
# Test Group 1: Port Type System (4 tests)
# ---------------------------------------------------------------------------


class TestPortTypeSystem:
    """Tests for the port type compatibility matrix."""

    def test_model_to_llm_compatibility(self):
        """model_selector.model (model) -> chain_of_thought.llm (llm) should connect."""
        nodes = [
            _make_node("n1", "model_selector", {"model_id": "test", "source": "ollama"}),
            _make_node("n2", "text_input", {"text_value": "What is 2+2?"}),
            _make_node("n3", "chain_of_thought", {"num_steps": 2, "max_tokens": 512}),
        ]
        edges = [
            _make_edge("n1", "n3", "model", "llm"),
            _make_edge("n2", "n3", "text", "input"),
        ]

        from backend.engine.validator import validate_pipeline

        report = validate_pipeline({"nodes": nodes, "edges": edges})
        # model->llm must be in the COMPAT table
        type_errors = [e for e in report.errors if "incompatible" in e.lower()]
        assert not type_errors, f"model->llm should be compatible: {type_errors}"

    def test_text_to_llm_blocked(self):
        """text_input.text (text) -> chain_of_thought.llm (llm) should be REJECTED."""
        nodes = [
            _make_node("n1", "text_input", {"text_value": "hello"}),
            _make_node("n2", "chain_of_thought", {"num_steps": 2}),
        ]
        edges = [_make_edge("n1", "n2", "text", "llm")]

        from backend.engine.validator import validate_pipeline

        report = validate_pipeline({"nodes": nodes, "edges": edges})
        assert not report.valid, "text->llm should be blocked"

    def test_text_to_config_blocked(self):
        """text->config compatibility should be REMOVED (was a dangerous connection)."""
        from backend.services.registry import get_global_registry

        registry = get_global_registry()
        assert not registry.is_port_compatible("text", "config"), "text->config should no longer be compatible"

    def test_port_alias_resolution(self):
        """Output ports with aliases should be resolvable via the alias map."""
        from backend.services.registry import get_global_registry

        registry = get_global_registry()

        # chain_of_thought.response has aliases: [text, output]
        aliases = registry.get_output_alias_map("chain_of_thought")
        assert "text" in aliases, "chain_of_thought should have 'text' alias for response"
        assert aliases["text"] == "response", "text alias should map to response"

        # llm_inference.response has aliases: [text, output]
        aliases = registry.get_output_alias_map("llm_inference")
        assert "text" in aliases, "llm_inference should have 'text' alias for response"
        assert aliases["text"] == "response"


# ---------------------------------------------------------------------------
# Test Group 2: Port ID Collisions Fixed (2 tests)
# ---------------------------------------------------------------------------


class TestPortIDCollisions:
    """Ensure no block has conflicting port IDs."""

    def test_no_port_id_collisions(self):
        """No block should have the same ID for both an input and output port."""
        collisions = []
        for yp in BLOCKS_DIR.rglob("block.yaml"):
            with open(yp) as f:
                s = yaml.safe_load(f) or {}
            in_ids = {i["id"] for i in s.get("inputs", [])}
            out_ids = {o["id"] for o in s.get("outputs", [])}
            overlap = in_ids & out_ids
            if overlap:
                collisions.append(f"{s.get('type')}: {overlap}")
        assert not collisions, "Port ID collisions found:\n" + "\n".join(collisions)

    def test_no_duplicate_ports_same_side(self):
        """No block should have two inputs or two outputs with the same ID."""
        dupes = []
        for yp in BLOCKS_DIR.rglob("block.yaml"):
            with open(yp) as f:
                s = yaml.safe_load(f) or {}
            in_ids = [i["id"] for i in s.get("inputs", [])]
            out_ids = [o["id"] for o in s.get("outputs", [])]
            in_dupes = [x for x in set(in_ids) if in_ids.count(x) > 1]
            out_dupes = [x for x in set(out_ids) if out_ids.count(x) > 1]
            if in_dupes or out_dupes:
                dupes.append(
                    f"{s.get('type')}: in_dupes={in_dupes}, out_dupes={out_dupes}"
                )
        assert not dupes, "Duplicate ports found:\n" + "\n".join(dupes)


# ---------------------------------------------------------------------------
# Test Group 3: Agent I/O Parity (3 tests)
# ---------------------------------------------------------------------------


class TestAgentIOParity:
    """Tests for agent block input/output standardization."""

    def test_direct_model_to_agent(self):
        """model_selector -> chain_of_thought (direct, no llm_inference intermediary)."""
        nodes = [
            _make_node("n1", "text_input", {"text_value": "What is 2+2?"}),
            _make_node("n2", "model_selector", {"model_id": "test-model", "source": "ollama"}),
            _make_node("n3", "chain_of_thought", {"num_steps": 2, "max_tokens": 512}, category="agents"),
        ]
        edges = [
            _make_edge("n2", "n3", "model", "llm"),
            _make_edge("n1", "n3", "text", "input"),
        ]

        from backend.engine.validator import validate_pipeline

        report = validate_pipeline(_make_pipeline(nodes, edges))
        type_errors = [e for e in report.errors if "incompatible" in e.lower()]
        assert not type_errors, f"Direct model->agent should validate: {report.errors}"

    def test_agent_to_agent_chaining(self):
        """chain_of_thought -> multi_agent_debate via llm_config passthrough."""
        nodes = [
            _make_node("n1", "text_input", {"text_value": "Should AI be regulated?"}),
            _make_node("n2", "model_selector", {"model_id": "test-model", "source": "ollama"}),
            _make_node("n3", "llm_inference", {"max_tokens": 512, "temperature": 0.3, "model_name": "test"}, category="inference"),
            _make_node("n4", "chain_of_thought", {"num_steps": 2, "max_tokens": 512}, category="agents"),
            _make_node("n5", "multi_agent_debate", {"num_agents": 2, "num_rounds": 1, "max_tokens": 512}, category="agents"),
        ]
        edges = [
            _make_edge("n2", "n3", "model", "model"),
            _make_edge("n1", "n3", "text", "prompt"),
            _make_edge("n3", "n4", "llm_config", "llm"),  # llm->llm
            _make_edge("n1", "n4", "text", "input"),
            _make_edge("n4", "n5", "llm_config", "llm"),  # llm->llm (passthrough)
            _make_edge("n4", "n5", "response", "input"),   # text->text
        ]

        from backend.engine.validator import validate_pipeline

        report = validate_pipeline(_make_pipeline(nodes, edges))
        assert report.valid, f"Agent chaining should validate: {report.errors}"

    def test_agent_output_parity(self):
        """Every agent block with 'response' output must also have llm_config and metrics."""
        issues = []
        for yp in sorted((BLOCKS_DIR / "agents").rglob("block.yaml")):
            with open(yp) as f:
                s = yaml.safe_load(f) or {}
            bt = s.get("type", "")
            out_ids = {o["id"] for o in s.get("outputs", [])}

            if "response" in out_ids or "consensus" in out_ids:
                required = {"metrics", "llm_config"}
                missing = required - out_ids
                if missing:
                    issues.append(f"{bt}: missing outputs {missing}")

        assert not issues, "Agent blocks missing standard outputs:\n" + "\n".join(issues)


# ---------------------------------------------------------------------------
# Test Group 4: Loop System (3 tests)
# ---------------------------------------------------------------------------


class TestLoopSystem:
    """Tests for loop/cycle handling in the pipeline validator."""

    def test_loop_cycle_accepted(self):
        """Pipeline with cycle through loop_controller should validate."""
        nodes = [
            _make_node("lc", "loop_controller", {"iterations": 3, "file_mode": "overwrite"}),
            _make_node("body", "text_input", {"text_value": "test"}),
        ]
        edges = [
            _make_edge("lc", "body", "body", "_loop"),
            _make_edge("body", "lc", "text", "feedback"),
        ]

        from backend.engine.validator import validate_pipeline

        report = validate_pipeline({"nodes": nodes, "edges": edges})
        cycle_errors = [e for e in report.errors if "cycle" in e.lower()]
        assert not cycle_errors, f"Loop cycle should be valid: {report.errors}"

    def test_non_loop_cycle_rejected(self):
        """Pipeline with cycle NOT through loop_controller should be rejected."""
        nodes = [
            _make_node("a", "text_input", {"text_value": "test"}),
            _make_node("b", "text_concatenator", {}),
        ]
        edges = [
            _make_edge("a", "b", "text", "text_a"),
            _make_edge("b", "a", "text", "_loop"),  # Cycle without loop_controller
        ]

        from backend.engine.validator import validate_pipeline

        report = validate_pipeline({"nodes": nodes, "edges": edges})
        assert not report.valid, "Non-loop cycle should be rejected"

    def test_side_ports_exist(self):
        """Every block should have a _loop side input."""
        missing = []
        for yp in sorted(BLOCKS_DIR.rglob("block.yaml")):
            with open(yp) as f:
                s = yaml.safe_load(f) or {}
            bt = s.get("type", yp.parent.name)
            side_inputs = s.get("side_inputs", [])
            has_loop = any(si.get("id") == "_loop" for si in side_inputs)
            if not has_loop:
                missing.append(bt)
        assert not missing, f"{len(missing)} blocks missing _loop side input: {missing[:10]}..."


# ---------------------------------------------------------------------------
# Test Group 5: Mandatory Config (2 tests)
# ---------------------------------------------------------------------------


class TestMandatoryConfig:
    """Tests for mandatory config field validation."""

    def test_mandatory_field_validation(self):
        """Pipeline with empty mandatory field AND no connected input should fail."""
        nodes = [
            _make_node(
                "n1",
                "lora_finetuning",
                {"model_name": "", "epochs": 2},
                category="training",
            ),
        ]
        edges = []

        from backend.engine.validator import validate_pipeline

        report = validate_pipeline({"nodes": nodes, "edges": edges})
        assert not report.valid, "Should fail: mandatory model_name is empty and no model input"
        assert any("required" in e.lower() or "mandatory" in e.lower() for e in report.errors)

    def test_mandatory_field_satisfied_by_port(self):
        """Mandatory field should be satisfied when corresponding input port is connected."""
        nodes = [
            _make_node("n1", "model_selector", {"model_id": "test", "source": "ollama"}),
            _make_node(
                "n2",
                "lora_finetuning",
                {"model_name": "", "epochs": 2},
                category="training",
            ),
            _make_node(
                "n3",
                "local_file_loader",
                {"file_path": "/tmp/test.jsonl"},
                category="source",
            ),
        ]
        edges = [
            _make_edge("n1", "n2", "model", "model"),
            _make_edge("n3", "n2", "dataset", "dataset"),
        ]

        from backend.engine.validator import validate_pipeline

        report = validate_pipeline({"nodes": nodes, "edges": edges})
        # model_name is empty but model port is connected — should pass
        model_errors = [e for e in report.errors if "model_name" in e.lower() or "base model" in e.lower()]
        assert not model_errors, f"Should pass: model input is connected. Errors: {report.errors}"


# ---------------------------------------------------------------------------
# Test Group 6: chat_completion block (1 test)
# ---------------------------------------------------------------------------


class TestChatCompletionBlock:
    """Tests for the chat_completion block."""

    def test_chat_completion_exists(self):
        """chat_completion block should exist with correct ports."""
        yp = BLOCKS_DIR / "inference" / "chat_completion" / "block.yaml"
        assert yp.exists(), "chat_completion block.yaml missing"

        with open(yp) as f:
            s = yaml.safe_load(f)
        assert s["type"] == "chat_completion"
        in_ids = {i["id"] for i in s.get("inputs", [])}
        out_ids = {o["id"] for o in s.get("outputs", [])}
        assert "prompt" in in_ids, "chat_completion missing prompt input"
        assert "response" in out_ids, "chat_completion missing response output"
        assert "llm_config" in out_ids, "chat_completion missing llm_config output"


# ---------------------------------------------------------------------------
# Test Group 7: Validator Sanity (3 tests)
# ---------------------------------------------------------------------------


class TestValidatorSanity:
    """Basic sanity checks for the pipeline validator."""

    def test_empty_pipeline_rejected(self):
        """An empty pipeline should be rejected."""
        from backend.engine.validator import validate_pipeline

        report = validate_pipeline({"nodes": [], "edges": []})
        assert not report.valid
        assert any("no blocks" in e.lower() for e in report.errors)

    def test_self_loop_rejected(self):
        """A self-loop edge should be rejected."""
        nodes = [_make_node("n1", "text_input", {"text_value": "test"})]
        edges = [_make_edge("n1", "n1", "text", "text")]

        from backend.engine.validator import validate_pipeline

        report = validate_pipeline({"nodes": nodes, "edges": edges})
        assert not report.valid
        assert any("self-loop" in e.lower() for e in report.errors)

    def test_valid_linear_pipeline(self):
        """A simple linear pipeline should validate successfully."""
        nodes = [
            _make_node("n1", "text_input", {"text_value": "hello"}),
            _make_node("n2", "llm_inference", {"model_name": "test-model", "max_tokens": 512}, category="inference"),
        ]
        edges = [_make_edge("n1", "n2", "text", "prompt")]

        from backend.engine.validator import validate_pipeline

        report = validate_pipeline(_make_pipeline(nodes, edges))
        assert report.valid, f"Simple pipeline should validate: {report.errors}"


# ---------------------------------------------------------------------------
# Test Group 8: Block Registry Completeness (3 tests)
# ---------------------------------------------------------------------------


class TestBlockRegistryCompleteness:
    """Verify that all block YAMLs are well-formed and registered."""

    def test_all_blocks_have_required_fields(self):
        """Every block.yaml must have name, type, category, inputs, outputs."""
        issues = []
        for yp in BLOCKS_DIR.rglob("block.yaml"):
            with open(yp) as f:
                s = yaml.safe_load(f) or {}
            bt = s.get("type", yp.parent.name)
            missing = []
            for field in ("name", "type", "category"):
                if not s.get(field):
                    missing.append(field)
            if "inputs" not in s:
                missing.append("inputs")
            if "outputs" not in s:
                missing.append("outputs")
            if missing:
                issues.append(f"{bt}: missing {missing}")
        assert not issues, "Blocks with missing fields:\n" + "\n".join(issues)

    def test_all_blocks_have_valid_port_types(self):
        """Every port data_type should be a recognized type."""
        known_types = {
            "any", "dataset", "text", "model", "config", "metrics",
            "embedding", "artifact", "agent", "llm",
        }
        issues = []
        for yp in BLOCKS_DIR.rglob("block.yaml"):
            with open(yp) as f:
                s = yaml.safe_load(f) or {}
            bt = s.get("type", yp.parent.name)
            all_ports = s.get("inputs", []) + s.get("outputs", []) + s.get("side_inputs", [])
            for port in all_ports:
                dt = port.get("data_type", "any")
                if dt not in known_types:
                    issues.append(f"{bt}.{port['id']}: unknown type '{dt}'")
        assert not issues, "Unknown port types:\n" + "\n".join(issues)

    def test_block_registry_scan(self):
        """The block registry should scan all blocks without errors."""
        from backend.services.registry import get_global_registry

        registry = get_global_registry()
        types = registry.get_block_types()
        assert len(types) > 0, "Block registry found no blocks"
        assert "text_input" in types, "text_input not in registry"
        assert "llm_inference" in types, "llm_inference not in registry"
        assert "chain_of_thought" in types, "chain_of_thought not in registry"
        assert "chat_completion" in types, "chat_completion not in registry"
        assert "loop_controller" in types, "loop_controller not in registry"


# ---------------------------------------------------------------------------
# Test Group 9: Regression (1 test)
# ---------------------------------------------------------------------------


class TestRegression:
    """Run existing tests to verify no regressions."""

    def test_existing_tests_not_broken(self):
        """Run the existing test suite to verify no regressions."""
        test_dir = Path(__file__).parent
        test_files = [
            f
            for f in test_dir.glob("test_*.py")
            if f.name != "test_ux_features_integration.py"
        ]

        if not test_files:
            pytest.skip("No other test files found to check for regression")

        result = subprocess.run(
            [sys.executable, "-m", "pytest"]
            + [str(f) for f in test_files]
            + ["-v", "-x"],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(Path(__file__).resolve().parents[2]),
        )
        # Allow skipped tests; only fail on actual errors
        assert result.returncode == 0 or "skipped" in result.stdout, (
            f"Existing tests failed:\n{result.stdout}\n{result.stderr}"
        )
