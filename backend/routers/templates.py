"""API routes for pipeline templates."""
from __future__ import annotations

import importlib
import logging
import subprocess
import uuid
from urllib.request import urlopen

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..config import OLLAMA_URL
from ..database import get_db
from ..models.pipeline import Pipeline
from ..services.templates import get_template_service

logger = logging.getLogger("blueprint.templates")
router = APIRouter(prefix="/api/templates", tags=["templates"])


@router.get("")
def list_templates():
    """Return all available templates (summary view without full node data)."""
    svc = get_template_service()
    return svc.list_templates()


@router.get("/{template_id}")
def get_template(template_id: str):
    """Return a single template with full node/edge data."""
    svc = get_template_service()
    tpl = svc.get_template(template_id)
    if tpl is None:
        raise HTTPException(404, f"Template '{template_id}' not found")
    return tpl


@router.post("/{template_id}/instantiate")
def instantiate_template(template_id: str, db: Session = Depends(get_db)):
    """Create a new pipeline from a template and return the pipeline."""
    svc = get_template_service()
    result = svc.instantiate(template_id)
    if result is None:
        raise HTTPException(404, f"Template '{template_id}' not found")

    pipeline = Pipeline(
        id=str(uuid.uuid4()),
        name=result["name"],
        description=result["description"],
        definition=result["definition"],
    )
    db.add(pipeline)
    db.commit()
    db.refresh(pipeline)
    return {
        "pipeline_id": pipeline.id,
        "name": pipeline.name,
        "description": pipeline.description,
        "definition": pipeline.definition,
        "created_at": pipeline.created_at.isoformat() if pipeline.created_at else None,
    }


# ─── Prerequisite checks ─────────────────────────────────────────────

def _check_ollama() -> dict:
    """Probe the Ollama API to determine if it's running and has models."""
    try:
        resp = urlopen(f"{OLLAMA_URL}/api/tags", timeout=2)
        if resp.status == 200:
            import json
            data = json.loads(resp.read())
            count = len(data.get("models", []))
            return {
                "id": "ollama",
                "label": "Ollama",
                "available": True,
                "detail": f"Running ({count} model{'s' if count != 1 else ''})",
            }
    except Exception:
        pass
    # Check if ollama binary is installed even if not running
    try:
        result = subprocess.run(
            ["which", "ollama"], capture_output=True, timeout=3, text=True,
        )
        if result.returncode == 0:
            return {
                "id": "ollama",
                "label": "Ollama",
                "available": False,
                "detail": "Installed but not running — start with: ollama serve",
            }
    except Exception:
        pass
    return {
        "id": "ollama",
        "label": "Ollama",
        "available": False,
        "detail": "Not installed — get it from ollama.ai",
    }


def _check_torch() -> dict:
    """Check if PyTorch is installed and what device is available."""
    try:
        torch = importlib.import_module("torch")
        version = getattr(torch, "__version__", "unknown")
        if hasattr(torch, "cuda") and torch.cuda.is_available():
            device = "CUDA"
        elif hasattr(torch, "backends") and hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            device = "MPS (Apple Silicon)"
        else:
            device = "CPU"
        return {
            "id": "torch",
            "label": "PyTorch",
            "available": True,
            "detail": f"v{version} ({device})",
        }
    except ImportError:
        return {
            "id": "torch",
            "label": "PyTorch",
            "available": False,
            "detail": "Not installed — pip install torch",
        }


# Cache capability checks for 30 seconds to avoid repeated subprocess calls
_prereq_cache: dict | None = None
_prereq_cache_ts: float = 0


@router.get("/prerequisites/check")
def check_prerequisites():
    """Return real-time availability of services and capabilities.

    Response: {services: {ollama: {...}}, capabilities: {torch: {...}}}
    Cached for 30s to avoid repeated subprocess overhead.
    """
    import time
    global _prereq_cache, _prereq_cache_ts

    now = time.monotonic()
    if _prereq_cache is not None and (now - _prereq_cache_ts) < 30:
        return _prereq_cache

    ollama = _check_ollama()
    torch = _check_torch()

    result = {
        "services": {
            "ollama": ollama,
        },
        "capabilities": {
            "torch": torch,
        },
    }
    _prereq_cache = result
    _prereq_cache_ts = now
    return result
