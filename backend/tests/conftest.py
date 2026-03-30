"""Shared pytest fixtures for backend integration tests.

Provides an isolated, temporary in-memory SQLite database for tests that
need real SQL operations without polluting the user's development database.

Usage in test files:

    def test_something(test_client):
        resp = test_client.get("/api/presets")
        assert resp.status_code == 200

The ``test_client`` fixture:
  - Spins up a fresh in-memory SQLite database with all tables created
  - Uses ``StaticPool`` so every connection shares the same in-memory DB
    (SQLite in-memory databases are per-connection without this)
  - Overrides FastAPI's ``get_db`` dependency to use the temp DB
  - Returns a ``TestClient`` bound to the app
  - Automatically tears down and clears dependency overrides per-test

For tests that only need the raw DB session (no HTTP layer):

    def test_model(test_db):
        test_db.add(SomeModel(...))
        test_db.commit()
"""

from __future__ import annotations

import sys
import os

import pytest
from sqlalchemy import create_engine, event as sa_event
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

# Ensure project root is importable
PROJECT_ROOT = os.path.join(os.path.dirname(__file__), '..', '..')
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


@pytest.fixture(scope="module")
def _isolated_engine():
    """Create an in-memory SQLite engine shared across one test module.

    ``StaticPool`` is critical: it forces a single underlying DBAPI
    connection so that tables created by ``create_all`` are visible to
    all subsequent sessions.  Without it, each pool checkout gets its
    own empty in-memory database.
    """
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @sa_event.listens_for(engine, "connect")
    def _set_pragmas(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    # Import ALL models so Base.metadata registers every table.
    # This mirrors the import list in backend/database.py:init_db().
    from backend.database import Base
    from backend.models import (  # noqa: F401
        project, experiment, experiment_phase, pipeline,
        run, dataset, artifact, paper, sweep, workspace,
    )
    from backend.models.preset import Preset  # noqa: F401

    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture(scope="module")
def _isolated_session_factory(_isolated_engine):
    """Session factory bound to the isolated engine."""
    return sessionmaker(autocommit=False, autoflush=False, bind=_isolated_engine)


@pytest.fixture()
def test_db(_isolated_session_factory) -> Session:
    """Yield a database session that rolls back after each test.

    Gives each test function a clean slate without re-creating tables.
    """
    session = _isolated_session_factory()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture()
def test_client(_isolated_session_factory) -> TestClient:
    """TestClient with ``get_db`` overridden to use the isolated database.

    Each test gets its own session.  Rows inserted during the test are
    rolled back afterward so tests don't leak state to each other.
    """
    from backend.database import get_db
    from backend.main import app

    session = _isolated_session_factory()

    def _override_get_db():
        try:
            yield session
        finally:
            pass  # Lifecycle managed by the fixture, not the generator

    app.dependency_overrides[get_db] = _override_get_db
    client = TestClient(app)
    try:
        yield client
    finally:
        session.rollback()
        session.close()
        app.dependency_overrides.pop(get_db, None)


# ── Block-level test fixtures (live server) ─────────────────────────
# Re-export from block_test_helpers so all test_blocks_*.py files can use them.
from .block_test_helpers import live_backend, ollama_model  # noqa: F401
