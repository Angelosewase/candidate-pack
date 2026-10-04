"""Dataset request endpoints."""

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


@router.get(
    "",
    response_model=Page[RequestOut],
    summary="List dataset requests",
    response_description="Paginated list of requests visible to the caller",
)
def list_requests(
    status: RequestStatus | None = Query(default=None, description="Filter by status"),
    limit: int = Query(50, ge=1, le=200, description="Maximum items to return"),
    offset: int = Query(0, ge=0, description="Number of items to skip"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Page[RequestOut]:
    """List dataset requests.

    - **Clients** see only their own requests.
    - **Operators and admins** see all requests.

    Use the `status` query parameter to filter by workflow state.
    """
    rows = service.list_requests(db, user, status=status, limit=limit + 1, offset=offset)
    items = [_to_out(r, count, user) for r, count in rows[:limit]]
    total = service.count_requests(db, user, status=status)
    return Page(items=items, limit=limit, offset=offset, total=total, has_more=len(rows) > limit)


@router.post(
    "",
    response_model=RequestDetailOut,
    status_code=201,
    summary="Create a dataset request",
    response_description="The newly created request with status 'submitted'",
)
def create_request(
    body: RequestCreate, db: Session = Depends(get_db), user: User = Depends(client_only)
) -> RequestDetailOut:
    """Create a new dataset request (client only).

    The request is created in **submitted** status. An operator must move it to
    **in_progress** before episodes can be assigned.

    - `deadline` must be today or later.
    - `episodes_requested` must be between 1 and 100,000.
    """
    return _detail(db, service.create_request(db, user, body), user)


@router.get(
    "/{request_id}",
    response_model=RequestDetailOut,
    summary="Get a request",
    response_description="Full request detail including status-change history",
)
def get_request(
    request_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> RequestDetailOut:
    """Fetch a single request by ID.

    Clients receive **404** (not 403) when accessing another client's request —
    this prevents probing for valid request IDs.
    """
    return _detail(db, service.get_visible_request(db, user, request_id), user)


@router.post(
    "/{request_id}/transitions",
    response_model=RequestDetailOut,
    summary="Transition request status",
    response_description="Updated request after the status change",
)
def transition(
    request_id: int,
    body: TransitionIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),  # role rules are per-transition, in the service
) -> RequestDetailOut:
    """Advance a request to the next status.

    Only valid transitions are allowed; the caller's role must own that step:

    | Transition | Required role |
    |---|---|
    | `submitted → in_progress` | operator / admin |
    | `in_progress → delivered` | operator / admin |
    | `delivered → accepted` | client |
    | `delivered → rejected` | client |
    | `rejected → in_progress` | operator / admin |

    - Moving to `delivered` requires at least `episodes_requested` active assignments,
      none of which may be graded **bad**.
    - Moving to `rejected` requires a non-empty `note` (reason for rejection).
    """
    request = service.transition(db, user, request_id, body.to_status, body.note)
    return _detail(db, request, user)


@router.get(
    "/{request_id}/assignments",
    response_model=list[AssignmentOut],
    summary="List active assignments",
    response_description="Episodes currently assigned to the request",
)
def list_assignments(
    request_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> list[AssignmentOut]:
    """Return all episodes currently assigned to a request.

    Subject to the same visibility rules as `GET /requests/{id}`: clients only
    see their own requests.
    """
    service.get_visible_request(db, user, request_id)  # enforce visibility
    return [_assignment_out(a) for a in assignment_service.list_assignments(db, request_id)]


@router.post(
    "/{request_id}/assignments",
    response_model=list[AssignmentOut],
    status_code=201,
    summary="Assign episodes to a request",
    response_description="All active assignments after the operation",
)
def assign(
    request_id: int,
    body: AssignIn,
    db: Session = Depends(get_db),
    user: User = Depends(staff_only),
) -> list[AssignmentOut]:
    """Assign a batch of episodes to a request (staff only).

    Rules (all-or-nothing: if any episode violates a rule, nothing is assigned):

    - The request must be in **in_progress** status.
    - Episodes must exist and be graded **good** or **usable**.
    - Each episode can only be actively assigned to one request at a time.
    - Re-assigning an episode that is already on *this* request is idempotent.

    Duplicate IDs in the request body are deduplicated automatically.
    """
    assigned = assignment_service.assign(db, user, request_id, body.episode_ids)
    return [_assignment_out(a) for a in assigned]


@router.delete(
    "/{request_id}/assignments/{episode_id}",
    status_code=204,
    summary="Unassign an episode",
    response_description="No content on success",
)
def unassign(
    request_id: int,
    episode_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(staff_only),
) -> Response:
    """Remove an episode from a request (staff only).

    The request must be in **in_progress** status. The episode is not deleted;
    it becomes available for assignment to another request.
    """
    assignment_service.unassign(db, user, request_id, episode_id)
    return Response(status_code=204)
