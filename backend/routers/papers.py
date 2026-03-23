import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.paper import Paper
from ..schemas.paper import PaperCreate, PaperUpdate, PaperResponse

router = APIRouter(prefix="/api/papers", tags=["papers"])


@router.get("", response_model=list[PaperResponse])
def list_papers(project_id: str | None = None, db: Session = Depends(get_db)):
    q = db.query(Paper)
    if project_id:
        q = q.filter(Paper.project_id == project_id)
    return q.order_by(Paper.updated_at.desc()).all()


@router.post("", response_model=PaperResponse, status_code=201)
def create_paper(data: PaperCreate, db: Session = Depends(get_db)):
    paper = Paper(id=str(uuid.uuid4()), **data.model_dump())
    db.add(paper)
    db.commit()
    db.refresh(paper)
    return paper


@router.get("/{paper_id}", response_model=PaperResponse)
def get_paper(paper_id: str, db: Session = Depends(get_db)):
    paper = db.query(Paper).filter(Paper.id == paper_id).first()
    if not paper:
        raise HTTPException(404, "Paper not found")
    return paper


@router.put("/{paper_id}", response_model=PaperResponse)
def update_paper(paper_id: str, data: PaperUpdate, db: Session = Depends(get_db)):
    paper = db.query(Paper).filter(Paper.id == paper_id).first()
    if not paper:
        raise HTTPException(404, "Paper not found")
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(paper, key, value)
    db.commit()
    db.refresh(paper)
    return paper


@router.delete("/{paper_id}", status_code=204)
def delete_paper(paper_id: str, db: Session = Depends(get_db)):
    paper = db.query(Paper).filter(Paper.id == paper_id).first()
    if not paper:
        raise HTTPException(404, "Paper not found")
    db.delete(paper)
    db.commit()
