import logging
import os
import threading
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .database import init_db, SessionLocal
from .config import ensure_dirs
from .models.run import Run, LiveRun
from .utils.structured_logger import (
    init_structured_logging, log_recovery, log_event,
)
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from .routers import projects, pipelines, runs, datasets, blocks, events, execution, control_tower, system, models, papers, secrets, custom_blocks, inference, plugins, sweeps

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
    """Background thread that checks for stale runs every RECOVERY_CHECK_INTERVAL seconds."""
    while not _recovery_stop.is_set():
        _recovery_stop.wait(RECOVERY_CHECK_INTERVAL)
        if _recovery_stop.is_set():
            break
        try:
            _recover_stale_runs()
        except Exception as e:
            _recovery_logger.warning("Periodic recovery check failed: %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    ensure_dirs()
    init_db()
    init_structured_logging()
    log_event("server_start", message="Blueprint server starting",
              data={"heartbeat_timeout_s": HEARTBEAT_TIMEOUT})

    # Recover stale runs from previous crash
    _recover_stale_runs()

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
    yield
    # Shutdown
    log_event("server_stop", message="Blueprint server shutting down")
    _recovery_stop.set()
    try:
        from .routers.execution import shutdown_executor
        shutdown_executor()
    except Exception:
        pass
    try:
        from .routers.sweeps import shutdown_sweep_executor
        shutdown_sweep_executor()
    except Exception:
        pass
    try:
        from .utils.model_watcher import stop_watcher
        stop_watcher()
    except Exception:
        pass


app = FastAPI(
    lifespan=lifespan,
    title="Blueprint API",
    description="Specific Labs Blueprint — ML Experiment Workbench",
    version="0.1.0",
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


@app.get("/api/health")
def health():
    from .database import SessionLocal
    from sqlalchemy import text
    from fastapi.responses import JSONResponse
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
import sys
import logging

_spa_logger = logging.getLogger("blueprint.spa")


def get_frontend_path() -> str | None:
    """Resolve the frontend dist folder across all deployment modes."""
    candidates: list[tuple[str, str]] = []

    # 1. Dev: 'frontend/dist' relative to the backend package directory
    dev_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "frontend", "dist",
    )
    candidates.append(("dev", dev_path))

    is_frozen = getattr(sys, "frozen", False)

    if is_frozen:
        meipass = getattr(sys, "_MEIPASS", "")
        exe_dir = os.path.dirname(sys.executable)

        # 2. PyInstaller bundle: frontend bundled inside _MEIPASS
        candidates.append(("meipass", os.path.join(meipass, "frontend", "dist")))

        # 3. Electron App Bundle: Contents/Resources/app/dist
        candidates.append(("electron", os.path.join(exe_dir, "app", "dist")))

        # 4. Fallback: dist/ next to the executable (standalone test)
        candidates.append(("sibling", os.path.join(exe_dir, "dist")))

    for label, path in candidates:
        index_html = os.path.join(path, "index.html")
        _spa_logger.debug("SPA probe [%s]: %s  exists=%s", label, path, os.path.exists(index_html))
        if os.path.isfile(index_html):
            _spa_logger.info("SPA resolved via [%s]: %s", label, path)
            return path

    _spa_logger.warning("SPA dist folder not found. Tried: %s", [c[1] for c in candidates])
    return None


frontend_path = get_frontend_path()

if frontend_path:
    # Mount static assets directory
    assets_dir = os.path.join(frontend_path, "assets")
    if os.path.isdir(assets_dir):
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/")
    def serve_root():
        """Serve index.html for the root path (/{path:path} doesn't match '/')."""
        return FileResponse(os.path.join(frontend_path, "index.html"))

    @app.get("/{catchall:path}")
    def serve_spa(catchall: str):
        """SPA catch-all: serve the requested file or fall back to index.html."""
        file_path = os.path.join(frontend_path, catchall)
        if os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(frontend_path, "index.html"))
else:
    @app.get("/")
    def no_frontend():
        return {"error": "Frontend dist folder not found."}

    @app.get("/{catchall:path}")
    def no_frontend_catchall(catchall: str):
        return {"error": "Frontend dist folder not found."}
