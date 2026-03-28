"""CapabilityDetector — detects installed ML libraries, services, and GPU availability.

Reports which install profile is active ('base', 'inference', 'training', 'full')
and whether individual capabilities (torch, transformers, ollama, etc.) are present.
Used to determine which blocks are available vs. disabled.

Detection is split into two phases so it never blocks server startup:

  Phase 1 (synchronous, ~50ms):  import checks + GPU detection
  Phase 2 (background thread):   network probes (Ollama health check)

Callers always get a consistent snapshot via ``detect()``.  The snapshot
auto-upgrades once Phase 2 completes.  ``refresh()`` reruns both phases
synchronously (acceptable for user-triggered actions like POST /refresh).
"""

from __future__ import annotations

import logging
import platform
import sys
import threading
from typing import Any

logger = logging.getLogger("blueprint.capabilities")


# ── Import-based capability checks ────────────────────────────────────
# Map of capability name → Python module name to attempt importing.

_CAPABILITY_CHECKS: dict[str, str] = {
    "torch": "torch",
    "transformers": "transformers",
    "peft": "peft",
    "bitsandbytes": "bitsandbytes",
    "datasets": "datasets",
    "accelerate": "accelerate",
    "scikit_learn": "sklearn",
    "pandas": "pandas",
    "numpy": "numpy",
    "scipy": "scipy",
    "mlx": "mlx",
    "sentencepiece": "sentencepiece",
    "tokenizers": "tokenizers",
    "safetensors": "safetensors",
    "trl": "trl",
    "pillow": "PIL",
    "opencv": "cv2",
    "matplotlib": "matplotlib",
    "seaborn": "seaborn",
}


def _check_import(module_name: str) -> bool:
    """Try to import a module, return True if available."""
    try:
        __import__(module_name)
        return True
    except ImportError:
        return False


def _check_ollama() -> bool:
    """Check if Ollama is running on localhost:11434.

    Uses a short timeout to avoid blocking. Returns False on any failure.
    """
    try:
        import httpx
        resp = httpx.get("http://localhost:11434/api/version", timeout=2.0)
        return resp.status_code == 200
    except Exception:
        pass
    # Fallback to requests
    try:
        import requests
        resp = requests.get("http://localhost:11434/api/version", timeout=2.0)
        return resp.status_code == 200
    except Exception:
        return False


def _check_gpu() -> dict[str, Any]:
    """Detect GPU availability and return info."""
    result: dict[str, Any] = {
        "available": False,
        "backend": "none",
        "name": None,
    }

    # Check CUDA
    try:
        import torch
        if torch.cuda.is_available():
            result["available"] = True
            result["backend"] = "cuda"
            result["name"] = torch.cuda.get_device_name(0)
            return result
    except ImportError:
        pass

    # Check MPS (Apple Silicon)
    try:
        import torch
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            result["available"] = True
            result["backend"] = "mps"
            result["name"] = "Apple Silicon GPU"
            return result
    except (ImportError, AttributeError):
        pass

    # Check MLX (macOS only)
    if platform.system() == "Darwin":
        try:
            import mlx.core  # noqa: F401
            result["available"] = True
            result["backend"] = "mlx"
            result["name"] = "Apple Silicon (MLX)"
            return result
        except ImportError:
            pass

    return result


def _determine_profile(caps: dict[str, bool]) -> str:
    """Determine which install profile best matches the detected capabilities.

    Profiles:
    - 'base':      Only core FastAPI/SQLAlchemy/etc. No ML libs.
    - 'inference':  Can run inference (has ollama or transformers for inference)
    - 'training':   Can train models (torch + transformers + peft/trl)
    - 'full':       Has training + evaluation + data science + everything
    """
    has_torch = caps.get("torch", False)
    has_transformers = caps.get("transformers", False)
    has_peft = caps.get("peft", False) or caps.get("trl", False)
    has_datasets = caps.get("datasets", False)
    has_ollama = caps.get("ollama", False)
    has_sklearn = caps.get("scikit_learn", False)
    has_data_libs = caps.get("pandas", False) and caps.get("numpy", False)

    # Full: training libs + evaluation/data science
    if has_torch and has_transformers and has_peft and has_datasets and has_sklearn and has_data_libs:
        return "full"

    # Training: torch + transformers + fine-tuning lib
    if has_torch and has_transformers and has_peft:
        return "training"

    # Inference: can run models (ollama or transformers)
    if has_ollama or has_transformers:
        return "inference"

    return "base"


class CapabilityDetector:
    """Singleton detector for system ML capabilities.

    Call ``detect()`` to get a full snapshot.  On first call, Phase 1 runs
    synchronously while Phase 2 is launched in a background thread.  The
    returned dict is safe to read immediately — the ``ollama`` key starts
    as ``False`` and flips to ``True`` once the background probe succeeds.

    Use ``refresh()`` to force re-detection of *all* capabilities
    synchronously (acceptable latency for explicit user actions).
    """

    def __init__(self) -> None:
        self._cache: dict[str, Any] | None = None
        self._lock = threading.Lock()
        self._phase2_complete = threading.Event()

    # ── Public API ─────────────────────────────────────────────────

    def detect(self) -> dict[str, Any]:
        """Return the capability report (cached after first call).

        First call: runs Phase 1 synchronously, kicks off Phase 2 in
        a daemon thread.  Subsequent calls return the same (mutable)
        dict, which may have been updated by Phase 2 in the background.
        """
        if self._cache is not None:
            return self._cache
        with self._lock:
            # Double-check after acquiring the lock
            if self._cache is not None:
                return self._cache
            self._cache = self._run_phase1()
            self._start_phase2()
        return self._cache

    def refresh(self) -> dict[str, Any]:
        """Force a full synchronous re-detection (both phases).

        Intended for user-triggered actions (POST /capabilities/refresh,
        or after ``pip install``).  The ~2 s Ollama timeout is acceptable
        here because the user is explicitly asking for a refresh.
        """
        with self._lock:
            self._phase2_complete.clear()
            self._cache = self._run_phase1()
            self._run_phase2_sync()
        return self._cache

    def wait_ready(self, timeout: float = 5.0) -> bool:
        """Block until Phase 2 has completed.  Returns True if ready.

        Useful in tests to avoid races.  Production code should never
        need this — ``detect()`` always returns a consistent snapshot.
        """
        return self._phase2_complete.wait(timeout)

    # ── Phase 1: fast, synchronous (~50 ms) ────────────────────────

    def _run_phase1(self) -> dict[str, Any]:
        """Import checks + GPU detection.  No network I/O."""
        capabilities: dict[str, bool] = {}
        for cap_name, module_name in _CAPABILITY_CHECKS.items():
            capabilities[cap_name] = _check_import(module_name)

        # GPU detection (local, no network)
        gpu_info = _check_gpu()
        capabilities["gpu"] = gpu_info["available"]

        # Ollama defaults to False — upgraded by Phase 2
        capabilities["ollama"] = False

        plat = {
            "os": platform.system().lower(),
            "arch": platform.machine(),
            "python_version": (
                f"{sys.version_info.major}.{sys.version_info.minor}"
                f".{sys.version_info.micro}"
            ),
            "gpu_name": gpu_info["name"],
            "gpu_backend": gpu_info["backend"],
        }

        installed_profile = _determine_profile(capabilities)

        logger.info(
            "Phase 1 complete: profile=%s, gpu=%s (%s)",
            installed_profile,
            gpu_info["available"],
            gpu_info["backend"],
        )

        return {
            "capabilities": capabilities,
            "platform": plat,
            "installed_profile": installed_profile,
        }

    # ── Phase 2: network probes (background thread) ─────────────────

    def _start_phase2(self) -> None:
        """Kick off Phase 2 in a daemon thread."""
        t = threading.Thread(target=self._run_phase2_sync, daemon=True)
        t.start()

    def _run_phase2_sync(self) -> None:
        """Run network-dependent probes and update the cached report in place.

        Safe to call from any thread — mutations are atomic dict writes.
        """
        try:
            assert self._cache is not None
            ollama_ok = _check_ollama()
            self._cache["capabilities"]["ollama"] = ollama_ok

            # Re-derive profile now that we know about Ollama
            self._cache["installed_profile"] = _determine_profile(
                self._cache["capabilities"]
            )

            logger.info(
                "Phase 2 complete: ollama=%s, profile=%s",
                ollama_ok,
                self._cache["installed_profile"],
            )
        except Exception as exc:
            logger.warning("Phase 2 capability detection failed: %s", exc)
        finally:
            self._phase2_complete.set()


# ── Module-level singleton ────────────────────────────────────────────

_instance: CapabilityDetector | None = None


def get_capability_detector() -> CapabilityDetector:
    """Return the module-level singleton, creating it on first access."""
    global _instance
    if _instance is None:
        _instance = CapabilityDetector()
    return _instance


def set_capability_detector(detector: CapabilityDetector) -> None:
    """Install the app-level singleton.  Called once by ``main.py`` at startup."""
    global _instance
    _instance = detector


# ═══════════════════════════════════════════════════════════════════════════
# Dry-Run Hardware Estimation — detect_capabilities()
#
# Provides resource-level detail (memory sizes, GPU backends, unified memory)
# for the dry-run simulator.  Separate from the CapabilityDetector class
# which focuses on library/profile availability for block gating.
# ═══════════════════════════════════════════════════════════════════════════

import functools


@functools.lru_cache(maxsize=1)
def detect_capabilities() -> dict[str, Any]:
    """Detect system hardware capabilities for dry-run resource estimation.

    Returns a dict with keys:
        torch: bool              — PyTorch is importable
        mlx: bool                — MLX is importable
        gpu_backend: str         — 'cuda' | 'rocm' | 'metal' | 'mps' | 'none'
        gpu_name: str            — GPU model name
        gpu_memory_mb: int       — Dedicated or unified GPU memory in MB
        system_memory_mb: int    — Total system RAM in MB
        unified_memory: bool     — True on Apple Silicon
        accelerators: dict       — {mlx, cuda, mps, rocm} availability
        metal_active_mb: int     — MLX Metal active memory (0 if unavailable)
        disk_free_gb: float      — Free disk space in GB
    """
    caps: dict[str, Any] = {
        "torch": False,
        "mlx": False,
        "gpu_backend": "none",
        "gpu_name": "none",
        "gpu_memory_mb": 0,
        "system_memory_mb": _detect_system_memory_mb(),
        "unified_memory": False,
        "accelerators": {},
        "metal_active_mb": 0,
        "disk_free_gb": 0.0,
    }

    _detect_apple_silicon(caps)
    _detect_torch_hardware(caps)
    _detect_mlx_hardware(caps)
    _detect_disk(caps)

    caps["accelerators"] = {
        "cuda": caps["gpu_backend"] == "cuda",
        "rocm": caps["gpu_backend"] == "rocm",
        "metal": caps["gpu_backend"] in ("metal", "mps"),
        "mlx": caps["mlx"],
        "mps": _check_mps(),
    }

    if caps["gpu_memory_mb"] == 0:
        _fallback_hardware_profile(caps)

    return caps


def invalidate_cache() -> None:
    """Clear the cached capabilities (useful for testing)."""
    detect_capabilities.cache_clear()


def _detect_system_memory_mb() -> int:
    try:
        import psutil
        return int(psutil.virtual_memory().total / (1024 * 1024))
    except ImportError:
        pass
    if platform.system() == "Darwin":
        try:
            import subprocess
            raw = subprocess.check_output(
                ["sysctl", "-n", "hw.memsize"], timeout=5, stderr=subprocess.DEVNULL,
            ).decode().strip()
            return int(int(raw) / (1024 * 1024))
        except Exception:
            pass
    elif platform.system() == "Linux":
        try:
            with open("/proc/meminfo") as f:
                for line in f:
                    if line.startswith("MemTotal"):
                        return int(int(line.split()[1]) / 1024)
        except Exception:
            pass
    try:
        import os
        return int((os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE")) / (1024 * 1024))
    except (ValueError, OSError, AttributeError):
        pass
    return 16384


def _detect_apple_silicon(caps: dict[str, Any]) -> None:
    if platform.system() != "Darwin" or platform.machine().lower() not in ("arm64", "aarch64"):
        return
    caps["unified_memory"] = True
    caps["gpu_memory_mb"] = caps["system_memory_mb"]
    caps["gpu_backend"] = "metal"
    try:
        import subprocess, json as _json
        raw = subprocess.check_output(
            ["system_profiler", "SPDisplaysDataType", "-json"], timeout=10, stderr=subprocess.DEVNULL,
        ).decode()
        for gpu in _json.loads(raw).get("SPDisplaysDataType", []):
            name = gpu.get("sppci_model", "")
            if name:
                caps["gpu_name"] = name
                break
    except Exception:
        caps["gpu_name"] = f"Apple Silicon ({platform.machine()})"


def _detect_torch_hardware(caps: dict[str, Any]) -> None:
    try:
        import torch
        caps["torch"] = True
    except ImportError:
        return
    if torch.cuda.is_available():
        try:
            props = torch.cuda.get_device_properties(0)
            is_rocm = hasattr(torch.version, "hip") and torch.version.hip is not None
            caps["gpu_backend"] = "rocm" if is_rocm else "cuda"
            caps["gpu_name"] = props.name
            caps["gpu_memory_mb"] = int(props.total_mem / (1024 * 1024))
        except Exception:
            caps["gpu_backend"] = "cuda"
    elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        if caps["gpu_backend"] == "none":
            caps["gpu_backend"] = "mps"
    elif hasattr(torch, "xpu") and torch.xpu.is_available():
        try:
            props = torch.xpu.get_device_properties(0)
            caps["gpu_backend"] = "xpu"
            caps["gpu_name"] = props.name
            caps["gpu_memory_mb"] = int(getattr(props, "total_memory", 0) / (1024 * 1024))
        except Exception:
            caps["gpu_backend"] = "xpu"


def _detect_mlx_hardware(caps: dict[str, Any]) -> None:
    try:
        import mlx.core  # noqa: F401
        caps["mlx"] = True
    except ImportError:
        return
    try:
        import mlx.core.metal as metal
        caps["metal_active_mb"] = int(metal.get_active_memory() / (1024 * 1024))
        caps["metal_peak_mb"] = int(metal.get_peak_memory() / (1024 * 1024))
        caps["metal_cache_mb"] = int(metal.get_cache_memory() / (1024 * 1024))
        if hasattr(metal, "device_info"):
            info = metal.device_info()
            if isinstance(info, dict):
                mem = info.get("memory_size", 0)
                if mem > 0:
                    caps["gpu_memory_mb"] = int(mem / (1024 * 1024))
    except Exception:
        pass


def _check_mps() -> bool:
    try:
        import torch
        return hasattr(torch.backends, "mps") and torch.backends.mps.is_available()
    except ImportError:
        return False


def _fallback_hardware_profile(caps: dict[str, Any]) -> None:
    try:
        from ..utils.hardware import get_hardware_profile
        profile = get_hardware_profile()
        for gpu in profile.get("gpu", []):
            if gpu.get("type") in ("metal", "cuda", "rocm") and gpu.get("vram_gb", 0) > 0:
                vram_mb = int(gpu["vram_gb"] * 1024)
                if vram_mb > caps["gpu_memory_mb"]:
                    caps["gpu_memory_mb"] = vram_mb
                    caps["gpu_backend"] = gpu["type"]
                    caps["gpu_name"] = gpu.get("name", caps["gpu_name"])
                break
        ram_gb = profile.get("ram", {}).get("total_gb", 0)
        if ram_gb > 0 and caps["system_memory_mb"] < int(ram_gb * 1024):
            caps["system_memory_mb"] = int(ram_gb * 1024)
        caps["disk_free_gb"] = profile.get("disk", {}).get("free_gb", caps["disk_free_gb"])
    except Exception:
        pass


def _detect_disk(caps: dict[str, Any]) -> None:
    try:
        import shutil
        from pathlib import Path
        usage = shutil.disk_usage(str(Path.home()))
        caps["disk_free_gb"] = round(usage.free / (1024 ** 3), 1)
    except Exception:
        pass
