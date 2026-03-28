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


@router.get("/config")
def get_workspace_config(db: Session = Depends(get_db)):
    """Return global workspace-level pipeline config overrides.

    These are the lowest-precedence overrides, applied to ALL pipelines.
    Project-level overrides (via /api/projects/{id}/config) take precedence
    over global overrides.
    """
    settings = _get_or_create_settings(db)
    config = settings.pipeline_config or {}

    # Compute 'affects N blocks' counts by checking which blocks have matching schema keys
    affects_counts: dict[str, int] = {}
    try:
        from ..services.registry import get_global_registry
        registry = get_global_registry()
        if registry:
            all_schemas = registry.list_all()
            for key in config:
                count = 0
                for schema in all_schemas:
                    config_fields = getattr(schema, 'config', [])
                    field_keys = {
                        (f.get('key') if isinstance(f, dict) else getattr(f, 'key', ''))
                        for f in config_fields
                    }
                    if key in field_keys:
                        count += 1
                affects_counts[key] = count
    except Exception:
        pass

    return {
        "scope": "global",
        "config": config,
        "affects_counts": affects_counts,
    }


@router.put("/config")
def update_workspace_config(body: dict, db: Session = Depends(get_db)):
    """Update workspace-level pipeline config overrides.

    Body: { "config": { key: value, ... } }
    Replaces the entire workspace config dict.
    """
    settings = _get_or_create_settings(db)
    new_config = body.get("config", {})
    if not isinstance(new_config, dict):
        from fastapi import HTTPException
        raise HTTPException(400, "config must be a dict")
    settings.pipeline_config = new_config
    db.commit()
    db.refresh(settings)
    return {"ok": True, "config": settings.pipeline_config}


@router.post("/config/preview-impact")
def preview_workspace_config_impact(body: dict, db: Session = Depends(get_db)):
    """Preview the impact of workspace config changes on a pipeline.

    Body: {
        "pipeline_id": str,
        "config": { key: value },
        "scope": "global" | "project"  (default: "global")
    }
    Returns a diff of what would change per node.

    When scope is "global", the proposed config replaces the global workspace config.
    When scope is "project", the proposed config replaces the project config while
    keeping the global config unchanged.
    """
    from ..models.pipeline import Pipeline
    from ..engine.planner import GraphPlanner
    from ..engine.config_merge import merge_workspace_config
    from ..services.registry import get_global_registry

    pipeline_id = body.get("pipeline_id")
    proposed_config = body.get("config", {})
    scope = body.get("scope", "global")
    if not pipeline_id:
        from fastapi import HTTPException
        raise HTTPException(400, "pipeline_id is required")

    pipeline = db.query(Pipeline).filter(Pipeline.id == pipeline_id).first()
    if not pipeline:
        from fastapi import HTTPException
        raise HTTPException(404, "Pipeline not found")

    definition = pipeline.definition or {}
    nodes = definition.get("nodes", [])
    edges = definition.get("edges", [])
    definition_config = definition.get("workspace_config") or None

    registry = get_global_registry()
    if registry is None:
        from ..services.registry import BlockRegistryService
        registry = BlockRegistryService()

    planner = GraphPlanner(registry)

    # Current effective config (merges global → project → definition)
    current_merged = merge_workspace_config(
        definition_config=definition_config,
        project_id=pipeline.project_id,
        db=db,
    )
    result_before = planner.plan(nodes, edges, workspace_config=current_merged or None)

    # Proposed effective config — depends on scope
    if scope == "project":
        # Replace project config with proposed, keep global
        from ..models.workspace import WorkspaceSettings as _WS
        _ws = db.query(_WS).filter_by(id="default").first()
        proposed_merged = dict(_ws.pipeline_config or {}) if _ws else {}
        proposed_merged.update(proposed_config)
        if definition_config:
            proposed_merged.update(definition_config)
    else:
        # Replace global config with proposed, keep project
        from ..models.project import Project as _Proj
        proposed_merged = dict(proposed_config)
        if pipeline.project_id:
            _proj = db.query(_Proj).filter_by(id=pipeline.project_id).first()
            if _proj and _proj.pipeline_config:
                proposed_merged.update(_proj.pipeline_config)
        if definition_config:
            proposed_merged.update(definition_config)

    result_after = planner.plan(nodes, edges, workspace_config=proposed_merged or None)

    diffs: dict[str, dict] = {}
    if result_before.plan and result_after.plan:
        node_label_map = {n["id"]: n for n in nodes}
        for node_id in result_after.plan.nodes:
            before_node = result_before.plan.nodes.get(node_id)
            after_node = result_after.plan.nodes.get(node_id)
            if not before_node or not after_node:
                continue

            node_diffs: dict[str, dict] = {}
            all_keys = set(before_node.resolved_config.keys()) | set(after_node.resolved_config.keys())
            for key in all_keys:
                old_val = before_node.resolved_config.get(key)
                new_val = after_node.resolved_config.get(key)
                if old_val != new_val:
                    node_diffs[key] = {"before": old_val, "after": new_val}
            if node_diffs:
                node_label = node_label_map.get(node_id, {}).get("data", {}).get("label", node_id)
                diffs[node_id] = {"label": node_label, "changes": node_diffs}

    return {"diffs": diffs}


@router.get("/inbox", response_model=list[InboxFile])
def list_inbox(db: Session = Depends(get_db)):
    """List files currently in the inbox directory."""
    settings = _get_or_create_settings(db)
    if not settings.root_path:
        return []

    manager = WorkspaceManager(settings.root_path)
    return [InboxFile(**f) for f in manager.list_inbox_files()]
