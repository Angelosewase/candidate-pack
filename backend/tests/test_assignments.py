"""Assignment rules + delivery preconditions (service level).

Covers the brief's assignment rules:
- only good/usable episodes can be assigned;
- an episode can be assigned to at most one request at a time;
- re-assigning to the *same* request is idempotent;
- unassign releases the episode for another request;
- a request cannot move to delivered until it has episodes_requested assigned.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.errors import Conflict, NotFound
from app.models import Assignment, Episode, Quality, RequestStatus, Robot, Role, User
from app.schemas import RequestCreate
from app.security import hash_password
from app.services import assignments as assign_service
from app.services import requests as request_service


def _unique(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def make_user(db, role: Role) -> User:
    email = f"{_unique(role.value)}@example.com"
    user = User(
        email=email,
        name=f"{role.value} user",
        role=role,
        password_hash=hash_password("password123"),
        is_active=True,
    )
    db.add(user)
    db.commit()
    return user


def make_episode(db, quality: Quality, episode_id: str | None = None) -> Episode:
    robot_id = "arm-01"
    if db.get(Robot, robot_id) is None:
        db.add(Robot(robot_id=robot_id))
        db.commit()
    ep = Episode(
        episode_id=episode_id or f"EP-{uuid.uuid4().int % 10**9:09d}",
        robot_id=robot_id,
        task_name="pick cup",
        recorded_at=datetime.now(UTC) - timedelta(days=1),
        duration_seconds=60,
        operator_name="tester",
        quality=quality,
    )
    db.add(ep)
    db.commit()
    return ep


def make_request(db, client: User, episodes_requested: int = 2) -> int:
    req = request_service.create_request(
        db,
        client,
        RequestCreate(
            task_name="pick cup",
            episodes_requested=episodes_requested,
            deadline=(datetime.now(UTC) + timedelta(days=30)).date(),
            notes="",
        ),
    )
    return req.id


def move_to_in_progress(db, staff: User, request_id: int) -> None:
    request_service.transition(db, staff, request_id, RequestStatus.IN_PROGRESS)


def test_assign_good_and_usable_ok(db):
    staff = make_user(db, Role.OPERATOR)
    client = make_user(db, Role.CLIENT)
    rid = make_request(db, client)
    move_to_in_progress(db, staff, rid)
    good = make_episode(db, Quality.GOOD)
    usable = make_episode(db, Quality.USABLE)
    out = assign_service.assign(db, staff, rid, [good.episode_id, usable.episode_id])
    assert {a.episode_id for a in out} == {good.episode_id, usable.episode_id}


def test_assign_bad_rejected(db):
    staff = make_user(db, Role.OPERATOR)
    client = make_user(db, Role.CLIENT)
    rid = make_request(db, client)
    move_to_in_progress(db, staff, rid)
    bad = make_episode(db, Quality.BAD)
    with pytest.raises(Conflict, match="Only 'good' or 'usable'"):
        assign_service.assign(db, staff, rid, [bad.episode_id])
    assert db.scalar(select(Assignment).where(Assignment.episode_id == bad.episode_id)) is None


def test_assign_missing_episode_reports_ids_and_assigns_nothing(db):
    staff = make_user(db, Role.OPERATOR)
    client = make_user(db, Role.CLIENT)
    rid = make_request(db, client)
    move_to_in_progress(db, staff, rid)
    good = make_episode(db, Quality.GOOD)
    with pytest.raises(NotFound) as exc:
        assign_service.assign(db, staff, rid, [good.episode_id, "EP-000000001"])
    assert "EP-000000001" in str(exc.value.details)
    # All-or-nothing: the valid episode was not assigned either.
    assert assign_service.list_assignments(db, rid) == []


def test_double_assignment_to_other_request_conflicts(db):
    staff = make_user(db, Role.OPERATOR)
    client = make_user(db, Role.CLIENT)
    rid1 = make_request(db, client)
    rid2 = make_request(db, client)
    move_to_in_progress(db, staff, rid1)
    move_to_in_progress(db, staff, rid2)
    ep = make_episode(db, Quality.GOOD)
    assign_service.assign(db, staff, rid1, [ep.episode_id])
    with pytest.raises(Conflict, match="already assigned"):
        assign_service.assign(db, staff, rid2, [ep.episode_id])


def test_reassign_same_request_is_idempotent(db):
    staff = make_user(db, Role.OPERATOR)
    client = make_user(db, Role.CLIENT)
    rid = make_request(db, client)
    move_to_in_progress(db, staff, rid)
    ep = make_episode(db, Quality.GOOD)
    assign_service.assign(db, staff, rid, [ep.episode_id])
    out = assign_service.assign(db, staff, rid, [ep.episode_id])
    assert len(out) == 1
    assert out[0].episode_id == ep.episode_id


def test_unassign_releases_for_other_request(db):
    staff = make_user(db, Role.OPERATOR)
    client = make_user(db, Role.CLIENT)
    rid1 = make_request(db, client)
    rid2 = make_request(db, client)
    move_to_in_progress(db, staff, rid1)
    move_to_in_progress(db, staff, rid2)
    ep = make_episode(db, Quality.USABLE)
    assign_service.assign(db, staff, rid1, [ep.episode_id])
    assign_service.unassign(db, staff, rid1, ep.episode_id)
    out = assign_service.assign(db, staff, rid2, [ep.episode_id])
    assert [a.episode_id for a in out] == [ep.episode_id]


def test_assign_only_in_in_progress(db):
    staff = make_user(db, Role.OPERATOR)
    client = make_user(db, Role.CLIENT)
    rid = make_request(db, client)  # still submitted
    ep = make_episode(db, Quality.GOOD)
    with pytest.raises(Conflict, match="only be assigned while the request is in progress"):
        assign_service.assign(db, staff, rid, [ep.episode_id])


def test_delivered_requires_enough_episodes(db):
    staff = make_user(db, Role.OPERATOR)
    client = make_user(db, Role.CLIENT)
    rid = make_request(db, client, episodes_requested=2)
    move_to_in_progress(db, staff, rid)
    ep = make_episode(db, Quality.GOOD)
    assign_service.assign(db, staff, rid, [ep.episode_id])
    with pytest.raises(Conflict, match="needs 2 episodes"):
        request_service.transition(db, staff, rid, RequestStatus.DELIVERED)
    ep2 = make_episode(db, Quality.USABLE)
    assign_service.assign(db, staff, rid, [ep2.episode_id])
    done = request_service.transition(db, staff, rid, RequestStatus.DELIVERED)
    assert done.status == RequestStatus.DELIVERED
