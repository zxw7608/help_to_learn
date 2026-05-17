from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # App
    SECRET_KEY: str = "change-me-to-a-long-random-secret-string"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    # Public-facing site domain, used to generate share links sent to Telegram/Anki.
    # Example: https://learn.example.com  (no trailing slash)
    SITE_BASE_URL: str = "http://localhost:5173"

    # Database & Storage
    DATABASE_URL: str = "sqlite:///./data.db"
    STORAGE_BASE_PATH: str = "./storage"

    # wangwangit/tts Worker
    TTS_WORKER_URL: str = "https://tts.wangwangit.com"
    TTS_TOKEN: Optional[str] = None

    # Telegram
    TELEGRAM_BOT_TOKEN: Optional[str] = None

    # Anki
    ANKI_CONNECT_URL: str = "http://localhost:8765"

    # Worker
    JOB_POLL_INTERVAL: int = 5

    # STT
    STT_BACKEND: str = "api"  # "api" or "whisper_cpp"
    STT_MAX_CONSECUTIVE_FAILURES: int = 4
    STT_WHISPER_MODEL_PATH: str = ""  # path to GGML model file for whisper_cpp

    # Proxy settings (applies to HTTP requests and yt-dlp)
    # Example: http://127.0.0.1:7890  or  socks5://127.0.0.1:1080
    HTTP_PROXY: Optional[str] = None
    HTTPS_PROXY: Optional[str] = None
    # yt-dlp specific proxy (defaults to HTTP_PROXY if not set)
    YTDLP_PROXY: Optional[str] = None
    # Path to cookies.txt for yt-dlp (Netscape format).
    # If not set, auto-detects ./cookies.txt in the working directory.
    YTDLP_COOKIES: Optional[str] = None

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
