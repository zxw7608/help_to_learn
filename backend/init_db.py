"""
Database initialisation.

- Fresh DB  → create all tables from SQLModel metadata, stamp alembic to head.
- Existing  → ``alembic upgrade head``.

Usage:  uv run python backend/init_db.py
"""

import subprocess

from sqlmodel import SQLModel, Session, create_engine, text

from backend.config import settings


def init_db():
    engine = create_engine(
        settings.DATABASE_URL,
        connect_args={"check_same_thread": False},
        echo=False,
    )

    # Import all models so SQLModel.metadata is populated
    from backend.models import (  # noqa: F401
        user, material, segment, job, push_record, analysis_record, system_setting, invite_code, 
    )

    with Session(engine) as session:
        row = session.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
        ).fetchone()

    if row is None:
        print("Fresh database — creating tables ...")
        SQLModel.metadata.create_all(engine)
        subprocess.run(["alembic", "stamp", "head"], check=True)
        print("Done.")
    else:
        print("Existing database — running migrations ...")
        subprocess.run(["alembic", "upgrade", "head"], check=True)
        print("Schema is up to date.")


if __name__ == "__main__":
    init_db()
