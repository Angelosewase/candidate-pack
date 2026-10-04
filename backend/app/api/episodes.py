from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import STAFF, get_current_user, require_roles
from app.config import get_settings
from app.errors import InvalidInput, PayloadTooLarge
from app.models import Quality, User
from app.schemas import AnalyticsOut, EpisodeOut, Page
from app.services import analytics as analytics_service
from app.services import episodes as episode_service
from app.services import importer

router = APIRouter(tags=["episodes"])
staff_only = require_roles(*STAFF)


@router.get("/episodes", response_model=Page[EpisodeOut])
def list_episodes(
    task_name: str | None = None,
    quality: Quality | None = None,
    robot_id: str | None = None,
    assignable_only: bool = False,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _: User = Depends(staff_only),
) -> Page[EpisodeOut]:
    rows = episode_service.list_episodes(
        db,
        task_name=task_name,
        quality=quality,
        robot_id=robot_id,
        assignable_only=assignable_only,
        limit=limit + 1,
        offset=offset,
    )
    items = [
        EpisodeOut.model_validate({**EpisodeOut.model_validate(e).model_dump(), "assigned_request_id": r})
        for e, r in rows[:limit]
    ]
    return Page(items=items, limit=limit, offset=offset, has_more=len(rows) > limit)


@router.post("/import", status_code=201)
async def import_csv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(staff_only),
) -> dict:
    max_bytes = get_settings().max_import_bytes
    data = await file.read()
    if len(data) > max_bytes:
        raise PayloadTooLarge(
            f"File is {len(data)} bytes; limit is {max_bytes} bytes",
            details={"size_bytes": len(data), "limit_bytes": max_bytes},
        )
    text = importer.decode_upload(data)
    return importer.import_episodes(db, text, filename=file.filename or "upload.csv", uploaded_by=user.id)


@router.get("/imports", response_model=list[dict])
def list_imports(
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(staff_only),
) -> list[dict]:
    runs = episode_service.list_import_runs(db, limit=limit)
    return [
        {
            "id": r.id,
            "filename": r.filename,
            "total_rows": r.total_rows,
            "inserted": r.inserted,
            "updated": r.updated,
            "unchanged": r.unchanged,
            "skipped": r.skipped,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in runs
    ]


@router.get("/analytics", response_model=AnalyticsOut)
def get_analytics(
    date_from: date,
    date_to: date,
    db: Session = Depends(get_db),
    _: User = Depends(staff_only),
) -> AnalyticsOut:
    if date_from > date_to:
        raise InvalidInput("date_from must not be after date_to")
    return analytics_service.get_analytics(db, date_from, date_to)
