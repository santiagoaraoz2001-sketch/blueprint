"""
Planner Data Models — immutable (frozen) dataclasses for the unified execution planner.

These models represent the output of the planning phase: a fully resolved,
deterministic execution plan that the executor can run without further graph
analysis.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ResolvedNode:
    """A single node fully resolved for execution."""

    node_id: str
    block_type: str
    block_version: str
    resolved_config: dict[str, Any]
    config_sources: dict[str, str]  # config key -> origin: 'user'|'workspace'|'inherited:<node_id>'|'block_default'
    cache_fingerprint: str
    cache_eligible: bool
    in_loop: bool
    loop_id: str | None


@dataclass(frozen=True)
class LoopBoundary:
    """Describes a valid loop subgraph identified during planning.

    A loop may have multiple feedback edges when the loop body branches and
    multiple paths converge back to the controller (e.g. a branch that
    produces text and another that produces metrics, both feeding back).
    All such edges must be excluded from the DAG before topological sorting.
    """

    controller_node_id: str
    body_node_ids: tuple[str, ...]
    feedback_edges: tuple[tuple[str, str], ...]  # all (source, target) edges from body → controller
    max_iterations: int


@dataclass(frozen=True)
class ExecutionPlan:
    """The complete, immutable execution plan produced by the planner."""

    execution_order: tuple[str, ...]
    nodes: dict[str, ResolvedNode]
    loops: tuple[LoopBoundary, ...]
    independent_subgraphs: tuple[tuple[str, ...], ...]
    plan_hash: str
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class PlannerResult:
    """Wrapper returned by the planner: either a valid plan or errors."""

    is_valid: bool
    errors: tuple[str, ...]
    plan: ExecutionPlan | None
