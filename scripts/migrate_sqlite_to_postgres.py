from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import Integer, create_engine, func, inspect, select, text
from sqlalchemy.engine import Connection, Engine

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.config import BASE_DIR, normalize_sqlite_url  # noqa: E402
from pipeline.database import init_database, normalize_engine_url  # noqa: E402
from pipeline.models import Base  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Migrate content_pipeline data from SQLite to PostgreSQL.",
    )
    parser.add_argument(
        "--sqlite-url",
        default=os.getenv("SQLITE_DATABASE_URL", f"sqlite:///{(BASE_DIR / 'data' / 'pipeline.db').as_posix()}"),
        help="Source SQLite SQLAlchemy URL.",
    )
    parser.add_argument(
        "--postgres-url",
        default=os.getenv("POSTGRES_DATABASE_URL") or os.getenv("APP_DATABASE_URL"),
        help="Target PostgreSQL SQLAlchemy URL. Can also be set with POSTGRES_DATABASE_URL or APP_DATABASE_URL.",
    )
    parser.add_argument(
        "--truncate-target",
        action="store_true",
        help="Delete existing target rows before importing.",
    )
    return parser.parse_args()


def create_source_engine(sqlite_url: str) -> Engine:
    if not sqlite_url.startswith("sqlite:///"):
        raise ValueError("--sqlite-url must be a sqlite:/// URL")
    return create_engine(normalize_sqlite_url(sqlite_url), future=True)


def create_target_engine(postgres_url: str | None) -> Engine:
    if not postgres_url:
        raise ValueError("--postgres-url is required")
    normalized_url = normalize_engine_url(postgres_url)
    if not normalized_url.startswith("postgresql"):
        raise ValueError("--postgres-url must be a PostgreSQL URL")
    return create_engine(normalized_url, future=True, pool_pre_ping=True)


def table_count(connection: Connection, table: Any) -> int:
    return int(connection.execute(select(func.count()).select_from(table)).scalar_one())


def ensure_target_is_empty(engine: Engine) -> None:
    with engine.connect() as connection:
        non_empty_tables = [
            table.name
            for table in Base.metadata.sorted_tables
            if inspect(engine).has_table(table.name) and table_count(connection, table) > 0
        ]
    if non_empty_tables:
        joined = ", ".join(non_empty_tables)
        raise RuntimeError(
            f"Target database already contains data in: {joined}. "
            "Re-run with --truncate-target only after backing up the target database."
        )


def truncate_target(engine: Engine) -> None:
    with engine.begin() as connection:
        for table in reversed(Base.metadata.sorted_tables):
            if inspect(engine).has_table(table.name):
                connection.execute(table.delete())


def rows_from_source(connection: Connection, table: Any) -> list[dict[str, Any]]:
    source_columns = {column["name"] for column in inspect(connection).get_columns(table.name)}
    selected_columns = [table.c[name] for name in table.c.keys() if name in source_columns]
    if not selected_columns:
        return []
    return [dict(row._mapping) for row in connection.execute(select(*selected_columns)).all()]


def reset_postgres_sequence(connection: Connection, table: Any) -> None:
    if "id" not in table.c:
        return
    if not isinstance(table.c.id.type, Integer):
        return
    max_id = connection.execute(select(func.max(table.c.id))).scalar()
    if max_id is None:
        return
    connection.execute(
        text(
            """
            SELECT setval(sequence_name, :next_value, true)
            FROM (
                SELECT pg_get_serial_sequence(:table_name, 'id') AS sequence_name
            ) AS sequence_info
            WHERE sequence_name IS NOT NULL
            """
        ),
        {"table_name": table.name, "next_value": int(max_id)},
    )


def migrate(source_engine: Engine, target_engine: Engine, truncate: bool) -> None:
    init_database(target_engine)
    if truncate:
        truncate_target(target_engine)
    else:
        ensure_target_is_empty(target_engine)

    with source_engine.connect() as source, target_engine.begin() as target:
        source_tables = set(inspect(source_engine).get_table_names())
        for table in Base.metadata.sorted_tables:
            if table.name not in source_tables:
                print(f"skip {table.name}: source table does not exist")
                continue
            rows = rows_from_source(source, table)
            if not rows:
                print(f"skip {table.name}: no rows")
                continue
            target.execute(table.insert(), rows)
            reset_postgres_sequence(target, table)
            print(f"copied {table.name}: {len(rows)} rows")


def main() -> int:
    args = parse_args()
    source_engine = create_source_engine(args.sqlite_url)
    target_engine = create_target_engine(args.postgres_url)
    migrate(source_engine, target_engine, args.truncate_target)
    print("migration complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
