from pydantic import BaseModel
from datetime import datetime
from typing import Optional


# ── System Settings ────────────────────────────

class RegistrationSettingsRead(BaseModel):
    registration_enabled: bool = True
    invite_verification_enabled: bool = False

    model_config = {"from_attributes": True}


class RegistrationSettingsUpdate(BaseModel):
    registration_enabled: Optional[bool] = None
    invite_verification_enabled: Optional[bool] = None


# ── Invite Codes ───────────────────────────────

class InviteCodeCreate(BaseModel):
    max_uses: int = 5
    expires_at: Optional[datetime] = None


class InviteCodeRead(BaseModel):
    id: int
    code: str
    creator_user_id: Optional[int]
    max_uses: int
    current_uses: int
    is_active: bool
    created_at: datetime
    expires_at: Optional[datetime]

    model_config = {"from_attributes": True}


class InviteUsageRead(BaseModel):
    id: int
    invite_code_id: int
    used_by_user_id: int
    used_at: datetime

    model_config = {"from_attributes": True}


class InviteCodeDetail(InviteCodeRead):
    usages: list[InviteUsageRead] = []
