from sqlmodel import SQLModel, create_engine, Session, text
from backend.config import settings

engine = create_engine(
    settings.DATABASE_URL,
    connect_args={
        "check_same_thread": False,
        # Wait up to 30 s before raising "database is locked".
        # Needed because multiple job threads write concurrently.
        "timeout": 30,
    },
    echo=False,
)

# Enable WAL mode so readers don't block writers and vice versa.
# Must be done once after engine creation.
with engine.connect() as conn:
    conn.execute(text("PRAGMA journal_mode=WAL"))
    conn.execute(text("PRAGMA busy_timeout=30000"))
    conn.commit()


def get_session():
    with Session(engine) as session:
        yield session
