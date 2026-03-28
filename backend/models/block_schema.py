"""Pydantic models for the block registry — single source of truth for block metadata."""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field, field_validator


# All valid port data types
VALID_DATA_TYPES = frozenset({
    "text", "dataset", "model", "embedding", "metrics",
    "artifact", "config", "any", "llm", "number", "boolean", "file_path",
    "agent",
})


# Valid values for PortSchema.expected_type_family
VALID_TYPE_FAMILIES = frozenset({"dict", "str", "list", "path", "any"})

# Valid values for PortSchema.cardinality
VALID_CARDINALITIES = frozenset({"scalar", "list", "any"})

# Valid values for PortSchema.multi_input
VALID_MULTI_INPUT_MODES = frozenset({"aggregate", "last_write", "error"})


class PortSchema(BaseModel):
    """Schema for a single input or output port on a block."""
    id: str
    label: str
    data_type: str
    required: bool = False
    default: Any = None
    aliases: list[str] = Field(default_factory=list)
    description: str = ""
    position: str | None = None
    expected_type_family: str = "any"
    cardinality: str = "any"
    multi_input: str = "aggregate"


class ConfigField(BaseModel):
    """Schema for a single configuration field on a block."""
    key: str
    label: str
    type: str
    default: Any = None
    required: bool = False
    options: list[str] = Field(default_factory=list)
    min: float | None = None
    max: float | None = None
    description: str = ""
    propagate: bool = False
    section: str = ""
    depends_on: dict[str, Any] | None = None
    path_mode: str | None = None
    file_extensions: list[str] = Field(default_factory=list)


# Simple semver pattern: major.minor.patch with optional pre-release
_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-+].+)?$")


class BlockSchema(BaseModel):
    """Complete metadata for a single block — parsed from block.yaml."""
    block_type: str
    category: str
    label: str
    description: str = ""
    version: str = "0.0.0"
    inputs: list[PortSchema] = Field(default_factory=list)
    outputs: list[PortSchema] = Field(default_factory=list)
    config: list[ConfigField] = Field(default_factory=list)
    side_inputs: list[PortSchema] = Field(default_factory=list)
    source_type: str = "builtin"
    source_path: str = ""
    exportable: bool = True
    supports_partial_rerun: bool = True
    maturity: str = "stable"
    tags: list[str] = Field(default_factory=list)
    aliases: list[str] = Field(default_factory=list)
    icon: str = ""
    accent: str = ""
    deprecated: bool = False
    requires: list[str] = Field(default_factory=list)

    @field_validator("version")
    @classmethod
    def validate_version(cls, v: str) -> str:
        if v and not _SEMVER_RE.match(v):
            raise ValueError(f"Invalid semver version: {v!r}")
        return v
