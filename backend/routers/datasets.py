import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.dataset import Dataset
from ..schemas.dataset import DatasetCreate, DatasetResponse
from ..config import SNAPSHOTS_DIR
import shutil
import os
import time
from pathlib import Path

router = APIRouter(prefix="/api/datasets", tags=["datasets"])


@router.get("", response_model=list[DatasetResponse])
def list_datasets(db: Session = Depends(get_db)):
    return db.query(Dataset).order_by(Dataset.created_at.desc()).all()


@router.post("", response_model=DatasetResponse, status_code=201)
def register_dataset(data: DatasetCreate, db: Session = Depends(get_db)):
    dataset = Dataset(id=str(uuid.uuid4()), **data.model_dump())
    db.add(dataset)
    db.commit()
    db.refresh(dataset)
    return dataset


@router.get("/{dataset_id}", response_model=DatasetResponse)
def get_dataset(dataset_id: str, db: Session = Depends(get_db)):
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not dataset:
        raise HTTPException(404, "Dataset not found")
    return dataset


@router.get("/{dataset_id}/preview")
def preview_dataset(dataset_id: str, rows: int = 20, db: Session = Depends(get_db)):
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not dataset:
        raise HTTPException(404, "Dataset not found")
    # TODO: Read actual file and return preview rows
    return {"dataset_id": dataset_id, "rows": [], "total_rows": dataset.row_count or 0}


@router.delete("/{dataset_id}", status_code=204)
def delete_dataset(dataset_id: str, db: Session = Depends(get_db)):
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not dataset:
        raise HTTPException(404, "Dataset not found")
    db.delete(dataset)
    db.commit()


@router.post("/{dataset_id}/snapshots")
def create_snapshot(dataset_id: str, db: Session = Depends(get_db)):
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not dataset:
        raise HTTPException(404, "Dataset not found")
    if not dataset.source_path or not os.path.exists(dataset.source_path):
        raise HTTPException(400, "Dataset source file not found")
    
    snapshot_dir = SNAPSHOTS_DIR / dataset_id
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = int(time.time())
    snapshot_id = f"snap_{timestamp}"
    original_ext = Path(dataset.source_path).suffix
    snapshot_path = snapshot_dir / f"{snapshot_id}{original_ext}"
    
    shutil.copy2(dataset.source_path, snapshot_path)
    return {"id": snapshot_id, "timestamp": timestamp, "dataset_id": dataset_id}


@router.get("/{dataset_id}/snapshots")
def list_snapshots(dataset_id: str, db: Session = Depends(get_db)):
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not dataset:
        raise HTTPException(404, "Dataset not found")
    
    snapshot_dir = SNAPSHOTS_DIR / dataset_id
    if not snapshot_dir.exists():
        return []
    
    snapshots = []
    # Only keep last 24h of snapshots based on file modification time or name
    cutoff = time.time() - (24 * 3600)
    
    for file in snapshot_dir.iterdir():
        if not file.is_file() or not file.name.startswith("snap_"):
            continue
        try:
            ts = int(file.stem.replace("snap_", ""))
            # Cleanup old
            if ts < cutoff:
                file.unlink()
                continue
            snapshots.append({
                "id": file.stem,
                "timestamp": ts,
                "dataset_id": dataset_id,
                "size_bytes": file.stat().st_size
            })
        except ValueError:
            pass
            
    return sorted(snapshots, key=lambda x: x["timestamp"], reverse=True)


@router.post("/{dataset_id}/snapshots/{snapshot_id}/restore")
def restore_snapshot(dataset_id: str, snapshot_id: str, db: Session = Depends(get_db)):
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not dataset:
        raise HTTPException(404, "Dataset not found")
    if not dataset.source_path:
        raise HTTPException(400, "Dataset has no source path to restore to")
        
    snapshot_dir = SNAPSHOTS_DIR / dataset_id
    original_ext = Path(dataset.source_path).suffix
    snapshot_path = snapshot_dir / f"{snapshot_id}{original_ext}"

    # Guard against path traversal
    try:
        snapshot_path.resolve().relative_to(snapshot_dir.resolve())
    except ValueError:
        raise HTTPException(400, "Invalid snapshot ID")

    if not snapshot_path.exists():
        raise HTTPException(404, "Snapshot not found")
        
    # Overwrite the current working file with the snapshot
    shutil.copy2(snapshot_path, dataset.source_path)
    # Bump version
    dataset.version = (dataset.version or 1) + 1
    db.commit()
    return {"status": "ok", "restored_version": dataset.version}
