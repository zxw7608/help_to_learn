from sqlmodel import SQLModel, create_engine, Session
from backend.config import settings

engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False,
)


def create_db_and_tables() -> None:
    """Import all models first so SQLModel.metadata knows about them, then create tables."""
    # noqa: F401 — imports required for SQLModel metadata registration
    from backend.models import user, material, segment, job, push_record, analysis_record  # noqa: F401
    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session
