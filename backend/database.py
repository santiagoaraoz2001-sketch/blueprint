from sqlalchemy import create_engine, event as sa_event
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from .config import DATABASE_URL, ensure_dirs

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


def init_db():
    # Import all models so they register with Base.metadata
    from .models import project, experiment, experiment_phase, pipeline, run, dataset, artifact, paper, sweep, workspace  # noqa: F401
    try:
        from alembic.config import Config
        from alembic import command
        import os
        alembic_cfg = Config(os.path.join(os.path.dirname(__file__), "alembic.ini"))
        command.upgrade(alembic_cfg, "head")
    except Exception:
        # Fallback for fresh installs or if alembic isn't available
        Base.metadata.create_all(bind=engine)
