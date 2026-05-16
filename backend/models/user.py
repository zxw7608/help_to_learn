from sqlmodel import SQLModel, Field
from datetime import datetime
from typing import Optional
import sqlalchemy as sa

class User(SQLModel, table=True):
    __tablename__ = "users"

    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(unique=True, index=True, max_length=64)
    email: str = Field(unique=True, index=True, max_length=256)
    hashed_password: str

    telegram_chat_id: Optional[str] = Field(default=None, max_length=64)
    telegram_bot_token: Optional[str] = Field(default=None, max_length=256)
    anki_deck_name: str = Field(default="English::Listening", max_length=256)
    anki_model_name: str = Field(default="问答题", max_length=256)
    anki_connect_url: str = Field(default="http://127.0.0.1:8765", max_length=512)
    tts_worker_url: str = Field(default="https://tts.wangwangit.com", max_length=512)
    tts_token: Optional[str] = Field(default=None, max_length=256)
    ai_base_url: Optional[str] = Field(default=None, max_length=512)
    ai_api_key: Optional[str] = Field(default=None, max_length=256)
    ai_model: Optional[str] = Field(default=None, max_length=128)
    ai_prompt: Optional[str] = Field(default=None, max_length=4096, sa_type=sa.TEXT())
    http_proxy: Optional[str] = Field(default=None, max_length=512)
    https_proxy: Optional[str] = Field(default=None, max_length=512)
    ytdlp_proxy: Optional[str] = Field(default=None, max_length=512)
    ytdlp_cookies: Optional[str] = Field(default=None, max_length=512)

    created_at: datetime = Field(default_factory=datetime.utcnow)
    is_active: bool = Field(default=True)
