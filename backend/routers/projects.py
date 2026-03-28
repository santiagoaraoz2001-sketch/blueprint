import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, case, literal_column
from sqlalchemy.sql import label

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

@router.get("")
def list_projects(status: str | None = None, db: Session = Depends(get_db)):
    q = db.query(Project)
    if status:
        q = q.filter(Project.status == status)
    projects = q.order_by(Project.updated_at.desc()).all()

    if not projects:
        return []

    project_ids = [p.id for p in projects]

    # ── Single query: pipelines with run count + latest run status ──
    # Subquery: per-pipeline run count
    run_count_sq = (
        db.query(
            Run.pipeline_id,
            func.count(Run.id).label("run_count"),
        )
        .group_by(Run.pipeline_id)
        .subquery()
    )

    # Subquery: per-pipeline latest run (by started_at DESC)
    latest_run_sq = (
        db.query(
            Run.pipeline_id,
            Run.status.label("latest_status"),
            func.max(Run.started_at).label("max_started"),
        )
        .group_by(Run.pipeline_id)
        .subquery()
    )

    # Join pipelines with both subqueries
    pipe_rows = (
        db.query(
            Pipeline.id,
            Pipeline.name,
            Pipeline.project_id,
            Pipeline.source_pipeline_id,
            Pipeline.variant_notes,
            Pipeline.config_diff,
            func.coalesce(run_count_sq.c.run_count, 0).label("run_count"),
            latest_run_sq.c.latest_status,
        )
        .outerjoin(run_count_sq, Pipeline.id == run_count_sq.c.pipeline_id)
        .outerjoin(latest_run_sq, Pipeline.id == latest_run_sq.c.pipeline_id)
        .filter(Pipeline.project_id.in_(project_ids))
        .all()
    )

    # Group pipeline rows by project_id
    pipes_by_project: dict[str, list[dict]] = {pid: [] for pid in project_ids}
    for row in pipe_rows:
        pid = row.project_id
        if pid in pipes_by_project:
            pipes_by_project[pid].append({
                "id": row.id,
                "name": row.name,
                "run_count": row.run_count,
                "latest_run_status": row.latest_status,
                "source_pipeline_id": row.source_pipeline_id,
                "variant_notes": row.variant_notes,
                "config_diff": row.config_diff,
            })

    result = []
    for project in projects:
        p_dict = ProjectResponse.model_validate(project).model_dump()
        pipeline_summaries = pipes_by_project.get(project.id, [])
        p_dict["pipelines"] = pipeline_summaries
        p_dict["total_pipeline_count"] = len(pipeline_summaries)
        result.append(p_dict)

    return result


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


@router.get("/{project_id}")
def get_project(project_id: str, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    p_dict = ProjectResponse.model_validate(project).model_dump()

    # Query 1: All pipelines for this project
    pipelines = (
        db.query(Pipeline)
        .filter(Pipeline.project_id == project_id)
        .order_by(Pipeline.updated_at.desc())
        .all()
    )
    pipeline_ids = [p.id for p in pipelines]

    # Query 2: All runs for all pipelines in one query, grouped by pipeline
    runs_by_pipeline: dict[str, list] = {pid: [] for pid in pipeline_ids}
    if pipeline_ids:
        all_runs = (
            db.query(Run)
            .filter(Run.pipeline_id.in_(pipeline_ids))
            .order_by(Run.started_at.desc())
            .all()
        )
        for r in all_runs:
            if r.pipeline_id in runs_by_pipeline:
                runs_by_pipeline[r.pipeline_id].append(r)

    pipeline_details = []
    for pipe in pipelines:
        runs = runs_by_pipeline.get(pipe.id, [])
        pipeline_details.append({
            "id": pipe.id,
            "name": pipe.name,
            "description": pipe.description,
            "source_pipeline_id": pipe.source_pipeline_id,
            "variant_notes": pipe.variant_notes,
            "config_diff": pipe.config_diff,
            "notes": pipe.notes,
            "created_at": pipe.created_at.isoformat() if pipe.created_at else None,
            "updated_at": pipe.updated_at.isoformat() if pipe.updated_at else None,
            "run_count": len(runs),
            "latest_run_status": runs[0].status if runs else None,
            "runs": [
                {
                    "id": r.id,
                    "status": r.status,
                    "started_at": r.started_at.isoformat() if r.started_at else None,
                    "finished_at": r.finished_at.isoformat() if r.finished_at else None,
                    "duration_seconds": r.duration_seconds,
                    "metrics": r.metrics or {},
                    "notes": r.notes,
                    "tags": r.tags,
                    "starred": r.starred or False,
                }
                for r in runs
            ],
        })

    p_dict["pipelines"] = pipeline_details
    return p_dict


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
