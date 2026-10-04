from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import events
from app.errors import Conflict, NotFound
from app.models import Assignment, Episode, Quality, RequestStatus, User
from app.services.requests import get_visible_request

ASSIGNABLE_QUALITIES = (Quality.GOOD, Quality.USABLE)


def list_assignments(db: Session, request_id: int) -> list[Assignment]:
    return list(
        db.scalars(
            select(Assignment)
            .where(Assignment.request_id == request_id, Assignment.released_at.is_(None))
            .order_by(Assignment.assigned_at, Assignment.id)
        )
    )


def assign(db: Session, user: User, request_id: int, episode_ids: list[str]) -> list[Assignment]:
    """Assign episodes to a request. All-or-nothing: if any episode fails a rule,
    nothing is assigned and the error lists every offending episode."""
    request = get_visible_request(db, user, request_id, for_update=True)
    if request.status != RequestStatus.IN_PROGRESS:
        raise Conflict("Episodes can only be assigned while the request is in progress")

    ids = list(dict.fromkeys(e.strip().upper() for e in episode_ids))  # dedupe, keep order
    episodes = {
        e.episode_id: e for e in db.scalars(select(Episode).where(Episode.episode_id.in_(ids)))
    }

    missing = [i for i in ids if i not in episodes]
    if missing:
        raise NotFound("Some episodes do not exist", details={"episode_ids": missing})

    not_assignable = [i for i in ids if episodes[i].quality not in ASSIGNABLE_QUALITIES]
    if not_assignable:
        raise Conflict(
            "Only 'good' or 'usable' episodes can be assigned",
            details={"episode_ids": not_assignable},
        )

    existing = {
        a.episode_id: a.request_id
        for a in db.scalars(
            select(Assignment).where(
                Assignment.episode_id.in_(ids), Assignment.released_at.is_(None)
            )
        )
    }
    elsewhere = {e: r for e, r in existing.items() if r != request.id}
    if elsewhere:
        raise Conflict(
            "Some episodes are already assigned to another request",
            details={"assigned_elsewhere": elsewhere},
        )

    # Re-assigning an episode already on *this* request is a no-op (idempotent).
    for episode_id in ids:
        if episode_id not in existing:
            db.add(Assignment(request_id=request.id, episode_id=episode_id, assigned_by=user.id))
    try:
        db.flush()
    except IntegrityError as exc:
        # Lost a race with a concurrent assignment of the same episode; the partial
        # unique index is the final guard.
        db.rollback()
        raise Conflict("An episode was assigned to another request concurrently; retry") from exc

    events.publish(db, "assignments_changed", request)
    db.commit()
    return list_assignments(db, request.id)


def unassign(db: Session, user: User, request_id: int, episode_id: str) -> None:
    request = get_visible_request(db, user, request_id, for_update=True)
    if request.status != RequestStatus.IN_PROGRESS:
        raise Conflict("Episodes can only be unassigned while the request is in progress")
    assignment = db.scalar(
        select(Assignment).where(
            Assignment.request_id == request.id,
            Assignment.episode_id == episode_id.strip().upper(),
            Assignment.released_at.is_(None),
        )
    )
    if assignment is None:
        raise NotFound("Episode is not assigned to this request")
    assignment.released_at = func.now()
    assignment.released_by = user.id
    events.publish(db, "assignments_changed", request)
    db.commit()
