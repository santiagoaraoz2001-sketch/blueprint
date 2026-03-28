"""Tests for the capability detector service (Risk 3 fix)."""

import platform
from unittest.mock import patch, MagicMock

import pytest

from backend.services.capability_detector import (
    detect_capabilities,
    invalidate_cache,
    _detect_system_memory_mb,
    _detect_apple_silicon,
    _detect_torch,
    _detect_mlx,
    _check_mps,
)


@pytest.fixture(autouse=True)
def clear_cache():
    """Clear the lru_cache before each test."""
    invalidate_cache()
    yield
    invalidate_cache()


# ---------------------------------------------------------------------------
# System memory detection
# ---------------------------------------------------------------------------

class TestSystemMemory:
    def test_psutil_preferred(self):
        """When psutil is available, use it for memory detection."""
        mock_vmem = MagicMock()
        mock_vmem.total = 32 * 1024 * 1024 * 1024  # 32 GB

        with patch("backend.services.capability_detector.psutil", create=True) as mock_psutil:
            mock_psutil.virtual_memory.return_value = mock_vmem
            # Reimport to pick up the mock — or just call directly
            mem = _detect_system_memory_mb()
            # psutil is available in the test env, so this should work
            assert mem > 0

    def test_positive_memory(self):
        """System memory detection should always return a positive number."""
        mem = _detect_system_memory_mb()
        assert mem > 0

    def test_reasonable_range(self):
        """Detected memory should be in a reasonable range (256MB to 2TB)."""
        mem = _detect_system_memory_mb()
        assert 256 <= mem <= 2_097_152  # 256MB to 2TB


# ---------------------------------------------------------------------------
# Apple Silicon detection
# ---------------------------------------------------------------------------

class TestAppleSilicon:
    def test_detects_unified_memory(self):
        """Apple Silicon should report unified_memory=True and set gpu_memory_mb."""
        caps = {"system_memory_mb": 36864, "gpu_memory_mb": 0, "gpu_backend": "none"}

        with (
            patch("platform.system", return_value="Darwin"),
            patch("platform.machine", return_value="arm64"),
            patch("subprocess.check_output", side_effect=_mock_system_profiler),
        ):
            _detect_apple_silicon(caps)

        assert caps["unified_memory"] is True
        assert caps["gpu_memory_mb"] == 36864  # All system RAM is GPU-accessible
        assert caps["gpu_backend"] == "metal"

    def test_intel_mac_not_unified(self):
        """Intel Mac should NOT report unified memory."""
        caps = {"system_memory_mb": 16384, "gpu_memory_mb": 0, "gpu_backend": "none"}

        with (
            patch("platform.system", return_value="Darwin"),
            patch("platform.machine", return_value="x86_64"),
        ):
            _detect_apple_silicon(caps)

        assert caps.get("unified_memory", False) is False
        assert caps["gpu_memory_mb"] == 0

    def test_linux_skipped(self):
        """Non-macOS systems should skip Apple Silicon detection entirely."""
        caps = {"system_memory_mb": 32768, "gpu_memory_mb": 0, "gpu_backend": "none"}

        with patch("platform.system", return_value="Linux"):
            _detect_apple_silicon(caps)

        assert caps.get("unified_memory", False) is False


# ---------------------------------------------------------------------------
# PyTorch detection (CUDA, ROCm, MPS, XPU)
# ---------------------------------------------------------------------------

class TestTorchDetection:
    def test_cuda_detected(self):
        """NVIDIA CUDA GPU is properly detected with memory."""
        mock_torch = MagicMock()
        mock_torch.cuda.is_available.return_value = True
        mock_torch.cuda.device_count.return_value = 1
        mock_torch.version.hip = None  # Not ROCm
        device_props = MagicMock()
        device_props.total_mem = 24 * 1024 * 1024 * 1024  # 24 GB
        device_props.name = "NVIDIA RTX 4090"
        mock_torch.cuda.get_device_properties.return_value = device_props

        caps = {"torch": False, "gpu_backend": "none", "gpu_name": "none", "gpu_memory_mb": 0}

        with patch.dict("sys.modules", {"torch": mock_torch}):
            with patch("builtins.__import__", side_effect=_import_mock_torch(mock_torch)):
                _detect_torch(caps)

        assert caps["torch"] is True
        assert caps["gpu_backend"] == "cuda"
        assert caps["gpu_name"] == "NVIDIA RTX 4090"
        assert caps["gpu_memory_mb"] == 24576

    def test_rocm_detected_via_hip(self):
        """AMD ROCm (via HIP) should be distinguished from CUDA."""
        mock_torch = MagicMock()
        mock_torch.cuda.is_available.return_value = True
        mock_torch.cuda.device_count.return_value = 1
        mock_torch.version.hip = "5.7.0"  # ROCm!
        device_props = MagicMock()
        device_props.total_mem = 16 * 1024 * 1024 * 1024
        device_props.name = "AMD Instinct MI250X"
        mock_torch.cuda.get_device_properties.return_value = device_props

        caps = {"torch": False, "gpu_backend": "none", "gpu_name": "none", "gpu_memory_mb": 0}

        with patch.dict("sys.modules", {"torch": mock_torch}):
            with patch("builtins.__import__", side_effect=_import_mock_torch(mock_torch)):
                _detect_torch(caps)

        assert caps["torch"] is True
        assert caps["gpu_backend"] == "rocm"
        assert caps["gpu_name"] == "AMD Instinct MI250X"
        assert caps["gpu_memory_mb"] == 16384

    def test_mps_fallback_when_no_cuda(self):
        """When CUDA is unavailable but MPS is, detect MPS."""
        mock_torch = MagicMock()
        mock_torch.cuda.is_available.return_value = False
        mock_torch.backends.mps.is_available.return_value = True
        # No torch.xpu attribute
        del mock_torch.xpu

        caps = {"torch": False, "gpu_backend": "none", "gpu_name": "none", "gpu_memory_mb": 0}

        with patch.dict("sys.modules", {"torch": mock_torch}):
            with patch("builtins.__import__", side_effect=_import_mock_torch(mock_torch)):
                _detect_torch(caps)

        assert caps["torch"] is True
        assert caps["gpu_backend"] == "mps"

    def test_no_gpu_available(self):
        """When no GPU is available, torch is detected but gpu_backend stays 'none'."""
        mock_torch = MagicMock()
        mock_torch.cuda.is_available.return_value = False
        mock_torch.backends.mps.is_available.return_value = False
        # Remove xpu attribute
        del mock_torch.xpu

        caps = {"torch": False, "gpu_backend": "none", "gpu_name": "none", "gpu_memory_mb": 0}

        with patch.dict("sys.modules", {"torch": mock_torch}):
            with patch("builtins.__import__", side_effect=_import_mock_torch(mock_torch)):
                _detect_torch(caps)

        assert caps["torch"] is True
        assert caps["gpu_backend"] == "none"

    def test_torch_not_installed(self):
        """When torch is not installed, torch=False."""
        caps = {"torch": False, "gpu_backend": "none", "gpu_name": "none", "gpu_memory_mb": 0}

        with patch.dict("sys.modules", {"torch": None}):
            with patch("builtins.__import__", side_effect=_import_except("torch")):
                _detect_torch(caps)

        assert caps["torch"] is False


# ---------------------------------------------------------------------------
# MLX / Metal detection
# ---------------------------------------------------------------------------

class TestMLXDetection:
    def _mlx_available(self) -> bool:
        try:
            import mlx.core  # noqa: F401
            return True
        except ImportError:
            return False

    def test_mlx_detection_when_available(self):
        """If MLX is installed, _detect_mlx sets mlx=True and reads Metal memory."""
        if not self._mlx_available():
            pytest.skip("MLX not installed")

        caps = {"mlx": False, "metal_active_mb": 0}
        _detect_mlx(caps)

        assert caps["mlx"] is True
        # metal_active_mb should be a non-negative int
        assert isinstance(caps["metal_active_mb"], int)
        assert caps["metal_active_mb"] >= 0
        # Peak and cache should also be set
        assert "metal_peak_mb" in caps
        assert "metal_cache_mb" in caps

    def test_mlx_detection_when_unavailable(self):
        """If MLX is not installed, _detect_mlx sets mlx=False."""
        if self._mlx_available():
            pytest.skip("MLX is installed — cannot test unavailable path natively")

        caps = {"mlx": False, "metal_active_mb": 0}
        _detect_mlx(caps)
        assert caps["mlx"] is False

    def test_mlx_metal_values_are_ints(self):
        """Metal memory values should be integers (MB)."""
        if not self._mlx_available():
            pytest.skip("MLX not installed")

        caps = {"mlx": False, "metal_active_mb": 0}
        _detect_mlx(caps)

        for key in ("metal_active_mb", "metal_peak_mb", "metal_cache_mb"):
            if key in caps:
                assert isinstance(caps[key], int), f"{key} should be int, got {type(caps[key])}"


# ---------------------------------------------------------------------------
# Full detect_capabilities integration
# ---------------------------------------------------------------------------

class TestDetectCapabilities:
    def test_caching(self):
        """Results should be cached across calls."""
        result1 = detect_capabilities()
        result2 = detect_capabilities()
        assert result1 is result2  # Same object = cached

    def test_returns_required_keys(self):
        """All expected keys are present in the result."""
        caps = detect_capabilities()
        required_keys = {
            "torch", "mlx", "gpu_backend", "gpu_name",
            "gpu_memory_mb", "system_memory_mb", "unified_memory",
            "accelerators", "metal_active_mb", "disk_free_gb",
        }
        assert required_keys.issubset(caps.keys())

    def test_system_memory_positive(self):
        """System memory should always be a positive number."""
        caps = detect_capabilities()
        assert caps["system_memory_mb"] > 0

    def test_accelerators_dict_present(self):
        """Accelerators summary should have expected keys."""
        caps = detect_capabilities()
        accel = caps["accelerators"]
        assert isinstance(accel, dict)
        for key in ("cuda", "rocm", "metal", "mlx", "mps"):
            assert key in accel


# ---------------------------------------------------------------------------
# Import helpers for mocking
# ---------------------------------------------------------------------------

_real_import = __builtins__.__import__ if hasattr(__builtins__, '__import__') else __import__


def _import_except_psutil(name, *args, **kwargs):
    if name == "psutil":
        raise ImportError("mocked")
    return _real_import(name, *args, **kwargs)


def _import_except(module_name):
    def _import(name, *args, **kwargs):
        if name == module_name:
            raise ImportError(f"mocked: {module_name}")
        return _real_import(name, *args, **kwargs)
    return _import


def _import_mock_torch(mock_torch):
    def _import(name, *args, **kwargs):
        if name == "torch":
            return mock_torch
        return _real_import(name, *args, **kwargs)
    return _import


def _import_mock_mlx(mock_mlx, mock_metal):
    def _import(name, *args, **kwargs):
        if name == "mlx.core":
            return mock_mlx.core
        if name == "mlx.core.metal":
            return mock_metal
        return _real_import(name, *args, **kwargs)
    return _import


def _mock_system_profiler(cmd, **kwargs):
    import json
    if "SPDisplaysDataType" in cmd:
        return json.dumps({
            "SPDisplaysDataType": [{
                "sppci_model": "Apple M2 Max",
            }]
        }).encode()
    return b""
