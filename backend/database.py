from sqlmodel import SQLModel, create_engine, Session
from backend.config import settings

engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False,
)

def get_session():
    with Session(engine) as session:
        yield session
