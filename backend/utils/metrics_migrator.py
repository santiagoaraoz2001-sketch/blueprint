"""Migrate old metric events to current schema version."""

import logging

from ..engine.metrics_schema import MetricEvent, CURRENT_SCHEMA_VERSION

log = logging.getLogger(__name__)


def migrate_metrics_log(metrics_log: list[dict]) -> list[dict]:
    """Migrate a metrics_log to current schema version.

    Resilient to malformed entries — they are skipped with a warning
    so that a single corrupt event doesn't block the whole migration.
    """
    migrated = []
    for i, entry in enumerate(metrics_log):
        try:
            event = MetricEvent.from_dict(entry)
            event.schema_version = CURRENT_SCHEMA_VERSION
            migrated.append(event.to_dict())
        except Exception:
            log.warning("Skipping unparseable metric entry at index %d: %r", i, entry)
            continue
    return migrated
