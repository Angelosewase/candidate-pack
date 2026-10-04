from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import events
from app.errors import Conflict, Forbidden, InvalidInput, NotFound
from app.models import (
    Assignment,
    DatasetRequest,
    Episode,
    Quality,
    RequestStatus,
    RequestStatusEvent,
    Role,
    User,
)
from app.schemas import RequestCreate
from app.workflow import is_valid_transition, roles_for


def get_visible_request(
    db: Session, user: User, request_id: int, *, for_update: bool = False
) -> DatasetRequest:
    """Load a request the user is allowed to see.

    Clients get 404 (not 403) for other clients' requests, so ids can't be probed.
    ``for_update`` takes a row lock: every operation that changes a request's status or
    its assignments goes through this lock, which serialises e.g. "assign" vs "deliver".
    """
    stmt = select(DatasetRequest).where(DatasetRequest.id == request_id)
    if for_update:
        stmt = stmt.with_for_update(of=DatasetRequest)
    request = db.scalar(stmt)
    if request is None or (user.role == Role.CLIENT and request.client_id != user.id):
        raise NotFound("Request not found")
    return request


def active_assignment_count(db: Session, request_id: int) -> int:
    return db.scalar(
        select(func.count())
        .select_from(Assignment)
        .where(Assignment.request_id == request_id, Assignment.released_at.is_(None))
    ) or 0


def _assigned_counts_subquery():
    return (
        select(Assignment.request_id, func.count().label("assigned_count"))
        .where(Assignment.released_at.is_(None))
        .group_by(Assignment.request_id)
        .subquery()
    )


def list_requests(
    db: Session,
    user: User,
    *,
    status: RequestStatus | None,
    limit: int,
    offset: int,
) -> list[tuple[DatasetRequest, int]]:
    counts = _assigned_counts_subquery()
    stmt = (
        select(DatasetRequest, func.coalesce(counts.c.assigned_count, 0))
        .outerjoin(counts, counts.c.request_id == DatasetRequest.id)
        .order_by(DatasetRequest.created_at.desc(), DatasetRequest.id.desc())
        .limit(limit)
        .offset(offset)
    )
    if user.role == Role.CLIENT:
        stmt = stmt.where(DatasetRequest.client_id == user.id)
    if status is not None:
        stmt = stmt.where(DatasetRequest.status == status)
    return [(r, c) for r, c in db.execute(stmt).all()]


def list_events(db: Session, request_id: int) -> list[RequestStatusEvent]:
    return list(
        db.scalars(
            select(RequestStatusEvent)
            .where(RequestStatusEvent.request_id == request_id)
            .order_by(RequestStatusEvent.created_at, RequestStatusEvent.id)
        )
    )


def create_request(db: Session, client: User, data: RequestCreate) -> DatasetRequest:
    if data.deadline < datetime.now(UTC).date():
        raise InvalidInput("Deadline cannot be in the past")
    request = DatasetRequest(
        client_id=client.id,
        task_name=data.task_name,
        episodes_requested=data.episodes_requested,
        deadline=data.deadline,
        notes=data.notes,
        status=RequestStatus.SUBMITTED,
    )
    db.add(request)
    db.flush()
    db.add(
        RequestStatusEvent(
            request_id=request.id,
            from_status=None,
            to_status=RequestStatus.SUBMITTED,
            actor_id=client.id,
        )
    )
    events.publish(db, "request_created", request)
    db.commit()
    return request


def transition(
    db: Session,
    user: User,
    request_id: int,
    target: RequestStatus,
    note: str | None = None,
) -> DatasetRequest:
    request = get_visible_request(db, user, request_id, for_update=True)
    current = request.status

    if not is_valid_transition(current, target):
        raise Conflict(f"Cannot move a request from '{current}' to '{target}'")
    if user.role not in roles_for(current, target):
        raise Forbidden(f"Your role cannot move a request from '{current}' to '{target}'")
    if target == RequestStatus.REJECTED and not note:
        raise InvalidInput("A reason is required when rejecting a delivery")
    if target == RequestStatus.DELIVERED:
        _check_ready_for_delivery(db, request)

    request.status = target
    request.updated_at = func.now()
    db.add(
        RequestStatusEvent(
            request_id=request.id,
            from_status=current,
            to_status=target,
            actor_id=user.id,
            note=note or None,
        )
    )
    events.publish(db, "request_status_changed", request)
    db.commit()
    db.refresh(request)
    return request


def _check_ready_for_delivery(db: Session, request: DatasetRequest) -> None:
    assigned = active_assignment_count(db, request.id)
    if assigned < request.episodes_requested:
        raise Conflict(
            f"Request needs {request.episodes_requested} episodes assigned before delivery; "
            f"it has {assigned}"
        )
    # An episode could have been re-graded 'bad' by a later import after it was assigned.
    now_bad = list(
        db.scalars(
            select(Episode.episode_id)
            .join(Assignment, Assignment.episode_id == Episode.episode_id)
            .where(
                Assignment.request_id == request.id,
                Assignment.released_at.is_(None),
                Episode.quality == Quality.BAD,
            )
        )
    )
    if now_bad:
        raise Conflict(
            "Some assigned episodes are now graded 'bad'; unassign them first",
            details={"episode_ids": now_bad},
        )
