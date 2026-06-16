#!/usr/bin/env python3
"""Run SQL migration files against PostgreSQL."""

import argparse
import os
import sys
from pathlib import Path

import psycopg


MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"


def get_database_url() -> str:
    return os.getenv(
        "DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5432/dingtalk_attendance",
    )


def run_sql_file(connection, sql_path: Path) -> None:
    sql = sql_path.read_text(encoding="utf-8")
    with connection.cursor() as cursor:
        cursor.execute(sql)
    connection.commit()
    print(f"Applied: {sql_path.name}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run PostgreSQL migrations")
    parser.add_argument(
        "direction",
        choices=["up", "down"],
        help="Apply up migration or rollback down migration",
    )
    parser.add_argument(
        "--file",
        default="001_initial_schema",
        help="Migration base name without .up.sql/.down.sql suffix",
    )
    args = parser.parse_args()

    suffix = ".up.sql" if args.direction == "up" else ".down.sql"
    migration_file = MIGRATIONS_DIR / f"{args.file}{suffix}"
    if not migration_file.exists():
        print(f"Migration file not found: {migration_file}", file=sys.stderr)
        return 1

    database_url = get_database_url()
    try:
        with psycopg.connect(database_url) as connection:
            run_sql_file(connection, migration_file)
    except psycopg.Error as exc:
        print(f"Migration failed: {exc}", file=sys.stderr)
        return 1

    print("Migration completed successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
