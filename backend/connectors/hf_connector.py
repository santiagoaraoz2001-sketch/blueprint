"""Hugging Face Hub export connector.

Pushes model artifacts and an auto-generated model card to the HF Hub.
"""

import logging
from datetime import datetime, timezone
from pathlib import Path

from ..block_sdk.exceptions import BlockDependencyError
from .base import BaseConnector, ConnectorConfig, ExportResult
from .registry import register_connector

_logger = logging.getLogger("blueprint.connectors.huggingface")


# ---------------------------------------------------------------------------
# Model card generation
# ---------------------------------------------------------------------------

def _escape_md_table(value: str) -> str:
    """Escape characters that break Markdown table cells."""
    return value.replace("|", "\\|").replace("\n", " ")


def _format_config_value(val, max_len: int = 200) -> str:
    """Format a config value for display in the model card.

    Collapses large structures to avoid overwhelming the card.
    """
    if isinstance(val, (list, tuple)):
        if len(val) > 5:
            return f"[{len(val)} items]"
        rep = repr(val)
    elif isinstance(val, dict):
        if len(val) > 5:
            return f"{{...{len(val)} keys}}"
        rep = repr(val)
    else:
        rep = repr(val)

    if len(rep) > max_len:
        return rep[: max_len - 3] + "..."
    return rep


def _generate_model_card(run_export: dict, repo_id: str, license_id: str) -> str:
    """Build a Markdown model card from run export metadata."""
    run_info = run_export.get("run", {})
    config = run_export.get("config", {})
    summary = run_export.get("metrics", {}).get("summary", {})
    env = run_export.get("environment", {})
    provenance = run_export.get("data_provenance", {})

    model_name = repo_id.split("/")[-1] if "/" in repo_id else repo_id

    # YAML front-matter
    lines = [
        "---",
        f"license: {license_id}",
        "tags:",
        "  - blueprint",
        "---",
        "",
        f"# {model_name}",
        "",
        "This model was trained and exported using Blueprint.",
        "",
        "## Provenance",
        "",
        f"- **Blueprint Run ID:** `{run_info.get('id', 'N/A')}`",
        f"- **Pipeline ID:** `{run_info.get('pipeline_id', 'N/A')}`",
        f"- **Status:** {run_info.get('status', 'N/A')}",
        f"- **Exported at:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
    ]

    # Training configuration
    if config:
        lines.append("## Training Configuration")
        lines.append("")
        lines.append("```python")
        for key, val in config.items():
            lines.append(f"{key}: {_format_config_value(val)}")
        lines.append("```")
        lines.append("")

    # Benchmark results
    if summary:
        lines.append("## Benchmark Results")
        lines.append("")
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        for metric, value in summary.items():
            safe_metric = _escape_md_table(str(metric))
            if isinstance(value, float):
                lines.append(f"| {safe_metric} | {value:.4f} |")
            else:
                safe_value = _escape_md_table(str(value))
                lines.append(f"| {safe_metric} | {safe_value} |")
        lines.append("")

    # Environment
    if env:
        lines.append("## Environment")
        lines.append("")
        for k, v in env.items():
            lines.append(f"- **{k}:** {v}")
        lines.append("")

    # Data provenance
    if provenance:
        lines.append("## Data Provenance")
        lines.append("")
        for k, v in provenance.items():
            lines.append(f"- **{k}:** `{v}`")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Connector
# ---------------------------------------------------------------------------


class HuggingFaceConnector(BaseConnector):
    """Export connector for Hugging Face Hub."""

    @property
    def name(self) -> str:
        return "huggingface"

    @property
    def display_name(self) -> str:
        return "Hugging Face Hub"

    @property
    def description(self) -> str:
        return "Push model artifacts and an auto-generated model card to the Hugging Face Hub."

    def get_config_fields(self) -> list[ConnectorConfig]:
        return [
            ConnectorConfig(
                name="hf_token",
                label="HF Token",
                type="password",
                required=True,
                description="Hugging Face API token with write access.",
            ),
            ConnectorConfig(
                name="repo_id",
                label="Repository ID",
                type="string",
                required=True,
                description="Target repo (e.g. 'MyOrg/my-model').",
            ),
            ConnectorConfig(
                name="private",
                label="Private Repository",
                type="select",
                required=False,
                default="true",
                options=["true", "false"],
                description="Whether the repository should be private.",
            ),
            ConnectorConfig(
                name="commit_message",
                label="Commit Message",
                type="string",
                required=False,
                default="",
                description="Custom commit message. Auto-generated if blank.",
            ),
            ConnectorConfig(
                name="license",
                label="License",
                type="string",
                required=False,
                default="apache-2.0",
                description="SPDX license identifier for the model card.",
            ),
        ]

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate_config(self, config: dict) -> tuple[bool, str]:
        hf_token = (config.get("hf_token") or "").strip()
        if not hf_token:
            return False, "Hugging Face token is required."

        repo_id = (config.get("repo_id") or "").strip()
        if not repo_id:
            return False, "Repository ID is required."

        # repo_id should look like "owner/model-name" or just "model-name"
        # (HF allows both, but warn on obviously invalid formats).
        if repo_id.startswith("/") or repo_id.endswith("/") or "//" in repo_id:
            return False, (
                f"Invalid repository ID '{repo_id}'. "
                "Expected format: 'owner/model-name' or 'model-name'."
            )

        try:
            import huggingface_hub  # noqa: F401
        except ImportError:
            return False, (
                "The 'huggingface_hub' package is not installed. "
                "Install it with: pip install huggingface_hub"
            )

        return True, ""

    # ------------------------------------------------------------------
    # Connectivity test
    # ------------------------------------------------------------------

    def test_connection(self, config: dict) -> tuple[bool, str]:
        valid, err = self.validate_config(config)
        if not valid:
            return False, err

        try:
            from huggingface_hub import HfApi
        except ImportError:
            return False, "huggingface_hub package is not installed."

        hf_token = config["hf_token"].strip()
        try:
            api = HfApi(token=hf_token)
            info = api.whoami()
            username = info.get("name", "unknown")
            return True, f"Connected to Hugging Face Hub as '{username}'."
        except Exception as exc:
            return False, f"Failed to connect to HF Hub: {exc}"

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def export(self, run_export: dict, config: dict) -> ExportResult:
        try:
            from huggingface_hub import CommitOperationAdd, HfApi
        except ImportError:
            raise BlockDependencyError(
                dependency="huggingface_hub",
                install_hint="pip install huggingface_hub",
            )

        hf_token = config["hf_token"].strip()
        repo_id = config["repo_id"].strip()
        private = (config.get("private", "true")).lower() == "true"
        commit_msg = (config.get("commit_message") or "").strip()
        license_id = (config.get("license") or "apache-2.0").strip()

        run_info = run_export.get("run", {})
        run_id = run_info.get("id", "unknown")

        if not commit_msg:
            commit_msg = f"Upload from Blueprint run {run_id}"

        api = HfApi(token=hf_token)

        # --- create / ensure repo exists ----------------------------
        try:
            api.create_repo(
                repo_id=repo_id,
                private=private,
                exist_ok=True,
            )
        except Exception as exc:
            _logger.warning("HF create_repo failed for '%s': %s", repo_id, exc)
            return ExportResult(
                success=False,
                message=f"Failed to create or access repository '{repo_id}': {exc}",
            )

        # --- build commit operations --------------------------------
        # Batch model card + artifacts into a single atomic commit.
        model_card = _generate_model_card(run_export, repo_id, license_id)
        operations: list[CommitOperationAdd] = [
            CommitOperationAdd(
                path_in_repo="README.md",
                path_or_fileobj=model_card.encode("utf-8"),
            ),
        ]

        artifacts = run_export.get("artifacts", [])
        skipped: list[str] = []
        for art in artifacts:
            path = art.get("path", "")
            art_name = art.get("name", "")
            if not path or not art_name:
                continue
            if not Path(path).exists():
                skipped.append(art_name)
                _logger.warning("Artifact not found, skipping: %s", path)
                continue
            operations.append(
                CommitOperationAdd(
                    path_in_repo=art_name,
                    path_or_fileobj=path,
                ),
            )

        artifacts_uploaded = len(operations) - 1  # exclude the README

        # --- push single commit -------------------------------------
        try:
            commit_info = api.create_commit(
                repo_id=repo_id,
                operations=operations,
                commit_message=commit_msg,
            )
        except Exception as exc:
            _logger.exception("HF create_commit failed for '%s'", repo_id)
            return ExportResult(
                success=False,
                message=f"Failed to push to '{repo_id}': {exc}",
            )

        hub_url = f"https://huggingface.co/{repo_id}"
        commit_url = getattr(commit_info, "commit_url", hub_url)

        _logger.info(
            "Pushed to HF Hub '%s' — %d artifacts, %d skipped",
            repo_id,
            artifacts_uploaded,
            len(skipped),
        )

        details: dict = {
            "repo_id": repo_id,
            "private": private,
            "artifacts_uploaded": artifacts_uploaded,
            "model_card_generated": True,
            "commit_url": commit_url,
        }
        if skipped:
            details["skipped_artifacts"] = skipped

        return ExportResult(
            success=True,
            message=f"Model pushed to Hugging Face Hub: {repo_id}",
            url=hub_url,
            external_id=repo_id,
            details=details,
        )


# Register at import time
register_connector(HuggingFaceConnector())
