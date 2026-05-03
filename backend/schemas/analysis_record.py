from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class AnalysisRecordCreate(BaseModel):
    selected_phrase: str
    analysis: str


class AnalysisRecordRead(BaseModel):
    id: int
    segment_id: int
    user_id: int
    selected_phrase: str
    analysis: str
    created_at: datetime

    model_config = {"from_attributes": True}


class AnalysisRecordListItem(AnalysisRecordRead):
    """Extended read model with segment context for list views."""
    segment_text: Optional[str] = None
    segment_index: Optional[int] = None
    material_id: Optional[int] = None
    material_title: Optional[str] = None
