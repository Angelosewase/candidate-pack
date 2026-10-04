"""API request/response schemas. Input models forbid unknown fields."""

import re
from datetime import date, datetime
from typing import Annotated, Generic, TypeVar

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints

from app.models import Quality, RequestStatus, Role
from app.normalize import normalize_email, normalize_task_name

T = TypeVar("T")

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _valid_email(value: str) -> str:
    value = normalize_email(value)
    if not _EMAIL_RE.match(value):
        raise ValueError("not a valid email address")
    return value


def _valid_task_name(value: str) -> str:
    value = normalize_task_name(value)
    if not value:
        raise ValueError("must not be blank")
    return value


Email = Annotated[str, StringConstraints(max_length=254), AfterValidator(_valid_email)]
TaskName = Annotated[str, StringConstraints(max_length=200), AfterValidator(_valid_task_name)]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Password = Annotated[str, StringConstraints(min_length=6, max_length=200)]


class InputModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class OutputModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page(OutputModel, Generic[T]):
    """Paginated list response."""

    items: list[T]
    limit: int
    offset: int
    has_more: bool


# --- health -----------------------------------------------------------------------


class HealthOut(BaseModel):
    """Liveness response."""

    status: str = Field(examples=["ok"])


# --- auth / users -----------------------------------------------------------------


class LoginIn(InputModel):
    """Login credentials."""

    email: Annotated[str, StringConstraints(max_length=254)] = Field(
        examples=["admin@example.com"]
    )
    password: Annotated[str, StringConstraints(max_length=200)] = Field(examples=["ops123"])


class UserOut(OutputModel):
    """Full user representation (returned after login or from the admin user list)."""

    id: int
    email: str
    name: str
    organisation: str | None
    role: Role
    is_active: bool
    created_at: datetime


class UserBrief(OutputModel):
    """Condensed user reference embedded inside other objects."""

    id: int
    name: str
    organisation: str | None = None
    role: Role


class TokenOut(BaseModel):
    """JWT access token and the authenticated user."""

    access_token: str
    token_type: str = "bearer"
    user: UserOut


class UserCreate(InputModel):
    """Payload for admin-only user creation."""

    email: Email
    name: Name
    password: Password
    role: Role
    organisation: Name | None = None


class UserUpdate(InputModel):
    """Partial update payload for admin-only user management.

    All fields are optional; only supplied fields are changed.
    """

    name: Name | None = None
    organisation: Name | None = None
    role: Role | None = None
    is_active: bool | None = None
    password: Password | None = None


# --- requests ---------------------------------------------------------------------


class RequestCreate(InputModel):
    """Payload to create a new dataset request (client only)."""

    task_name: TaskName = Field(examples=["pick cup"])
    episodes_requested: int = Field(ge=1, le=100_000, examples=[50])
    deadline: date = Field(examples=["2026-12-31"])
    notes: Annotated[str, StringConstraints(max_length=5000)] = Field(default="", examples=[""])


class TransitionIn(InputModel):
    """Payload to advance a request's status."""

    to_status: RequestStatus
    note: Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)] | None = Field(
        default=None,
        description="Required when rejecting a delivered request.",
        examples=["Gripper was occluded in all clips."],
    )


class StatusEventOut(OutputModel):
    """One entry in the audit trail of a request's status history."""

    id: int
    from_status: RequestStatus | None
    to_status: RequestStatus
    actor: UserBrief
    note: str | None
    created_at: datetime


class RequestOut(OutputModel):
    """Dataset request summary (returned in list views)."""

    id: int
    client: UserBrief
    task_name: str
    episodes_requested: int
    deadline: date
    notes: str
    status: RequestStatus
    created_at: datetime
    updated_at: datetime
    assigned_count: int = Field(description="Number of episodes currently assigned.")
    allowed_transitions: list[RequestStatus] = Field(
        description="Status values the calling user may transition this request to."
    )


class RequestDetailOut(RequestOut):
    """Full request detail including the complete status-change audit trail."""

    events: list[StatusEventOut]


# --- episodes / assignments -------------------------------------------------------


class EpisodeOut(OutputModel):
    """Episode metadata, optionally annotated with the request it's assigned to."""

    episode_id: str
    robot_id: str
    task_name: str
    recorded_at: datetime
    duration_seconds: int | None
    operator_name: str | None
    quality: Quality
    assigned_request_id: int | None = Field(
        default=None,
        description="ID of the request this episode is currently assigned to, or null.",
    )


class AssignIn(InputModel):
    """Batch assignment payload (staff only). Up to 500 episode IDs per call."""

    episode_ids: list[Annotated[str, StringConstraints(strip_whitespace=True, max_length=50)]] = (
        Field(min_length=1, max_length=500, examples=[["EP-000000001", "EP-000000002"]])
    )


class AssignmentOut(OutputModel):
    """A single active episode assignment."""

    episode: EpisodeOut
    assigned_at: datetime
    assigned_by: int


# --- import history ---------------------------------------------------------------


class ImportRunOut(BaseModel):
    """Summary of one CSV import run (returned by GET /imports)."""

    id: int
    filename: str
    total_rows: int
    inserted: int
    updated: int
    unchanged: int
    skipped: int
    created_at: datetime | None


# --- analytics --------------------------------------------------------------------


class EpisodesPerDay(BaseModel):
    """Episode count for one calendar day and one robot."""

    day: date
    robot_id: str
    episodes: int


class RequestFulfilment(BaseModel):
    """Request pipeline health statistics for the queried date range."""

    by_status: dict[RequestStatus, int] = Field(
        description="Count of requests grouped by current status."
    )
    total: int = Field(description="Total requests in the date range.")
    delivered_count: int = Field(description="Requests that reached 'delivered' at least once.")
    median_hours_submitted_to_delivered: float | None = Field(
        description="Median hours from submission to first delivery. Null if no deliveries."
    )


class TopTask(BaseModel):
    """One entry in the top-5 tasks by good episode count."""

    task_name: str
    good_episodes: int


class AnalyticsOut(BaseModel):
    """Analytics response for a given date range."""

    date_from: date
    date_to: date
    episodes_per_day: list[EpisodesPerDay]
    request_fulfilment: RequestFulfilment
    top_tasks_by_good_episodes: list[TopTask]
