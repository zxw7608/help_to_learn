from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from backend.database import get_session
from backend.dependencies import get_current_user
from backend.models.user import User
from backend.models.segment import Segment
from backend.models.material import Material
from backend.models.analysis_record import AnalysisRecord
from backend.schemas.analysis_record import (
    AnalysisRecordCreate,
    AnalysisRecordRead,
    AnalysisRecordListItem,
)

router = APIRouter()


@router.post("/segments/{segment_id}/analysis", response_model=AnalysisRecordRead)
def save_analysis(
    segment_id: int,
    body: AnalysisRecordCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    segment = session.get(Segment, segment_id)
    if not segment or segment.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Segment not found")

    record = AnalysisRecord(
        segment_id=segment_id,
        user_id=current_user.id,
        selected_phrase=body.selected_phrase,
        analysis=body.analysis,
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


@router.get("/segments/{segment_id}/analysis", response_model=list[AnalysisRecordRead])
def get_segment_analysis(
    segment_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    segment = session.get(Segment, segment_id)
    if not segment or segment.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Segment not found")

    records = session.exec(
        select(AnalysisRecord)
        .where(AnalysisRecord.segment_id == segment_id)
        .order_by(AnalysisRecord.created_at.desc())
    ).all()
    return list(records)


@router.get("/analysis-records", response_model=list[AnalysisRecordListItem])
def list_analysis_records(
    page: int = 1,
    size: int = 20,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    offset = (page - 1) * size

    rows = session.exec(
        select(
            AnalysisRecord,
            Segment.text,
            Segment.index,
            Segment.material_id,
        )
        .join(Segment, AnalysisRecord.segment_id == Segment.id)
        .where(AnalysisRecord.user_id == current_user.id)
        .where(Segment.user_id == current_user.id)
        .order_by(AnalysisRecord.created_at.desc())
        .offset(offset)
        .limit(size)
    ).all()

    results = []
    for record, seg_text, seg_index, seg_material_id in rows:
        item = AnalysisRecordListItem(
            id=record.id,
            segment_id=record.segment_id,
            user_id=record.user_id,
            selected_phrase=record.selected_phrase,
            analysis=record.analysis,
            created_at=record.created_at,
            segment_text=seg_text,
            segment_index=seg_index,
            material_id=seg_material_id,
            material_title=None,
        )
        results.append(item)

    # Resolve material titles
    material_ids = list(set(r.material_id for r in results if r.material_id))
    if material_ids:
        materials = session.exec(
            select(Material).where(Material.id.in_(material_ids))
        ).all()
        title_map = {m.id: m.title for m in materials}
        for r in results:
            if r.material_id:
                r.material_title = title_map.get(r.material_id)

    return results
