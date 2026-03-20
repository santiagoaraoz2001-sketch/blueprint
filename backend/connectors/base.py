"""
Export Connector Base — interface for all export connectors.

Connectors push run data to external services. Each connector:
1. Declares its required config fields (e.g., API key, project name)
2. Validates the config before export
3. Exports run data using the structured export format
4. Returns a result with status and external URL (if applicable)
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ConnectorConfig:
    """Describes a single config field required by a connector.

    Attributes:
        name:  Machine-readable key (e.g. ``api_key``).
        label: Human-readable label (e.g. ``API Key``).
        type:  Field type — ``string``, ``password``, or ``select``.
        required: Whether the field must be provided.
        default:  Default value shown in the UI.
        description: Help text for the field.
        options: Valid choices when ``type`` is ``select``.  ``None`` for
                 non-select fields.
    """
    name: str
    label: str
    type: str = "string"
    required: bool = True
    default: Any = ""
    description: str = ""
    options: Optional[list[str]] = None


@dataclass
class ExportResult:
    """Result returned by a connector after an export attempt.

    Attributes:
        success: Whether the export completed without error.
        message: Human-readable status message.
        url: Link to the exported resource in the external service.
        external_id: ID of the resource in the external system.
        details: Arbitrary extra metadata the connector wants to surface.
    """
    success: bool
    message: str
    url: Optional[str] = None
    external_id: Optional[str] = None
    details: dict = field(default_factory=dict)


class BaseConnector(ABC):
    """Base class for all export connectors.

    Subclasses must implement:
    - ``name``, ``display_name``, ``description`` properties
    - ``get_config_fields()`` — declare required config
    - ``validate_config(config)`` — validate before export
    - ``export(run_export, config)`` — perform the export
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier (e.g., 'wandb', 'huggingface', 'jupyter')."""
        ...

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable name (e.g., 'Weights & Biases')."""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """Short description of what this connector does."""
        ...

    @abstractmethod
    def get_config_fields(self) -> list[ConnectorConfig]:
        """Return the config fields this connector needs."""
        ...

    @abstractmethod
    def validate_config(self, config: dict) -> tuple[bool, str]:
        """Validate connector config.

        Returns:
            A ``(valid, error_message)`` tuple.  When valid is ``True``
            the error message should be an empty string.
        """
        ...

    @abstractmethod
    def export(self, run_export: dict, config: dict) -> ExportResult:
        """Export a run to the external service.

        Args:
            run_export: The structured export dict produced by
                ``engine.run_export.generate_run_export``.
            config: User-provided connector config (already validated).
        """
        ...

    def test_connection(self, config: dict) -> tuple[bool, str]:
        """Test connectivity to the external service.

        Subclasses can override to perform a real connectivity check (e.g.,
        list projects, verify token scope).  The default implementation
        delegates to ``validate_config`` which only checks field presence
        and package availability.

        Returns:
            A ``(reachable, message)`` tuple.
        """
        return self.validate_config(config)

    def to_dict(self) -> dict:
        """Serialize connector metadata for API responses."""
        return {
            "name": self.name,
            "display_name": self.display_name,
            "description": self.description,
            "config_fields": [
                {
                    "name": f.name,
                    "label": f.label,
                    "type": f.type,
                    "required": f.required,
                    "default": f.default,
                    "description": f.description,
                    **({"options": f.options} if f.options is not None else {}),
                }
                for f in self.get_config_fields()
            ],
        }
