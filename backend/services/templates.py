"""Template service — loads and validates pipeline templates from JSON files."""
from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from typing import Any

logger = logging.getLogger("blueprint.templates")

# Templates directory at repo root
TEMPLATES_DIR = Path(__file__).parent.parent.parent / "templates"


class TemplateService:
    """Reads template JSON files from the templates/ directory and validates
    block references against the block registry."""

    def __init__(self, registry=None):
        self._registry = registry
        self._cache: dict[str, dict[str, Any]] | None = None

    def _load_templates(self) -> dict[str, dict[str, Any]]:
        """Load all template JSON files from disk. Cached after first call."""
        if self._cache is not None:
            return self._cache

        templates: dict[str, dict[str, Any]] = {}
        if not TEMPLATES_DIR.exists():
            logger.warning("Templates directory not found: %s", TEMPLATES_DIR)
            return templates

        for path in sorted(TEMPLATES_DIR.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                tid = data.get("id", path.stem)
                data["id"] = tid
                templates[tid] = data
            except Exception as exc:
                logger.warning("Failed to load template %s: %s", path.name, exc)

        self._cache = templates
        logger.info("Loaded %d templates from %s", len(templates), TEMPLATES_DIR)
        return templates

    def invalidate_cache(self):
        """Force re-read of template files on next access."""
        self._cache = None

    def list_templates(self) -> list[dict[str, Any]]:
        """Return all templates as a list of summary dicts (no full node data)."""
        templates = self._load_templates()
        result = []
        for tpl in templates.values():
            result.append({
                "id": tpl["id"],
                "name": tpl["name"],
                "description": tpl.get("description", ""),
                "difficulty": tpl.get("difficulty", "beginner"),
                "estimated_runtime": tpl.get("estimated_runtime", ""),
                "required_services": tpl.get("required_services", []),
                "required_capabilities": tpl.get("required_capabilities", []),
                "block_count": len(tpl.get("nodes", [])),
                "tags": tpl.get("tags", []),
            })
        return result

    def get_template(self, template_id: str) -> dict[str, Any] | None:
        """Return a single template by ID, or None if not found."""
        templates = self._load_templates()
        return templates.get(template_id)

    def validate_template(self, template: dict[str, Any]) -> list[str]:
        """Validate that all block types in a template exist in the registry.
        Returns a list of error messages (empty = valid)."""
        errors = []
        if self._registry is None:
            return errors

        nodes = template.get("nodes", [])
        for node in nodes:
            block_type = node.get("data", {}).get("type") or node.get("type", "")
            if block_type and not self._registry.get_block_info(block_type):
                errors.append(f"Block type '{block_type}' not found in registry")
        return errors

    def instantiate(self, template_id: str) -> dict[str, Any] | None:
        """Create a pipeline definition from a template.

        Returns a dict with {name, description, definition} suitable for
        creating a Pipeline via the pipelines API, or None if not found.
        """
        tpl = self.get_template(template_id)
        if tpl is None:
            return None

        # Deep-copy nodes with fresh IDs to avoid collisions
        id_map: dict[str, str] = {}
        nodes = []
        for node in tpl.get("nodes", []):
            old_id = node["id"]
            new_id = f"tpl_{uuid.uuid4().hex[:8]}"
            id_map[old_id] = new_id
            new_node = {
                **node,
                "id": new_id,
            }
            nodes.append(new_node)

        # Remap edges
        edges = []
        for edge in tpl.get("edges", []):
            new_edge = {
                **edge,
                "id": f"e_{uuid.uuid4().hex[:8]}",
                "source": id_map.get(edge["source"], edge["source"]),
                "target": id_map.get(edge["target"], edge["target"]),
            }
            edges.append(new_edge)

        return {
            "name": tpl["name"],
            "description": tpl.get("description", ""),
            "definition": {
                "nodes": nodes,
                "edges": edges,
                **({"workspace_config": tpl["default_config"]} if tpl.get("default_config") else {}),
            },
        }


# Module-level singleton (lazily set by the router)
_service: TemplateService | None = None


def get_template_service() -> TemplateService:
    """Get or create the module-level TemplateService singleton."""
    global _service
    if _service is None:
        _service = TemplateService()
    return _service


def set_template_service(svc: TemplateService):
    """Replace the module-level singleton (used during app startup)."""
    global _service
    _service = svc
