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
    """Enable WAL mode for safe concurrent reads and busy timeout."""
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=5000")
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
    from .models import project, experiment, pipeline, run, dataset, artifact, paper  # noqa: F401
    try:
        from alembic.config import Config
        from alembic import command
        import os
        alembic_cfg = Config(os.path.join(os.path.dirname(__file__), "alembic.ini"))
        command.upgrade(alembic_cfg, "head")
    except Exception:
        # Fallback for fresh installs or if alembic isn't available
        Base.metadata.create_all(bind=engine)
