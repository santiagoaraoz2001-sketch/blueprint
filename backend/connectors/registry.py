"""Connector Registry — manages available export connectors.

Thread-safe registry for connector instances.  Connectors are typically
registered once at import time (app startup), but the registry is safe
for concurrent reads from request handlers.
"""

import logging
import threading
from typing import Optional

from .base import BaseConnector

_logger = logging.getLogger("blueprint.connectors")

_lock = threading.Lock()
_connectors: dict[str, BaseConnector] = {}


def register_connector(connector: BaseConnector) -> None:
    """Register a connector instance.

    Raises:
        ValueError: If the connector's ``name`` is empty or already
            registered under a different instance.
    """
    name = connector.name
    if not name or not name.strip():
        raise ValueError("Connector name must be a non-empty string")

    with _lock:
        existing = _connectors.get(name)
        if existing is not None and existing is not connector:
            _logger.warning(
                "Overwriting existing connector '%s' (%s) with %s",
                name,
                type(existing).__name__,
                type(connector).__name__,
            )
        _connectors[name] = connector
        _logger.info("Registered export connector '%s' (%s)", name, connector.display_name)


def get_connector(name: str) -> Optional[BaseConnector]:
    """Look up a connector by name.  Returns ``None`` if not found."""
    with _lock:
        return _connectors.get(name)


def list_connectors() -> list[dict]:
    """Return serialized metadata for every registered connector."""
    with _lock:
        return [c.to_dict() for c in _connectors.values()]
