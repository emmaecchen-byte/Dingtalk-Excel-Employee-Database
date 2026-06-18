from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.database import Base, engine


def _sqlite_table_exists(engine: Engine, table_name: str) -> bool:
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name=:name"),
            {"name": table_name},
        ).first()
    return row is not None


def _sqlite_column_names(engine: Engine, table_name: str) -> set:
    if not _sqlite_table_exists(engine, table_name):
        return set()
    with engine.connect() as conn:
        rows = conn.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
    return {row[1] for row in rows}


def ensure_auth_schema() -> None:
    Base.metadata.create_all(bind=engine)

    if engine.dialect.name == "sqlite":
        user_columns = _sqlite_column_names(engine, "users")
        attendance_columns = _sqlite_column_names(engine, "monthly_attendance")
        with engine.begin() as conn:
            if "password_hash" not in user_columns:
                conn.execute(text("ALTER TABLE users ADD COLUMN password_hash VARCHAR(255)"))
            if "is_active" not in user_columns:
                conn.execute(text("ALTER TABLE users ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT 1"))
            if "total_compensatory_leave" not in attendance_columns:
                conn.execute(
                    text(
                        "ALTER TABLE monthly_attendance "
                        "ADD COLUMN total_compensatory_leave NUMERIC(5, 1) NOT NULL DEFAULT 0"
                    )
                )
            if "manual_overrides" not in attendance_columns:
                conn.execute(
                    text(
                        "ALTER TABLE monthly_attendance "
                        "ADD COLUMN manual_overrides TEXT NOT NULL DEFAULT '{}'"
                    )
                )
            if "last_manual_edit" not in attendance_columns:
                conn.execute(text("ALTER TABLE monthly_attendance ADD COLUMN last_manual_edit DATETIME"))
            for day in range(1, 32):
                column = f"day_{day}"
                if column not in attendance_columns:
                    conn.execute(text(f"ALTER TABLE monthly_attendance ADD COLUMN {column} VARCHAR(50)"))
            for day in range(1, 32):
                column = f"overtime_day_{day}"
                if column not in attendance_columns:
                    conn.execute(
                        text(
                            f"ALTER TABLE monthly_attendance ADD COLUMN {column} NUMERIC(5, 1)"
                        )
                    )
            period_columns = _sqlite_column_names(engine, "attendance_periods")
            if period_columns:
                if "data_source" not in period_columns:
                    conn.execute(
                        text(
                            "ALTER TABLE attendance_periods "
                            "ADD COLUMN data_source VARCHAR(20) NOT NULL DEFAULT 'upload'"
                        )
                    )
                if "confirmed_by" not in period_columns:
                    conn.execute(text("ALTER TABLE attendance_periods ADD COLUMN confirmed_by INTEGER"))
                if "confirmed_at" not in period_columns:
                    conn.execute(text("ALTER TABLE attendance_periods ADD COLUMN confirmed_at DATETIME"))
                if "archived_by" not in period_columns:
                    conn.execute(text("ALTER TABLE attendance_periods ADD COLUMN archived_by INTEGER"))
                if "archived_at" not in period_columns:
                    conn.execute(text("ALTER TABLE attendance_periods ADD COLUMN archived_at DATETIME"))
