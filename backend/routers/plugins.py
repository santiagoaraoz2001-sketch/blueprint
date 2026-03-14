"""Plugin endpoints — list panels, manage plugin state."""

from __future__ import annotations

from fastapi import APIRouter

from ..plugins.registry import plugin_registry

router = APIRouter(prefix="/api/plugins", tags=["plugins"])


@router.get("/panels")
def list_panels():
    """Return all panels registered by loaded plugins."""
    return {"panels": plugin_registry.get_panels()}


@router.get("")
def list_plugins():
    """Return all registered plugins."""
    return {
        "plugins": [
            {"name": p.name, "version": p.version, "is_loaded": p.is_loaded}
            for p in plugin_registry.list_plugins()
        ]
    }
