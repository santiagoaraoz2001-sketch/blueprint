"""Response models for system endpoints."""

from pydantic import BaseModel
from typing import Any


class FeatureFlagsResponse(BaseModel):
    """Feature flags for the application."""
    marketplace: bool


class SystemMetricsResponse(BaseModel):
    """Live system resource metrics."""
    cpu_percent: float
    memory_percent: float
    memory_gb: float
    memory_total_gb: float
    gpu_percent: float | None = None


class CapabilitiesResponse(BaseModel):
    """ML capabilities derived from hardware profile."""
    gpu_available: bool
    gpu_backend: str
    max_vram_gb: float
    usable_memory_gb: float
    max_model_size: str
    can_fine_tune: bool
    can_run_local_llm: bool
    disk_ok: bool
    accelerators: dict[str, Any]


class BenchmarkRefreshResponse(BaseModel):
    """Returned after refreshing benchmark cache."""
    status: str
    entries: int


class ScheduleStage(BaseModel):
    """A single stage in a parallel execution schedule."""
    stage: int
    blocks: list[str]
    label: str | None = None


class ScheduleResponse(BaseModel):
    """Returned from the parallel schedule endpoint."""
    stages: list[dict[str, Any]]
    total_stages: int
    max_parallelism: int


class DependencySummary(BaseModel):
    """Summary of dependency health across all blocks."""
    total_blocks: int
    ready_blocks: int
    missing_packages: list[str]
    in_virtual_env: bool


class PackageStatus(BaseModel):
    """Status of a single Python package."""
    package: str
    installed: bool
    version: str | None = None


class BlockDepStatus(BaseModel):
    """Dependency status for a single block."""
    ready: bool
    total_deps: int
    missing: list[str]
    install_command: str | None = None


class DependencyCheckResponse(BaseModel):
    """Full dependency health report."""
    summary: DependencySummary
    packages: dict[str, PackageStatus]
    blocks: dict[str, BlockDepStatus]


class InstallResponse(BaseModel):
    """Returned after installing packages."""
    success: bool
    stdout: str = ""
    stderr: str = ""
    installed: list[str] = []
    error: str | None = None


class DiagnosticsResponse(BaseModel):
    """Run diagnostics from structured logs."""
    run_id: str
    events: list[dict[str, Any]]
    event_count: int
    truncated: bool = False
    max_events: int | None = None
