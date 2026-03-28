"""Deploy router — export models to Ollama, HuggingFace, ONNX, or standalone server."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.model_record import ModelRecord
from ..services.deploy import (
    check_all_targets,
    export_to_huggingface,
    export_to_ollama,
    export_to_onnx,
    generate_inference_server,
)

logger = logging.getLogger("blueprint.deploy")

router = APIRouter(prefix="/api/models", tags=["deploy"])

_LOCALHOST_HOSTS = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}


# ── Request schemas ──────────────────────────────────────────────────

class OllamaDeployConfig(BaseModel):
    model_name: str | None = None


class HuggingFaceDeployConfig(BaseModel):
    repo_id: str
    hf_token: str
    private: bool = True


class OnnxDeployConfig(BaseModel):
    output_path: str


class ServerDeployConfig(BaseModel):
    output_dir: str


# ── Check available targets ──────────────────────────────────────────

@router.get("/deploy/targets")
def get_deploy_targets():
    """Return availability status for each deploy target."""
    return check_all_targets()


# ── Deploy endpoints ─────────────────────────────────────────────────

def _get_model(model_id: str, db: Session) -> ModelRecord:
    model = db.query(ModelRecord).filter(ModelRecord.id == model_id).first()
    if not model:
        raise HTTPException(404, "Model not found")
    return model


@router.post("/{model_id}/deploy/ollama")
def deploy_ollama(model_id: str, config: OllamaDeployConfig, db: Session = Depends(get_db)):
    """Export model to Ollama."""
    model = _get_model(model_id, db)
    if not model.model_path:
        raise HTTPException(400, "Model has no file path set")
    result = export_to_ollama(model, model.model_path, model_name=config.model_name)
    if not result["success"]:
        raise HTTPException(422, result["error"])
    return result


@router.post("/{model_id}/deploy/huggingface")
def deploy_huggingface(
    model_id: str,
    config: HuggingFaceDeployConfig,
    request: Request,
    db: Session = Depends(get_db),
):
    """Export model to HuggingFace Hub.

    Security: accepts ``$secret:NAME`` in hf_token to read from the
    encrypted secrets store.  The token is never echoed in the response.
    A warning is logged when the request originates from a non-localhost client.
    """
    # Warn if the token is being sent over a non-localhost connection
    client_host = request.client.host if request.client else "unknown"
    if client_host not in _LOCALHOST_HOSTS:
        logger.warning(
            "HuggingFace deploy request received from non-localhost client %s. "
            "Token may be exposed in transit if HTTPS is not configured.",
            client_host,
        )

    model = _get_model(model_id, db)
    result = export_to_huggingface(model, config.hf_token, config.repo_id, private=config.private)
    if not result["success"]:
        raise HTTPException(422, result["error"])
    return result


@router.post("/{model_id}/deploy/onnx")
def deploy_onnx(model_id: str, config: OnnxDeployConfig, db: Session = Depends(get_db)):
    """Export model to ONNX format."""
    model = _get_model(model_id, db)
    result = export_to_onnx(model, config.output_path)
    if not result["success"]:
        raise HTTPException(422, result["error"])
    return result


@router.post("/{model_id}/deploy/server")
def deploy_server(model_id: str, config: ServerDeployConfig, db: Session = Depends(get_db)):
    """Generate a standalone inference server."""
    model = _get_model(model_id, db)
    result = generate_inference_server(model, config.output_dir)
    if not result["success"]:
        raise HTTPException(422, result["error"])
    return result
