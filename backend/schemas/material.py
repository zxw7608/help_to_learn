from pydantic import BaseModel
from datetime import datetime
from typing import Optional
from backend.models.material import SourceType, MediaType, MaterialType, MaterialStatus


class MaterialCreate_URL_Media(BaseModel):
    url: str
    title: Optional[str] = None
    language: str = "en"
    material_type: MaterialType = MaterialType.main


class MaterialCreate_URL_Article(BaseModel):
    url: str
    title: Optional[str] = None
    language: str = "en"
    material_type: MaterialType = MaterialType.main


class MaterialCreate_Text(BaseModel):
    text: str
    title: str
    language: str = "en"
    material_type: MaterialType = MaterialType.main


class MaterialCreate_TextSnippet(BaseModel):
    text: str
    title: Optional[str] = None
    language: str = "en"


class MaterialRead(BaseModel):
    id: int
    user_id: int
    title: str
    source_type: SourceType
    source_url: Optional[str]
    media_type: Optional[MediaType]
    duration: Optional[float]
    language: str
    material_type: MaterialType
    status: MaterialStatus
    error_msg: Optional[str]
    is_deleted: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MaterialPage(BaseModel):
    items: list[MaterialRead]
    total: int
    page: int
    size: int
