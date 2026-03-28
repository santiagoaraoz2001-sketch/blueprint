"""Copilot router — rule-based alerts, AI explanations, and variant suggestions."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.pipeline import Pipeline
from ..services.copilot_rules import RuleEngine, get_variant_field_hints
from ..services.copilot_ai import AICopilot

logger = logging.getLogger("blueprint.copilot")

router = APIRouter(prefix="/api/copilot", tags=["copilot"])

# Singleton instances — stateless, safe to share
_rule_engine = RuleEngine()
_ai_copilot = AICopilot()


def _get_registry(request: Request):
    """Retrieve the BlockRegistryService from app state."""
    return getattr(request.app.state, "registry", None)


# ── Request / Response Models ────────────────────────────────────────

class AlertResponse(BaseModel):
    id: str
    severity: str
    title: str
    message: str
    affected_node_id: str | None
    suggested_action: str | None
    auto_dismissible: bool


class AlertsPayload(BaseModel):
    nodes: list[dict[str, Any]] = Field(default_factory=list)
    edges: list[dict[str, Any]] = Field(default_factory=list)
    capabilities: dict[str, Any] | None = None


class ExplainRequest(BaseModel):
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]


class DiagnoseRequest(BaseModel):
    run_id: str
    error_context: dict[str, Any]
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]


class SuggestVariantRequest(BaseModel):
    source_pipeline_id: str
    intent: str


class VariantFieldChange(BaseModel):
    field: str
    current_value: Any
    suggested_value: Any


class VariantNodeChanges(BaseModel):
    node_id: str
    node_label: str
    changes: list[VariantFieldChange]


class SuggestVariantResponse(BaseModel):
    suggestions: list[VariantNodeChanges]
    field_hints: dict[str, list[str]]


# ── Endpoints ────────────────────────────────────────────────────────

@router.post("/alerts", response_model=list[AlertResponse])
def evaluate_alerts(payload: AlertsPayload, request: Request):
    """Evaluate pipeline graph against all copilot rules.

    Accepts nodes/edges/capabilities inline (for real-time canvas evaluation).
    Returns alerts sorted by severity.
    """
    registry = _get_registry(request)
    alerts = _rule_engine.evaluate(
        nodes=payload.nodes,
        edges=payload.edges,
        capabilities=payload.capabilities,
        registry=registry,
    )
    return [AlertResponse(**a.to_dict()) for a in alerts]


@router.get("/alerts")
def get_alerts_for_pipeline(
    pipeline_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """Evaluate rules for a saved pipeline by ID."""
    pipeline = db.query(Pipeline).filter(Pipeline.id == pipeline_id).first()
    if not pipeline:
        raise HTTPException(404, "Pipeline not found")

    definition = pipeline.definition or {}
    nodes = definition.get("nodes", [])
    edges = definition.get("edges", [])

    registry = _get_registry(request)
    alerts = _rule_engine.evaluate(
        nodes=nodes,
        edges=edges,
        registry=registry,
    )
    return [a.to_dict() for a in alerts]


@router.post("/explain")
def explain_pipeline(payload: ExplainRequest, request: Request):
    """Use AI to explain a pipeline step-by-step."""
    registry = _get_registry(request)
    result = _ai_copilot.explain_pipeline(
        nodes=payload.nodes,
        edges=payload.edges,
        registry=registry,
    )
    if result is None:
        return {
            "available": False,
            "explanation": None,
            "message": "AI features require a local inference backend. Start Ollama to enable pipeline explanations.",
        }
    return {
        "available": True,
        "explanation": result,
    }


@router.post("/diagnose")
def diagnose_error(payload: DiagnoseRequest):
    """Use AI to diagnose a pipeline run error."""
    result = _ai_copilot.diagnose_error(
        run_id=payload.run_id,
        error_context=payload.error_context,
        nodes=payload.nodes,
        edges=payload.edges,
    )
    if result is None:
        return {
            "available": False,
            "diagnosis": None,
            "message": "AI features require a local inference backend. Start Ollama to enable error diagnosis.",
        }
    return {
        "available": True,
        "diagnosis": result,
    }


@router.post("/suggest-variant", response_model=SuggestVariantResponse)
def suggest_variant(
    payload: SuggestVariantRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Suggest config changes for a pipeline variant based on natural language intent.

    Combines rule-based field highlighting (always available) with AI-powered
    suggestions (when Ollama/MLX is running).
    """
    pipeline = db.query(Pipeline).filter(Pipeline.id == payload.source_pipeline_id).first()
    if not pipeline:
        raise HTTPException(404, "Pipeline not found")

    definition = pipeline.definition or {}
    nodes = definition.get("nodes", [])
    edges = definition.get("edges", [])
    registry = _get_registry(request)

    # Rule-based field hints (always works)
    field_hints = get_variant_field_hints(nodes, registry)

    # AI-powered suggestions (optional)
    suggestions: list[VariantNodeChanges] = []
    ai_changes = _ai_copilot.suggest_variant_config(
        source_pipeline=definition,
        user_intent=payload.intent,
        registry=registry,
    )

    if ai_changes:
        node_map = {n["id"]: n for n in nodes}
        for node_id, changes in ai_changes.items():
            if not isinstance(changes, dict):
                continue
            node = node_map.get(node_id)
            if node is None:
                continue

            current_config = node.get("data", {}).get("config", {})
            label = node.get("data", {}).get("label", node_id)

            field_changes = []
            for field, new_val in changes.items():
                field_changes.append(VariantFieldChange(
                    field=field,
                    current_value=current_config.get(field),
                    suggested_value=new_val,
                ))

            if field_changes:
                suggestions.append(VariantNodeChanges(
                    node_id=node_id,
                    node_label=label,
                    changes=field_changes,
                ))

    return SuggestVariantResponse(
        suggestions=suggestions,
        field_hints=field_hints,
    )


@router.get("/status")
def copilot_status():
    """Return copilot health: rule engine always available, AI is optional."""
    ai_available = _ai_copilot.is_available()
    return {
        "rules_available": True,
        "ai_available": ai_available,
        "message": (
            "All copilot features active."
            if ai_available
            else "Rule-based alerts active. Start Ollama or MLX for AI-powered features."
        ),
    }
