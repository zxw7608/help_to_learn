import json
import os
import shutil
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from sqlmodel import Session, select, func

from backend.database import get_session
from backend.dependencies import get_current_user
from backend.models.user import User
from backend.models.material import Material, MaterialStatus, MaterialType, SourceType, MediaType
from backend.models.job import Job, JobType, JobStatus
from backend.models.segment import Segment
from backend.schemas.material import (
    MaterialRead, MaterialPage,
    MaterialCreate_URL_Media, MaterialCreate_URL_Article, MaterialCreate_Text,
    MaterialCreate_TextSnippet,
)
from backend.schemas.job import MaterialJobCreated
from backend.config import settings

router = APIRouter()


def _create_job(session: Session, material_id: int) -> Job:
    job = Job(
        job_type=JobType.process_material,
        payload=json.dumps({"material_id": material_id}),
        status=JobStatus.pending,
    )
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


def _trigger_worker() -> None:
    """Notify the worker to poll immediately instead of waiting for the next interval."""
    import threading
    threading.Thread(target=_run_worker_poll, daemon=True).start()


def _run_worker_poll() -> None:
    """Run one poll cycle in-process, then signal the scheduler to check again soon."""
    try:
        from backend.worker import poll_and_process
        poll_and_process()
    except Exception:
        pass


@router.post("/upload", response_model=MaterialJobCreated, status_code=status.HTTP_201_CREATED)
async def upload_material(
    title: str = Form(...),
    language: str = Form("en"),
    material_type: MaterialType = Form(MaterialType.main),
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Upload a local video or audio file."""
    # Validate file extension
    allowed = {".mp4", ".mp3", ".wav", ".m4a", ".mkv", ".webm", ".aac"}
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in allowed:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext}")

    # Save file to originals
    from backend.services.processor import get_duration
    material = Material(
        user_id=current_user.id,
        title=title,
        source_type=SourceType.upload,
        language=language,
        media_type=MediaType.video if ext in {".mp4", ".mkv", ".webm"} else MediaType.audio,
        material_type=material_type,
    )
    session.add(material)
    session.commit()
    session.refresh(material)

    out_dir = os.path.join(settings.STORAGE_BASE_PATH, "originals", str(current_user.id), str(material.id))
    os.makedirs(out_dir, exist_ok=True)
    file_path = os.path.join(out_dir, file.filename)

    with open(file_path, "wb") as f:
        content = await file.read()
        f.write(content)

    # Try to get duration
    try:
        duration = get_duration(file_path)
        material.duration = duration
    except Exception:
        pass

    material.original_file_path = file_path
    session.add(material)
    session.commit()

    job = _create_job(session, material.id)
    _trigger_worker()
    return MaterialJobCreated(material_id=material.id, job_id=job.id)


@router.post("/url-media", response_model=MaterialJobCreated, status_code=status.HTTP_201_CREATED)
def import_url_media(
    body: MaterialCreate_URL_Media,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Import a media URL (YouTube, Bilibili, etc.) via yt-dlp."""
    material = Material(
        user_id=current_user.id,
        title=body.title or body.url,
        source_type=SourceType.url_media,
        source_url=body.url,
        language=body.language,
        media_type=MediaType.video,
        material_type=body.material_type,
    )
    session.add(material)
    session.commit()
    session.refresh(material)

    job = _create_job(session, material.id)
    _trigger_worker()
    return MaterialJobCreated(material_id=material.id, job_id=job.id)


@router.post("/url-article", response_model=MaterialJobCreated, status_code=status.HTTP_201_CREATED)
def import_url_article(
    body: MaterialCreate_URL_Article,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Import an article URL. Text will be scraped and TTS audio generated."""
    material = Material(
        user_id=current_user.id,
        title=body.title or body.url,
        source_type=SourceType.url_article,
        source_url=body.url,
        language=body.language,
        media_type=MediaType.text,
        material_type=body.material_type,
    )
    session.add(material)
    session.commit()
    session.refresh(material)

    job = _create_job(session, material.id)
    _trigger_worker()
    return MaterialJobCreated(material_id=material.id, job_id=job.id)


@router.post("/text", response_model=MaterialJobCreated, status_code=status.HTTP_201_CREATED)
def import_text(
    body: MaterialCreate_Text,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Import plain text directly. TTS audio will be generated for each sentence."""
    material = Material(
        user_id=current_user.id,
        title=body.title,
        source_type=SourceType.text,
        raw_text=body.text,
        language=body.language,
        media_type=MediaType.text,
        material_type=body.material_type,
    )
    session.add(material)
    session.commit()
    session.refresh(material)

    job = _create_job(session, material.id)
    _trigger_worker()
    return MaterialJobCreated(material_id=material.id, job_id=job.id)


@router.post("/text-snippet", response_model=MaterialJobCreated, status_code=status.HTTP_201_CREATED)
def import_text_snippet(
    body: MaterialCreate_TextSnippet,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Import a short text snippet as a temporary material. TTS will be generated."""
    title = body.title or (body.text[:50] + ("..." if len(body.text) > 50 else ""))
    material = Material(
        user_id=current_user.id,
        title=title,
        source_type=SourceType.text,
        raw_text=body.text,
        language=body.language,
        media_type=MediaType.text,
        material_type=MaterialType.temporary,
    )
    session.add(material)
    session.commit()
    session.refresh(material)

    job = _create_job(session, material.id)
    _trigger_worker()
    return MaterialJobCreated(material_id=material.id, job_id=job.id)


@router.get("", response_model=MaterialPage)
def list_materials(
    page: int = 1,
    size: int = 20,
    material_type: Optional[MaterialType] = None,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    offset = (page - 1) * size
    conditions = [
        Material.user_id == current_user.id,
        Material.is_deleted == False,
    ]
    if material_type is not None:
        conditions.append(Material.material_type == material_type)

    query = select(Material).where(*conditions).order_by(Material.created_at.desc())

    total = session.exec(select(func.count()).select_from(
        select(Material).where(*conditions).subquery()
    )).one()

    items = session.exec(query.offset(offset).limit(size)).all()
    return MaterialPage(items=list(items), total=total, page=page, size=size)


@router.get("/{material_id}", response_model=MaterialRead)
def get_material(
    material_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    material = session.get(Material, material_id)
    if not material or material.user_id != current_user.id or material.is_deleted:
        raise HTTPException(status_code=404, detail="Material not found")
    return material


@router.delete("/{material_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_material(
    material_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Soft-delete: marks is_deleted=True. Original file is NEVER removed."""
    material = session.get(Material, material_id)
    if not material or material.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Material not found")

    material.is_deleted = True
    material.updated_at = datetime.utcnow()
    session.add(material)
    session.commit()


@router.delete("/{material_id}/storage", status_code=status.HTTP_204_NO_CONTENT)
def delete_material_storage(
    material_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Hard-delete of physical files: removes originals, audio, and temp folders."""
    material = session.get(Material, material_id)
    if not material or material.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Material not found")

    # Paths to cleanup
    paths_to_delete = [
        os.path.join(settings.STORAGE_BASE_PATH, "originals", str(current_user.id), str(material.id)),
        os.path.join(settings.STORAGE_BASE_PATH, "audio", str(current_user.id), str(material.id)),
        os.path.join(settings.STORAGE_BASE_PATH, "temp", str(current_user.id), str(material.id)),
    ]

    for path in paths_to_delete:
        if os.path.exists(path):
            shutil.rmtree(path, ignore_errors=True)

    material.original_file_path = None
    material.updated_at = datetime.utcnow()
    session.add(material)
    session.commit()


@router.get("/{material_id}/segments")
def get_material_segments(
    material_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    material = session.get(Material, material_id)
    if not material or material.user_id != current_user.id or material.is_deleted:
        raise HTTPException(status_code=404, detail="Material not found")

    segments = session.exec(
        select(Segment)
        .where(Segment.material_id == material_id)
        .order_by(Segment.index)
    ).all()
    return list(segments)


@router.post("/{material_id}/re-execute", response_model=MaterialJobCreated)
def re_execute_material(
    material_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Restart processing for a material. Resets status and deletes existing segments."""
    material = session.get(Material, material_id)
    if not material or material.user_id != current_user.id or material.is_deleted:
        raise HTTPException(status_code=404, detail="Material not found")

    # Reset material status
    material.status = MaterialStatus.pending
    material.error_msg = None
    material.updated_at = datetime.utcnow()

    # Delete old segments
    old_segments = session.exec(select(Segment).where(Segment.material_id == material_id)).all()
    for seg in old_segments:
        session.delete(seg)

    session.add(material)
    session.commit()
    session.refresh(material)

    job = _create_job(session, material.id)
    _trigger_worker()
    return MaterialJobCreated(material_id=material.id, job_id=job.id)
