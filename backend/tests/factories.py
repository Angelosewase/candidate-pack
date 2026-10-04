"""Shared test factories used across multiple test modules."""

import uuid
from datetime import UTC, datetime, timedelta

from app.models import Episode, Quality, RequestStatus, Robot, Role, User
from app.schemas import RequestCreate
from app.security import hash_password
from app.services import assignments as assign_service
from app.services import requests as request_service


def unique_id(prefix: str = "") -> str:
    """Return a short unique string, optionally prefixed."""
    return f"{prefix}{uuid.uuid4().hex[:8]}"


def make_user(db, role: Role, *, organisation: str | None = None) -> User:
    """Create and persist a user with a unique email."""
    user = User(
        email=f"{unique_id(role.value + '-')}@example.com",
        name=f"{role.value.title()} User",
        role=role,
        password_hash=hash_password("password123"),
        is_active=True,
        organisation=organisation,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def make_episode(
    db,
    quality: Quality = Quality.GOOD,
    *,
    task_name: str = "pick cup",
    robot_id: str = "arm-01",
    recorded_at: datetime | None = None,
    episode_id: str | None = None,
) -> Episode:
    """Create and persist an episode, ensuring the robot row exists."""
    if db.get(Robot, robot_id) is None:
        db.add(Robot(robot_id=robot_id))
        db.commit()
    ep = Episode(
        episode_id=episode_id or f"EP-{uuid.uuid4().int % 10**9:09d}",
        robot_id=robot_id,
        task_name=task_name,
        recorded_at=recorded_at or (datetime.now(UTC) - timedelta(days=1)),
        duration_seconds=60,
        operator_name="tester",
        quality=quality,
    )
    db.add(ep)
    db.commit()
    db.refresh(ep)
    return ep


def make_request(
    db,
    client: User,
    episodes_requested: int = 2,
    *,
    task_name: str = "pick cup",
    days_until_deadline: int = 30,
) -> int:
    """Create a dataset request in submitted status. Returns the request ID."""
    req = request_service.create_request(
        db,
        client,
        RequestCreate(
            task_name=task_name,
            episodes_requested=episodes_requested,
            deadline=(datetime.now(UTC) + timedelta(days=days_until_deadline)).date(),
            notes="",
        ),
    )
    return req.id


def move_to_in_progress(db, staff: User, request_id: int) -> None:
    request_service.transition(db, staff, request_id, RequestStatus.IN_PROGRESS)


def fully_assign_and_deliver(
    db, staff: User, client: User, request_id: int, count: int
) -> None:
    """Assign `count` good episodes and move the request to delivered."""
    for _ in range(count):
        ep = make_episode(db, Quality.GOOD)
        assign_service.assign(db, staff, request_id, [ep.episode_id])
    request_service.transition(db, staff, request_id, RequestStatus.DELIVERED)
