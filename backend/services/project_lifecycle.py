"""
Auto-lifecycle service for project/phase progress tracking.

Updates phase and project counters when runs complete or fail.
Never crashes execution — all errors are caught and logged.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..models.run import Run
from ..models.pipeline import Pipeline
from ..models.experiment_phase import ExperimentPhase
from ..models.project import Project

logger = logging.getLogger("blueprint.lifecycle")


def on_run_completed(run_id: str, db: Session) -> None:
    """Update phase/project counters after a run completes successfully."""
    try:
        _update_lifecycle(run_id, db)
    except Exception as e:
        logger.warning("Lifecycle update failed for run %s: %s", run_id, e)


def on_run_failed(run_id: str, db: Session) -> None:
    """Update counts only (never change statuses) after a run fails."""
    try:
        _update_counts_only(run_id, db)
    except Exception as e:
        logger.warning("Lifecycle count update failed for run %s: %s", run_id, e)


def _update_lifecycle(run_id: str, db: Session) -> None:
    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        return

    pipeline = db.query(Pipeline).filter(Pipeline.id == run.pipeline_id).first()
    if not pipeline or not pipeline.experiment_phase_id:
        return  # Unassigned pipeline — valid, nothing to do

    phase = db.query(ExperimentPhase).filter(ExperimentPhase.id == pipeline.experiment_phase_id).first()
    if not phase:
        return

    project = db.query(Project).filter(Project.id == phase.project_id).first()
    if not project:
        return

    # Count completed runs for this phase
    phase_pipeline_ids = [
        p.id for p in db.query(Pipeline.id).filter(Pipeline.experiment_phase_id == phase.id).all()
    ]
    if phase_pipeline_ids:
        phase.completed_runs = db.query(Run).filter(
            Run.pipeline_id.in_(phase_pipeline_ids),
            Run.status == "complete",
        ).count()

    # Auto-complete phase if all runs done
    if phase.total_runs > 0 and phase.completed_runs >= phase.total_runs:
        phase.status = "complete"

    # Update project-level aggregates
    _update_project_aggregates(project, db)

    db.commit()


def _update_counts_only(run_id: str, db: Session) -> None:
    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        return

    pipeline = db.query(Pipeline).filter(Pipeline.id == run.pipeline_id).first()
    if not pipeline or not pipeline.experiment_phase_id:
        return

    phase = db.query(ExperimentPhase).filter(ExperimentPhase.id == pipeline.experiment_phase_id).first()
    if not phase:
        return

    project = db.query(Project).filter(Project.id == phase.project_id).first()
    if not project:
        return

    # Recount completed runs for this phase (don't change statuses)
    phase_pipeline_ids = [
        p.id for p in db.query(Pipeline.id).filter(Pipeline.experiment_phase_id == phase.id).all()
    ]
    if phase_pipeline_ids:
        phase.completed_runs = db.query(Run).filter(
            Run.pipeline_id.in_(phase_pipeline_ids),
            Run.status == "complete",
        ).count()

    _update_project_aggregates(project, db)
    db.commit()


def _update_project_aggregates(project: Project, db: Session) -> None:
    """Sum completed_runs across all project phases and compute hours."""
    phases = db.query(ExperimentPhase).filter(ExperimentPhase.project_id == project.id).all()

    project.completed_experiments = sum(p.completed_runs or 0 for p in phases)

    # Sum durations of all runs linked to this project's phases
    all_phase_ids = [p.id for p in phases]
    if all_phase_ids:
        pipeline_ids = [
            p.id for p in db.query(Pipeline.id).filter(Pipeline.experiment_phase_id.in_(all_phase_ids)).all()
        ]
        if pipeline_ids:
            runs = db.query(Run).filter(
                Run.pipeline_id.in_(pipeline_ids),
                Run.duration_seconds.isnot(None),
            ).all()
            total_seconds = sum(r.duration_seconds for r in runs)
            project.actual_compute_hours = total_seconds / 3600.0

    # Set started_at if not already set
    if not project.started_at:
        project.started_at = datetime.now(timezone.utc)
