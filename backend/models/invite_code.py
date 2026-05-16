from sqlmodel import SQLModel, Field
from datetime import datetime
from typing import Optional


class InviteCode(SQLModel, table=True):
    __tablename__ = "invite_codes"

    id: Optional[int] = Field(default=None, primary_key=True)
    code: str = Field(unique=True, index=True, max_length=32)
    creator_user_id: Optional[int] = Field(default=None, foreign_key="users.id")
    max_uses: int = Field(default=5)
    current_uses: int = Field(default=0)
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = Field(default=None)


class InviteUsage(SQLModel, table=True):
    __tablename__ = "invite_usages"

    id: Optional[int] = Field(default=None, primary_key=True)
    invite_code_id: int = Field(foreign_key="invite_codes.id")
    used_by_user_id: int = Field(foreign_key="users.id")
    used_at: datetime = Field(default_factory=datetime.utcnow)
