"""Workspace Config Merge — merges config overrides from multiple scopes.

Config precedence (highest to lowest):
1. Pipeline definition's embedded ``workspace_config``
2. Project-level ``pipeline_config`` overrides
3. Global workspace ``pipeline_config`` overrides

The result is a single flat dict passed to the config resolver as ``workspace_config``.
This dict sits between "user-set" values and "schema defaults" in the resolver's
full precedence chain: user > workspace_config > inherited > block_default.

This module is the single source of truth for config merging logic.
Both the planner (plan endpoint) and the executor call through it.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def merge_workspace_config(
    *,
    definition_config: dict[str, Any] | None = None,
    project_id: str | None = None,
    db: Session | None = None,
) -> dict[str, Any]:
    """Merge config overrides from global workspace, project, and pipeline definition.

    Args:
        definition_config: The ``workspace_config`` dict embedded in the pipeline
            definition JSON.  May be ``None``.
        project_id: The project owning this pipeline.  Used to load project-level
            overrides from the database.  May be ``None`` for unattached pipelines.
        db: An active SQLAlchemy session.  Required when ``project_id`` is set.
            When ``None``, project/global lookups are skipped (useful for tests
            and planner calls that already have the config).

    Returns:
        A merged dict of config overrides, ready to pass as ``workspace_config``
        to ``resolve_configs``.
    """
    merged: dict[str, Any] = {}

    # Layer 1: Global workspace config (lowest precedence of the three)
    if db is not None:
        global_config = _load_global_config(db)
        if global_config:
            merged.update(global_config)

    # Layer 2: Project-level config (overrides global)
    if db is not None and project_id:
        project_config = _load_project_config(db, project_id)
        if project_config:
            merged.update(project_config)

    # Layer 3: Pipeline definition config (highest precedence)
    if definition_config:
        merged.update(definition_config)

    return merged


def _load_global_config(db: Session) -> dict[str, Any] | None:
    """Load the singleton workspace pipeline_config.  Fail-open on error."""
    try:
        from ..models.workspace import WorkspaceSettings
        ws = db.query(WorkspaceSettings).filter_by(id="default").first()
        if ws and ws.pipeline_config:
            return dict(ws.pipeline_config)
    except Exception as exc:
        logger.debug("Could not load global workspace config: %s", exc)
    return None


def _load_project_config(db: Session, project_id: str) -> dict[str, Any] | None:
    """Load a project's pipeline_config.  Fail-open on error."""
    try:
        from ..models.project import Project
        project = db.query(Project).filter_by(id=project_id).first()
        if project and project.pipeline_config:
            return dict(project.pipeline_config)
    except Exception as exc:
        logger.debug("Could not load project %s config: %s", project_id, exc)
    return None
