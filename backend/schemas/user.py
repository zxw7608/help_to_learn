from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional


class UserRead(BaseModel):
    id: int
    username: str
    email: str
    telegram_chat_id: Optional[str]
    telegram_bot_token: Optional[str]
    anki_deck_name: str
    anki_model_name: str
    anki_connect_url: str
    tts_worker_url: str
    ai_base_url: Optional[str] = None
    ai_api_key: Optional[str] = None
    ai_model: Optional[str] = None
    ai_prompt: Optional[str] = None
    http_proxy: Optional[str] = None
    https_proxy: Optional[str] = None
    ytdlp_proxy: Optional[str] = None
    ytdlp_cookies: Optional[str] = None
    created_at: datetime
    is_active: bool
    is_admin: bool

    model_config = {"from_attributes": True}


class UserUpdate(BaseModel):
    telegram_chat_id: Optional[str] = None
    telegram_bot_token: Optional[str] = None
    anki_deck_name: Optional[str] = None
    anki_model_name: Optional[str] = None
    anki_connect_url: Optional[str] = None
    tts_worker_url: Optional[str] = None
    tts_token: Optional[str] = None
    ai_base_url: Optional[str] = None
    ai_api_key: Optional[str] = None
    ai_model: Optional[str] = None
    ai_prompt: Optional[str] = None
    http_proxy: Optional[str] = None
    https_proxy: Optional[str] = None
    ytdlp_proxy: Optional[str] = None
    ytdlp_cookies: Optional[str] = None
