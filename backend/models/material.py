from sqlmodel import SQLModel, Field
from datetime import datetime
from typing import Optional
from enum import Enum


class SourceType(str, Enum):
    upload = "upload"           # Local video/audio file upload
    url_media = "url_media"     # YouTube/Bilibili etc. (yt-dlp)
    url_article = "url_article" # Article/webpage URL (text scrape)
    text = "text"               # Plain text paste (no original audio)


class MediaType(str, Enum):
    video = "video"
    audio = "audio"
    text = "text"


class MaterialType(str, Enum):
    main = "main"
    temporary = "temporary"


class MaterialStatus(str, Enum):
    pending = "pending"
    processing = "processing"
    done = "done"
    failed = "failed"


class Material(SQLModel, table=True):
    __tablename__ = "materials"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    title: str = Field(max_length=512)

    source_type: SourceType
    source_url: Optional[str] = Field(default=None, max_length=2048)
    raw_text: Optional[str] = Field(default=None)         # url_article / text
    original_file_path: Optional[str] = Field(default=None, max_length=1024)  # upload / url_media, never deleted
    media_type: Optional[MediaType] = Field(default=None)
    duration: Optional[float] = Field(default=None)       # seconds, media only
    language: str = Field(default="en", max_length=16)
    material_type: MaterialType = Field(default=MaterialType.main, max_length=5)

    status: MaterialStatus = Field(default=MaterialStatus.pending)
    error_msg: Optional[str] = Field(default=None)
    is_deleted: bool = Field(default=False)

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
