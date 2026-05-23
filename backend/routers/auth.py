from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from backend.database import get_session
from backend.models.user import User
from backend.models.system_setting import SystemSetting
from backend.models.invite_code import InviteCode, InviteUsage
from backend.schemas.auth import RegisterRequest, LoginRequest, TokenResponse, RefreshRequest, AccessTokenResponse
from backend.services.auth_service import (
    get_password_hash, verify_password,
    create_access_token, create_refresh_token, decode_token,
)

router = APIRouter()


@router.get("/registration-status")
def registration_status(session: Session = Depends(get_session)):
    return {
        "registration_enabled": _get_setting(session, "registration_enabled", "true") == "true",
        "invite_required": _get_setting(session, "invite_verification_enabled", "false") == "true",
        "user_invite_generation_enabled": _get_setting(session, "user_invite_generation_enabled", "false") == "true",
    }


def _get_setting(session: Session, key: str, default: str = "") -> str:
    row = session.get(SystemSetting, key)
    return row.value if row else default


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest, session: Session = Depends(get_session)):
    # ── Global registration check ──────────────────────────────────────────
    reg_enabled = _get_setting(session, "registration_enabled", "true")
    if reg_enabled != "true":
        raise HTTPException(status_code=403, detail="Registration is currently disabled")

    invite_required = _get_setting(session, "invite_verification_enabled", "false")

    # ── Invite code validation ─────────────────────────────────────────────
    if invite_required == "true":
        if not body.invite_code:
            raise HTTPException(status_code=400, detail="Invite code is required")
        invite = session.exec(
            select(InviteCode).where(InviteCode.code == body.invite_code)
        ).first()
        if not invite or not invite.is_active:
            raise HTTPException(status_code=400, detail="Invalid invite code")
        if invite.current_uses >= invite.max_uses:
            raise HTTPException(status_code=400, detail="Invite code has reached its usage limit")
        if invite.expires_at and invite.expires_at < datetime.utcnow():
            raise HTTPException(status_code=400, detail="Invite code has expired")

    # ── Duplicate check ────────────────────────────────────────────────────
    existing = session.exec(
        select(User).where((User.username == body.username) | (User.email == body.email))
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Username or email already registered")

    # ── Create user ────────────────────────────────────────────────────────
    # First user in the system becomes admin automatically
    user_count = session.exec(select(User)).first()
    is_first = user_count is None

    user = User(
        username=body.username,
        email=body.email,
        hashed_password=get_password_hash(body.password),
        is_admin=is_first,
    )
    session.add(user)
    session.commit()
    session.refresh(user)

    # ── Record invite usage ────────────────────────────────────────────────
    if invite_required == "true" and body.invite_code:
        invite = session.exec(
            select(InviteCode).where(InviteCode.code == body.invite_code)
        ).first()
        if invite:
            invite.current_uses += 1
            if invite.current_uses >= invite.max_uses:
                invite.is_active = False
            session.add(invite)
            usage = InviteUsage(invite_code_id=invite.id, used_by_user_id=user.id)
            session.add(usage)
            session.commit()

    return TokenResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
    )


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, session: Session = Depends(get_session)):
    user = session.exec(select(User).where(User.username == body.username)).first()
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is disabled")

    return TokenResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
    )


@router.post("/refresh", response_model=AccessTokenResponse)
def refresh_token(body: RefreshRequest, session: Session = Depends(get_session)):
    payload = decode_token(body.refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    user_id = payload.get("sub")
    user = session.get(User, int(user_id))
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or disabled")

    return AccessTokenResponse(access_token=create_access_token(user.id))
