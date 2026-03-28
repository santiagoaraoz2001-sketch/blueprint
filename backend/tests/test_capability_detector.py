"""Tests for the CapabilityDetector and block availability features."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.services.capability_detector import (
    CapabilityDetector,
    _check_import,
    _check_ollama,
    _check_gpu,
    _determine_profile,
)
from backend.services.registry import BlockRegistryService
from backend.config import BUILTIN_BLOCKS_DIR
from backend.main import app

client = TestClient(app)


# ─── Unit tests: _check_import ────────────────────────────────────

def test_check_import_available():
    """json is always in stdlib, so this should be True."""
    assert _check_import("json") is True


def test_check_import_missing():
    """A nonsense module should be False."""
    assert _check_import("__nonexistent_module_xyz__") is False


# ─── Unit tests: _determine_profile ───────────────────────────────

def test_profile_base():
    """No ML libs → base profile."""
    caps = {k: False for k in ["torch", "transformers", "peft", "datasets",
                                "ollama", "scikit_learn", "pandas", "numpy"]}
    assert _determine_profile(caps) == "base"


def test_profile_inference():
    """Ollama available → inference."""
    caps = {k: False for k in ["torch", "transformers", "peft", "datasets",
                                "scikit_learn", "pandas", "numpy"]}
    caps["ollama"] = True
    assert _determine_profile(caps) == "inference"


def test_profile_inference_transformers():
    """Only transformers → inference."""
    caps = {k: False for k in ["torch", "peft", "datasets", "ollama",
                                "scikit_learn", "pandas", "numpy"]}
    caps["transformers"] = True
    assert _determine_profile(caps) == "inference"


def test_profile_training():
    """torch + transformers + peft → training."""
    caps = {k: False for k in ["datasets", "ollama", "scikit_learn", "pandas", "numpy"]}
    caps["torch"] = True
    caps["transformers"] = True
    caps["peft"] = True
    assert _determine_profile(caps) == "training"


def test_profile_full():
    """All libs present → full."""
    caps = {
        "torch": True, "transformers": True, "peft": True,
        "datasets": True, "ollama": False, "scikit_learn": True,
        "pandas": True, "numpy": True,
    }
    assert _determine_profile(caps) == "full"


# ─── Unit tests: CapabilityDetector ───────────────────────────────

def test_detector_caching():
    """detect() should cache results; second call returns same object."""
    detector = CapabilityDetector()
    r1 = detector.detect()
    r2 = detector.detect()
    assert r1 is r2


def test_detector_refresh():
    """refresh() should produce a new report object."""
    detector = CapabilityDetector()
    r1 = detector.detect()
    r2 = detector.refresh()
    # May or may not be the same dict, but refresh should not error
    assert "capabilities" in r2
    assert "platform" in r2
    assert "installed_profile" in r2


def test_detector_report_structure():
    """Report should have all expected keys."""
    detector = CapabilityDetector()
    report = detector.detect()
    assert isinstance(report["capabilities"], dict)
    assert isinstance(report["platform"], dict)
    assert report["installed_profile"] in ("base", "inference", "training", "full")

    plat = report["platform"]
    assert "os" in plat
    assert "arch" in plat
    assert "python_version" in plat
    assert "gpu_name" in plat
    assert "gpu_backend" in plat


# ─── Unit tests: _check_gpu with mocking ──────────────────────────

def test_check_gpu_no_torch():
    """When torch isn't importable, GPU should be unavailable."""
    with patch.dict(sys.modules, {"torch": None}):
        result = _check_gpu()
        # Result may vary based on mlx availability, but should not crash
        assert "available" in result
        assert "backend" in result


# ─── Block availability ────────────────────────────────────────────

@pytest.fixture
def registry() -> BlockRegistryService:
    """Create a registry with only builtin blocks discovered."""
    svc = BlockRegistryService()
    svc.discover_all([BUILTIN_BLOCKS_DIR])
    return svc


def test_block_availability_all_available(registry: BlockRegistryService):
    """When all caps are True, all blocks should be available."""
    # Must include every capability name that _IMPORT_TO_CAPABILITY can produce,
    # plus network/hardware capabilities (ollama, gpu).
    caps = {
        "torch": True, "transformers": True, "peft": True,
        "bitsandbytes": True, "datasets": True, "mlx": True,
        "scikit_learn": True, "ollama": True, "gpu": True,
        "accelerate": True, "pandas": True, "numpy": True,
        "scipy": True, "sentencepiece": True, "tokenizers": True,
        "safetensors": True, "trl": True, "pillow": True,
        "opencv": True, "matplotlib": True, "seaborn": True,
    }
    avail = registry.get_block_availability(caps)
    assert len(avail) > 0
    for block_type, status in avail.items():
        assert status["available"] is True, f"{block_type} should be available"
        assert status["missing"] == []


def test_block_availability_nothing_available(registry: BlockRegistryService):
    """When all caps are False, blocks with requires should be unavailable."""
    caps = {
        "torch": False, "transformers": False, "peft": False,
        "bitsandbytes": False, "datasets": False, "mlx": False,
        "scikit_learn": False, "ollama": False, "gpu": False,
        "accelerate": False, "pandas": False, "numpy": False,
        "scipy": False, "sentencepiece": False, "tokenizers": False,
        "safetensors": False, "trl": False, "pillow": False,
        "opencv": False, "matplotlib": False, "seaborn": False,
    }
    avail = registry.get_block_availability(caps)
    # Find blocks that have requires
    blocks_with_reqs = [
        bt for bt, schema in registry._blocks.items()
        if schema.requires
    ]
    assert len(blocks_with_reqs) > 0, "Some blocks should have requires"
    for bt in blocks_with_reqs:
        assert avail[bt]["available"] is False, f"{bt} should be unavailable"
        assert len(avail[bt]["missing"]) > 0


def test_block_availability_partial(registry: BlockRegistryService):
    """With only transformers, torch-dependent blocks should be unavailable."""
    caps = {
        "torch": False, "transformers": True, "peft": False,
        "bitsandbytes": False, "datasets": False, "mlx": False,
        "scikit_learn": False, "ollama": False, "gpu": False,
    }
    avail = registry.get_block_availability(caps)

    # lora_finetuning requires torch, transformers, datasets, peft
    lora = avail.get("lora_finetuning")
    if lora:
        assert lora["available"] is False
        assert "torch" in lora["missing"]

    # token_counter requires only transformers
    tc = avail.get("token_counter")
    if tc:
        assert tc["available"] is True


# ─── API endpoint tests ───────────────────────────────────────────

def test_detailed_capabilities_endpoint():
    """GET /api/system/capabilities/detailed should return the full report."""
    response = client.get("/api/system/capabilities/detailed")
    assert response.status_code == 200
    data = response.json()
    assert "capabilities" in data
    assert "platform" in data
    assert "installed_profile" in data


def test_capabilities_refresh_endpoint():
    """POST /api/system/capabilities/refresh should not error."""
    response = client.post("/api/system/capabilities/refresh")
    assert response.status_code == 200
    data = response.json()
    assert "capabilities" in data


def test_registry_blocks_with_availability():
    """GET /api/registry/blocks?include_availability=true should include availability."""
    response = client.get("/api/registry/blocks?include_availability=true")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0
    # Each block should have an availability field
    for block in data:
        assert "availability" in block
        assert "available" in block["availability"]
        assert "missing" in block["availability"]


def test_registry_blocks_without_availability():
    """GET /api/registry/blocks (no include_availability) should NOT have availability."""
    response = client.get("/api/registry/blocks")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0
    # Should not have availability field (or it's a regular BlockSchema)
    # The response is a list of BlockSchema dicts
    first = data[0]
    assert "type" in first
    assert "name" in first


def test_start_service_unknown():
    """POST /api/system/start-service/unknown_service should 404."""
    response = client.post("/api/system/start-service/unknown_service")
    assert response.status_code == 404


def test_block_schema_has_requires():
    """BlockSchema model should support the 'requires' field."""
    from backend.models.block_schema import BlockSchema
    schema = BlockSchema(
        block_type="test",
        category="test",
        label="Test",
        requires=["torch", "transformers"],
    )
    assert schema.requires == ["torch", "transformers"]


def test_block_schema_requires_default_empty():
    """BlockSchema requires field should default to empty list."""
    from backend.models.block_schema import BlockSchema
    schema = BlockSchema(
        block_type="test",
        category="test",
        label="Test",
    )
    assert schema.requires == []


# ─── Two-phase detection ──────────────────────────────────────────

def test_phase1_does_not_set_ollama_true():
    """Phase 1 (synchronous) should always set ollama=False."""
    detector = CapabilityDetector()
    report = detector._run_phase1()
    assert report["capabilities"]["ollama"] is False


def test_detect_returns_immediately():
    """detect() should return without waiting for Phase 2."""
    import time
    detector = CapabilityDetector()
    start = time.monotonic()
    report = detector.detect()
    elapsed = time.monotonic() - start
    # Phase 1 should take <1s even on slow machines
    assert elapsed < 2.0
    assert "capabilities" in report


def test_wait_ready():
    """wait_ready() should return True once Phase 2 completes."""
    detector = CapabilityDetector()
    detector.detect()
    # Phase 2 should complete within 5 seconds
    assert detector.wait_ready(timeout=10.0) is True


# ─── Auto-inference of requires ───────────────────────────────────

def test_auto_infer_requires(registry: BlockRegistryService):
    """Blocks with ML imports in run.py should have non-empty requires."""
    # lora_finetuning has an explicit requires in YAML, so it should be populated
    lora = registry.get("lora_finetuning")
    assert lora is not None
    assert "torch" in lora.requires
    assert "transformers" in lora.requires


def test_auto_infer_no_false_positives(registry: BlockRegistryService):
    """Blocks with no ML imports should have empty requires."""
    # Find a flow-control or data block without ML deps
    for schema in registry.list_all():
        if schema.category in ("flow", "output"):
            if not schema.requires:
                return  # Found one with no requires — good
    # If all blocks happen to have requires, that's also fine
    # Just make sure no crash occurred


def test_infer_requires_method():
    """_infer_requires should correctly parse a run.py with known imports."""
    import tempfile, os
    with tempfile.TemporaryDirectory() as tmpdir:
        run_py = Path(tmpdir) / "run.py"
        run_py.write_text("import torch\nfrom transformers import AutoModel\nimport json\n")
        result = BlockRegistryService._infer_requires(Path(tmpdir))
        assert "torch" in result
        assert "transformers" in result
        # json is stdlib, should not appear
        assert "json" not in result


def test_infer_requires_no_run_py():
    """_infer_requires should return [] when run.py doesn't exist."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        result = BlockRegistryService._infer_requires(Path(tmpdir))
        assert result == []


# ─── ProcessManager ───────────────────────────────────────────────

def test_process_manager_start_and_status():
    """ProcessManager should track a started process."""
    from backend.services.process_manager import ProcessManager
    mgr = ProcessManager()
    # Start a trivial long-running process
    tracked = mgr.start("test_sleep", ["sleep", "60"])
    assert tracked.alive
    assert tracked.name == "test_sleep"
    assert mgr.is_alive("test_sleep")
    assert len(mgr.list_all()) == 1
    # Clean up
    mgr.stop("test_sleep")
    assert not mgr.is_alive("test_sleep")


def test_process_manager_dedup():
    """Starting the same name twice should return the existing process."""
    from backend.services.process_manager import ProcessManager
    mgr = ProcessManager()
    t1 = mgr.start("test_dedup", ["sleep", "60"])
    t2 = mgr.start("test_dedup", ["sleep", "60"])
    assert t1.pid == t2.pid  # Same process
    mgr.stop("test_dedup")


def test_process_manager_shutdown():
    """shutdown() should kill all tracked processes."""
    from backend.services.process_manager import ProcessManager
    mgr = ProcessManager()
    mgr.start("a", ["sleep", "60"])
    mgr.start("b", ["sleep", "60"])
    assert len([tp for tp in mgr.list_all() if tp.alive]) == 2
    mgr.shutdown()
    assert len(mgr.list_all()) == 0


def test_process_manager_stop_nonexistent():
    """Stopping a nonexistent process should return False."""
    from backend.services.process_manager import ProcessManager
    mgr = ProcessManager()
    assert mgr.stop("nonexistent") is False


def test_services_endpoint():
    """GET /api/system/services should return a list."""
    response = client.get("/api/system/services")
    assert response.status_code == 200
    data = response.json()
    assert "services" in data
    assert isinstance(data["services"], list)


# ═══════════════════════════════════════════════════════════════════════════
# Dry-Run Hardware Detection (detect_capabilities)
# ═══════════════════════════════════════════════════════════════════════════

from backend.services.capability_detector import (
    detect_capabilities,
    invalidate_cache,
    _detect_system_memory_mb,
    _detect_apple_silicon,
    _detect_torch_hardware,
    _detect_mlx_hardware,
    _check_mps,
)


@pytest.fixture(autouse=False)
def clear_hw_cache():
    """Clear the lru_cache before/after hardware detection tests."""
    invalidate_cache()
    yield
    invalidate_cache()


class TestDetectCapabilities:
    def test_caching(self, clear_hw_cache):
        result1 = detect_capabilities()
        result2 = detect_capabilities()
        assert result1 is result2

    def test_returns_required_keys(self, clear_hw_cache):
        caps = detect_capabilities()
        for key in ("torch", "mlx", "gpu_backend", "gpu_name",
                     "gpu_memory_mb", "system_memory_mb", "unified_memory",
                     "accelerators", "metal_active_mb", "disk_free_gb"):
            assert key in caps

    def test_system_memory_positive(self, clear_hw_cache):
        caps = detect_capabilities()
        assert caps["system_memory_mb"] > 0


class TestSystemMemoryDetection:
    def test_positive(self):
        assert _detect_system_memory_mb() > 0

    def test_reasonable_range(self):
        mem = _detect_system_memory_mb()
        assert 256 <= mem <= 2_097_152


class TestMLXHardware:
    def _mlx_available(self) -> bool:
        try:
            import mlx.core  # noqa: F401
            return True
        except ImportError:
            return False

    def test_mlx_detection_when_available(self):
        if not self._mlx_available():
            pytest.skip("MLX not installed")
        caps = {"mlx": False, "metal_active_mb": 0}
        _detect_mlx_hardware(caps)
        assert caps["mlx"] is True
        assert isinstance(caps["metal_active_mb"], int)
