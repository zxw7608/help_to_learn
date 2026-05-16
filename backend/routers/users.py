import os

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlmodel import Session

from backend.config import settings
from backend.database import get_session
from backend.dependencies import get_current_user
from backend.models.user import User
from backend.schemas.user import UserRead, UserUpdate

router = APIRouter()


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
