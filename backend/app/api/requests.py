from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import STAFF, get_current_user, require_roles
from app.models import Assignment, DatasetRequest, RequestStatus, Role, User
from app.schemas import (
    AssignIn,
    AssignmentOut,
    EpisodeOut,
    Page,
    RequestCreate,
    RequestDetailOut,
    RequestOut,
    StatusEventOut,
    TransitionIn,
)
from app.services import assignments as assignment_service
from app.services import requests as service
from app.workflow import allowed_targets

router = APIRouter(prefix="/requests", tags=["requests"])
staff_only = require_roles(*STAFF)
client_only = require_roles(Role.CLIENT)


def _to_out(request: DatasetRequest, assigned_count: int, user: User) -> RequestOut:
    return RequestOut.model_validate(
        {
            **{k: getattr(request, k) for k in RequestOut.model_fields if hasattr(request, k)},
            "assigned_count": assigned_count,
            "allowed_transitions": allowed_targets(request.status, user.role),
        }
    )


def _detail(db: Session, request: DatasetRequest, user: User) -> RequestDetailOut:
    base = _to_out(request, service.active_assignment_count(db, request.id), user)
    events = [StatusEventOut.model_validate(e) for e in service.list_events(db, request.id)]
    return RequestDetailOut(**base.model_dump(), events=events)


def _assignment_out(a: Assignment) -> AssignmentOut:
    episode = EpisodeOut.model_validate(a.episode)
    episode.assigned_request_id = a.request_id
    return AssignmentOut(episode=episode, assigned_at=a.assigned_at, assigned_by=a.assigned_by)


@router.get("", response_model=Page[RequestOut])
def list_requests(
    status: RequestStatus | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Page[RequestOut]:
    rows = service.list_requests(db, user, status=status, limit=limit + 1, offset=offset)
    items = [_to_out(r, count, user) for r, count in rows[:limit]]
    return Page(items=items, limit=limit, offset=offset, has_more=len(rows) > limit)


@router.post("", response_model=RequestDetailOut, status_code=201)
def create_request(
    body: RequestCreate, db: Session = Depends(get_db), user: User = Depends(client_only)
) -> RequestDetailOut:
    return _detail(db, service.create_request(db, user, body), user)


@router.get("/{request_id}", response_model=RequestDetailOut)
def get_request(
    request_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> RequestDetailOut:
    return _detail(db, service.get_visible_request(db, user, request_id), user)


@router.post("/{request_id}/transitions", response_model=RequestDetailOut)
def transition(
    request_id: int,
    body: TransitionIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),  # role rules are per-transition, in the service
) -> RequestDetailOut:
    request = service.transition(db, user, request_id, body.to_status, body.note)
    return _detail(db, request, user)


@router.get("/{request_id}/assignments", response_model=list[AssignmentOut])
def list_assignments(
    request_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> list[AssignmentOut]:
    service.get_visible_request(db, user, request_id)  # clients: only their own
    return [_assignment_out(a) for a in assignment_service.list_assignments(db, request_id)]


@router.post("/{request_id}/assignments", response_model=list[AssignmentOut], status_code=201)
def assign(
    request_id: int,
    body: AssignIn,
    db: Session = Depends(get_db),
    user: User = Depends(staff_only),
) -> list[AssignmentOut]:
    assigned = assignment_service.assign(db, user, request_id, body.episode_ids)
    return [_assignment_out(a) for a in assigned]


@router.delete("/{request_id}/assignments/{episode_id}", status_code=204)
def unassign(
    request_id: int,
    episode_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(staff_only),
) -> Response:
    assignment_service.unassign(db, user, request_id, episode_id)
    return Response(status_code=204)
