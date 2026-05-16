import os
import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlmodel import Session, select

from backend.config import settings
from backend.database import get_session
from backend.dependencies import get_current_user
from backend.models.user import User
from backend.models.invite_code import InviteCode, InviteUsage
from backend.schemas.user import UserRead, UserUpdate
from backend.schemas.system import InviteCodeRead, InviteCodeDetail, InviteUsageRead

router = APIRouter()

INVITE_COOLDOWN_HOURS = 48
INVITE_MAX_USES = 5


@router.get("/me", response_model=UserRead)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.patch("/me", response_model=UserRead)
def update_me(
    body: UserUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    data = body.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(current_user, key, value)
    session.add(current_user)
    session.commit()
    session.refresh(current_user)
    return current_user


@router.post("/me/cookies")
def upload_cookies(
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Upload a Netscape-format cookies.txt for yt-dlp."""
    content = file.file.read()
    if len(content) > 1024 * 1024:
        raise HTTPException(status_code=413, detail="cookies.txt must be under 1 MB")

    # Save to user-specific path
    cookies_dir = os.path.join(settings.STORAGE_BASE_PATH, "cookies", str(current_user.id))
    os.makedirs(cookies_dir, exist_ok=True)
    cookies_path = os.path.join(cookies_dir, "cookies.txt")
    with open(cookies_path, "wb") as f:
        f.write(content)

    # Persist path in user settings
    current_user.ytdlp_cookies = cookies_path
    session.add(current_user)
    session.commit()

    return {"path": cookies_path, "size": len(content)}


# ── Invite Codes ──────────────────────────────────────

@router.get("/me/invite-codes", response_model=list[InviteCodeDetail])
def list_my_invite_codes(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    codes = session.exec(
        select(InviteCode)
        .where(InviteCode.creator_user_id == current_user.id)
        .order_by(InviteCode.created_at.desc())
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


@router.post("/me/invite-codes", response_model=InviteCodeRead)
def generate_invite_code(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Generate an invite code. 48-hour cooldown between generations."""
    # Check cooldown
    latest = session.exec(
        select(InviteCode)
        .where(InviteCode.creator_user_id == current_user.id)
        .order_by(InviteCode.created_at.desc())
    ).first()

    if latest:
        cooldown_until = latest.created_at + timedelta(hours=INVITE_COOLDOWN_HOURS)
        if datetime.utcnow() < cooldown_until:
            wait_hours = max(1, round((cooldown_until - datetime.utcnow()).total_seconds() / 3600))
            raise HTTPException(
                status_code=429,
                detail=f"Cooldown active. You can generate a new invite code in {wait_hours} hour(s).",
            )

    code = secrets.token_hex(4)  # 8-char hex string
    invite = InviteCode(
        code=code,
        creator_user_id=current_user.id,
        max_uses=INVITE_MAX_USES,
    )
    session.add(invite)
    session.commit()
    session.refresh(invite)
    return invite
