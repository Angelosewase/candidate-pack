from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Assignment, Episode, ImportRun, Quality
from app.normalize import normalize_task_name


def _episode_filters(stmt, *, task_name, quality, robot_id, assignable_only):
    if task_name:
        stmt = stmt.where(Episode.task_name == normalize_task_name(task_name))
    if quality:
        stmt = stmt.where(Episode.quality == quality)
    if robot_id:
        stmt = stmt.where(Episode.robot_id == robot_id.strip().lower())
    if assignable_only:
        stmt = stmt.where(
            Assignment.id.is_(None), Episode.quality.in_((Quality.GOOD, Quality.USABLE))
        )
    return stmt


def list_episodes(
    db: Session,
    *,
    task_name: str | None,
    quality: Quality | None,
    robot_id: str | None,
    assignable_only: bool,
    limit: int,
    offset: int,
) -> list[tuple[Episode, int | None]]:
    """Episodes with the id of the request they're currently assigned to (if any)."""
    stmt = (
        select(Episode, Assignment.request_id)
        .outerjoin(
            Assignment,
            (Assignment.episode_id == Episode.episode_id) & Assignment.released_at.is_(None),
        )
        .order_by(Episode.recorded_at.desc(), Episode.episode_id)
        .limit(limit)
        .offset(offset)
    )
    stmt = _episode_filters(
        stmt,
        task_name=task_name,
        quality=quality,
        robot_id=robot_id,
        assignable_only=assignable_only,
    )
    return [(e, r) for e, r in db.execute(stmt).all()]


def count_episodes(
    db: Session,
    *,
    task_name: str | None,
    quality: Quality | None,
    robot_id: str | None,
    assignable_only: bool,
) -> int:
    """Total rows matching the list_episodes filters (drives pagination)."""
    stmt = (
        select(func.count())
        .select_from(Episode)
        .outerjoin(
            Assignment,
            (Assignment.episode_id == Episode.episode_id) & Assignment.released_at.is_(None),
        )
    )
    stmt = _episode_filters(
        stmt,
        task_name=task_name,
        quality=quality,
        robot_id=robot_id,
        assignable_only=assignable_only,
    )
    return db.scalar(stmt) or 0


def list_import_runs(db: Session, limit: int = 20) -> list[ImportRun]:
    return list(db.scalars(select(ImportRun).order_by(ImportRun.id.desc()).limit(limit)))
