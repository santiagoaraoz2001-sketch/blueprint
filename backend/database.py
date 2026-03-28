import logging
import os

from sqlalchemy import create_engine, event as sa_event, inspect
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from .config import DATABASE_URL, DB_PATH, ensure_dirs

logger = logging.getLogger("blueprint.database")

ensure_dirs()

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    pool_pre_ping=True,
    echo=False,
)


@sa_event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_conn, connection_record):
    """Enable WAL mode and performance-safe PRAGMAs for concurrent access.

    All PRAGMAs are individually wrapped to gracefully handle environments
    where the database path is unavailable (e.g., in-memory test databases).
    """
    cursor = dbapi_conn.cursor()
    for pragma in [
        "PRAGMA journal_mode=WAL",
        "PRAGMA busy_timeout=5000",
        "PRAGMA synchronous=NORMAL",       # Safe in WAL mode, major write speedup
        "PRAGMA cache_size=-65536",         # 64MB page cache (vs default 2MB)
        "PRAGMA temp_store=MEMORY",         # Keep temp tables in RAM
        "PRAGMA mmap_size=268435456",       # 256MB memory-mapped I/O
        "PRAGMA foreign_keys=ON",           # Enforce referential integrity
    ]:
        try:
            cursor.execute(pragma)
        except Exception:
            pass
    cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _db_has_tables() -> bool:
    """Check whether the database file exists and contains any tables."""
    if not DB_PATH.exists():
        return False
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    return len(tables) > 0


def init_db():
    """Initialize the database schema.

    Behavior:
    - Fresh install (no tables): Use Base.metadata.create_all() and stamp
      Alembic to HEAD so future migrations start from the right place.
    - Existing database (has tables): Run Alembic migrations only. If
      migration fails, raise RuntimeError — never fall back to create_all()
      which could silently create an inconsistent schema.
    """
    # Import all models so they register with Base.metadata
    from .models import project, experiment, experiment_phase, pipeline, pipeline_version, run, dataset, artifact, paper, sweep, workspace, preset, pipeline_sequence, execution_decision, model_record  # noqa: F401

    has_tables = _db_has_tables()

    if not has_tables:
        # Fresh install — create all tables from current models
        logger.info("Fresh database detected — creating schema from models")
        Base.metadata.create_all(bind=engine)

        # Stamp Alembic HEAD so future migrations work correctly
        try:
            from alembic.config import Config
            from alembic import command

            alembic_cfg = Config(os.path.join(os.path.dirname(__file__), "alembic.ini"))
            command.stamp(alembic_cfg, "head")
            logger.info("Stamped Alembic revision to HEAD")
        except Exception as exc:
            logger.warning(
                "Could not stamp Alembic HEAD (non-critical for fresh install): %s",
                exc,
            )
    else:
        # Existing database — must use Alembic migrations
        logger.info("Existing database detected — running Alembic migrations")
        try:
            from alembic.config import Config
            from alembic import command

            alembic_cfg = Config(os.path.join(os.path.dirname(__file__), "alembic.ini"))
            command.upgrade(alembic_cfg, "head")
            logger.info("Alembic migrations completed successfully")
        except Exception as exc:
            raise RuntimeError(
                f"Database migration failed. Run: alembic upgrade head. Error: {exc}"
            ) from exc
