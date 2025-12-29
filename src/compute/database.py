"""Database configuration with WAL mode support for multi-process access."""

from __future__ import annotations

import logging
from collections.abc import Callable, Generator
from pathlib import Path

from alembic import command
from alembic.config import Config as AlembicConfig
from cl_server_shared.config import Config
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine.interfaces import DBAPIConnection
from sqlalchemy.orm import Session, sessionmaker

logger = logging.getLogger(__name__)


def enable_wal_mode(
    dbapi_conn: DBAPIConnection,
    connection_record: object,
) -> None:
    """Enable WAL mode and set optimization pragmas for SQLite.

    This function should be registered as an event listener on SQLite engines.
    WAL mode enables concurrent reads and single writer, critical for multi-process access.
    """
    _ = connection_record
    cursor = dbapi_conn.cursor()
    try:
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA cache_size=-64000")
        cursor.execute("PRAGMA temp_store=MEMORY")
        cursor.execute("PRAGMA mmap_size=30000000000")
        cursor.execute("PRAGMA wal_autocheckpoint=1000")
        cursor.execute("PRAGMA busy_timeout=10000")
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


def create_db_engine(
    database_url: str,
    *,
    echo: bool = False,
) -> Engine:
    """Create SQLAlchemy engine with WAL mode for SQLite.

    Args:
        database_url: Database URL (SQLite or other)
        echo: Enable SQL query logging

    Returns:
        SQLAlchemy engine instance
    """
    engine = create_engine(
        database_url,
        connect_args={"check_same_thread": False},
        echo=echo,
    )

    # Register WAL mode listener for SQLite
    if database_url.lower().startswith("sqlite"):
        event.listen(engine, "connect", enable_wal_mode)

    return engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Create session factory from engine.

    Args:
        engine: SQLAlchemy engine

    Returns:
        Session factory
    """
    return sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        class_=Session,
    )


def get_db_session(
    session_factory: Callable[[], Session],
) -> Generator[Session, None, None]:
    """Database session dependency for FastAPI.

    Args:
        session_factory: Session factory callable

    Yields:
        Database session
    """
    db = session_factory()
    try:
        yield db
    finally:
        db.close()


# Create engine with WAL mode - use WORKER_DATABASE_URL for task management
engine = create_db_engine(Config.WORKER_DATABASE_URL, echo=False)

SessionLocal: sessionmaker[Session] = create_session_factory(engine)


def get_db() -> Generator[Session, None, None]:
    """Get database session for FastAPI dependency injection."""
    yield from get_db_session(SessionLocal)


def run_migrations() -> None:
    """Run Alembic migrations to ensure database schema is up to date.

    This function should be called on server/worker startup to automatically
    apply any pending migrations.

    Raises:
        FileNotFoundError: If alembic.ini, versions directory, or migrations not found
        RuntimeError: If migrations fail to run
    """
    # Find alembic.ini in the package directory
    package_dir = Path(__file__).parent.parent.parent
    alembic_ini = package_dir / "alembic.ini"

    if not alembic_ini.exists():
        msg = (
            f"alembic.ini not found at {alembic_ini}\n"
            "Database migrations cannot be run without alembic configuration."
        )
        logger.error(msg)
        raise FileNotFoundError(msg)

    # Check versions directory exists
    versions_dir = package_dir / "alembic" / "versions"
    if not versions_dir.exists():
        msg = (
            f"Alembic versions directory not found at {versions_dir}\n"
            "Please create it with: mkdir -p alembic/versions"
        )
        logger.error(msg)
        raise FileNotFoundError(msg)

    # Check that at least one migration exists
    migration_files = list(versions_dir.glob("*.py"))
    # Filter out __pycache__ and __init__.py
    migration_files = [f for f in migration_files if f.name != "__init__.py"]
    if not migration_files:
        msg = (
            f"No migration files found in {versions_dir}\n"
            "Please create an initial migration with:\n"
            "  uv run alembic revision --autogenerate -m 'initial schema'"
        )
        logger.error(msg)
        raise FileNotFoundError(msg)

    # Create Alembic config and run migrations
    alembic_cfg = AlembicConfig(str(alembic_ini))
    alembic_cfg.set_main_option("script_location", str(package_dir / "alembic"))

    try:
        logger.info("Running database migrations...")
        command.upgrade(alembic_cfg, "head")
        logger.info("Database migrations completed successfully")
    except Exception as e:
        msg = f"Failed to run database migrations: {e}"
        logger.error(msg)
        raise RuntimeError(msg) from e
