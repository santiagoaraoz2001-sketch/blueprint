import pytest
from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)

def test_health():
    response = client.get("/api/health")
    data = response.json()
    assert data["service"] == "blueprint"
    # Health endpoint may return 200 (ok) or 503 (degraded) depending on DB availability
    assert response.status_code in (200, 503)
    assert data["status"] in ("ok", "degraded")

def test_hardware_capabilities():
    response = client.get("/api/system/capabilities")
    assert response.status_code == 200
    data = response.json()
    assert "gpu_available" in data
    assert "usable_memory_gb" in data
    assert "max_model_size" in data


def test_system_health_endpoint():
    """The /api/system/health endpoint returns all required fields."""
    response = client.get("/api/system/health")
    assert response.status_code == 200
    data = response.json()
    # All fields from HealthResponse must be present
    assert "cpu_percent" in data
    assert "memory_percent" in data
    assert "memory_total_gb" in data
    assert "disk_free_gb" in data
    assert "ollama_connected" in data
    assert "active_runs" in data
    assert "queued_runs" in data
    # Types
    assert isinstance(data["cpu_percent"], (int, float))
    assert isinstance(data["memory_total_gb"], (int, float))
    assert isinstance(data["disk_free_gb"], (int, float))
    assert isinstance(data["ollama_connected"], bool)
    assert isinstance(data["active_runs"], int)


def test_infer_severity():
    """_infer_severity correctly classifies log messages by prefix."""
    from backend.engine.executor import _infer_severity

    assert _infer_severity("[ERROR] something broke") == "error"
    assert _infer_severity("error: connection refused") == "error"
    assert _infer_severity("Error: timeout") == "error"
    assert _infer_severity("[WARN] slow query") == "warn"
    assert _infer_severity("[WARNING] deprecated API") == "warn"
    assert _infer_severity("warning: disk almost full") == "warn"
    assert _infer_severity("[DEBUG] cache hit") == "debug"
    assert _infer_severity("Loading model...") == "info"
    assert _infer_severity("Processing 100 rows") == "info"
    assert _infer_severity("") == "info"
    assert _infer_severity(42) == "info"  # non-string → info
    assert _infer_severity(None) == "info"


def test_block_context_severity():
    """BlockContext.log_message accepts optional severity kwarg."""
    from backend.block_sdk.context import BlockContext

    captured = []

    def mock_message_cb(msg, severity=None):
        captured.append((msg, severity))

    ctx = BlockContext(
        run_dir="/tmp/test_run",
        block_dir="/tmp/test_block",
        config={},
        inputs={},
        message_callback=mock_message_cb,
    )

    # Default: severity=None (inferred by executor)
    ctx.log_message("hello")
    assert captured[-1] == ("hello", None)

    # Explicit severity via keyword
    ctx.log_message("oops", severity="error")
    assert captured[-1] == ("oops", "error")

    # Convenience methods
    ctx.log_info("info msg")
    assert captured[-1] == ("info msg", "info")

    ctx.log_warn("warn msg")
    assert captured[-1] == ("warn msg", "warn")

    ctx.log_error("error msg")
    assert captured[-1] == ("error msg", "error")

    ctx.log_debug("debug msg")
    assert captured[-1] == ("debug msg", "debug")

    # Invalid severity silently falls back to None
    ctx.log_message("bad level", severity="critical")
    assert captured[-1] == ("bad level", None)
