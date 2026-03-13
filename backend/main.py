import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .database import init_db
from .config import ensure_dirs
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from .routers import projects, pipelines, runs, datasets, blocks, events, execution, control_tower, system, models, papers, secrets, custom_blocks, inference


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    ensure_dirs()
    init_db()

    # Recover stale runs from previous crash
    try:
        from datetime import datetime, timezone, timedelta
        from .database import SessionLocal
        from .models.run import Run, LiveRun
        import logging
        _recovery_logger = logging.getLogger("blueprint.recovery")
        session = SessionLocal()
        stale_cutoff = datetime.now(timezone.utc) - timedelta(minutes=5)
        stale_runs = session.query(Run).filter(Run.status == "running").all()
        recovered = 0
        for stale_run in stale_runs:
            if stale_run.last_heartbeat is None or stale_run.last_heartbeat < stale_cutoff:
                stale_run.status = "failed"
                stale_run.error_message = "Recovered: process terminated unexpectedly"
                stale_run.finished_at = datetime.now(timezone.utc)
                # Also update live run
                live = session.query(LiveRun).filter(LiveRun.run_id == stale_run.id).first()
                if live:
                    live.status = "failed"
                recovered += 1
        if recovered:
            session.commit()
            _recovery_logger.info("Recovered %d stale run(s) from previous session", recovered)
        session.close()
    except Exception as e:
        import logging
        logging.getLogger("blueprint.recovery").warning("Stale run recovery failed: %s", e)

    # Start background model directory watcher
    try:
        from .utils.model_watcher import start_watcher
        import logging
        _logger = logging.getLogger(__name__)
        start_watcher(
            on_change=lambda models: _logger.info("Model watcher: %d models detected", len(models)),
            poll_interval=30.0,
        )
    except Exception:
        pass  # Non-critical — watcher is a convenience feature
    yield
    # Shutdown
    try:
        from .routers.execution import shutdown_executor
        shutdown_executor()
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
