from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .config import AppConfig
from .models import Base


def create_app_engine(config: AppConfig) -> Engine:
    if config.app_database_url.startswith("sqlite:///"):
        db_path = Path(config.app_database_url.removeprefix("sqlite:///"))
        db_path.parent.mkdir(parents=True, exist_ok=True)
    return create_engine(config.app_database_url, future=True)


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
