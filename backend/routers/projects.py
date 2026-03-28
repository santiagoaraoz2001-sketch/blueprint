import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func

from ..database import get_db
from ..models.project import Project
from ..models.experiment_phase import ExperimentPhase
from ..models.pipeline import Pipeline
from ..models.run import Run
from ..schemas.project import ProjectCreate, ProjectUpdate, ProjectResponse
from ..schemas.experiment_phase import (
    ExperimentPhaseCreate, ExperimentPhaseUpdate, ExperimentPhaseResponse,
    QuickSetupRequest,
)

router = APIRouter(prefix="/api/projects", tags=["projects"])


# ── Project CRUD ──────────────────────────────────────────────────────

@router.get("", response_model=list[ProjectResponse])
def list_projects(status: str | None = None, db: Session = Depends(get_db)):
    q = db.query(Project)
    if status:
        q = q.filter(Project.status == status)
    return q.order_by(Project.updated_at.desc()).all()


@router.post("", response_model=ProjectResponse, status_code=201)
def create_project(data: ProjectCreate, db: Session = Depends(get_db)):
    project = Project(id=str(uuid.uuid4()), **data.model_dump())
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@router.get("/dashboard")
def project_dashboard(db: Session = Depends(get_db)):
    """Aggregate dashboard: status counts, compute hours, blocked papers, unassigned runs."""
    projects = db.query(Project).all()

    by_status: dict[str, int] = {}
    for p in projects:
        by_status[p.status] = by_status.get(p.status, 0) + 1

    total_compute = sum(p.actual_compute_hours or 0 for p in projects)
    blocked = [
        {"id": p.id, "name": p.name, "blocked_by": p.blocked_by}
        for p in projects if p.status == "blocked"
    ]

    currently_running = [
        {"id": p.id, "name": p.name}
        for p in projects if p.status == "active"
    ]

    recently_completed = [
        {"id": p.id, "name": p.name, "completed_at": p.completed_at.isoformat() if p.completed_at else None}
        for p in sorted(
            [p for p in projects if p.status == "complete"],
            key=lambda p: p.completed_at or p.updated_at,
            reverse=True,
        )[:5]
    ]

    # Unassigned runs: runs whose pipeline has no experiment_phase_id
    unassigned_pipelines = db.query(Pipeline.id).filter(Pipeline.experiment_phase_id.is_(None)).subquery()
    unassigned_count = db.query(func.count(Run.id)).filter(
        Run.pipeline_id.in_(db.query(unassigned_pipelines.c.id)),
        Run.status == "complete",
    ).scalar() or 0

    recent_unassigned = []
    if unassigned_count > 0:
        unassigned_rows = db.query(Run, Pipeline.name).join(
            Pipeline, Run.pipeline_id == Pipeline.id
        ).filter(
            Pipeline.experiment_phase_id.is_(None),
            Run.status == "complete",
        ).order_by(Run.finished_at.desc()).limit(10).all()
        for r, pipeline_name in unassigned_rows:
            recent_unassigned.append({
                "run_id": r.id,
                "pipeline_name": pipeline_name or "",
                "metrics": r.metrics or {},
            })

    return {
        "total_papers": len(projects),
        "by_status": by_status,
        "currently_running": currently_running,
        "recently_completed": recently_completed,
        "total_compute_hours": total_compute,
        "blocked_papers": blocked,
        "unassigned_runs": unassigned_count,
        "recent_unassigned": recent_unassigned,
    }


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(project_id: str, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")
    return project


@router.put("/{project_id}", response_model=ProjectResponse)
def update_project(project_id: str, data: ProjectUpdate, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(project, key, value)
    db.commit()
    db.refresh(project)
    return project


@router.delete("/{project_id}", status_code=204)
def delete_project(project_id: str, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")
    # Also delete associated phases
    db.query(ExperimentPhase).filter(ExperimentPhase.project_id == project_id).delete()
    db.delete(project)
    db.commit()


# ── Experiment Phases ─────────────────────────────────────────────────

@router.get("/{project_id}/phases", response_model=list[ExperimentPhaseResponse])
def list_phases(project_id: str, db: Session = Depends(get_db)):
    _require_project(project_id, db)
    return db.query(ExperimentPhase).filter(
        ExperimentPhase.project_id == project_id
    ).order_by(ExperimentPhase.sort_order).all()


@router.post("/{project_id}/phases", response_model=ExperimentPhaseResponse, status_code=201)
def create_phase(project_id: str, data: ExperimentPhaseCreate, db: Session = Depends(get_db)):
    _require_project(project_id, db)
    phase = ExperimentPhase(
        id=str(uuid.uuid4()),
        project_id=project_id,
        **data.model_dump(),
    )
    db.add(phase)
    db.commit()
    db.refresh(phase)
    return phase


@router.get("/{project_id}/phases/{phase_id}", response_model=ExperimentPhaseResponse)
def get_phase(project_id: str, phase_id: str, db: Session = Depends(get_db)):
    phase = db.query(ExperimentPhase).filter(
        ExperimentPhase.id == phase_id,
        ExperimentPhase.project_id == project_id,
    ).first()
    if not phase:
        raise HTTPException(404, "Phase not found")
    return phase


@router.put("/{project_id}/phases/{phase_id}", response_model=ExperimentPhaseResponse)
def update_phase(project_id: str, phase_id: str, data: ExperimentPhaseUpdate, db: Session = Depends(get_db)):
    phase = db.query(ExperimentPhase).filter(
        ExperimentPhase.id == phase_id,
        ExperimentPhase.project_id == project_id,
    ).first()
    if not phase:
        raise HTTPException(404, "Phase not found")
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(phase, key, value)
    db.commit()
    db.refresh(phase)
    return phase


@router.delete("/{project_id}/phases/{phase_id}", status_code=204)
def delete_phase(project_id: str, phase_id: str, db: Session = Depends(get_db)):
    phase = db.query(ExperimentPhase).filter(
        ExperimentPhase.id == phase_id,
        ExperimentPhase.project_id == project_id,
    ).first()
    if not phase:
        raise HTTPException(404, "Phase not found")
    # Unlink any pipelines pointing to this phase
    db.query(Pipeline).filter(Pipeline.experiment_phase_id == phase_id).update(
        {"experiment_phase_id": None}
    )
    db.delete(phase)
    db.commit()


# ── Quick Setup ───────────────────────────────────────────────────────

@router.post("/{project_id}/quick-setup", response_model=ProjectResponse)
def quick_setup(project_id: str, data: QuickSetupRequest, db: Session = Depends(get_db)):
    """Bulk-create phases for a project. Sets project.total_experiments = sum of total_runs."""
    project = _require_project(project_id, db)

    for idx, phase_data in enumerate(data.phases):
        phase = ExperimentPhase(
            id=str(uuid.uuid4()),
            project_id=project_id,
            phase_id=phase_data.phase_id,
            name=phase_data.name,
            total_runs=phase_data.total_runs,
            description=phase_data.description,
            research_question=phase_data.research_question,
            sort_order=idx,
        )
        db.add(phase)

    project.total_experiments = sum(p.total_runs for p in data.phases)
    db.commit()
    db.refresh(project)
    return project


# ── Stats ─────────────────────────────────────────────────────────────

@router.get("/{project_id}/stats")
def project_stats(project_id: str, db: Session = Depends(get_db)):
    """Detailed stats for a single project."""
    _require_project(project_id, db)

    phases = db.query(ExperimentPhase).filter(ExperimentPhase.project_id == project_id).all()
    phase_ids = [p.id for p in phases]

    # Get all pipelines linked to this project's phases
    pipeline_ids = []
    if phase_ids:
        pipeline_ids = [
            p.id for p in db.query(Pipeline.id).filter(Pipeline.experiment_phase_id.in_(phase_ids)).all()
        ]

    # Also include pipelines directly linked to this project
    direct_pipeline_ids = [
        p.id for p in db.query(Pipeline.id).filter(Pipeline.project_id == project_id).all()
    ]
    all_pipeline_ids = list(set(pipeline_ids + direct_pipeline_ids))

    if not all_pipeline_ids:
        return {
            "total_runs": 0, "completed_runs": 0, "failed_runs": 0, "running_runs": 0,
            "total_compute_hours": 0, "best_run": None, "latest_run": None,
            "phases": [], "active_runs": [],
        }

    runs = db.query(Run).filter(Run.pipeline_id.in_(all_pipeline_ids)).all()

    total_runs = len(runs)
    completed_runs = sum(1 for r in runs if r.status == "complete")
    failed_runs = sum(1 for r in runs if r.status == "failed")
    running_runs = sum(1 for r in runs if r.status == "running")
    total_compute = sum((r.duration_seconds or 0) for r in runs) / 3600.0

    # Best run: completed run with highest primary metric
    best_run = None
    completed = [r for r in runs if r.status == "complete" and r.metrics]
    if completed:
        best = max(completed, key=lambda r: max(r.metrics.values()) if r.metrics else 0)
        best_run = {"run_id": best.id, "metrics": best.metrics}

    # Latest run
    latest = max(runs, key=lambda r: r.started_at, default=None)
    latest_run = {"run_id": latest.id, "status": latest.status} if latest else None

    # Active runs
    active_runs = [
        {"run_id": r.id, "pipeline_id": r.pipeline_id, "status": r.status}
        for r in runs if r.status == "running"
    ]

    # Phases summary
    phases_summary = [
        {
            "id": p.id, "phase_id": p.phase_id, "name": p.name,
            "status": p.status, "total_runs": p.total_runs,
            "completed_runs": p.completed_runs,
        }
        for p in phases
    ]

    return {
        "total_runs": total_runs,
        "completed_runs": completed_runs,
        "failed_runs": failed_runs,
        "running_runs": running_runs,
        "total_compute_hours": total_compute,
        "best_run": best_run,
        "latest_run": latest_run,
        "phases": phases_summary,
        "active_runs": active_runs,
    }


# ── Helpers ───────────────────────────────────────────────────────────

def _require_project(project_id: str, db: Session) -> Project:
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")
    return project


# ---------------------------------------------------------------------------
# Project-scoped pipeline config overrides
# ---------------------------------------------------------------------------


@router.get("/{project_id}/config")
def get_project_config(project_id: str, db: Session = Depends(get_db)):
    """Return project-level pipeline config overrides.

    These sit between global workspace config and per-pipeline definition config
    in the merge precedence chain: global → project → definition.
    """
    project = _require_project(project_id, db)
    config = project.pipeline_config or {}

    # Also return the effective merged config for context
    from ..engine.config_merge import merge_workspace_config
    effective = merge_workspace_config(project_id=project_id, db=db)

    return {
        "project_config": config,
        "effective_config": effective,
    }


@router.put("/{project_id}/config")
def update_project_config(project_id: str, body: dict, db: Session = Depends(get_db)):
    """Update project-level pipeline config overrides.

    Body: { "config": { key: value, ... } }
    Replaces the entire project config dict.
    """
    project = _require_project(project_id, db)
    new_config = body.get("config", {})
    if not isinstance(new_config, dict):
        raise HTTPException(400, "config must be a dict")
    project.pipeline_config = new_config
    db.commit()
    db.refresh(project)
    return {"ok": True, "config": project.pipeline_config}
