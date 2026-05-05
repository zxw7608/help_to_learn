from sqlmodel import SQLModel, Field
from datetime import datetime
from typing import Optional
import sqlalchemy as sa

class AnalysisRecord(SQLModel, table=True):
    __tablename__ = "analysis_records"

    id: Optional[int] = Field(default=None, primary_key=True)
    segment_id: int = Field(foreign_key="segments.id", index=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    selected_phrase: str = Field(description="The phrase selected by user for analysis", sa_type=sa.TEXT())
    analysis: str = Field(description="AI-generated analysis result", sa_type=sa.TEXT())
    created_at: datetime = Field(default_factory=datetime.utcnow)
