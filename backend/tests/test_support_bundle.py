"""Tests for the support bundle system (backend/routers/replay.py).

Covers:
- test_bundle_contains_required_sections: all JSON files present
- test_bundle_redacts_secrets: api_key='sk-12345' → '[REDACTED]'
- test_bundle_valid_json: all files parse as valid JSON/JSONL
"""

import io
import json
import zipfile
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from backend.models.execution_decision import ExecutionDecision
from backend.models.artifact import ArtifactRecord
from backend.routers.replay import (
    _deep_redact,
    _is_secret_key,
    _final_secret_scan,
)


# ── Redaction Unit Tests ────────────────────────────────────────────────


class TestSecretRedaction:
    """Test secret detection and redaction utilities."""

    def test_is_secret_key_detects_common_patterns(self):
        """Verify common secret key patterns are detected."""
        assert _is_secret_key("api_key") is True
        assert _is_secret_key("API_KEY") is True
        assert _is_secret_key("hf_token") is True
        assert _is_secret_key("auth_token") is True
        assert _is_secret_key("my_password") is True
        assert _is_secret_key("openai_api_key") is True
        assert _is_secret_key("aws_secret_access_key") is True
        assert _is_secret_key("apikey") is True

    def test_is_secret_key_allows_safe_keys(self):
        """Verify non-secret keys are not flagged."""
        assert _is_secret_key("model_name") is False
        assert _is_secret_key("batch_size") is False
        assert _is_secret_key("learning_rate") is False
        assert _is_secret_key("output_path") is False

    def test_deep_redact_replaces_secret_values(self):
        """Verify secret values are replaced with [REDACTED]."""
        config = {
            "model": "gpt-4",
            "api_key": "sk-12345",
            "nested": {
                "hf_token": "hf_abc123",
                "batch_size": 32,
            },
            "items": [
                {"auth_token": "tok_xyz", "name": "test"},
            ],
        }

        redacted = _deep_redact(config)

        assert redacted["model"] == "gpt-4"
        assert redacted["api_key"] == "[REDACTED]"
        assert redacted["nested"]["hf_token"] == "[REDACTED]"
        assert redacted["nested"]["batch_size"] == 32
        assert redacted["items"][0]["auth_token"] == "[REDACTED]"
        assert redacted["items"][0]["name"] == "test"

    def test_deep_redact_handles_secret_references(self):
        """Verify $secret: references are redacted."""
        config = {
            "api_endpoint": "https://api.example.com",
            "credential": "$secret:MY_KEY",
        }

        redacted = _deep_redact(config)

        assert redacted["api_endpoint"] == "https://api.example.com"
        assert redacted["credential"] == "[REDACTED]"

    def test_deep_redact_preserves_non_string_values(self):
        """Verify non-string values are not accidentally redacted."""
        config = {
            "api_key": 12345,  # numeric, not a string
            "token_count": 100,
        }

        redacted = _deep_redact(config)

        # api_key has a secret key name but numeric value → should NOT redact
        assert redacted["api_key"] == 12345
        assert redacted["token_count"] == 100

    def test_final_secret_scan_catches_serialized_secrets(self):
        """Verify final scan catches secrets in serialized JSON."""
        content = json.dumps({
            "config": {
                "api_key": "sk-live-12345",
                "model": "gpt-4",
            }
        }, indent=2)

        scanned = _final_secret_scan(content)

        assert "sk-live-12345" not in scanned
        assert "[REDACTED]" in scanned
        assert "gpt-4" in scanned


# ── Support Bundle Tests ────────────────────────────────────────────────


REQUIRED_BUNDLE_FILES = {
    "pipeline.json",
    "execution_plan.json",
    "resolved_configs.json",
    "artifact_manifests.json",
    "execution_decisions.json",
    "classified_errors.json",
    "environment.json",
    "events.jsonl",
    "run_metadata.json",
}


def _make_mock_run(run_id="run_bundle", status="complete"):
    """Create a mock Run for support bundle testing."""
    run = MagicMock()
    run.id = run_id
    run.pipeline_id = "pipe_1"
    run.status = status
    run.started_at = datetime(2026, 3, 28, 10, 0, 0, tzinfo=timezone.utc)
    run.finished_at = datetime(2026, 3, 28, 10, 5, 0, tzinfo=timezone.utc)
    run.duration_seconds = 300.0
    run.error_message = None
    run.config_snapshot = {
        "nodes": [
            {"id": "n1", "data": {"type": "text_input", "config": {"api_key": "sk-12345", "text": "hello"}}},
            {"id": "n2", "data": {"type": "model_trainer", "config": {"batch_size": 32}}},
        ],
        "edges": [
            {"source": "n1", "target": "n2", "sourceHandle": "output", "targetHandle": "input"},
        ],
    }
    return run


def _make_decisions(run_id="run_bundle"):
    """Create mock ExecutionDecision records."""
    return [
        ExecutionDecision(
            run_id=run_id, node_id="n1", block_type="text_input",
            execution_order=0, decision="execute", status="completed",
            started_at=datetime(2026, 3, 28, 10, 0, 0, tzinfo=timezone.utc),
            duration_ms=100.0,
            resolved_config={"api_key": "sk-12345", "text": "hello"},
            config_sources={"api_key": "user", "text": "user"},
        ),
        ExecutionDecision(
            run_id=run_id, node_id="n2", block_type="model_trainer",
            execution_order=1, decision="execute", status="completed",
            started_at=datetime(2026, 3, 28, 10, 0, 1, tzinfo=timezone.utc),
            duration_ms=4900.0,
            resolved_config={"batch_size": 32},
            config_sources={"batch_size": "block_default"},
        ),
    ]


def _generate_bundle(run_id="run_bundle", status="complete", decisions=None, artifacts=None):
    """Generate a support bundle and return the zip content."""
    from backend.routers.replay import generate_support_bundle

    run = _make_mock_run(run_id, status)
    if decisions is None:
        decisions = _make_decisions(run_id)
    if artifacts is None:
        artifacts = []

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = run
    mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = decisions
    mock_db.query.return_value.filter.return_value.all.return_value = artifacts

    with patch("backend.routers.replay._collect_events_jsonl", return_value=[
        {"event": "node_started", "node_id": "n1", "timestamp": 1711612800},
        {"event": "node_completed", "node_id": "n1", "timestamp": 1711612801},
        {"event": "node_started", "node_id": "n2", "timestamp": 1711612801},
        {"event": "node_completed", "node_id": "n2", "timestamp": 1711612806},
    ]):
        response = generate_support_bundle(run_id, mock_db)

    # Read the response body
    return io.BytesIO(response.body)


class TestSupportBundle:
    """Tests for support bundle generation."""

    def test_bundle_contains_required_sections(self):
        """Verify all JSON files are present in the bundle."""
        buf = _generate_bundle()
        with zipfile.ZipFile(buf, "r") as zf:
            names = set(zf.namelist())
            for required in REQUIRED_BUNDLE_FILES:
                assert required in names, f"Missing required file: {required}"

    def test_bundle_redacts_secrets(self):
        """Insert a config with api_key='sk-12345', verify [REDACTED] in bundle."""
        buf = _generate_bundle()
        with zipfile.ZipFile(buf, "r") as zf:
            # Check pipeline.json
            pipeline = json.loads(zf.read("pipeline.json"))
            # Walk all string values to ensure sk-12345 is not present
            pipeline_str = json.dumps(pipeline)
            assert "sk-12345" not in pipeline_str
            assert "[REDACTED]" in pipeline_str

            # Check resolved_configs.json
            configs = json.loads(zf.read("resolved_configs.json"))
            configs_str = json.dumps(configs)
            assert "sk-12345" not in configs_str
            assert "[REDACTED]" in configs_str

            # Check execution_decisions.json
            decisions = json.loads(zf.read("execution_decisions.json"))
            decisions_str = json.dumps(decisions)
            assert "sk-12345" not in decisions_str

    def test_bundle_valid_json(self):
        """Verify all files parse as valid JSON or JSONL."""
        buf = _generate_bundle()
        with zipfile.ZipFile(buf, "r") as zf:
            for name in zf.namelist():
                content = zf.read(name).decode("utf-8")
                if name.endswith(".jsonl"):
                    # Each non-empty line must be valid JSON
                    for line_num, line in enumerate(content.splitlines(), 1):
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            json.loads(line)
                        except json.JSONDecodeError:
                            pytest.fail(f"Invalid JSON on line {line_num} of {name}: {line[:100]}")
                elif name.endswith(".json"):
                    try:
                        json.loads(content)
                    except json.JSONDecodeError:
                        pytest.fail(f"Invalid JSON in {name}")

    def test_bundle_run_metadata_has_correct_fields(self):
        """Verify run_metadata.json has expected fields."""
        buf = _generate_bundle()
        with zipfile.ZipFile(buf, "r") as zf:
            metadata = json.loads(zf.read("run_metadata.json"))

        assert metadata["run_id"] == "run_bundle"
        assert metadata["pipeline_id"] == "pipe_1"
        assert metadata["status"] == "complete"
        assert metadata["started_at"] is not None
        assert metadata["finished_at"] is not None
        assert metadata["duration_seconds"] == 300.0

    def test_bundle_environment_has_python_version(self):
        """Verify environment.json includes Python version."""
        buf = _generate_bundle()
        with zipfile.ZipFile(buf, "r") as zf:
            env = json.loads(zf.read("environment.json"))

        assert "python_version" in env
        assert "os" in env

    def test_bundle_events_jsonl_has_content(self):
        """Verify events.jsonl contains expected events."""
        buf = _generate_bundle()
        with zipfile.ZipFile(buf, "r") as zf:
            content = zf.read("events.jsonl").decode("utf-8")
            lines = [l for l in content.splitlines() if l.strip()]

        assert len(lines) == 4
        first_event = json.loads(lines[0])
        assert first_event["event"] == "node_started"

    def test_bundle_execution_plan_has_order(self):
        """Verify execution_plan.json contains execution_order."""
        buf = _generate_bundle()
        with zipfile.ZipFile(buf, "r") as zf:
            plan = json.loads(zf.read("execution_plan.json"))

        assert "execution_order" in plan
        assert plan["execution_order"] == ["n1", "n2"]

    def test_bundle_for_failed_run_includes_errors(self):
        """Verify failed run bundle contains classified errors."""
        decisions = [
            ExecutionDecision(
                run_id="run_fail", node_id="n1", block_type="text_input",
                execution_order=0, decision="execute", status="completed",
                duration_ms=100.0,
            ),
            ExecutionDecision(
                run_id="run_fail", node_id="n2", block_type="model_trainer",
                execution_order=1, decision="execute", status="failed",
                error_json={"title": "Out of Memory", "message": "GPU OOM", "action": "Reduce batch"},
            ),
        ]

        buf = _generate_bundle(run_id="run_fail", status="failed", decisions=decisions)
        with zipfile.ZipFile(buf, "r") as zf:
            errors = json.loads(zf.read("classified_errors.json"))

        assert len(errors) == 1
        assert errors[0]["node_id"] == "n2"
        assert errors[0]["error"]["title"] == "Out of Memory"

    def test_bundle_404_for_missing_run(self):
        """Verify 404 for non-existent run."""
        from backend.routers.replay import generate_support_bundle
        from fastapi import HTTPException

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            generate_support_bundle("nonexistent", mock_db)
        assert exc_info.value.status_code == 404

    def test_bundle_deep_redact_nested_secrets(self):
        """Verify deeply nested secrets are redacted."""
        decisions = [
            ExecutionDecision(
                run_id="run_deep", node_id="n1", block_type="api_caller",
                execution_order=0, decision="execute", status="completed",
                resolved_config={
                    "endpoint": "https://api.example.com",
                    "headers": {
                        "Authorization_token": "Bearer secret-value",
                        "Content-Type": "application/json",
                    },
                    "nested": {
                        "inner": {
                            "api_key": "sk-nested-secret",
                        }
                    }
                },
                config_sources={},
            ),
        ]

        buf = _generate_bundle(run_id="run_deep", decisions=decisions)
        with zipfile.ZipFile(buf, "r") as zf:
            configs = json.loads(zf.read("resolved_configs.json"))
            configs_str = json.dumps(configs)

        assert "secret-value" not in configs_str
        assert "sk-nested-secret" not in configs_str
        assert "[REDACTED]" in configs_str
        assert "https://api.example.com" in configs_str
