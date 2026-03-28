"""Blueprint API — ML Experiment Workbench server."""
from __future__ import annotations

import atexit
import logging
import os
import sys
import threading
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from .config import BLOCKS_DIR, BUILTIN_BLOCKS_DIR, CUSTOM_BLOCKS_DIR, ENABLE_MARKETPLACE, ensure_dirs
from .database import SessionLocal, init_db
from .services.registry import BlockRegistryService, set_global_registry
from .services.capability_detector import CapabilityDetector, set_capability_detector
from .services.process_manager import ProcessManager, set_process_manager
from .models.run import LiveRun, Run
from .routers import (
    artifacts, block_generator, blocks, connectors, control_tower, copilot,
    custom_blocks, dashboard, datasets, events, execution, inference, marketplace,
    models, model_registry, outputs, papers, pipelines, pipeline_versions, plugins,
    presets, projects, registry, replay, runs, secrets, sweeps, system, templates,
    workspace,
)
from .utils.structured_logger import init_structured_logging, log_event, log_recovery

_recovery_logger = logging.getLogger("blueprint.recovery")

# Configurable heartbeat timeout (seconds). Default: 5 minutes.
HEARTBEAT_TIMEOUT = int(os.environ.get("BLUEPRINT_HEARTBEAT_TIMEOUT", "300"))

# Periodic recovery check interval (seconds). Default: 2 minutes.
RECOVERY_CHECK_INTERVAL = int(os.environ.get("BLUEPRINT_RECOVERY_INTERVAL", "120"))

_recovery_stop = threading.Event()


def _recover_stale_runs():
    """Find running runs with stale heartbeats and mark them as failed."""
    session = SessionLocal()
    try:
        stale_cutoff = datetime.now(timezone.utc) - timedelta(seconds=HEARTBEAT_TIMEOUT)
        stale_runs = session.query(Run).filter(Run.status == "running").all()
        recovered_ids = []
        for stale_run in stale_runs:
            if stale_run.last_heartbeat is None or stale_run.last_heartbeat < stale_cutoff:
                original_status = stale_run.status
                stale_run.status = "failed"
                stale_run.error_message = "Recovered: process terminated unexpectedly"
                stale_run.finished_at = datetime.now(timezone.utc)
                # Also update live run
                live = session.query(LiveRun).filter(LiveRun.run_id == stale_run.id).first()
                if live:
                    live.status = "failed"
                log_recovery(stale_run.id, original_status)
                recovered_ids.append(stale_run.id)
        if recovered_ids:
            session.commit()
            _recovery_logger.info("Recovered %d stale run(s)", len(recovered_ids))
            # Notify connected frontends via SSE
            try:
                from .routers.events import publish_event
                for run_id in recovered_ids:
                    publish_event(run_id, "run_failed", {
                        "run_id": run_id,
                        "error": "Recovered: process terminated unexpectedly",
                    })
            except Exception:
                pass  # SSE notification is best-effort
    except Exception as e:
        try:
            session.rollback()
        except Exception:
            pass
        _recovery_logger.warning("Stale run recovery failed: %s", e)
    finally:
        session.close()


def _periodic_recovery_loop():
    """Background thread that checks for stale runs every RECOVERY_CHECK_INTERVAL seconds.

    Also performs periodic decision log cleanup (daily cadence — runs when the
    interval counter aligns, not on every check).
    """
    _cycle_count = 0
    # Run decision cleanup roughly once per hour (RECOVERY_CHECK_INTERVAL is 120s,
    # so every 30 cycles ≈ 3600s = 1 hour).
    _DECISION_CLEANUP_CYCLES = max(1, 3600 // RECOVERY_CHECK_INTERVAL)

    while not _recovery_stop.is_set():
        _recovery_stop.wait(RECOVERY_CHECK_INTERVAL)
        if _recovery_stop.is_set():
            break
        _cycle_count += 1

        try:
            _recover_stale_runs()
        except Exception as e:
            _recovery_logger.warning("Periodic recovery check failed: %s", e)

        # Decision log cleanup — hourly cadence
        if _cycle_count % _DECISION_CLEANUP_CYCLES == 0:
            try:
                from .services.decision_cleanup import cleanup_old_decisions
                result = cleanup_old_decisions()
                if result.get("deleted", 0) > 0:
                    _recovery_logger.info(
                        "Decision cleanup: deleted %d records", result["deleted"],
                    )
            except Exception as e:
                _recovery_logger.debug("Decision cleanup skipped: %s", e)


_shutdown_once = threading.Event()


def _full_shutdown():
    """Centralized shutdown sequence. Idempotent — safe to call multiple times.

    Runs from:
      1. FastAPI lifespan exit (normal shutdown via SIGTERM/SIGINT)
      2. atexit handler (fallback for hard crashes, SIGKILL of parent, etc.)
    """
    if _shutdown_once.is_set():
        return  # Already ran
    _shutdown_once.set()

    _shutdown_logger = logging.getLogger("blueprint.shutdown")
    _shutdown_logger.info("Beginning full shutdown sequence...")

    log_event("server_stop", message="Blueprint server shutting down")
    _recovery_stop.set()

    # 0. Terminate all tracked worker subprocesses
    try:
        from .engine.worker_tracker import terminate_all_workers, write_pid_manifest
        from .config import BASE_DIR
        terminated = terminate_all_workers()
        if terminated:
            _shutdown_logger.info("Terminated %d worker subprocess(es)", terminated)
    except Exception:
        pass

    # 1. Pipeline executor (bounded timeout)
    try:
        from .routers.execution import shutdown_executor
        shutdown_executor()
    except Exception:
        pass

    # 2. Sequential pipeline sequences
    try:
        from .routers.dashboard import shutdown_sequences
        shutdown_sequences()
    except Exception:
        pass

    # 3. Sweep executor
    try:
        from .routers.sweeps import shutdown_sweep_executor
        shutdown_sweep_executor()
    except Exception:
        pass

    # 4. Kill spawned inference servers (Ollama, mlx_lm.server)
    try:
        from .routers.inference import shutdown_spawned_servers
        shutdown_spawned_servers()
    except Exception:
        pass

    # 3b. Kill processes tracked by ProcessManager (start-service, etc.)
    try:
        from .services.process_manager import get_process_manager
        get_process_manager().shutdown()
    except Exception:
        pass

    # 5. Model watcher
    try:
        from .utils.model_watcher import stop_watcher
        stop_watcher()
    except Exception:
        pass

    # 6. Inbox watcher
    try:
        from .services.inbox_watcher import stop_watcher as stop_inbox_watcher
        stop_inbox_watcher()
    except Exception:
        pass

    _shutdown_logger.info("Shutdown sequence complete.")


# Register atexit fallback so _full_shutdown runs even if the lifespan
# context is never properly exited (e.g. the process is killed, uvicorn
# crashes, or the Python interpreter is tearing down).
atexit.register(_full_shutdown)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    ensure_dirs()
    init_db()
    init_structured_logging()
    log_event("server_start", message="Blueprint server starting",
              data={"heartbeat_timeout_s": HEARTBEAT_TIMEOUT})

    # Initialize block registry (single source of truth for block discovery)
    registry = BlockRegistryService()
    registry.discover_all([BUILTIN_BLOCKS_DIR, BLOCKS_DIR, CUSTOM_BLOCKS_DIR])
    app.state.registry = registry
    set_global_registry(registry)

    # Initialize template service with registry for block validation
    from .services.templates import TemplateService, set_template_service
    tpl_svc = TemplateService(registry=registry)
    set_template_service(tpl_svc)

    health = registry.get_health()
    logging.getLogger("blueprint.registry").info(
        "Block registry ready: %d total, %d valid, %d broken",
        health["total"], health["valid"], health["broken"],
    )

    # Initialize capability detector (Phase 1: import checks + GPU, Phase 2: network probes in background)
    cap_detector = CapabilityDetector()
    app.state.capability_detector = cap_detector
    set_capability_detector(cap_detector)
    cap_report = cap_detector.detect()  # Phase 1 is synchronous (<50ms), Phase 2 runs in background
    logging.getLogger("blueprint.capabilities").info(
        "Capability detector Phase 1 ready: profile=%s (network probes running in background)",
        cap_report["installed_profile"],
    )

    # Initialize process manager (tracks spawned child processes for clean shutdown)
    proc_mgr = ProcessManager()
    app.state.process_manager = proc_mgr
    set_process_manager(proc_mgr)

    # Recover stale runs and orphaned sequences from previous crash
    _recover_stale_runs()
    try:
        from .routers.dashboard import recover_orphaned_sequences
        recover_orphaned_sequences()
    except Exception as e:
        logging.getLogger("blueprint.recovery").warning("Sequence recovery failed: %s", e)

    # Recover runs stuck in running/pending from hard crashes (subprocess-aware)
    try:
        from .engine.worker_tracker import recover_stale_runs_on_startup, write_pid_manifest
        from .config import BASE_DIR
        crashed_ids = recover_stale_runs_on_startup(SessionLocal)
        if crashed_ids:
            logging.getLogger("blueprint.recovery").info(
                "Recovered %d crashed run(s) on startup: %s",
                len(crashed_ids), crashed_ids,
            )
        # Write initial PID manifest for orphan detection
        write_pid_manifest(BASE_DIR)
    except Exception as exc:
        logging.getLogger("blueprint.recovery").warning(
            "Worker recovery on startup failed: %s", exc
        )

    # Clean up old execution decisions on startup
    try:
        from .services.decision_cleanup import cleanup_old_decisions
        cleanup_old_decisions()
    except Exception:
        pass  # Non-critical — cleanup will run periodically

    # Start periodic stale-run recovery thread
    _recovery_stop.clear()
    recovery_thread = threading.Thread(target=_periodic_recovery_loop, daemon=True)
    recovery_thread.start()

    # Load plugins (non-critical — individual plugin errors are isolated)
    from .plugins.registry import plugin_registry
    try:
        plugin_registry.load_all()
    except Exception as e:
        logging.getLogger("blueprint.plugins").error("Plugin system init failed: %s", e)

    # Seed marketplace registry with built-in items (if enabled)
    if ENABLE_MARKETPLACE:
        try:
            from .services.marketplace_service import seed_registry
            seed_registry()
        except Exception as e:
            logging.getLogger("blueprint.marketplace").error("Marketplace seed failed: %s", e)

    # Start background model directory watcher
    try:
        from .utils.model_watcher import start_watcher
        _logger = logging.getLogger(__name__)
        start_watcher(
            on_change=lambda models: _logger.info("Model watcher: %d models detected", len(models)),
            poll_interval=30.0,
        )
    except Exception:
        pass  # Non-critical — watcher is a convenience feature

    # Start inbox watcher if workspace is configured
    try:
        from .services.inbox_watcher import start_watcher as start_inbox_watcher
        _ws_session = SessionLocal()
        try:
            from .models.workspace import WorkspaceSettings as WS
            ws = _ws_session.query(WS).filter_by(id="default").first()
            if ws and ws.root_path and ws.watcher_enabled:
                start_inbox_watcher(ws.root_path)
                logging.getLogger(__name__).info("Inbox watcher started: %s", ws.root_path)
        finally:
            _ws_session.close()
    except Exception:
        pass  # Non-critical
    yield
    # Shutdown
    _full_shutdown()


app = FastAPI(
    lifespan=lifespan,
    title="Blueprint API",
    description="Specific Labs Blueprint — ML Experiment Workbench",
    version="0.2.2",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get(
        "CORS_ORIGINS",
        "http://localhost:5173,http://localhost:3000,http://localhost:4174,"
        "http://127.0.0.1:5173,http://127.0.0.1:4174",
    ).split(","),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "Accept", "X-Requested-With"],
)

# Mount routers
app.include_router(projects.router)
app.include_router(dashboard.router)
app.include_router(pipelines.router)
app.include_router(runs.router)
app.include_router(datasets.router)
app.include_router(blocks.router)
app.include_router(events.router)
app.include_router(execution.router)
app.include_router(control_tower.router)
app.include_router(system.router)
app.include_router(models.router)
app.include_router(papers.router)
app.include_router(secrets.router)
app.include_router(custom_blocks.router)
app.include_router(inference.router)
app.include_router(plugins.router)
app.include_router(sweeps.router)
app.include_router(connectors.router)
app.include_router(block_generator.router)
app.include_router(outputs.router)
app.include_router(workspace.router)
app.include_router(artifacts.router)
app.include_router(copilot.router)
app.include_router(registry.router)
app.include_router(dashboard.router)
app.include_router(pipeline_versions.router)
app.include_router(model_registry.router)
app.include_router(replay.router)
app.include_router(presets.router)
app.include_router(templates.router)
if ENABLE_MARKETPLACE:
    app.include_router(marketplace.router)


def get_registry(request: Request) -> BlockRegistryService:
    """FastAPI dependency — retrieve the singleton BlockRegistryService."""
    return request.app.state.registry


@app.get("/api/health")
def health():
    try:
        session = SessionLocal()
        session.execute(text("SELECT 1"))
        session.close()
        return {"status": "ok", "service": "blueprint", "db": "connected"}
    except Exception as e:
        return JSONResponse(
            status_code=503,
            content={"status": "degraded", "service": "blueprint", "db": str(e)},
        )


# ── Serve Frontend SPA ──────────────────────────────────────────────

_spa_logger = logging.getLogger("blueprint.spa")


def get_frontend_path() -> Path | None:
    """Resolve the frontend dist folder across all deployment modes."""
    candidates: list[tuple[str, Path]] = []

    # 0. Explicit path from Electron or env override (highest priority)
    env_dist = os.environ.get("BLUEPRINT_FRONTEND_DIST")
    if env_dist:
        candidates.append(("env", Path(env_dist)))

    # 1. Dev: 'frontend/dist' relative to the backend package directory
    dev_path = Path(__file__).resolve().parent.parent / "frontend" / "dist"
    candidates.append(("dev", dev_path))

    if getattr(sys, "frozen", False):
        meipass = Path(getattr(sys, "_MEIPASS", ""))
        exe_dir = Path(sys.executable).parent

        # 2. PyInstaller bundle: frontend bundled inside _MEIPASS
        candidates.append(("meipass", meipass / "frontend" / "dist"))

        # 3. Electron App Bundle: Contents/Resources/app/dist
        candidates.append(("electron", exe_dir / "app" / "dist"))

        # 4. Fallback: dist/ next to the executable (standalone test)
        candidates.append(("sibling", exe_dir / "dist"))

    for label, path in candidates:
        index_html = path / "index.html"
        _spa_logger.debug("SPA probe [%s]: %s  exists=%s", label, path, index_html.exists())
        if index_html.is_file():
            _spa_logger.info("SPA resolved via [%s]: %s", label, path)
            return path

    _spa_logger.warning("SPA dist folder not found. Tried: %s", [str(c[1]) for c in candidates])
    return None


frontend_path = get_frontend_path()

if frontend_path:
    assets_dir = frontend_path / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    _index_html = str(frontend_path / "index.html")

    @app.get("/")
    def serve_root():
        """Serve index.html for the root path."""
        return FileResponse(_index_html)

    @app.get("/{catchall:path}")
    def serve_spa(catchall: str):
        """SPA catch-all: serve the requested file or fall back to index.html."""
        requested = frontend_path / catchall
        if requested.is_file():
            return FileResponse(str(requested))
        return FileResponse(_index_html)
else:
    @app.get("/")
    def no_frontend():
        return {"error": "Frontend dist folder not found."}

    @app.get("/{catchall:path}")
    def no_frontend_catchall(catchall: str):
        return {"error": "Frontend dist folder not found."}
