"""Presets API — save, load, and list config presets per block type."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.preset import Preset

router = APIRouter(prefix="/api/presets", tags=["presets"])


# ── Built-in presets (always available, not stored in DB) ─────

BUILTIN_PRESETS: list[dict[str, Any]] = [
    # LoRA Fine-Tuning presets
    {
        "id": "builtin-lora-quick-test",
        "block_type": "lora_finetuning",
        "name": "Quick Test",
        "config_json": json.dumps({
            "r": 4,
            "epochs": 1,
            "lr": 1e-4,
            "batch_size": 4,
            "lora_dropout": 0.05,
        }),
        "builtin": True,
    },
    {
        "id": "builtin-lora-production",
        "block_type": "lora_finetuning",
        "name": "Production",
        "config_json": json.dumps({
            "r": 16,
            "epochs": 3,
            "lr": 2e-5,
            "batch_size": 8,
            "alpha": 32,
            "lora_dropout": 0.1,
        }),
        "builtin": True,
    },
    {
        "id": "builtin-lora-memory-efficient",
        "block_type": "lora_finetuning",
        "name": "Memory-Efficient",
        "config_json": json.dumps({
            "r": 4,
            "epochs": 3,
            "lr": 1e-4,
            "batch_size": 2,
            "gradient_checkpointing": True,
            "lora_dropout": 0.05,
        }),
        "builtin": True,
    },
    # DPO Alignment presets
    {
        "id": "builtin-dpo-default",
        "block_type": "dpo_alignment",
        "name": "Standard DPO",
        "config_json": json.dumps({
            "beta": 0.1,
            "epochs": 1,
            "lr": 5e-7,
            "batch_size": 4,
        }),
        "builtin": True,
    },
    # Hyperparameter Sweep presets
    {
        "id": "builtin-sweep-quick",
        "block_type": "hyperparameter_sweep",
        "name": "Quick Grid Search",
        "config_json": json.dumps({
            "strategy": "grid",
            "max_trials": 4,
        }),
        "builtin": True,
    },
]


class PresetCreate(BaseModel):
    block_type: str
    name: str
    config_json: str  # JSON-encoded config dict


class PresetResponse(BaseModel):
    id: str
    block_type: str
    name: str
    config_json: str
    builtin: bool = False

    model_config = {"from_attributes": True}


@router.get("")
def list_presets(block_type: str | None = None, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    """List presets, optionally filtered by block_type. Includes built-in presets."""
    results: list[dict[str, Any]] = []

    # Add matching built-in presets
    for bp in BUILTIN_PRESETS:
        if block_type is None or bp["block_type"] == block_type:
            results.append(bp)

    # Add user presets from DB
    query = db.query(Preset)
    if block_type:
        query = query.filter(Preset.block_type == block_type)
    for p in query.order_by(Preset.created_at.desc()).all():
        results.append({
            "id": str(p.id),
            "block_type": p.block_type,
            "name": p.name,
            "config_json": p.config_json,
            "builtin": False,
        })

    return results


@router.post("")
def create_preset(body: PresetCreate, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Save a new user preset."""
    # Validate that config_json is valid JSON
    try:
        json.loads(body.config_json)
    except json.JSONDecodeError:
        raise HTTPException(400, "config_json must be valid JSON")

    preset = Preset(
        block_type=body.block_type,
        name=body.name,
        config_json=body.config_json,
    )
    db.add(preset)
    db.commit()
    db.refresh(preset)

    return {
        "id": str(preset.id),
        "block_type": preset.block_type,
        "name": preset.name,
        "config_json": preset.config_json,
        "builtin": False,
    }


@router.delete("/{preset_id}")
def delete_preset(preset_id: str, db: Session = Depends(get_db)) -> dict[str, str]:
    """Delete a user preset. Built-in presets cannot be deleted."""
    if preset_id.startswith("builtin-"):
        raise HTTPException(400, "Cannot delete built-in presets")

    try:
        pid = int(preset_id)
    except ValueError:
        raise HTTPException(400, "Invalid preset ID")

    preset = db.query(Preset).filter(Preset.id == pid).first()
    if not preset:
        raise HTTPException(404, "Preset not found")

    db.delete(preset)
    db.commit()
    return {"status": "deleted"}
