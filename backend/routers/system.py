"""System information endpoints — hardware profile, capability detection,
benchmark data, and parallel scheduling."""

from __future__ import annotations

import ast
import importlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Query
from fastapi.responses import PlainTextResponse

from ..config import BASE_DIR, BUILTIN_BLOCKS_DIR, BLOCKS_DIR, ARTIFACTS_DIR

SAFE_MODEL_ID = re.compile(r'^[a-zA-Z0-9_\-./]+$')

try:
    import psutil
    _HAS_PSUTIL = True
except ImportError:
    _HAS_PSUTIL = False

from ..utils.hardware import get_hardware_profile
from ..utils.benchmarks import get_benchmarks, search_benchmarks, refresh_cache
from ..engine.parallelizer import build_schedule, explain_schedule
from ..schemas.system import (
    FeatureFlagsResponse,
    SystemMetricsResponse,
    CapabilitiesResponse,
    BenchmarkRefreshResponse,
    ScheduleResponse,
    DependencyCheckResponse,
    InstallResponse,
    DiagnosticsResponse,
    HealthResponse,
)

router = APIRouter(prefix="/api/system", tags=["system"])


# ---------------------------------------------------------------------------
# Feature Flags
# ---------------------------------------------------------------------------


@router.get("/features", response_model=FeatureFlagsResponse)
def get_feature_flags():
    """Return which optional features are enabled."""
    from ..config import ENABLE_MARKETPLACE
    return {
        "marketplace": ENABLE_MARKETPLACE,
    }


# ---------------------------------------------------------------------------
# Model Discovery
# ---------------------------------------------------------------------------


@router.get("/models")
def available_models():
    """Return discovered frameworks and their locally available models.

    Results are cached for 30 seconds to avoid repeated filesystem scanning.
    """
    from ..services.model_discovery import discover_frameworks

    return discover_frameworks()


@router.get("/hardware")
def hardware():
    """Return the full hardware profile of the host machine."""
    return get_hardware_profile()


@router.get("/metrics", response_model=SystemMetricsResponse)
def system_metrics():
    """Lightweight, non-blocking CPU/memory snapshot for output view polling."""
    if _HAS_PSUTIL:
        cpu = psutil.cpu_percent(interval=None)  # non-blocking (returns cached value)
        mem = psutil.virtual_memory()
        return {
            "cpu_percent": cpu,
            "memory_percent": mem.percent,
            "memory_gb": round(mem.used / (1024 ** 3), 1),
            "memory_total_gb": round(mem.total / (1024 ** 3), 1),
            "gpu_percent": None,
        }
    return {
        "cpu_percent": 0,
        "memory_percent": 0,
        "memory_gb": 0,
        "memory_total_gb": 0,
        "gpu_percent": None,
    }


@router.get("/metrics/prometheus")
def prometheus_metrics():
    """Expose system metrics in Prometheus text exposition format.

    This endpoint returns metrics compatible with Prometheus scraping.
    Configure your Prometheus instance to scrape /api/system/metrics/prometheus.
    """
    lines: list[str] = []

    if _HAS_PSUTIL:
        cpu = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory()
        lines.append("# HELP blueprint_cpu_percent CPU usage percentage")
        lines.append("# TYPE blueprint_cpu_percent gauge")
        lines.append(f"blueprint_cpu_percent {cpu}")
        lines.append("# HELP blueprint_memory_used_bytes Memory used in bytes")
        lines.append("# TYPE blueprint_memory_used_bytes gauge")
        lines.append(f"blueprint_memory_used_bytes {mem.used}")
        lines.append("# HELP blueprint_memory_total_bytes Total memory in bytes")
        lines.append("# TYPE blueprint_memory_total_bytes gauge")
        lines.append(f"blueprint_memory_total_bytes {mem.total}")
        lines.append("# HELP blueprint_memory_percent Memory usage percentage")
        lines.append("# TYPE blueprint_memory_percent gauge")
        lines.append(f"blueprint_memory_percent {mem.percent}")

        # Disk
        disk = psutil.disk_usage("/")
        lines.append("# HELP blueprint_disk_used_bytes Disk used in bytes")
        lines.append("# TYPE blueprint_disk_used_bytes gauge")
        lines.append(f"blueprint_disk_used_bytes {disk.used}")
        lines.append("# HELP blueprint_disk_total_bytes Total disk in bytes")
        lines.append("# TYPE blueprint_disk_total_bytes gauge")
        lines.append(f"blueprint_disk_total_bytes {disk.total}")

        # Per-CPU
        per_cpu = psutil.cpu_percent(interval=None, percpu=True)
        lines.append("# HELP blueprint_cpu_core_percent Per-core CPU usage")
        lines.append("# TYPE blueprint_cpu_core_percent gauge")
        for i, pct in enumerate(per_cpu):
            lines.append(f'blueprint_cpu_core_percent{{core="{i}"}} {pct}')

    # Active runs count (if available)
    try:
        from ..routers.events import _run_queues
        active_runs = len(_run_queues)
        lines.append("# HELP blueprint_active_runs Number of runs with active SSE streams")
        lines.append("# TYPE blueprint_active_runs gauge")
        lines.append(f"blueprint_active_runs {active_runs}")
    except Exception:
        pass

    return PlainTextResponse("\n".join(lines) + "\n", media_type="text/plain; version=0.0.4")


@router.get("/capabilities", response_model=CapabilitiesResponse)
def capabilities():
    """Derive high-level ML capabilities from the hardware profile.

    Returns a dict indicating what the current machine can reasonably do
    (e.g. run local LLMs, fine-tune, use GPU acceleration, etc.).
    """
    profile = get_hardware_profile()

    ram_gb = profile.get("ram", {}).get("total_gb", 0)
    gpus = profile.get("gpu", [])
    accel = profile.get("accelerators", {})
    disk_free = profile.get("disk", {}).get("free_gb", 0)

    # Best available GPU VRAM
    max_vram = max((g.get("vram_gb", 0) for g in gpus), default=0)

    # GPU backend
    has_gpu = any(g.get("type") in ("metal", "cuda", "rocm") for g in gpus)
    gpu_backend = "none"
    for g in gpus:
        if g.get("type") in ("metal", "cuda", "rocm"):
            gpu_backend = g["type"]
            break

    # What size models can we run?
    # Rough heuristic: model needs ~1.2x its parameter-count in GB of VRAM/RAM
    usable_memory = max(max_vram, ram_gb * 0.7)  # if unified memory, use RAM

    if usable_memory >= 48:
        max_model_size = "70b"
    elif usable_memory >= 24:
        max_model_size = "34b"
    elif usable_memory >= 14:
        max_model_size = "13b"
    elif usable_memory >= 6:
        max_model_size = "7b"
    elif usable_memory >= 3:
        max_model_size = "3b"
    else:
        max_model_size = "1b"

    return CapabilitiesResponse(
        gpu_available=has_gpu,
        gpu_backend=gpu_backend,
        max_vram_gb=max_vram,
        usable_memory_gb=round(usable_memory, 1),
        max_model_size=max_model_size,
        can_fine_tune=has_gpu and usable_memory >= 8,
        can_run_local_llm=usable_memory >= 4,
        disk_ok=disk_free >= 10,
        accelerators=accel,
    )


@router.get("/capabilities/detailed")
def detailed_capabilities():
    """Return detailed capability detection including per-library availability.

    Uses the CapabilityDetector singleton for comprehensive checks including
    torch, transformers, peft, ollama, GPU, and installed profile detection.
    """
    from ..services.capability_detector import get_capability_detector
    detector = get_capability_detector()
    return detector.detect()


@router.post("/capabilities/refresh")
def refresh_capabilities():
    """Force re-detection of all capabilities (e.g. after pip install)."""
    from ..services.capability_detector import get_capability_detector
    detector = get_capability_detector()
    return detector.refresh()


# ---------------------------------------------------------------------------
# One-click recovery: start services
# ---------------------------------------------------------------------------

_SERVICE_COMMANDS: dict[str, list[str]] = {
    "ollama": ["ollama", "serve"],
}


@router.post("/start-service/{name}")
def start_service(name: str):
    """Start a known service by name (e.g. 'ollama').

    Launches the service as a tracked background subprocess that will be
    cleaned up during server shutdown.  Returns immediately — the service
    may still be booting.
    """
    if name not in _SERVICE_COMMANDS:
        raise HTTPException(404, f"Unknown service: {name}. Available: {list(_SERVICE_COMMANDS.keys())}")

    cmd = _SERVICE_COMMANDS[name]
    try:
        # Check if already running externally (not spawned by us)
        if name == "ollama":
            from ..services.capability_detector import _check_ollama
            if _check_ollama():
                return {"status": "already_running", "service": name}

        from ..services.process_manager import get_process_manager
        mgr = get_process_manager()

        # ProcessManager handles dedup (returns existing if alive)
        tracked = mgr.start(name, cmd)
        return {
            "status": "started",
            "service": name,
            "pid": tracked.pid,
            "command": " ".join(cmd),
        }
    except FileNotFoundError:
        raise HTTPException(
            422,
            f"Service binary not found: {cmd[0]}. Install {name} first.",
        )
    except Exception as e:
        raise HTTPException(500, f"Failed to start {name}: {e}")


@router.post("/stop-service/{name}")
def stop_service(name: str):
    """Stop a previously started service by name."""
    from ..services.process_manager import get_process_manager
    mgr = get_process_manager()
    if mgr.stop(name):
        return {"status": "stopped", "service": name}
    raise HTTPException(404, f"No tracked process named '{name}'")


@router.get("/services")
def list_services():
    """Return status of all tracked background services."""
    from ..services.process_manager import get_process_manager
    mgr = get_process_manager()
    return {"services": [tp.to_dict() for tp in mgr.list_all()]}


# ---------------------------------------------------------------------------
# Health (status bar polling)
# ---------------------------------------------------------------------------

# ── Background Ollama connectivity checker ────────────────────────────
#
# Probing Ollama synchronously on every /health poll (every 5s from every
# connected frontend) would block the endpoint for up to 1s per request
# when Ollama is down or slow. Instead, a single daemon thread checks
# connectivity every 10s and caches the boolean result. The health
# endpoint reads the cached value with zero latency.

import threading as _health_threading
import time as _health_time

_ollama_lock = _health_threading.Lock()
_ollama_connected: bool = False
_ollama_last_check: float = 0.0
_ollama_checker_started: bool = False
_OLLAMA_CHECK_INTERVAL = 10.0  # seconds between probes


def _probe_ollama() -> bool:
    """Non-blocking probe: try to reach the Ollama API tags endpoint."""
    try:
        import urllib.request
        req = urllib.request.Request(
            "http://127.0.0.1:11434/api/tags", method="GET"
        )
        with urllib.request.urlopen(req, timeout=2) as resp:
            return resp.status == 200
    except Exception:
        return False


def _ollama_check_loop():
    """Background loop that probes Ollama and caches the result.

    Runs as a daemon thread — automatically dies when the main process exits.
    Uses a shorter interval (3s) right after startup or when Ollama is down,
    to detect recovery quickly. Falls back to the standard interval when
    connected, to minimize overhead.
    """
    global _ollama_connected, _ollama_last_check

    while True:
        connected = _probe_ollama()
        with _ollama_lock:
            _ollama_connected = connected
            _ollama_last_check = _health_time.monotonic()

        # Poll faster when disconnected (detect recovery sooner)
        interval = _OLLAMA_CHECK_INTERVAL if connected else 3.0
        _health_time.sleep(interval)


def _ensure_ollama_checker():
    """Lazily start the background checker on first health request.

    Lazy startup avoids spawning a thread during module import (which
    would be surprising in test environments or CLI tools that import
    but never serve).
    """
    global _ollama_checker_started
    if _ollama_checker_started:
        return
    with _ollama_lock:
        if _ollama_checker_started:
            return  # double-check under lock
        _ollama_checker_started = True
        t = _health_threading.Thread(target=_ollama_check_loop, daemon=True)
        t.start()


def _get_ollama_status() -> bool:
    """Read the cached Ollama connectivity status (zero-latency)."""
    _ensure_ollama_checker()
    with _ollama_lock:
        return _ollama_connected


@router.get("/health", response_model=HealthResponse)
def health():
    """Aggregated health snapshot for the frontend status bar.

    Polled every ~5 seconds. Non-blocking, best-effort for all fields.
    Ollama status comes from a background thread (zero latency).
    """
    import shutil

    cpu = 0.0
    mem_pct = 0.0
    mem_total_gb = 0.0
    gpu_pct: float | None = None
    gpu_name: str | None = None

    if _HAS_PSUTIL:
        cpu = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory()
        mem_pct = mem.percent
        mem_total_gb = round(mem.total / (1024 ** 3), 1)

    # Disk free space
    disk_free_gb = 0.0
    try:
        usage = shutil.disk_usage("/")
        disk_free_gb = round(usage.free / (1024 ** 3), 1)
    except Exception:
        pass

    # GPU info (best-effort)
    try:
        profile = get_hardware_profile()
        gpus = profile.get("gpu", [])
        for g in gpus:
            if g.get("type") in ("metal", "cuda", "rocm"):
                gpu_name = g.get("name")
                gpu_pct = g.get("utilization")
                break
    except Exception:
        pass

    # Active runs count
    active_runs = 0
    queued_runs = 0
    try:
        from ..routers.events import _run_queues
        active_runs = len(_run_queues)
    except Exception:
        pass

    return HealthResponse(
        cpu_percent=cpu,
        memory_percent=mem_pct,
        memory_total_gb=mem_total_gb,
        gpu_percent=gpu_pct,
        gpu_name=gpu_name,
        disk_free_gb=disk_free_gb,
        ollama_connected=_get_ollama_status(),
        active_runs=active_runs,
        queued_runs=queued_runs,
    )


# ---------------------------------------------------------------------------
# Benchmarks
# ---------------------------------------------------------------------------


@router.get("/benchmarks/{model_id:path}")
def model_benchmarks(model_id: str):
    """Return benchmark scores for a specific model."""
    if not SAFE_MODEL_ID.match(model_id):
        raise HTTPException(400, "Invalid model ID")
    result = get_benchmarks(model_id)
    if result is None:
        return {"model_id": model_id, "scores": {}, "source": "not_found"}
    return result.to_dict()


@router.get("/benchmarks")
def benchmark_search(
    q: str = Query("", description="Model name substring"),
    limit: int = Query(20, ge=1, le=100),
):
    """Search benchmark results by model name."""
    results = search_benchmarks(q, limit=limit)
    return [r.to_dict() for r in results]


@router.post("/benchmarks/refresh", response_model=BenchmarkRefreshResponse)
def benchmark_refresh():
    """Force-refresh the benchmark cache from the HuggingFace leaderboard."""
    count = refresh_cache(force=True)
    return {"status": "refreshed", "entries": count}


# ---------------------------------------------------------------------------
# Parallel scheduler
# ---------------------------------------------------------------------------


@router.post("/schedule", response_model=ScheduleResponse)
def compute_schedule(
    payload: dict[str, Any] = Body(..., description="Pipeline definition with nodes and edges"),
):
    """Compute a resource-aware parallel execution schedule for a pipeline.

    Expects ``{ "nodes": [...], "edges": [...] }`` in the request body.
    Returns the list of execution stages with human-readable labels.
    """
    nodes = payload.get("nodes", [])
    edges = payload.get("edges", [])
    hw_profile = get_hardware_profile()
    schedule = build_schedule(nodes, edges, hw_profile)
    return {
        "stages": explain_schedule(schedule, nodes),
        "total_stages": len(schedule),
        "max_parallelism": max((len(s) for s in schedule), default=0),
    }


# ---------------------------------------------------------------------------
# Dependency Health Check
# ---------------------------------------------------------------------------

# Package -> pip install name (when they differ)
_INSTALL_MAP = {
    'sklearn': 'scikit-learn',
    'cv2': 'opencv-python',
    'yaml': 'pyyaml',
    'PIL': 'Pillow',
    'bs4': 'beautifulsoup4',
    'attr': 'attrs',
    'dotenv': 'python-dotenv',
}

# Standard library modules to exclude
_STDLIB_MODULES = {
    'os', 'sys', 'json', 'math', 'time', 're', 'io', 'csv', 'copy',
    'pathlib', 'typing', 'collections', 'itertools', 'functools',
    'dataclasses', 'abc', 'enum', 'datetime', 'logging', 'hashlib',
    'base64', 'uuid', 'shutil', 'tempfile', 'subprocess', 'threading',
    'multiprocessing', 'socket', 'http', 'urllib', 'email', 'html',
    'xml', 'sqlite3', 'argparse', 'textwrap', 'string', 'struct',
    'pickle', 'gzip', 'zipfile', 'tarfile', 'glob', 'fnmatch',
    'signal', 'contextlib', 'warnings', 'traceback', 'inspect',
    'importlib', 'pkgutil', 'operator', 'statistics', 'random',
    'secrets', 'heapq', 'bisect', 'array', 'queue', 'weakref',
    'types', 'pprint', 'platform', 'ast', 'dis', 'code', 'codecs',
    'locale', 'gettext', 'unicodedata', 'difflib', 'readline',
    'rlcompleter', 'pdb', 'profile', 'timeit', 'unittest', 'doctest',
    'numbers', 'decimal', 'fractions', 'cmath', 'configparser',
}


def _extract_imports(run_py: Path) -> list[str]:
    """Parse top-level imports from a run.py file using AST."""
    try:
        tree = ast.parse(run_py.read_text())
    except Exception:
        return []
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name.split('.')[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                modules.add(node.module.split('.')[0])
    return sorted(modules)


def _scan_all_block_deps() -> dict[str, list[str]]:
    """Walk all block directories, parse imports from run.py files."""
    result: dict[str, list[str]] = {}
    for base_dir in [BUILTIN_BLOCKS_DIR, BLOCKS_DIR]:
        if not base_dir.exists():
            continue
        for run_py in base_dir.rglob('run.py'):
            block_type = run_py.parent.name
            imports = _extract_imports(run_py)
            third_party = [m for m in imports if m not in _STDLIB_MODULES and m != 'backend']
            if third_party:
                result[block_type] = third_party
    return result


def _check_package(package: str) -> dict:
    """Check if a package is importable and get its version."""
    try:
        mod = importlib.import_module(package)
        version = getattr(mod, '__version__', 'installed')
        return {'package': package, 'installed': True, 'version': str(version)}
    except ImportError:
        return {'package': package, 'installed': False, 'version': None}


@router.get("/dependencies", response_model=DependencyCheckResponse)
def check_dependencies():
    """Return dependency status for all blocks."""
    block_deps = _scan_all_block_deps()

    # Check all unique packages once
    all_packages: set[str] = set()
    for deps in block_deps.values():
        all_packages.update(deps)

    package_status = {pkg: _check_package(pkg) for pkg in sorted(all_packages)}

    # Map back to blocks
    block_status: dict[str, dict] = {}
    for block_type, deps in block_deps.items():
        missing = [d for d in deps if not package_status.get(d, {}).get('installed', False)]
        block_status[block_type] = {
            'ready': len(missing) == 0,
            'total_deps': len(deps),
            'missing': missing,
            'install_command': f"pip install {' '.join(_INSTALL_MAP.get(m, m) for m in missing)}" if missing else None,
        }

    total_blocks = len(block_status)
    ready_blocks = sum(1 for b in block_status.values() if b['ready'])

    # Virtual environment detection
    in_venv = sys.prefix != sys.base_prefix

    return {
        'summary': {
            'total_blocks': total_blocks,
            'ready_blocks': ready_blocks,
            'missing_packages': [p for p, s in package_status.items() if not s['installed']],
            'in_virtual_env': in_venv,
        },
        'packages': package_status,
        'blocks': block_status,
    }


@router.post("/install", response_model=InstallResponse)
def install_packages(body: dict):
    """Install missing packages via pip. Only allows packages found in block dependencies."""
    packages = body.get('packages', [])
    if not packages:
        return {'error': 'No packages specified'}

    # Validate: only allow known packages from block deps
    block_deps = _scan_all_block_deps()
    allowed: set[str] = set()
    for deps in block_deps.values():
        allowed.update(deps)

    safe = [_INSTALL_MAP.get(p, p) for p in packages if p in allowed]
    if not safe:
        return {'success': False, 'error': 'No valid packages specified'}

    try:
        result = subprocess.run(
            [sys.executable, '-m', 'pip', 'install', *safe],
            capture_output=True, text=True, timeout=300,
        )
        return {
            'success': result.returncode == 0,
            'stdout': result.stdout[-2000:] if result.stdout else '',
            'stderr': result.stderr[-2000:] if result.stderr else '',
            'installed': safe,
        }
    except subprocess.TimeoutExpired:
        return {'success': False, 'error': 'Installation timed out after 5 minutes'}
    except Exception as e:
        return {'success': False, 'error': str(e)}


# ---------------------------------------------------------------------------
# File / Directory Browser (fallback for non-Electron environments)
# ---------------------------------------------------------------------------


@router.post("/browse")
def browse_filesystem(body: dict = Body(...)):
    """Open a native file or directory picker dialog.

    Used as a fallback when the Electron IPC bridge is not available
    (e.g. running the frontend via plain Vite in a browser).

    Body: { "mode": "file" | "directory", "title": "...", "default_path": "..." }
    Returns: { "path": "/selected/path" } or { "path": null } if cancelled.
    """
    import tkinter as tk
    from tkinter import filedialog

    mode = body.get("mode", "file")
    title = body.get("title", "Select File" if mode == "file" else "Select Folder")
    default_path = body.get("default_path", "")

    # Create a hidden root window
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)

    try:
        if mode == "directory":
            path = filedialog.askdirectory(title=title, initialdir=default_path or None)
        else:
            file_extensions = body.get("file_extensions", [])
            filetypes = []
            if file_extensions:
                ext_str = " ".join(f"*{ext}" for ext in file_extensions)
                filetypes.append(("Supported files", ext_str))
            filetypes.append(("All files", "*.*"))
            path = filedialog.askopenfilename(
                title=title,
                initialdir=default_path or None,
                filetypes=filetypes,
            )
    finally:
        root.destroy()

    return {"path": path if path else None}


# ---------------------------------------------------------------------------
# Run Diagnostics
# ---------------------------------------------------------------------------

SAFE_RUN_ID = re.compile(r'^[a-zA-Z0-9_\-]+$')

# Maximum events returned per diagnostics query to prevent unbounded memory use.
_MAX_DIAGNOSTICS_EVENTS = 5000


def _iter_log_files(log_dir: Path) -> list[Path]:
    """Return all structured log files in chronological order (oldest first).

    Includes rotated backups (blueprint.jsonl.1, .2, etc.) so that events
    from older rotations are not lost.
    """
    main_file = log_dir / "blueprint.jsonl"
    # Rotated files: blueprint.jsonl.1 (newest backup) ... blueprint.jsonl.5 (oldest)
    backups = sorted(
        log_dir.glob("blueprint.jsonl.[0-9]*"),
        key=lambda p: int(p.suffix.lstrip(".")),
        reverse=True,  # highest number = oldest, read oldest first
    )
    files = []
    for f in backups:
        if f.is_file():
            files.append(f)
    if main_file.is_file():
        files.append(main_file)
    return files


@router.get("/diagnostics/{run_id}", response_model=DiagnosticsResponse)
def get_run_diagnostics(run_id: str):
    """Parse structured logs for a specific run — shows timeline of events."""
    if not SAFE_RUN_ID.match(run_id):
        raise HTTPException(400, "Invalid run ID")

    log_dir = BASE_DIR / "logs"
    log_files = _iter_log_files(log_dir) if log_dir.is_dir() else []
    if not log_files:
        return {"events": [], "error": "No log file found"}

    events = []
    truncated = False
    for log_file in log_files:
        try:
            with open(log_file) as f:
                for line in f:
                    try:
                        entry = json.loads(line)
                        if entry.get("run_id") == run_id:
                            events.append(entry)
                            if len(events) >= _MAX_DIAGNOSTICS_EVENTS:
                                truncated = True
                                break
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        continue
        except OSError:
            continue  # File may have been rotated away between glob and open
        if truncated:
            break

    result = {
        "run_id": run_id,
        "events": events,
        "event_count": len(events),
    }
    if truncated:
        result["truncated"] = True
        result["max_events"] = _MAX_DIAGNOSTICS_EVENTS
    return result


# ---------------------------------------------------------------------------
# Help Documentation
# ---------------------------------------------------------------------------

# Resolve docs/help/ relative to the project root (two levels up from this file).
_HELP_DIR = Path(__file__).resolve().parent.parent.parent / "docs" / "help"

# Allow only alphanumeric chars, hyphens, and underscores in topic names.
_SAFE_TOPIC = re.compile(r'^[a-zA-Z0-9_\-]+$')


@router.get("/help/{topic}")
def get_help_topic(topic: str):
    """Return the markdown content for a help documentation topic."""
    if not _SAFE_TOPIC.match(topic):
        raise HTTPException(400, "Invalid topic name")

    help_file = (_HELP_DIR / f"{topic}.md").resolve()

    # Prevent directory traversal: resolved path must be inside _HELP_DIR.
    if not str(help_file).startswith(str(_HELP_DIR.resolve())):
        raise HTTPException(400, "Invalid topic path")

    if not help_file.is_file():
        raise HTTPException(404, f"Help topic '{topic}' not found")

    content = help_file.read_text(encoding="utf-8")
    return {"topic": topic, "content": content}
