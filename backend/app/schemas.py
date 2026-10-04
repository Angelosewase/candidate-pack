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
    items: list[T]
    limit: int
    offset: int
    has_more: bool


# --- auth / users -----------------------------------------------------------------


class LoginIn(InputModel):
    email: Annotated[str, StringConstraints(max_length=254)]
    password: Annotated[str, StringConstraints(max_length=200)]


class UserOut(OutputModel):
    id: int
    email: str
    name: str
    organisation: str | None
    role: Role
    is_active: bool
    created_at: datetime


class UserBrief(OutputModel):
    id: int
    name: str
    organisation: str | None = None
    role: Role


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class UserCreate(InputModel):
    email: Email
    name: Name
    password: Password
    role: Role
    organisation: Name | None = None


class UserUpdate(InputModel):
    name: Name | None = None
    organisation: Name | None = None
    role: Role | None = None
    is_active: bool | None = None
    password: Password | None = None


# --- requests ---------------------------------------------------------------------


class RequestCreate(InputModel):
    task_name: TaskName
    episodes_requested: int = Field(ge=1, le=100_000)
    deadline: date
    notes: Annotated[str, StringConstraints(max_length=5000)] = ""


class TransitionIn(InputModel):
    to_status: RequestStatus
    note: Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)] | None = None


class StatusEventOut(OutputModel):
    id: int
    from_status: RequestStatus | None
    to_status: RequestStatus
    actor: UserBrief
    note: str | None
    created_at: datetime


class RequestOut(OutputModel):
    id: int
    client: UserBrief
    task_name: str
    episodes_requested: int
    deadline: date
    notes: str
    status: RequestStatus
    created_at: datetime
    updated_at: datetime
    assigned_count: int
    allowed_transitions: list[RequestStatus]


class RequestDetailOut(RequestOut):
    events: list[StatusEventOut]


# --- episodes / assignments -------------------------------------------------------


class EpisodeOut(OutputModel):
    episode_id: str
    robot_id: str
    task_name: str
    recorded_at: datetime
    duration_seconds: int | None
    operator_name: str | None
    quality: Quality
    assigned_request_id: int | None = None


class AssignIn(InputModel):
    episode_ids: list[Annotated[str, StringConstraints(strip_whitespace=True, max_length=50)]] = (
        Field(min_length=1, max_length=500)
    )


class AssignmentOut(OutputModel):
    episode: EpisodeOut
    assigned_at: datetime
    assigned_by: int


# --- analytics --------------------------------------------------------------------


class EpisodesPerDay(BaseModel):
    day: date
    robot_id: str
    episodes: int


class RequestFulfilment(BaseModel):
    by_status: dict[RequestStatus, int]
    total: int
    delivered_count: int
    median_hours_submitted_to_delivered: float | None


class TopTask(BaseModel):
    task_name: str
    good_episodes: int


class AnalyticsOut(BaseModel):
    date_from: date
    date_to: date
    episodes_per_day: list[EpisodesPerDay]
    request_fulfilment: RequestFulfilment
    top_tasks_by_good_episodes: list[TopTask]
