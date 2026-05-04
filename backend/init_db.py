from sqlmodel import SQLModel, create_engine, Session, text
from backend.config import settings
import subprocess

# Every column that any alembic migration adds to the users table, in order.
# Format: (migration_revision, column_name, column_type_sql)
_MIGRATION_COLUMNS = [
    ("2c6338faef8c", "telegram_bot_token", "VARCHAR(256)"),
    ("2c6338faef8c", "anki_model_name", "VARCHAR(256) NOT NULL DEFAULT 'Basic'"),
    ("81d962b1773d", "anki_connect_url", "VARCHAR(512) NOT NULL DEFAULT 'http://127.0.0.1:8765'"),
    ("9a1b2c3d4e5f", "ai_base_url", "VARCHAR(512)"),
    ("9a1b2c3d4e5f", "ai_api_key", "VARCHAR(256)"),
    ("a1b2c3d4e5f6", "ai_model", "VARCHAR(128)"),
    ("b1c2d3e4f5a7", "ai_prompt", "TEXT(4096)"),
]

# Tables created by migrations (not by the original create_all)
_MIGRATION_TABLES = ["analysis_records"]


def _column_exists(session, table: str, column: str) -> bool:
    result = session.execute(text(f"PRAGMA table_info('{table}')"))
    return any(row[1] == column for row in result.fetchall())


def _table_exists(session, table: str) -> bool:
    result = session.execute(
        text("SELECT name FROM sqlite_master WHERE type='table' AND name=:name"),
        {"name": table},
    )
    return result.fetchone() is not None


def _sync_schema(engine) -> None:
    """
    Bring the actual SQLite schema up to date with the latest models.
    Works regardless of whether alembic_version table exists or not.
    """
    with Session(engine) as session:
        # 1. Add any missing columns directly (bypasses alembic)
        for _, column, col_type in _MIGRATION_COLUMNS:
            if not _column_exists(session, "users", column):
                print(f"  Adding missing column: users.{column}")
                session.execute(
                    text(f"ALTER TABLE users ADD COLUMN {column} {col_type}")
                )
                session.commit()

        # 2. Create any missing tables via SQLModel
        need_create = False
        for table in _MIGRATION_TABLES:
            if not _table_exists(session, table):
                need_create = True
                break
        if need_create:
            print("  Creating missing tables via SQLModel...")
            from backend.models import (  # noqa: F401
                user, material, segment, job, push_record, analysis_record,
            )
            SQLModel.metadata.create_all(engine)

    # 3. Determine the highest fully-applied alembic revision
    with Session(engine) as session:
        highest_applied = None
        for revision, column, _ in _MIGRATION_COLUMNS:
            if _column_exists(session, "users", column):
                highest_applied = revision
            else:
                break

    # 4. Stamp alembic to match reality, then upgrade the rest
    if highest_applied:
        print(f"  Stamping alembic to {highest_applied} (matches schema)...")
        subprocess.run(["alembic", "stamp", highest_applied], check=True)
    else:
        # No migration columns exist yet (unlikely, but handle it)
        print("  Stamping alembic to base (2c6338faef8c)...")
        subprocess.run(["alembic", "stamp", "2c6338faef8c"], check=True)

    print("  Running alembic upgrade head...")
    subprocess.run(["alembic", "upgrade", "head"], check=True)


def init_db():
    engine = create_engine(settings.DATABASE_URL)

    with Session(engine) as session:
        has_users = _table_exists(session, "users")

    if not has_users:
        # ── Fresh install ──────────────────────────────────────────────────
        print("New database — creating all tables from models...")
        from backend.models import (  # noqa: F401
            user, material, segment, job, push_record, analysis_record,
        )
        SQLModel.metadata.create_all(engine)
        print("Stamping alembic to head...")
        subprocess.run(["alembic", "stamp", "head"], check=True)
        print("Database initialized.")
        return

    # ── Existing database — sync schema then upgrade ───────────────────────
    print("Existing database — syncing schema...")
    _sync_schema(engine)
    print("Database up to date.")


if __name__ == "__main__":
    init_db()
