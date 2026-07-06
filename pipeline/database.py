from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .config import AppConfig
from .models import Base


def is_sqlite_url(database_url: str) -> bool:
    return database_url.startswith("sqlite:///")


def normalize_engine_url(database_url: str) -> str:
    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql+psycopg://", 1)
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    return database_url


def int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def create_app_engine(config: AppConfig) -> Engine:
    database_url = normalize_engine_url(config.app_database_url)
    if is_sqlite_url(database_url):
        db_path = Path(database_url.removeprefix("sqlite:///"))
        db_path.parent.mkdir(parents=True, exist_ok=True)
        return create_engine(
            database_url,
            future=True,
            connect_args={"check_same_thread": False},
        )
    return create_engine(
        database_url,
        future=True,
        pool_pre_ping=True,
        pool_recycle=int_env("APP_DB_POOL_RECYCLE_SECONDS", 1800),
        pool_size=max(1, int_env("APP_DB_POOL_SIZE", 5)),
        max_overflow=max(0, int_env("APP_DB_MAX_OVERFLOW", 10)),
    )


def init_database(engine: Engine) -> None:
    Base.metadata.create_all(engine)
    ensure_task_job_columns(engine)


def ensure_task_job_columns(engine: Engine) -> None:
    inspector = inspect(engine)
    if "task_jobs" not in inspector.get_table_names():
        return
    existing_columns = {column["name"] for column in inspector.get_columns("task_jobs")}
    column_sql = {
        "celery_task_id": "VARCHAR(255) DEFAULT ''",
        "queue_name": "VARCHAR(80) DEFAULT 'default'",
        "priority": "INTEGER DEFAULT 5",
        "retry_count": "INTEGER DEFAULT 0",
        "max_retries": "INTEGER DEFAULT 3",
    }
    with engine.begin() as connection:
        for name, definition in column_sql.items():
            if name not in existing_columns:
                connection.execute(text(f"ALTER TABLE task_jobs ADD COLUMN {name} {definition}"))


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


@contextmanager
def session_scope(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
