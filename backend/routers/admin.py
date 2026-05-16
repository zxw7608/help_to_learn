import secrets
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from backend.database import get_session
from backend.dependencies import get_admin_user
from backend.models.user import User
from backend.models.system_setting import SystemSetting
from backend.models.invite_code import InviteCode, InviteUsage
from backend.schemas.system import (
    RegistrationSettingsRead,
    RegistrationSettingsUpdate,
    InviteCodeCreate,
    InviteCodeRead,
    InviteCodeDetail,
    InviteUsageRead,
)

router = APIRouter()


def _get_setting(session: Session, key: str, default: str = "") -> str:
    row = session.get(SystemSetting, key)
    return row.value if row else default


def _set_setting(session: Session, key: str, value: str) -> None:
    row = session.get(SystemSetting, key)
    if row:
        row.value = value
    else:
        row = SystemSetting(key=key, value=value)
    session.add(row)


# ── Registration Settings ──────────────────────────────────

@router.get("/registration", response_model=RegistrationSettingsRead)
def get_registration_settings(
    session: Session = Depends(get_session),
    _admin: User = Depends(get_admin_user),
):
    return RegistrationSettingsRead(
        registration_enabled=_get_setting(session, "registration_enabled", "true") == "true",
        invite_verification_enabled=_get_setting(session, "invite_verification_enabled", "false") == "true",
    )


@router.patch("/registration", response_model=RegistrationSettingsRead)
def update_registration_settings(
    body: RegistrationSettingsUpdate,
    session: Session = Depends(get_session),
    _admin: User = Depends(get_admin_user),
):
    if body.registration_enabled is not None:
        _set_setting(session, "registration_enabled", "true" if body.registration_enabled else "false")
    if body.invite_verification_enabled is not None:
        _set_setting(session, "invite_verification_enabled", "true" if body.invite_verification_enabled else "false")
    session.commit()
    return RegistrationSettingsRead(
        registration_enabled=_get_setting(session, "registration_enabled", "true") == "true",
        invite_verification_enabled=_get_setting(session, "invite_verification_enabled", "false") == "true",
    )


# ── Invite Codes (Admin) ───────────────────────────────────

@router.post("/invite-codes", response_model=InviteCodeRead)
def admin_create_invite_code(
    body: InviteCodeCreate,
    session: Session = Depends(get_session),
    _admin: User = Depends(get_admin_user),
):
    """Create an invite code. No cooldown. max_uses capped at 5."""
    max_uses = min(body.max_uses, 5)
    code = secrets.token_hex(4)
    invite = InviteCode(
        code=code,
        creator_user_id=None,  # admin-created
        max_uses=max_uses,
        expires_at=body.expires_at,
    )
    session.add(invite)
    session.commit()
    session.refresh(invite)
    return invite


@router.get("/invite-codes", response_model=list[InviteCodeDetail])
def admin_list_invite_codes(
    session: Session = Depends(get_session),
    _admin: User = Depends(get_admin_user),
):
    codes = session.exec(
        select(InviteCode).order_by(InviteCode.created_at.desc())
    ).all()
    result = []
    for c in codes:
        usages = session.exec(
            select(InviteUsage).where(InviteUsage.invite_code_id == c.id)
        ).all()
        detail = InviteCodeDetail.model_validate(c)
        detail.usages = [InviteUsageRead.model_validate(u) for u in usages]
        result.append(detail)
    return result
