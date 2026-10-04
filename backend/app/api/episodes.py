from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import STAFF, get_current_user, require_roles
from app.models import Quality, Role, User
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
    data = await file.read()
    text = importer.decode_upload(data)
    return importer.import_episodes(db, text, filename=file.filename or "upload.csv", uploaded_by=user.id)


@router.get("/analytics", response_model=AnalyticsOut)
def get_analytics(
    date_from: date,
    date_to: date,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(Role.ADMIN)),
) -> AnalyticsOut:
    return analytics_service.get_analytics(db, date_from, date_to)
