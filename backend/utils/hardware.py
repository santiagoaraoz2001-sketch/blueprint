"""Hardware profiler — detects CPU, RAM, GPU, disk, and ML-accelerator capabilities.

Every helper is wrapped in try/except so a single detection failure never
crashes the endpoint.  We deliberately avoid ``psutil`` (it may not be
installed) and shell out via ``subprocess`` instead.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_hardware_profile() -> dict[str, Any]:
    """Return a complete hardware snapshot."""
    return {
        "cpu": _detect_cpu(),
        "ram": _detect_ram(),
        "gpu": _detect_gpu(),
        "disk": _detect_disk(),
        "accelerators": _detect_accelerators(),
    }


# ---------------------------------------------------------------------------
# CPU
# ---------------------------------------------------------------------------

def _detect_cpu() -> dict[str, Any]:
    info: dict[str, Any] = {
        "brand": "unknown",
        "arch": platform.machine() or "unknown",
        "cores": os.cpu_count() or 0,
        "threads": os.cpu_count() or 0,
        "freq_mhz": 0,
    }

    system = platform.system()

    if system == "Darwin":
        # Brand string
        try:
            brand = subprocess.check_output(
                ["sysctl", "-n", "machdep.cpu.brand_string"],
                timeout=5,
                stderr=subprocess.DEVNULL,
            ).decode().strip()
            if brand:
                info["brand"] = brand
        except Exception:
            pass

        # Physical cores
        try:
            cores = subprocess.check_output(
                ["sysctl", "-n", "hw.physicalcpu"],
                timeout=5,
                stderr=subprocess.DEVNULL,
            ).decode().strip()
            info["cores"] = int(cores)
        except Exception:
            pass

        # Logical cores (threads)
        try:
            threads = subprocess.check_output(
                ["sysctl", "-n", "hw.logicalcpu"],
                timeout=5,
                stderr=subprocess.DEVNULL,
            ).decode().strip()
            info["threads"] = int(threads)
        except Exception:
            pass

        # CPU frequency (Hz -> MHz)
        try:
            freq_raw = subprocess.check_output(
                ["sysctl", "-n", "hw.cpufrequency"],
                timeout=5,
                stderr=subprocess.DEVNULL,
            ).decode().strip()
            info["freq_mhz"] = int(freq_raw) // 1_000_000
        except Exception:
            # Apple Silicon doesn't expose hw.cpufrequency — try
            # hw.cpufrequency_max or leave at 0.
            try:
                freq_raw = subprocess.check_output(
                    ["sysctl", "-n", "hw.cpufrequency_max"],
                    timeout=5,
                    stderr=subprocess.DEVNULL,
                ).decode().strip()
                info["freq_mhz"] = int(freq_raw) // 1_000_000
            except Exception:
                pass

    elif system == "Linux":
        # /proc/cpuinfo
        try:
            with open("/proc/cpuinfo") as f:
                cpuinfo = f.read()
            for line in cpuinfo.splitlines():
                if line.startswith("model name"):
                    info["brand"] = line.split(":", 1)[1].strip()
                    break
            # Count physical cores via unique core ids
            core_ids = set()
            for line in cpuinfo.splitlines():
                if line.startswith("core id"):
                    core_ids.add(line.split(":", 1)[1].strip())
            if core_ids:
                info["cores"] = len(core_ids)
            # CPU MHz
            for line in cpuinfo.splitlines():
                if line.startswith("cpu MHz"):
                    info["freq_mhz"] = int(float(line.split(":", 1)[1].strip()))
                    break
        except Exception:
            pass

        # nproc for thread count
        try:
            threads = subprocess.check_output(
                ["nproc", "--all"], timeout=5, stderr=subprocess.DEVNULL,
            ).decode().strip()
            info["threads"] = int(threads)
        except Exception:
            pass

    else:
        # Windows / other — best-effort via platform
        info["brand"] = platform.processor() or "unknown"

    return info


# ---------------------------------------------------------------------------
# RAM
# ---------------------------------------------------------------------------

def _detect_ram() -> dict[str, Any]:
    info: dict[str, Any] = {"total_gb": 0.0, "available_gb": 0.0}
    system = platform.system()

    if system == "Darwin":
        # Total RAM
        try:
            memsize = subprocess.check_output(
                ["sysctl", "-n", "hw.memsize"],
                timeout=5,
                stderr=subprocess.DEVNULL,
            ).decode().strip()
            info["total_gb"] = round(int(memsize) / (1024 ** 3), 1)
        except Exception:
            pass

        # Available RAM via vm_stat
        try:
            raw = subprocess.check_output(
                ["vm_stat"], timeout=5, stderr=subprocess.DEVNULL,
            ).decode()
            page_size = 16384  # default on Apple Silicon
            # Try to parse page size from first line
            first_line = raw.splitlines()[0] if raw.splitlines() else ""
            if "page size of" in first_line:
                try:
                    page_size = int(first_line.split("page size of")[1].strip().split()[0])
                except Exception:
                    pass
            free_pages = 0
            inactive_pages = 0
            for line in raw.splitlines():
                if "Pages free" in line:
                    free_pages = int(line.split(":")[1].strip().rstrip("."))
                elif "Pages inactive" in line:
                    inactive_pages = int(line.split(":")[1].strip().rstrip("."))
            available_bytes = (free_pages + inactive_pages) * page_size
            info["available_gb"] = round(available_bytes / (1024 ** 3), 1)
        except Exception:
            pass

    elif system == "Linux":
        try:
            with open("/proc/meminfo") as f:
                meminfo = f.read()
            for line in meminfo.splitlines():
                if line.startswith("MemTotal"):
                    kb = int(line.split()[1])
                    info["total_gb"] = round(kb / (1024 ** 2), 1)
                elif line.startswith("MemAvailable"):
                    kb = int(line.split()[1])
                    info["available_gb"] = round(kb / (1024 ** 2), 1)
        except Exception:
            pass

    return info


# ---------------------------------------------------------------------------
# GPU
# ---------------------------------------------------------------------------

def _detect_gpu() -> list[dict[str, Any]]:
    gpus: list[dict[str, Any]] = []
    system = platform.system()

    # --- macOS: system_profiler ------------------------------------------
    if system == "Darwin":
        try:
            raw = subprocess.check_output(
                ["system_profiler", "SPDisplaysDataType", "-json"],
                timeout=10,
                stderr=subprocess.DEVNULL,
            ).decode()
            data = json.loads(raw)
            displays = data.get("SPDisplaysDataType", [])
            for gpu in displays:
                name = gpu.get("sppci_model", "unknown")
                vram_str = gpu.get("sppci_vram", gpu.get("spdisplays_vram", "0"))
                # e.g. "36 GB" or "8192 MB"
                vram_gb = _parse_vram(vram_str)
                # For Apple Silicon unified memory, use total RAM as VRAM
                if vram_gb == 0 and "apple" in name.lower():
                    try:
                        memsize = subprocess.check_output(
                            ["sysctl", "-n", "hw.memsize"],
                            timeout=5,
                            stderr=subprocess.DEVNULL,
                        ).decode().strip()
                        vram_gb = round(int(memsize) / (1024 ** 3), 1)
                    except Exception:
                        pass
                gpus.append({
                    "name": name,
                    "vram_gb": vram_gb,
                    "type": "metal",
                })
        except Exception:
            pass

    # --- NVIDIA: nvidia-smi ----------------------------------------------
    if shutil.which("nvidia-smi"):
        try:
            raw = subprocess.check_output(
                [
                    "nvidia-smi",
                    "--query-gpu=name,memory.total,memory.free",
                    "--format=csv,noheader,nounits",
                ],
                timeout=10,
                stderr=subprocess.DEVNULL,
            ).decode()
            for line in raw.strip().splitlines():
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 3:
                    name = parts[0]
                    vram_total_mb = float(parts[1])
                    gpus.append({
                        "name": name,
                        "vram_gb": round(vram_total_mb / 1024, 1),
                        "type": "cuda",
                    })
        except Exception:
            pass

    # --- AMD ROCm: rocm-smi ----------------------------------------------
    if shutil.which("rocm-smi"):
        try:
            raw = subprocess.check_output(
                ["rocm-smi", "--showproductname", "--showmeminfo", "vram", "--json"],
                timeout=10,
                stderr=subprocess.DEVNULL,
            ).decode()
            data = json.loads(raw)
            for _card_id, card_info in data.items():
                if isinstance(card_info, dict):
                    name = card_info.get("Card Series", card_info.get("Card series", "AMD GPU"))
                    vram_bytes = int(card_info.get("VRAM Total Memory (B)", 0))
                    gpus.append({
                        "name": name,
                        "vram_gb": round(vram_bytes / (1024 ** 3), 1) if vram_bytes else 0,
                        "type": "rocm",
                    })
        except Exception:
            pass

    if not gpus:
        gpus.append({"name": "none detected", "vram_gb": 0, "type": "unknown"})

    return gpus


def _parse_vram(vram_str: str) -> float:
    """Parse a VRAM string like '36 GB' or '8192 MB' into GB."""
    if not isinstance(vram_str, str):
        return 0.0
    try:
        parts = vram_str.strip().split()
        value = float(parts[0])
        unit = parts[1].upper() if len(parts) > 1 else "MB"
        if unit == "GB":
            return round(value, 1)
        elif unit == "MB":
            return round(value / 1024, 1)
        elif unit == "TB":
            return round(value * 1024, 1)
        return round(value / 1024, 1)  # assume MB
    except Exception:
        return 0.0


# ---------------------------------------------------------------------------
# Disk
# ---------------------------------------------------------------------------

def _detect_disk() -> dict[str, Any]:
    info: dict[str, Any] = {"free_gb": 0.0}
    target = Path.home() / ".specific-labs"
    try:
        target.mkdir(parents=True, exist_ok=True)
        usage = shutil.disk_usage(str(target))
        info["free_gb"] = round(usage.free / (1024 ** 3), 1)
    except Exception:
        # Fallback to home dir
        try:
            usage = shutil.disk_usage(str(Path.home()))
            info["free_gb"] = round(usage.free / (1024 ** 3), 1)
        except Exception:
            pass
    return info


# ---------------------------------------------------------------------------
# ML Accelerators
# ---------------------------------------------------------------------------

def _detect_accelerators() -> dict[str, bool]:
    accel: dict[str, bool] = {
        "mlx": False,
        "cuda": False,
        "mps": False,
        "coreml": False,
    }

    # MLX
    try:
        result = subprocess.run(
            ["python3", "-c", "import mlx.core; print('ok')"],
            capture_output=True, timeout=10, text=True,
        )
        accel["mlx"] = result.returncode == 0 and "ok" in result.stdout
    except Exception:
        pass

    # CUDA (via torch)
    try:
        result = subprocess.run(
            ["python3", "-c", "import torch; print(torch.cuda.is_available())"],
            capture_output=True, timeout=10, text=True,
        )
        accel["cuda"] = result.returncode == 0 and "True" in result.stdout
    except Exception:
        pass

    # MPS (Apple Metal via torch)
    try:
        result = subprocess.run(
            ["python3", "-c", "import torch; print(torch.backends.mps.is_available())"],
            capture_output=True, timeout=10, text=True,
        )
        accel["mps"] = result.returncode == 0 and "True" in result.stdout
    except Exception:
        pass

    # CoreML
    try:
        result = subprocess.run(
            ["python3", "-c", "import coremltools; print('ok')"],
            capture_output=True, timeout=10, text=True,
        )
        accel["coreml"] = result.returncode == 0 and "ok" in result.stdout
    except Exception:
        pass

    return accel
