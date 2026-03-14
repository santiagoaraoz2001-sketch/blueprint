"""
Marketplace API — browse, install, and publish blocks/templates/plugins.

For v1, the marketplace is a local registry backed by a JSON file.
Future: remote registry at marketplace.specific.ai
"""

import logging
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from ..services import marketplace_service

router = APIRouter(prefix="/api/marketplace", tags=["marketplace"])
logger = logging.getLogger("blueprint.marketplace")


class PublishRequest(BaseModel):
    type: Literal["block", "template", "plugin"] = Field(description="Item type: block, template, or plugin")
    path: str = Field(min_length=1, description="Path to the local item to publish")
    name: str = Field(min_length=1, max_length=200, description="Display name for the item")
    description: str = Field(default="", max_length=2000, description="Item description")
    tags: list[str] = Field(default_factory=list, description="Searchable tags")
    license: str = Field(default="MIT", description="License type")
    author: str = Field(default="Local User", max_length=100, description="Author name")

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v: list[str]) -> list[str]:
        if len(v) > 20:
            raise ValueError("Maximum 20 tags allowed")
        return [t.strip().lower() for t in v if t.strip()]


class ReviewRequest(BaseModel):
    rating: int = Field(ge=1, le=5, description="Rating 1-5")
    text: str = Field(min_length=1, max_length=5000, description="Review text")


@router.get("/browse")
def browse_marketplace(
    category: str = "",
    search: str = Query(default="", max_length=200),
    sort: str = "popular",
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
):
    """Browse marketplace items with filtering, sorting, and pagination."""
    try:
        return marketplace_service.browse(
            category=category,
            search=search,
            sort=sort,
            page=page,
            per_page=per_page,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/installed")
def list_installed():
    """List all marketplace items currently installed."""
    return {"items": marketplace_service.list_installed()}


@router.get("/published")
def list_published():
    """List items published by the current user."""
    return {"items": marketplace_service.get_published_items()}


@router.get("/items/{item_id}")
def get_item_detail(item_id: str):
    """Get full details for a marketplace item."""
    try:
        item = marketplace_service.get_item(item_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not item:
        raise HTTPException(status_code=404, detail=f"Item '{item_id}' not found")
    return item


@router.post("/items/{item_id}/install")
def install_item(item_id: str):
    """Install a marketplace item."""
    try:
        return marketplace_service.install_item(item_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/items/{item_id}/uninstall")
def uninstall_item(item_id: str):
    """Remove an installed marketplace item."""
    try:
        return marketplace_service.uninstall_item(item_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/publish")
def publish_item(body: PublishRequest):
    """Publish a block/template/plugin to the marketplace."""
    try:
        return marketplace_service.publish_item(body.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/items/{item_id}/review")
def submit_review(item_id: str, body: ReviewRequest):
    """Submit a review for a marketplace item."""
    try:
        return marketplace_service.submit_review(item_id, body.rating, body.text)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/items/{item_id}/reviews")
def get_reviews(item_id: str):
    """Get all reviews for a marketplace item."""
    try:
        return {"reviews": marketplace_service.get_reviews(item_id)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/seed")
def seed_marketplace():
    """Seed the marketplace with built-in items (idempotent)."""
    marketplace_service.seed_registry()
    return {"status": "seeded"}
