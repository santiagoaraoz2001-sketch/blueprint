"""
Parameter Sweep — generates and manages grid/random search over config values.

Given a pipeline and a set of parameter ranges, generates all combinations
and executes each as a separate run. Results are aggregated into a comparison.
"""

import math
import random
import threading
from itertools import product
from typing import Any

# Safety limit to prevent accidental combinatorial explosion
MAX_GRID_COMBINATIONS = 500
MAX_RANDOM_SAMPLES = 200

# Supported random distribution types
DISTRIBUTION_TYPES = {"choice", "uniform", "log_uniform", "int_range"}


def generate_grid(ranges: dict[str, list[Any]]) -> list[dict[str, Any]]:
    """
    Generate all combinations from parameter ranges.

    ranges: {"lr": [1e-5, 5e-5, 1e-4], "batch_size": [2, 4, 8]}
    returns: [{"lr": 1e-5, "batch_size": 2}, {"lr": 1e-5, "batch_size": 4}, ...]

    Raises ValueError if the grid would exceed MAX_GRID_COMBINATIONS.
    """
    if not ranges:
        return []

    keys = list(ranges.keys())
    values = list(ranges.values())

    # Validate: each parameter must have at least one value
    for key, vals in zip(keys, values):
        if not isinstance(vals, list) or len(vals) == 0:
            raise ValueError(f"Parameter '{key}' must have a non-empty list of values")

    # Guard against combinatorial explosion
    total = 1
    for vals in values:
        total *= len(vals)
        if total > MAX_GRID_COMBINATIONS:
            raise ValueError(
                f"Grid would produce {total}+ combinations "
                f"(limit: {MAX_GRID_COMBINATIONS}). "
                f"Reduce parameter values or use random search."
            )

    return [dict(zip(keys, combo)) for combo in product(*values)]


def generate_random(ranges: dict[str, dict], n_samples: int) -> list[dict[str, Any]]:
    """
    Generate random samples from parameter distributions.

    ranges: {
        "lr": {"type": "log_uniform", "min": 1e-6, "max": 1e-3},
        "batch_size": {"type": "choice", "values": [2, 4, 8, 16]},
        "dropout": {"type": "uniform", "min": 0.0, "max": 0.5},
        "epochs": {"type": "int_range", "min": 1, "max": 10},
    }

    Raises ValueError for invalid distribution specs or excessive sample count.
    """
    if not ranges:
        return []

    if n_samples <= 0:
        raise ValueError("n_samples must be positive")
    if n_samples > MAX_RANDOM_SAMPLES:
        raise ValueError(
            f"n_samples ({n_samples}) exceeds limit ({MAX_RANDOM_SAMPLES})"
        )

    # Validate all specs upfront before generating any samples
    for key, spec in ranges.items():
        if not isinstance(spec, dict) or "type" not in spec:
            raise ValueError(
                f"Parameter '{key}' must be a dict with a 'type' field"
            )
        dist_type = spec["type"]
        if dist_type not in DISTRIBUTION_TYPES:
            raise ValueError(
                f"Parameter '{key}' has unknown distribution type '{dist_type}'. "
                f"Supported: {sorted(DISTRIBUTION_TYPES)}"
            )
        if dist_type == "choice":
            if "values" not in spec or not spec["values"]:
                raise ValueError(f"Parameter '{key}' (choice) requires non-empty 'values' list")
        elif dist_type in ("uniform", "log_uniform", "int_range"):
            if "min" not in spec or "max" not in spec:
                raise ValueError(f"Parameter '{key}' ({dist_type}) requires 'min' and 'max'")
            if spec["min"] > spec["max"]:
                raise ValueError(f"Parameter '{key}' ({dist_type}): min > max")
            if dist_type == "log_uniform" and spec["min"] <= 0:
                raise ValueError(f"Parameter '{key}' (log_uniform): min must be > 0")

    samples = []
    for _ in range(n_samples):
        sample = {}
        for key, spec in ranges.items():
            dist_type = spec["type"]
            if dist_type == "choice":
                sample[key] = random.choice(spec["values"])
            elif dist_type == "uniform":
                sample[key] = random.uniform(spec["min"], spec["max"])
            elif dist_type == "log_uniform":
                log_min = math.log(spec["min"])
                log_max = math.log(spec["max"])
                sample[key] = math.exp(random.uniform(log_min, log_max))
            elif dist_type == "int_range":
                sample[key] = random.randint(int(spec["min"]), int(spec["max"]))
        samples.append(sample)
    return samples


def _sort_key(v: Any) -> tuple:
    """Sort key that handles mixed types (numbers, strings, None) without TypeError."""
    if v is None:
        return (0, "")
    if isinstance(v, (int, float)):
        return (1, v)
    return (2, str(v))


class SweepManager:
    """Manages a parameter sweep across multiple runs.

    Thread-safe: record_result can be called from multiple executor threads.
    """

    def __init__(
        self,
        sweep_id: str,
        pipeline_id: str,
        configs: list[dict],
        target_node_id: str,
        metric_name: str,
    ):
        self.sweep_id = sweep_id
        self.pipeline_id = pipeline_id
        self.configs = configs
        self.target_node_id = target_node_id
        self.metric_name = metric_name
        self.run_ids: list[str] = []
        self.results: list[dict] = []  # {config: {...}, metric: float, run_id: str}
        self._lock = threading.Lock()

    def record_result(self, run_id: str, config: dict, metric: float | None):
        """Record the result from a completed sweep run. Thread-safe."""
        with self._lock:
            self.results.append({
                "config": config,
                "metric": metric,
                "run_id": run_id,
            })

    def get_best(self, minimize: bool = True) -> dict | None:
        """Return the result with the best metric value."""
        with self._lock:
            scored = [r for r in self.results if r["metric"] is not None]
        if not scored:
            return None
        return (
            min(scored, key=lambda r: r["metric"])
            if minimize
            else max(scored, key=lambda r: r["metric"])
        )

    def to_heatmap_data(self, x_param: str, y_param: str) -> dict:
        """Format results as heatmap data for the frontend."""
        with self._lock:
            results_snapshot = list(self.results)

        x_values = sorted(
            set(r["config"].get(x_param) for r in results_snapshot),
            key=_sort_key,
        )
        y_values = sorted(
            set(r["config"].get(y_param) for r in results_snapshot),
            key=_sort_key,
        )

        grid = []
        for y in y_values:
            row = []
            for x in x_values:
                match = next(
                    (
                        r
                        for r in results_snapshot
                        if r["config"].get(x_param) == x
                        and r["config"].get(y_param) == y
                    ),
                    None,
                )
                row.append(match["metric"] if match else None)
            grid.append(row)

        return {
            "x_param": x_param,
            "y_param": y_param,
            "x_values": x_values,
            "y_values": y_values,
            "grid": grid,
            "best": self.get_best(),
        }

    def get_progress(self) -> dict:
        """Return sweep progress summary."""
        total = len(self.configs)
        with self._lock:
            completed = len(self.results)
        return {
            "total": total,
            "completed": completed,
            "pending": total - completed,
            "percent": (completed / total * 100) if total > 0 else 0,
        }
