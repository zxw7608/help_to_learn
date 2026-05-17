import logging
import os
import secrets
import subprocess
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from backend.database import get_session
from backend.dependencies import get_admin_user
from backend.models.user import User
from backend.models.system_setting import SystemSetting
from backend.models.invite_code import InviteCode, InviteUsage
from backend.config import settings
from backend.schemas.system import (
    RegistrationSettingsRead,
    RegistrationSettingsUpdate,
    InviteCodeCreate,
    InviteCodeRead,
    InviteCodeDetail,
    InviteUsageRead,
    SttSettingsRead,
    SttSettingsUpdate,
    ModelDownloadRequest,
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


# ── STT Settings ──────────────────────────────────────

logger = logging.getLogger(__name__)


def _check_whisper_installed() -> bool:
    """Check if whisper_cpp_python package is pip-installed (module spec exists)."""
    import importlib.util
    return importlib.util.find_spec("whisper_cpp_python") is not None


def _check_whisper_ready() -> bool:
    """Check if whisper_cpp_python is fully functional (shared library loadable)."""
    try:
        from whisper_cpp_python import Whisper  # noqa: F401
        return True
    except (ImportError, FileNotFoundError, OSError, RuntimeError, AttributeError) as e:
        logger.warning(f"whisper_cpp_python is not ready: {e}")
        return False


def _resolve_model_path(session: Session) -> str:
    """Return the resolved whisper model path (setting or default)."""
    from backend.config import settings
    path = _get_setting(session, "stt_whisper_model_path", settings.STT_WHISPER_MODEL_PATH)
    if not path:
        path = os.path.join(settings.STORAGE_BASE_PATH, "models", "ggml-base.bin")
    return path


def _build_stt_response(session: Session) -> SttSettingsRead:
    model_path = _resolve_model_path(session)
    return SttSettingsRead(
        stt_backend=_get_setting(session, "stt_backend", settings.STT_BACKEND),
        stt_max_consecutive_failures=int(_get_setting(session, "stt_max_consecutive_failures", str(settings.STT_MAX_CONSECUTIVE_FAILURES))),
        stt_whisper_model_path=_get_setting(session, "stt_whisper_model_path", settings.STT_WHISPER_MODEL_PATH),
        model_exists=os.path.exists(model_path),
        whisper_installed=_check_whisper_installed(),
        whisper_ready=_check_whisper_ready(),
    )


@router.get("/stt", response_model=SttSettingsRead)
def get_stt_settings(
    session: Session = Depends(get_session),
    _admin: User = Depends(get_admin_user),
):
    return _build_stt_response(session)


@router.patch("/stt", response_model=SttSettingsRead)
def update_stt_settings(
    body: SttSettingsUpdate,
    session: Session = Depends(get_session),
    _admin: User = Depends(get_admin_user),
):
    if body.stt_backend is not None:
        _set_setting(session, "stt_backend", body.stt_backend)
    if body.stt_max_consecutive_failures is not None:
        _set_setting(session, "stt_max_consecutive_failures", str(body.stt_max_consecutive_failures))
    if body.stt_whisper_model_path is not None:
        _set_setting(session, "stt_whisper_model_path", body.stt_whisper_model_path)
    session.commit()
    return _build_stt_response(session)


@router.post("/stt/download-model", response_model=SttSettingsRead)
def download_stt_model(
    body: ModelDownloadRequest = ModelDownloadRequest(),
    session: Session = Depends(get_session),
    _admin: User = Depends(get_admin_user),
):
    """Download a whisper GGML model from HuggingFace."""
    from backend.services.transcriber import download_whisper_model
    from backend.config import settings

    save_dir = os.path.join(settings.STORAGE_BASE_PATH, "models")
    saved_path = download_whisper_model(model_size=body.model_size, save_dir=save_dir)
    _set_setting(session, "stt_whisper_model_path", saved_path)
    session.commit()

    return _build_stt_response(session)


@router.post("/stt/install-package", response_model=SttSettingsRead)
def install_whisper_package(
    session: Session = Depends(get_session),
    _admin: User = Depends(get_admin_user),
):
    """Install whisper-cpp-python via uv pip."""
    if _check_whisper_installed():
        return _build_stt_response(session)

    logger.info("Installing whisper-cpp-python via uv pip...")
    try:
        result = subprocess.run(
            ["uv", "pip", "install", "whisper-cpp-python"],
            capture_output=True, text=True, timeout=300,
        )
        if result.returncode != 0:
            logger.error(f"uv pip install failed: {result.stderr}")
            raise HTTPException(
                status_code=500,
                detail=f"Install failed: {result.stderr[:500]}",
            )
        logger.info("whisper-cpp-python installed successfully")
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=500, detail="Install timed out after 5 minutes")
    except FileNotFoundError:
        raise HTTPException(
            status_code=500,
            detail="uv not found. Please run: uv pip install whisper-cpp-python",
        )

    return _build_stt_response(session)
