import os
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from backend.database import get_session
from backend.dependencies import get_current_user
from backend.models.user import User
from backend.models.segment import Segment
from backend.models.material import Material
from backend.models.push_record import PushRecord, Platform, PushStatus
from backend.schemas.push_record import PushRequest, PushRecordRead
from backend.services import telegram_service
from backend.config import settings

router = APIRouter()


def _do_push(segment: Segment, user: User, platform: Platform, session: Session, anki_note_id: Optional[int] = None) -> PushRecord:
    from backend.config import settings as cfg

    record = PushRecord(
        segment_id=segment.id,
        user_id=user.id,
        platform=platform,
        status=PushStatus.pending,
    )
    session.add(record)
    session.commit()
    session.refresh(record)

    try:
        # Build a public share link pointing to the material page with segment anchor
        share_url = (
            f"{cfg.SITE_BASE_URL}/share/{segment.material_id}#seg-{segment.id}"
        )

        if platform == Platform.anki:
            # Backend just records the push, actual network push is handled in frontend
            record.anki_card_id = anki_note_id

        elif platform == Platform.telegram:
            if not user.telegram_chat_id:
                raise RuntimeError("Telegram chat ID not set. Update it in Settings.")
            bot_token = user.telegram_bot_token or cfg.TELEGRAM_BOT_TOKEN
            if not bot_token:
                raise RuntimeError("Telegram bot token is not configured (neither in Settings nor on Server).")
            caption = segment.text
            if segment.translation:
                caption += f"\n\n{segment.translation}"

            # Add hashtag based on material title or URL
            material = session.get(Material, segment.material_id)
            if material:
                tag_source = material.title or material.source_url or ""
                import re
                tag = re.sub(r'\W+', '', tag_source)
                if tag:
                    caption += f"\n\n#{tag}"

            # Append share link so the receiver can jump to this segment directly
            caption += f"\n\n🔗 <a href='{share_url}'>{share_url}</a>"

            telegram_service.send_audio(
                bot_token=bot_token,
                chat_id=user.telegram_chat_id,
                audio_path=segment.audio_file_path,
                caption=caption,
                http_proxy=user.http_proxy,
                https_proxy=user.https_proxy,
            )

        record.status = PushStatus.sent
        record.sent_at = datetime.utcnow()

    except Exception as e:
        record.status = PushStatus.failed
        record.error_msg = str(e)

    session.add(record)
    session.commit()
    session.refresh(record)
    return record


@router.post("/segments/{segment_id}/push", response_model=PushRecordRead)
def push_segment(
    segment_id: int,
    body: PushRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    segment = session.get(Segment, segment_id)
    if not segment or segment.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Segment not found")

    record = _do_push(segment, current_user, body.platform, session, body.anki_note_id)
    if record.status == PushStatus.failed:
        raise HTTPException(status_code=502, detail=record.error_msg)
    return record


@router.post("/materials/{material_id}/push", response_model=list[PushRecordRead])
def push_material(
    material_id: int,
    body: PushRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Bulk push all segments of a material."""
    material = session.get(Material, material_id)
    if not material or material.user_id != current_user.id or material.is_deleted:
        raise HTTPException(status_code=404, detail="Material not found")

    segments = session.exec(
        select(Segment)
        .where(Segment.material_id == material_id)
        .order_by(Segment.index)
    ).all()

    if not segments:
        raise HTTPException(status_code=400, detail="No segments found for this material")

    results = []
    for segment in segments:
        record = _do_push(segment, current_user, body.platform, session, body.anki_note_id)
        results.append(record)

    return results
