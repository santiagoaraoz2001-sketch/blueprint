import uuid
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.pipeline import Pipeline
from ..schemas.pipeline import PipelineCreate, PipelineUpdate, PipelineResponse

router = APIRouter(prefix="/api/pipelines", tags=["pipelines"])


@router.get("", response_model=list[PipelineResponse])
def list_pipelines(project_id: str | None = None, db: Session = Depends(get_db)):
    q = db.query(Pipeline)
    if project_id:
        q = q.filter(Pipeline.project_id == project_id)
    return q.order_by(Pipeline.updated_at.desc()).all()


@router.post("", response_model=PipelineResponse, status_code=201)
def create_pipeline(data: PipelineCreate, db: Session = Depends(get_db)):
    pipeline = Pipeline(id=str(uuid.uuid4()), **data.model_dump())
    db.add(pipeline)
    db.commit()
    db.refresh(pipeline)
    return pipeline


@router.get("/{pipeline_id}", response_model=PipelineResponse)
def get_pipeline(pipeline_id: str, db: Session = Depends(get_db)):
    pipeline = db.query(Pipeline).filter(Pipeline.id == pipeline_id).first()
    if not pipeline:
        raise HTTPException(404, "Pipeline not found")
    return pipeline


@router.put("/{pipeline_id}", response_model=PipelineResponse)
def update_pipeline(pipeline_id: str, data: PipelineUpdate, db: Session = Depends(get_db)):
    pipeline = db.query(Pipeline).filter(Pipeline.id == pipeline_id).first()
    if not pipeline:
        raise HTTPException(404, "Pipeline not found")
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(pipeline, key, value)
    db.commit()
    db.refresh(pipeline)
    return pipeline


@router.delete("/{pipeline_id}", status_code=204)
def delete_pipeline(pipeline_id: str, db: Session = Depends(get_db)):
    pipeline = db.query(Pipeline).filter(Pipeline.id == pipeline_id).first()
    if not pipeline:
        raise HTTPException(404, "Pipeline not found")
    db.delete(pipeline)
    db.commit()


@router.post("/{pipeline_id}/duplicate", response_model=PipelineResponse)
def duplicate_pipeline(pipeline_id: str, db: Session = Depends(get_db)):
    original = db.query(Pipeline).filter(Pipeline.id == pipeline_id).first()
    if not original:
        raise HTTPException(404, "Pipeline not found")
    clone = Pipeline(
        id=str(uuid.uuid4()),
        name=f"{original.name} (copy)",
        project_id=original.project_id,
        experiment_id=original.experiment_id,
        description=original.description,
        definition=original.definition,
    )
    db.add(clone)
    db.commit()
    db.refresh(clone)
    return clone


@router.get("/{pipeline_id}/compile")
def compile_pipeline(pipeline_id: str, db: Session = Depends(get_db)):
    from ..engine.compiler import compile_pipeline_to_python
    pipeline = db.query(Pipeline).filter(Pipeline.id == pipeline_id).first()
    if not pipeline:
        raise HTTPException(404, "Pipeline not found")
    
    definition = pipeline.definition or {}
    script = compile_pipeline_to_python(pipeline.name, definition)
    return PlainTextResponse(content=script, media_type="text/x-python")
