"""Jupyter Notebook export connector.

Generates a reproducible .ipynb notebook from a completed run, including
metadata, config, data loading, metrics, visualizations, and reproduction code.
"""

import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..block_sdk.exceptions import BlockDependencyError
from .base import BaseConnector, ConnectorConfig, ExportResult
from .registry import register_connector

_logger = logging.getLogger("blueprint.connectors.jupyter")

# Cap the number of timeseries events embedded in notebook cells to avoid
# creating multi-megabyte code cells for large training runs.
_MAX_VIZ_EVENTS = 10_000
_MAX_RAW_EVENTS = 50_000


# ---------------------------------------------------------------------------
# Safe JSON helpers
# ---------------------------------------------------------------------------

class _SafeEncoder(json.JSONEncoder):
    """JSON encoder that converts non-serializable values to strings."""

    def default(self, o: Any) -> Any:
        try:
            return super().default(o)
        except TypeError:
            return str(o)


def _safe_json(obj: Any, **kwargs: Any) -> str:
    """``json.dumps`` that never raises on non-serializable values."""
    return json.dumps(obj, cls=_SafeEncoder, **kwargs)


def _json_literal(obj: Any, indent: int = 2) -> str:
    """Return a Python expression string that reconstructs *obj* via ``json.loads``.

    The double-encoding keeps the generated cell safe regardless of what
    characters appear in the data.
    """
    return f"json.loads({json.dumps(_safe_json(obj, indent=indent))})"


# ---------------------------------------------------------------------------
# Cell builders
# ---------------------------------------------------------------------------

def _md(source: str) -> dict:
    """Notebook markdown cell descriptor."""
    return {"cell_type": "markdown", "source": source}


def _code(source: str) -> dict:
    """Notebook code cell descriptor."""
    return {"cell_type": "code", "source": source}


def _build_header_cell(run_export: dict) -> dict:
    run_info = run_export.get("run", {})
    env = run_export.get("environment", {})
    duration = run_info.get("duration_seconds")
    duration_str = f"{duration:.1f}s" if duration is not None else "N/A"

    return _md(
        "# Blueprint Run Report\n"
        "\n"
        f"- **Run ID:** `{run_info.get('id', 'N/A')}`\n"
        f"- **Pipeline ID:** `{run_info.get('pipeline_id', 'N/A')}`\n"
        f"- **Status:** {run_info.get('status', 'N/A')}\n"
        f"- **Started:** {run_info.get('started_at', 'N/A')}\n"
        f"- **Finished:** {run_info.get('finished_at', 'N/A')}\n"
        f"- **Duration:** {duration_str}\n"
        f"- **Blueprint Version:** {env.get('blueprint_version', 'N/A')}\n"
        f"- **Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}\n"
    )


def _build_config_cell(run_export: dict) -> dict:
    config = run_export.get("config", {})
    return _code(
        "# Pipeline Configuration\n"
        "import json\n"
        "\n"
        f"config = {_json_literal(config)}\n"
        "config"
    )


def _build_data_loading_cell(run_export: dict) -> dict:
    provenance = run_export.get("data_provenance", {})
    if not provenance:
        return _code(
            "# Data Provenance & Loading\n"
            "# No data fingerprints were recorded for this run.\n"
            "# TODO: Load your datasets here."
        )
    return _code(
        "# Data Provenance & Loading\n"
        "# Dataset fingerprints from the original run:\n"
        f"data_fingerprints = {_json_literal(provenance)}\n"
        "\n"
        "print('Dataset fingerprints:')\n"
        "for name, fp in data_fingerprints.items():\n"
        "    print(f'  {name}: {fp}')\n"
        "\n"
        "# TODO: Load your datasets here using the fingerprints above\n"
        "# to verify you are using the exact same data."
    )


def _build_metrics_cell(run_export: dict) -> dict:
    summary = run_export.get("metrics", {}).get("summary", {})
    if not summary:
        return _code(
            "# Metrics Summary\n"
            "# No summary metrics were recorded for this run."
        )
    return _code(
        "# Metrics Summary\n"
        f"metrics = {_json_literal(summary)}\n"
        "\n"
        "# Display as a table\n"
        "print('{:<40} {:>12}'.format('Metric', 'Value'))\n"
        "print('-' * 54)\n"
        "for name, value in metrics.items():\n"
        "    if isinstance(value, float):\n"
        "        print('{:<40} {:>12.4f}'.format(name, value))\n"
        "    else:\n"
        "        print('{:<40} {:>12}'.format(name, str(value)))"
    )


def _build_visualization_cell(run_export: dict) -> dict:
    timeseries = run_export.get("metrics", {}).get("timeseries", [])
    metric_events = [e for e in timeseries if e.get("type") == "metric"]

    if not metric_events:
        return _code(
            "# Visualizations\n"
            "# No timeseries metrics to plot."
        )

    # Downsample if the dataset is very large so the notebook stays small.
    truncated = len(metric_events) > _MAX_VIZ_EVENTS
    if truncated:
        step = len(metric_events) / _MAX_VIZ_EVENTS
        metric_events = [metric_events[int(i * step)] for i in range(_MAX_VIZ_EVENTS)]

    truncation_note = ""
    if truncated:
        truncation_note = (
            "# NOTE: Timeseries data was downsampled from the original run\n"
            f"# to {_MAX_VIZ_EVENTS:,} events for notebook size.\n"
        )

    return _code(
        "# Visualizations\n"
        "import matplotlib.pyplot as plt\n"
        "from collections import defaultdict\n"
        "\n"
        f"{truncation_note}"
        f"timeseries = {_json_literal(metric_events)}\n"
        "\n"
        "# Group metrics by name\n"
        "grouped = defaultdict(lambda: {'steps': [], 'values': []})\n"
        "for event in timeseries:\n"
        "    key = '{}/{}'.format(event.get('node_id', ''), event['name'])\n"
        "    step = event.get('step', len(grouped[key]['steps']))\n"
        "    try:\n"
        "        grouped[key]['values'].append(float(event['value']))\n"
        "        grouped[key]['steps'].append(step)\n"
        "    except (TypeError, ValueError):\n"
        "        pass  # skip non-numeric values\n"
        "\n"
        "# Plot each metric (up to 6)\n"
        "metric_names = list(grouped.keys())\n"
        "for row_start in range(0, min(len(metric_names), 6), 3):\n"
        "    batch = metric_names[row_start:row_start + 3]\n"
        "    fig, axes = plt.subplots(1, len(batch), figsize=(6 * len(batch), 4), squeeze=False)\n"
        "    for i, name in enumerate(batch):\n"
        "        data = grouped[name]\n"
        "        ax = axes[0][i]\n"
        "        ax.plot(data['steps'], data['values'], marker='o', markersize=3)\n"
        "        ax.set_title(name, fontsize=10)\n"
        "        ax.set_xlabel('Step')\n"
        "        ax.set_ylabel('Value')\n"
        "        ax.grid(True, alpha=0.3)\n"
        "    plt.tight_layout()\n"
        "    plt.show()"
    )


def _build_raw_data_cell(run_export: dict) -> dict:
    timeseries = run_export.get("metrics", {}).get("timeseries", [])
    total = len(timeseries)

    if not timeseries:
        return _code(
            "# Raw Timeseries Data\n"
            "# No timeseries data recorded."
        )

    truncated = total > _MAX_RAW_EVENTS
    if truncated:
        timeseries = timeseries[:_MAX_RAW_EVENTS]

    truncation_note = ""
    if truncated:
        truncation_note = (
            f"# NOTE: Showing first {_MAX_RAW_EVENTS:,} of {total:,} events.\n"
        )

    return _code(
        "# Raw Timeseries Data\n"
        f"{truncation_note}"
        f"raw_timeseries = {_json_literal(timeseries)}\n"
        f"print(f'Total events: {{len(raw_timeseries)}}')\n"
        "raw_timeseries[:5]  # Show first 5 events"
    )


def _build_reproduce_cell(run_export: dict) -> dict:
    config = run_export.get("config", {})
    return _code(
        "# Reproduce This Run\n"
        "# Re-run the same pipeline with the same configuration.\n"
        "\n"
        "# Option 1: Via Blueprint Python API\n"
        "# from blueprint import Pipeline\n"
        "# pipeline = Pipeline.from_config(config)\n"
        "# result = pipeline.run()\n"
        "\n"
        "# Option 2: Via Blueprint REST API\n"
        "import requests\n"
        "\n"
        f"pipeline_config = {_json_literal(config)}\n"
        "\n"
        "# Uncomment to execute:\n"
        "# resp = requests.post(\n"
        "#     'http://localhost:8000/api/runs/',\n"
        "#     json={'pipeline_config': pipeline_config}\n"
        "# )\n"
        "# print(resp.json())"
    )


# ---------------------------------------------------------------------------
# Connector
# ---------------------------------------------------------------------------


class JupyterConnector(BaseConnector):
    """Export connector that generates a reproducible Jupyter notebook."""

    @property
    def name(self) -> str:
        return "jupyter"

    @property
    def display_name(self) -> str:
        return "Jupyter Notebook"

    @property
    def description(self) -> str:
        return "Generate a reproducible Jupyter notebook with metrics, visualizations, and reproduction code."

    def get_config_fields(self) -> list[ConnectorConfig]:
        return [
            ConnectorConfig(
                name="output_dir",
                label="Output Directory",
                type="string",
                required=True,
                description="Directory to write the generated notebook.",
            ),
            ConnectorConfig(
                name="include_viz",
                label="Include Visualizations",
                type="select",
                required=False,
                default="true",
                options=["true", "false"],
                description="Include matplotlib visualization cells.",
            ),
            ConnectorConfig(
                name="include_raw_data",
                label="Include Raw Data",
                type="select",
                required=False,
                default="false",
                options=["true", "false"],
                description="Embed raw timeseries data in the notebook.",
            ),
        ]

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate_config(self, config: dict) -> tuple[bool, str]:
        output_dir = (config.get("output_dir") or "").strip()
        if not output_dir:
            return False, "Output directory is required."

        # Validate that the path is usable — either it already exists and
        # is writable, or we can create it.
        out = Path(output_dir)
        if out.exists():
            if not out.is_dir():
                return False, f"'{output_dir}' exists but is not a directory."
            if not os.access(out, os.W_OK):
                return False, f"Directory '{output_dir}' is not writable."
        else:
            # Check that the parent is writable so mkdir will succeed.
            parent = out.parent
            if parent.exists() and not os.access(parent, os.W_OK):
                return False, f"Parent directory '{parent}' is not writable."

        try:
            import nbformat  # noqa: F401
        except ImportError:
            return False, (
                "The 'nbformat' package is not installed. "
                "Install it with: pip install nbformat"
            )

        return True, ""

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def export(self, run_export: dict, config: dict) -> ExportResult:
        try:
            import nbformat
        except ImportError:
            raise BlockDependencyError(
                dependency="nbformat",
                install_hint="pip install nbformat",
            )

        output_dir = Path(config["output_dir"].strip())
        include_viz = (config.get("include_viz", "true")).lower() == "true"
        include_raw_data = (config.get("include_raw_data", "false")).lower() == "true"

        output_dir.mkdir(parents=True, exist_ok=True)

        run_id = run_export.get("run", {}).get("id", "unknown")
        filename = f"blueprint_run_{run_id}.ipynb"
        output_path = output_dir / filename

        # --- build cells -------------------------------------------
        cell_descriptors = [
            _build_header_cell(run_export),
            _build_config_cell(run_export),
            _build_data_loading_cell(run_export),
            _build_metrics_cell(run_export),
        ]

        if include_viz:
            cell_descriptors.append(_build_visualization_cell(run_export))

        if include_raw_data:
            cell_descriptors.append(_build_raw_data_cell(run_export))

        cell_descriptors.append(_build_reproduce_cell(run_export))

        # --- assemble notebook -------------------------------------
        nb = nbformat.v4.new_notebook()
        for desc in cell_descriptors:
            source = desc["source"]
            # Normalize source to a string (nbformat expects str, not list).
            if isinstance(source, list):
                source = "".join(source)
            if desc["cell_type"] == "markdown":
                nb.cells.append(nbformat.v4.new_markdown_cell(source))
            else:
                nb.cells.append(nbformat.v4.new_code_cell(source))

        # --- write atomically --------------------------------------
        # Write to a temp file first, then rename, to avoid leaving a
        # half-written notebook if the process is interrupted.
        tmp_path: str | None = None
        try:
            fd, tmp_path = tempfile.mkstemp(
                dir=str(output_dir), suffix=".ipynb.tmp",
            )
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                nbformat.write(nb, f)
            os.replace(tmp_path, str(output_path))
        except OSError as exc:
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
            _logger.exception("Failed to write notebook to %s", output_path)
            return ExportResult(
                success=False,
                message=f"Failed to write notebook: {exc}",
            )

        _logger.info(
            "Generated notebook %s — %d cells",
            output_path,
            len(nb.cells),
        )

        return ExportResult(
            success=True,
            message=f"Jupyter notebook generated: {filename}",
            url=str(output_path),
            external_id=filename,
            details={
                "output_path": str(output_path),
                "cell_count": len(nb.cells),
                "include_viz": include_viz,
                "include_raw_data": include_raw_data,
            },
        )


# Register at import time
register_connector(JupyterConnector())
