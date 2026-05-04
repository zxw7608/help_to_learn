from sqlmodel import SQLModel, create_engine, Session, text
from backend.config import settings
import subprocess

# Columns that alembic migrations add to the users table, in order.
# Each tuple: (migration_revision, column_name, column_type_sql)
_MIGRATION_COLUMNS = [
    # 2c6338faef8c — add_telegram_bot_token
    ("2c6338faef8c", "telegram_bot_token", "VARCHAR(256)"),
    ("2c6338faef8c", "anki_model_name", "VARCHAR(256) NOT NULL DEFAULT 'Basic'"),
    # 81d962b1773d — add_anki_connect_url_to_user
    ("81d962b1773d", "anki_connect_url", "VARCHAR(512) NOT NULL DEFAULT 'http://127.0.0.1:8765'"),
    # 9a1b2c3d4e5f — add_ai_config_and_analysis_records (columns only, table handled below)
    ("9a1b2c3d4e5f", "ai_base_url", "VARCHAR(512)"),
    ("9a1b2c3d4e5f", "ai_api_key", "VARCHAR(256)"),
    # a1b2c3d4e5f6 — add_ai_model_to_user
    ("a1b2c3d4e5f6", "ai_model", "VARCHAR(128)"),
    # b1c2d3e4f5a7 — add_ai_prompt_to_user
    ("b1c2d3e4f5a7", "ai_prompt", "TEXT(4096)"),
]

# Tables that migrations create (check existence before running migrate)
_MIGRATION_TABLES = [
    "analysis_records",
]


def _column_exists(session, table: str, column: str) -> bool:
    result = session.execute(
        text(f"PRAGMA table_info('{table}')")
    )
    return any(row[1] == column for row in result.fetchall())


def _table_exists(session, table: str) -> bool:
    result = session.execute(
        text("SELECT name FROM sqlite_master WHERE type='table' AND name=:name"),
        {"name": table},
    )
    return result.fetchone() is not None


def _add_missing_columns(engine) -> None:
    """Add any columns that alembic migrations would have added but are missing."""
    with Session(engine) as session:
        for revision, column, col_type in _MIGRATION_COLUMNS:
            if not _column_exists(session, "users", column):
                print(f"Adding missing column: users.{column}")
                # SQLite does not support full ALTER TABLE, but adding a
                # nullable column (or one with a constant default) is fine.
                session.execute(
                    text(f"ALTER TABLE users ADD COLUMN {column} {col_type}")
                )
                session.commit()

    # Create missing tables
    with Session(engine) as session:
        for table in _MIGRATION_TABLES:
            if not _table_exists(session, table):
                print(f"Table '{table}' missing — re-running create_all.")
                # Import all models so SQLModel.metadata knows about them
                from backend.models import user, material, segment, job, push_record, analysis_record  # noqa: F401
                SQLModel.metadata.create_all(engine)
                break  # create_all handles all missing tables at once


def _get_latest_applied_revision(engine) -> str | None:
    """Figure out the highest revision that has been fully applied."""
    with Session(engine) as session:
        applied = None
        for revision, column, _ in _MIGRATION_COLUMNS:
            if _column_exists(session, "users", column):
                applied = revision
            else:
                break
        return applied


def init_db():
    engine = create_engine(settings.DATABASE_URL)

    with Session(engine) as session:
        has_users = _table_exists(session, "users")
        alembic_exists = _table_exists(session, "alembic_version")

    if not has_users:
        # ── Fresh install ──────────────────────────────────────────────────
        print("New database. Creating all tables from models...")
        from backend.models import user, material, segment, job, push_record, analysis_record  # noqa: F401
        SQLModel.metadata.create_all(engine)
        print("Stamping alembic to head...")
        subprocess.run(["alembic", "stamp", "head"], check=True)
        print("Database initialized.")
        return

    if not alembic_exists:
        # ── Existing DB without alembic tracking ────────────────────────────
        print("Existing database without alembic version table. "
              "Adding missing columns...")
        _add_missing_columns(engine)

        # Stamp to the latest revision that has been applied
        latest = _get_latest_applied_revision(engine)
        if latest:
            print(f"Stamping alembic to {latest}...")
            subprocess.run(["alembic", "stamp", latest], check=True)
        else:
            print("No migration columns found. Stamping to base...")
            subprocess.run(["alembic", "stamp", "2c6338faef8c"], check=True)

        # Now run any remaining migrations
        print("Running alembic upgrade head...")
        subprocess.run(["alembic", "upgrade", "head"], check=True)
        print("Database migration complete.")
        return

    # ── Normal path: alembic exists, just upgrade ─────────────────────────
    print("Running alembic upgrades...")
    subprocess.run(["alembic", "upgrade", "head"], check=True)
    print("Database up to date.")


if __name__ == "__main__":
    init_db()
