"""Conftest for block-level tests — re-exports fixtures from block_test_helpers."""

from .block_test_helpers import live_backend, ollama_model  # noqa: F401
