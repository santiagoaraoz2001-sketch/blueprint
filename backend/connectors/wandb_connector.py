"""Weights & Biases export connector.

Pushes run metrics, config, and artifacts to a W&B project.
"""

import logging
import threading
from pathlib import Path
from typing import Any

from ..block_sdk.exceptions import BlockDependencyError
from .base import BaseConnector, ConnectorConfig, ExportResult
from .registry import register_connector

_logger = logging.getLogger("blueprint.connectors.wandb")

# wandb uses global process state for login and active-run tracking.
# Serialize the full init → log → finish lifecycle so concurrent exports
# with different API keys or projects don't interfere.
_wandb_lock = threading.Lock()


def _coerce_numeric(value: Any) -> float | None:
    """Try to coerce *value* to a float that wandb can log.

    Returns ``None`` for values that cannot be represented numerically
    (strings, dicts, lists, booleans, etc.).
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class WandbConnector(BaseConnector):
    """Export connector for Weights & Biases."""

    @property
    def name(self) -> str:
        return "wandb"

    @property
    def display_name(self) -> str:
        return "Weights & Biases"

    @property
    def description(self) -> str:
        return "Log metrics, config, and artifacts to a Weights & Biases project."

    def get_config_fields(self) -> list[ConnectorConfig]:
        return [
            ConnectorConfig(
                name="api_key",
                label="API Key",
                type="password",
                required=True,
                description="Your Weights & Biases API key.",
            ),
            ConnectorConfig(
                name="project",
                label="Project",
                type="string",
                required=True,
                description="W&B project name to log the run to.",
            ),
            ConnectorConfig(
                name="entity",
                label="Entity",
                type="string",
                required=False,
                default="",
                description="W&B entity (team or username). Leave blank for default.",
            ),
            ConnectorConfig(
                name="run_name",
                label="Run Name",
                type="string",
                required=False,
                default="",
                description="Custom name for the W&B run. Auto-generated if blank.",
            ),
        ]

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate_config(self, config: dict) -> tuple[bool, str]:
        api_key = (config.get("api_key") or "").strip()
        if not api_key:
            return False, "API key is required."

        project = (config.get("project") or "").strip()
        if not project:
            return False, "Project name is required."

        # Graceful dependency check — the /validate endpoint does not catch
        # exceptions, so we return a validation tuple rather than raising.
        try:
            import wandb  # noqa: F401
        except ImportError:
            return False, (
                "The 'wandb' package is not installed. "
                "Install it with: pip install wandb"
            )

        return True, ""

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def export(self, run_export: dict, config: dict) -> ExportResult:
        try:
            import wandb
        except ImportError:
            raise BlockDependencyError(
                dependency="wandb",
                install_hint="pip install wandb",
            )

        api_key = config["api_key"].strip()
        project = config["project"].strip()
        entity = (config.get("entity") or "").strip() or None
        run_name = (config.get("run_name") or "").strip() or None

        run_info = run_export.get("run", {})
        run_id = run_info.get("id", "unknown")

        if not run_name:
            run_name = f"blueprint-{run_id}"

        timeseries = run_export.get("metrics", {}).get("timeseries", [])
        summary = run_export.get("metrics", {}).get("summary", {})
        artifacts = run_export.get("artifacts", [])

        # Hold the lock for the full lifecycle to prevent global-state races.
        with _wandb_lock:
            return self._run_export(
                wandb,
                api_key=api_key,
                project=project,
                entity=entity,
                run_name=run_name,
                run_id=run_id,
                run_config=run_export.get("config", {}),
                timeseries=timeseries,
                summary=summary,
                environment=run_export.get("environment", {}),
                artifacts=artifacts,
            )

    def _run_export(
        self,
        wandb,
        *,
        api_key: str,
        project: str,
        entity: str | None,
        run_name: str,
        run_id: str,
        run_config: dict,
        timeseries: list[dict],
        summary: dict,
        environment: dict,
        artifacts: list[dict],
    ) -> ExportResult:
        """Execute the W&B lifecycle under the global lock."""

        # --- login --------------------------------------------------
        try:
            wandb.login(key=api_key, relogin=True)
        except Exception as exc:
            _logger.warning("wandb.login failed: %s", exc)
            return ExportResult(
                success=False,
                message=f"Failed to authenticate with Weights & Biases: {exc}",
            )

        # --- init ---------------------------------------------------
        try:
            wb_run = wandb.init(
                project=project,
                entity=entity,
                name=run_name,
                config=run_config,
                tags=["blueprint"],
            )
        except Exception as exc:
            _logger.warning("wandb.init failed: %s", exc)
            return ExportResult(
                success=False,
                message=f"Failed to create W&B run: {exc}",
            )

        # Capture identifiers before finish() so they are always available.
        wb_run_id = wb_run.id
        try:
            run_url = wb_run.get_url()
        except AttributeError:
            run_url = getattr(wb_run, "url", None)

        metrics_logged = 0
        artifacts_uploaded = 0
        skipped_values = 0

        try:
            # --- timeseries metrics ---------------------------------
            for event in timeseries:
                if event.get("type") != "metric":
                    continue
                metric_name = event.get("name", "")
                if not metric_name:
                    continue

                numeric = _coerce_numeric(event.get("value"))
                if numeric is None:
                    skipped_values += 1
                    continue

                node_id = event.get("node_id", "")
                key = f"{node_id}/{metric_name}" if node_id else metric_name
                step = event.get("step")
                log_kwargs: dict[str, Any] = {}
                if step is not None:
                    log_kwargs["step"] = step
                wb_run.log({key: numeric}, **log_kwargs)
                metrics_logged += 1

            # --- summary metrics ------------------------------------
            for k, v in summary.items():
                wb_run.summary[k] = v

            # --- environment ----------------------------------------
            if environment:
                wb_run.summary["environment"] = environment

            # --- artifacts ------------------------------------------
            files_added = 0
            for art in artifacts:
                path = art.get("path", "")
                art_name = art.get("name", "")
                if path and Path(path).exists():
                    files_added += 1

            if files_added > 0:
                artifact = wandb.Artifact(
                    name=f"blueprint-run-{run_id}",
                    type="blueprint-artifacts",
                )
                for art in artifacts:
                    path = art.get("path", "")
                    art_name = art.get("name", "")
                    if path and Path(path).exists():
                        artifact.add_file(path, name=art_name)
                wb_run.log_artifact(artifact)
                artifacts_uploaded = files_added

        except Exception as exc:
            _logger.exception("Error during W&B export for run %s", run_id)
            # Still finish the run cleanly before returning.
            wb_run.finish(exit_code=1)
            return ExportResult(
                success=False,
                message=f"W&B export failed during logging: {exc}",
                url=run_url,
                external_id=wb_run_id,
            )

        wb_run.finish()

        _logger.info(
            "Exported run %s to W&B project '%s' — %d metrics, %d artifacts, %d skipped",
            run_id,
            project,
            metrics_logged,
            artifacts_uploaded,
            skipped_values,
        )

        return ExportResult(
            success=True,
            message=f"Run exported to Weights & Biases: {run_name}",
            url=run_url,
            external_id=wb_run_id,
            details={
                "project": project,
                "entity": entity,
                "metrics_logged": metrics_logged,
                "artifacts_uploaded": artifacts_uploaded,
                "skipped_non_numeric": skipped_values,
            },
        )


# Register at import time
register_connector(WandbConnector())
