"""
Capability Detector — comprehensive system capability detection for dry-run simulation.

Detects available ML frameworks, GPU backends (CUDA, ROCm, Apple Metal/MPS),
memory (system RAM, GPU VRAM, unified memory), and accelerator libraries.

Results are cached for the process lifetime since hardware doesn't change
during a session.
"""

from __future__ import annotations

import functools
import logging
import platform
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

@functools.lru_cache(maxsize=1)
def detect_capabilities() -> dict[str, Any]:
    """Detect all system capabilities for dry-run estimation.

    Returns a dict with keys:
        torch: bool              — PyTorch is importable
        mlx: bool                — MLX is importable
        gpu_backend: str         — 'cuda' | 'rocm' | 'metal' | 'mps' | 'none'
        gpu_name: str            — GPU model name (e.g. "Apple M2 Max", "NVIDIA A100")
        gpu_memory_mb: int       — Dedicated or unified GPU memory in MB
        system_memory_mb: int    — Total system RAM in MB
        unified_memory: bool     — True on Apple Silicon (RAM is GPU-accessible)
        accelerators: dict       — {mlx, cuda, mps, rocm, coreml} availability
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

    # Detect Apple Silicon unified memory first
    _detect_apple_silicon(caps)

    # Detect PyTorch and its GPU backends
    _detect_torch(caps)

    # Detect MLX and Metal memory
    _detect_mlx(caps)

    # Detect disk space
    _detect_disk(caps)

    # Build accelerators summary
    caps["accelerators"] = {
        "cuda": caps["gpu_backend"] == "cuda",
        "rocm": caps["gpu_backend"] == "rocm",
        "metal": caps["gpu_backend"] == "metal" or caps["gpu_backend"] == "mps",
        "mlx": caps["mlx"],
        "mps": _check_mps(),
    }

    # Fall back to hardware.py for GPU detection if nothing found yet
    if caps["gpu_memory_mb"] == 0:
        _fallback_hardware_profile(caps)

    logger.debug(
        "Detected capabilities: gpu=%s mem=%dMB gpu_mem=%dMB unified=%s",
        caps["gpu_backend"], caps["system_memory_mb"],
        caps["gpu_memory_mb"], caps["unified_memory"],
    )

    return caps


def invalidate_cache() -> None:
    """Clear the cached capabilities (useful for testing)."""
    detect_capabilities.cache_clear()


# ---------------------------------------------------------------------------
# System memory
# ---------------------------------------------------------------------------

def _detect_system_memory_mb() -> int:
    """Detect total system RAM in MB."""
    # Try psutil first (most accurate and cross-platform)
    try:
        import psutil
        return int(psutil.virtual_memory().total / (1024 * 1024))
    except ImportError:
        pass

    system = platform.system()

    if system == "Darwin":
        # macOS: sysctl hw.memsize
        try:
            import subprocess
            raw = subprocess.check_output(
                ["sysctl", "-n", "hw.memsize"],
                timeout=5,
                stderr=subprocess.DEVNULL,
            ).decode().strip()
            return int(int(raw) / (1024 * 1024))
        except Exception:
            pass

    elif system == "Linux":
        # Linux: /proc/meminfo
        try:
            with open("/proc/meminfo") as f:
                for line in f:
                    if line.startswith("MemTotal"):
                        kb = int(line.split()[1])
                        return int(kb / 1024)
        except Exception:
            pass

    # os.sysconf fallback (POSIX)
    try:
        import os
        pages = os.sysconf("SC_PHYS_PAGES")
        page_size = os.sysconf("SC_PAGE_SIZE")
        return int((pages * page_size) / (1024 * 1024))
    except (ValueError, OSError, AttributeError):
        pass

    return 16384  # 16GB default


# ---------------------------------------------------------------------------
# Apple Silicon detection
# ---------------------------------------------------------------------------

def _detect_apple_silicon(caps: dict[str, Any]) -> None:
    """Detect Apple Silicon unified memory architecture."""
    if platform.system() != "Darwin":
        return

    machine = platform.machine().lower()
    is_apple_silicon = machine in ("arm64", "aarch64")

    if not is_apple_silicon:
        return

    # On Apple Silicon, all system RAM is unified (CPU + GPU share it)
    caps["unified_memory"] = True

    # GPU memory = total system memory on unified architecture
    # The GPU can use most of the system RAM (typically ~75% safely)
    caps["gpu_memory_mb"] = caps["system_memory_mb"]
    caps["gpu_backend"] = "metal"

    # Get GPU name from system_profiler
    try:
        import subprocess
        import json as _json
        raw = subprocess.check_output(
            ["system_profiler", "SPDisplaysDataType", "-json"],
            timeout=10,
            stderr=subprocess.DEVNULL,
        ).decode()
        data = _json.loads(raw)
        displays = data.get("SPDisplaysDataType", [])
        for gpu in displays:
            name = gpu.get("sppci_model", "")
            if name:
                caps["gpu_name"] = name
                break
    except Exception:
        caps["gpu_name"] = f"Apple Silicon ({machine})"


# ---------------------------------------------------------------------------
# PyTorch detection (CUDA, ROCm, MPS)
# ---------------------------------------------------------------------------

def _detect_torch(caps: dict[str, Any]) -> None:
    """Detect PyTorch and its GPU backends."""
    try:
        import torch
        caps["torch"] = True
    except ImportError:
        return

    # CUDA (NVIDIA)
    if torch.cuda.is_available():
        try:
            device_props = torch.cuda.get_device_properties(0)
            gpu_mem_mb = int(device_props.total_mem / (1024 * 1024))

            # Distinguish CUDA from ROCm — ROCm reports via torch.cuda
            # but torch.version.hip will be set
            is_rocm = hasattr(torch.version, "hip") and torch.version.hip is not None

            if is_rocm:
                caps["gpu_backend"] = "rocm"
                caps["gpu_name"] = device_props.name
                caps["gpu_memory_mb"] = gpu_mem_mb
            else:
                caps["gpu_backend"] = "cuda"
                caps["gpu_name"] = device_props.name
                caps["gpu_memory_mb"] = gpu_mem_mb

            # For multi-GPU, sum VRAM across all devices
            device_count = torch.cuda.device_count()
            if device_count > 1:
                total_vram = sum(
                    int(torch.cuda.get_device_properties(i).total_mem / (1024 * 1024))
                    for i in range(device_count)
                )
                # Report max single GPU for memory estimates (conservative)
                # but track total for reference
                caps["gpu_memory_mb"] = max(
                    caps["gpu_memory_mb"],
                    int(torch.cuda.get_device_properties(0).total_mem / (1024 * 1024)),
                )
                caps["total_gpu_memory_mb"] = total_vram
                caps["gpu_count"] = device_count

        except Exception as e:
            logger.debug("Failed to query CUDA device properties: %s", e)
            caps["gpu_backend"] = "cuda"
            # CUDA exists but we can't query properties — leave memory at 0
            return

    # MPS (Apple Metal Performance Shaders via PyTorch)
    elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        if caps["gpu_backend"] == "none":
            caps["gpu_backend"] = "mps"
        # On MPS, GPU memory = unified memory (already set by _detect_apple_silicon)

    # Intel XPU
    elif hasattr(torch, "xpu") and torch.xpu.is_available():
        try:
            device_props = torch.xpu.get_device_properties(0)
            caps["gpu_backend"] = "xpu"
            caps["gpu_name"] = device_props.name
            caps["gpu_memory_mb"] = int(
                getattr(device_props, "total_memory", 0) / (1024 * 1024)
            )
        except Exception:
            caps["gpu_backend"] = "xpu"


# ---------------------------------------------------------------------------
# MLX / Metal detection
# ---------------------------------------------------------------------------

def _detect_mlx(caps: dict[str, Any]) -> None:
    """Detect MLX framework and Metal memory state."""
    try:
        import mlx.core  # noqa: F401
        caps["mlx"] = True
    except ImportError:
        return

    # Query Metal memory usage via mlx.core.metal
    try:
        import mlx.core.metal as metal

        # Active memory: bytes currently held by live tensors
        active = metal.get_active_memory()
        caps["metal_active_mb"] = int(active / (1024 * 1024))

        # Peak memory: highest watermark this session
        peak = metal.get_peak_memory()
        caps["metal_peak_mb"] = int(peak / (1024 * 1024))

        # Cache memory: allocated but not in use (freed tensors)
        cache = metal.get_cache_memory()
        caps["metal_cache_mb"] = int(cache / (1024 * 1024))

        # Device info (if available in newer MLX versions)
        if hasattr(metal, "device_info"):
            info = metal.device_info()
            if isinstance(info, dict):
                # Some MLX versions return {"memory_size": bytes, ...}
                mem_size = info.get("memory_size", 0)
                if mem_size > 0:
                    caps["gpu_memory_mb"] = int(mem_size / (1024 * 1024))

    except Exception as e:
        logger.debug("Failed to query MLX Metal memory: %s", e)


def _check_mps() -> bool:
    """Check if MPS (Metal Performance Shaders) is available."""
    try:
        import torch
        return hasattr(torch.backends, "mps") and torch.backends.mps.is_available()
    except ImportError:
        return False


# ---------------------------------------------------------------------------
# Fallback: reuse hardware.py profile
# ---------------------------------------------------------------------------

def _fallback_hardware_profile(caps: dict[str, Any]) -> None:
    """Use the hardware profiler as a fallback for GPU detection."""
    try:
        from ..utils.hardware import get_hardware_profile

        profile = get_hardware_profile()
        gpus = profile.get("gpu", [])

        for gpu in gpus:
            gpu_type = gpu.get("type", "unknown")
            if gpu_type in ("metal", "cuda", "rocm") and gpu.get("vram_gb", 0) > 0:
                vram_mb = int(gpu["vram_gb"] * 1024)
                if vram_mb > caps["gpu_memory_mb"]:
                    caps["gpu_memory_mb"] = vram_mb
                    caps["gpu_backend"] = gpu_type
                    caps["gpu_name"] = gpu.get("name", caps["gpu_name"])
                break

        # System RAM fallback
        ram_gb = profile.get("ram", {}).get("total_gb", 0)
        if ram_gb > 0 and caps["system_memory_mb"] < int(ram_gb * 1024):
            caps["system_memory_mb"] = int(ram_gb * 1024)

        # Disk
        disk_free = profile.get("disk", {}).get("free_gb", 0)
        if disk_free > 0:
            caps["disk_free_gb"] = disk_free

    except Exception as e:
        logger.debug("Hardware profile fallback failed: %s", e)


# ---------------------------------------------------------------------------
# Disk space
# ---------------------------------------------------------------------------

def _detect_disk(caps: dict[str, Any]) -> None:
    """Detect available disk space."""
    try:
        import shutil
        from pathlib import Path
        usage = shutil.disk_usage(str(Path.home()))
        caps["disk_free_gb"] = round(usage.free / (1024 ** 3), 1)
    except Exception:
        pass
