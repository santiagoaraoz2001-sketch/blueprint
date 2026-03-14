"""API router for export connectors."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..config import ARTIFACTS_DIR
from ..connectors import registry as connector_registry
from ..database import get_db
from ..engine.run_export import generate_run_export
from ..models.run import Run

_logger = logging.getLogger("blueprint.connectors")

router = APIRouter(prefix="/api/connectors", tags=["connectors"])


class ConnectorConfigBody(BaseModel):
    config: dict = {}


# ───────── Connector discovery ─────────


@router.get("")
def list_connectors():
    """Return all registered export connectors with their config schemas."""
    return {"connectors": connector_registry.list_connectors()}


@router.get("/{connector_name}")
def get_connector_info(connector_name: str):
    """Return metadata and config schema for a single connector."""
    connector = connector_registry.get_connector(connector_name)
    if not connector:
        raise HTTPException(404, f"Connector '{connector_name}' not found")
    return connector.to_dict()


# ───────── Validation ─────────


@router.post("/{connector_name}/validate")
def validate_connector_config(connector_name: str, body: ConnectorConfigBody):
    """Validate a connector config without performing an export."""
    connector = connector_registry.get_connector(connector_name)
    if not connector:
        raise HTTPException(404, f"Connector '{connector_name}' not found")
    valid, error = connector.validate_config(body.config)
    return {"valid": valid, "error": error}


# ───────── Export ─────────


@router.post("/runs/{run_id}/export/{connector_name}")
def export_run(
    run_id: str,
    connector_name: str,
    body: ConnectorConfigBody,
    db: Session = Depends(get_db),
):
    """Export a run to an external service via a named connector."""
    connector = connector_registry.get_connector(connector_name)
    if not connector:
        raise HTTPException(404, f"Connector '{connector_name}' not found")

    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise HTTPException(404, "Run not found")

    # Validate config before doing any heavy work
    valid, error = connector.validate_config(body.config)
    if not valid:
        raise HTTPException(400, error)

    # Generate structured export
    run_export = generate_run_export(run, ARTIFACTS_DIR)

    # Perform export — catch connector errors so a buggy connector
    # doesn't crash the server with a 500
    _logger.info(
        "Exporting run %s via connector '%s'",
        run_id, connector_name,
    )
    try:
        result = connector.export(run_export, body.config)
    except Exception:
        _logger.exception(
            "Connector '%s' raised an unhandled exception while exporting run %s",
            connector_name, run_id,
        )
        raise HTTPException(
            502,
            f"Connector '{connector_name}' failed unexpectedly. Check server logs for details.",
        )

    _logger.info(
        "Export run %s via '%s': success=%s url=%s",
        run_id, connector_name, result.success, result.url,
    )

    return {
        "success": result.success,
        "message": result.message,
        "url": result.url,
        "external_id": result.external_id,
        "details": result.details,
    }
