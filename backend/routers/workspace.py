"""Workspace management API endpoints.

Handles workspace folder creation, settings persistence,
inbox monitoring, and path resolution for config auto-fill.
"""

from __future__ import annotations

import platform
import subprocess
from pathlib import Path

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.workspace import WorkspaceSettings
from ..schemas.workspace import (
    InboxFile,
    WorkspaceSettingsResponse,
    WorkspaceSettingsUpdate,
    WorkspaceStatus,
)
from ..services.inbox_watcher import (
    get_watcher_status,
    is_watcher_running,
    start_watcher,
    stop_watcher,
)
from ..services.workspace_manager import WorkspaceManager

router = APIRouter(prefix="/workspace", tags=["workspace"])


def _get_or_create_settings(db: Session) -> WorkspaceSettings:
    """Get or create the singleton workspace settings row."""
    settings = db.query(WorkspaceSettings).filter_by(id="default").first()
    if not settings:
        settings = WorkspaceSettings(id="default")
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return settings


@router.get("/settings", response_model=WorkspaceSettingsResponse)
def get_settings(db: Session = Depends(get_db)):
    """Return current workspace configuration."""
    settings = _get_or_create_settings(db)
    return WorkspaceSettingsResponse(
        root_path=settings.root_path,
        auto_fill_paths=settings.auto_fill_paths,
        watcher_enabled=settings.watcher_enabled,
    )


@router.put("/settings", response_model=WorkspaceSettingsResponse)
def update_settings(body: WorkspaceSettingsUpdate, db: Session = Depends(get_db)):
    """Update workspace configuration.

    If root_path changes, creates the folder structure at the new location.
    If watcher_enabled changes, starts/stops the inbox watcher accordingly.
    """
    settings = _get_or_create_settings(db)

    path_changed = False
    watcher_changed = False

    if body.root_path is not None and body.root_path != settings.root_path:
        settings.root_path = body.root_path if body.root_path else None
        path_changed = True

    if body.auto_fill_paths is not None:
        settings.auto_fill_paths = body.auto_fill_paths

    if body.watcher_enabled is not None and body.watcher_enabled != settings.watcher_enabled:
        settings.watcher_enabled = body.watcher_enabled
        watcher_changed = True

    db.commit()
    db.refresh(settings)

    # Create folder structure if path was set/changed
    if path_changed and settings.root_path:
        manager = WorkspaceManager(settings.root_path)
        manager.ensure_structure()

    # Start/stop watcher as needed
    if watcher_changed or path_changed:
        if settings.root_path and settings.watcher_enabled:
            stop_watcher()
            start_watcher(settings.root_path)
        else:
            stop_watcher()

    return WorkspaceSettingsResponse(
        root_path=settings.root_path,
        auto_fill_paths=settings.auto_fill_paths,
        watcher_enabled=settings.watcher_enabled,
    )


@router.get("/status", response_model=WorkspaceStatus)
def get_status(db: Session = Depends(get_db)):
    """Return workspace status: watcher state, folder health, inbox count."""
    settings = _get_or_create_settings(db)

    if not settings.root_path:
        return WorkspaceStatus()

    manager = WorkspaceManager(settings.root_path)
    watcher = get_watcher_status()

    return WorkspaceStatus(
        root_path=settings.root_path,
        watcher_running=watcher.get("running", False),
        folder_health=manager.get_folder_health(),
        inbox_count=manager.get_inbox_count(),
    )


@router.post("/initialize")
def initialize_workspace(db: Session = Depends(get_db)):
    """Force re-create the folder structure at the configured root path."""
    settings = _get_or_create_settings(db)
    if not settings.root_path:
        return {"ok": False, "error": "No workspace root configured"}

    manager = WorkspaceManager(settings.root_path)
    manager.ensure_structure()
    return {"ok": True, "path": settings.root_path}


@router.get("/paths")
def get_paths(db: Session = Depends(get_db)):
    """Return the full path map for frontend auto-fill display."""
    settings = _get_or_create_settings(db)
    if not settings.root_path:
        return {"paths": {}, "auto_fill_paths": False}

    manager = WorkspaceManager(settings.root_path)
    return {
        "paths": manager.get_all_paths(),
        "auto_fill_paths": settings.auto_fill_paths,
    }


@router.post("/open")
def open_in_finder(db: Session = Depends(get_db)):
    """Open the workspace root in the system file manager."""
    settings = _get_or_create_settings(db)
    if not settings.root_path:
        return {"ok": False, "error": "No workspace root configured"}

    path = settings.root_path
    if not Path(path).is_dir():
        return {"ok": False, "error": "Workspace directory does not exist"}

    try:
        system = platform.system()
        if system == "Darwin":
            subprocess.Popen(["open", path])
        elif system == "Windows":
            subprocess.Popen(["explorer", path])
        else:
            subprocess.Popen(["xdg-open", path])
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.get("/inbox", response_model=list[InboxFile])
def list_inbox(db: Session = Depends(get_db)):
    """List files currently in the inbox directory."""
    settings = _get_or_create_settings(db)
    if not settings.root_path:
        return []

    manager = WorkspaceManager(settings.root_path)
    return [InboxFile(**f) for f in manager.list_inbox_files()]
