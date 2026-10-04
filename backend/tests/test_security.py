"""Authorization + status-transition rules at the HTTP layer.

What the brief cares about:
- every action except login requires auth (401 without a token);
- clients see only their own requests (404, not 403, for another client's);
- role ownership of transitions (staff: submitted->in_progress->delivered,
  rejected->in_progress; clients: delivered->accepted/rejected);
- admin user management + self-lockout protection;
- deactivated users lose access immediately.
"""

import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.models import Role
from app.security import create_access_token, hash_password
from app.models import User


def _unique(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}@example.com"


def create_user(db, *, role: Role, password: str = "password123") -> User:
    user = User(
        email=_unique(role.value),
        name=f"{role.value} user",
        role=role,
        password_hash=hash_password(password),
        is_active=True,
    )
    db.add(user)
    db.commit()
    return user


def auth_headers(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


def make_request(client_api: TestClient, headers: dict, n: int = 1) -> dict:
    body = {
        "task_name": "pick cup",
        "episodes_requested": n,
        "deadline": (datetime.now(UTC) + timedelta(days=30)).date().isoformat(),
        "notes": "",
    }
    r = client_api.post("/requests", json=body, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def test_unauthenticated_is_401(client: TestClient):
    assert client.get("/requests").status_code == 401
    assert client.get("/episodes").status_code == 401
    assert client.get("/analytics?date_from=2026-01-01&date_to=2026-12-31").status_code == 401


def test_client_cannot_see_others_requests(client: TestClient, db):
    client_a = create_user(db, role=Role.CLIENT)
    client_b = create_user(db, role=Role.CLIENT)
    req = make_request(client, auth_headers(client_a))
    # Anti-probing: 404, not 403.
    r = client.get(f"/requests/{req['id']}", headers=auth_headers(client_b))
    assert r.status_code == 404
    # ... and it does not appear in the list either.
    r = client.get("/requests", headers=auth_headers(client_b))
    assert r.status_code == 200
    assert all(item["id"] != req["id"] for item in r.json()["items"])


def test_operator_sees_all_requests(client: TestClient, db):
    client_a = create_user(db, role=Role.CLIENT)
    operator = create_user(db, role=Role.OPERATOR)
    req = make_request(client, auth_headers(client_a))
    r = client.get(f"/requests/{req['id']}", headers=auth_headers(operator))
    assert r.status_code == 200


def test_client_cannot_do_staff_transition(client: TestClient, db):
    c = create_user(db, role=Role.CLIENT)
    req = make_request(client, auth_headers(c))
    r = client.post(
        f"/requests/{req['id']}/transitions",
        json={"to_status": "in_progress"},
        headers=auth_headers(c),
    )
    assert r.status_code == 403


def test_operator_cannot_accept_delivery(client: TestClient, db):
    c = create_user(db, role=Role.CLIENT)
    op = create_user(db, role=Role.OPERATOR)
    req = make_request(client, auth_headers(c))
    r = client.post(
        f"/requests/{req['id']}/transitions",
        json={"to_status": "accepted"},
        headers=auth_headers(op),
    )
    # Invalid transition for this state AND wrong role; either way it must fail
    # with 4xx, never succeed.
    assert r.status_code in (403, 409)


def test_reject_requires_reason(client: TestClient, db):
    from app.models import Episode, Quality, RequestStatus, Robot
    from app.services import assignments as assign_service
    from app.services import requests as request_service

    c = create_user(db, role=Role.CLIENT)
    op = create_user(db, role=Role.OPERATOR)
    req = make_request(client, auth_headers(c))
    request_service.transition(db, op, req["id"], RequestStatus.IN_PROGRESS)
    robot_id = "arm-01"
    if db.get(Robot, robot_id) is None:
        db.add(Robot(robot_id=robot_id))
        db.commit()
    ep = Episode(
        episode_id=f"EP-{uuid.uuid4().int % 10**9:09d}",
        robot_id=robot_id,
        task_name="pick cup",
        recorded_at=datetime.now(UTC) - timedelta(days=1),
        duration_seconds=10,
        quality=Quality.GOOD,
    )
    db.add(ep)
    db.commit()
    assign_service.assign(db, op, req["id"], [ep.episode_id])
    request_service.transition(db, op, req["id"], RequestStatus.DELIVERED)
    # No note -> 422; with note -> accepted path works.
    r = client.post(
        f"/requests/{req['id']}/transitions",
        json={"to_status": "rejected"},
        headers=auth_headers(c),
    )
    assert r.status_code == 422
    r = client.post(
        f"/requests/{req['id']}/transitions",
        json={"to_status": "rejected", "note": "gripper occluded"},
        headers=auth_headers(c),
    )
    assert r.status_code == 200
    assert r.json()["status"] == "rejected"


def test_client_cannot_assign_or_import(client: TestClient, db):
    c = create_user(db, role=Role.CLIENT)
    req = make_request(client, auth_headers(c))
    r = client.post(
        f"/requests/{req['id']}/assignments",
        json={"episode_ids": ["EP-00001"]},
        headers=auth_headers(c),
    )
    assert r.status_code == 403
    r = client.post(
        "/import",
        files={"file": ("ep.csv", "episode_id\n", "text/csv")},
        headers=auth_headers(c),
    )
    assert r.status_code == 403


def test_analytics_requires_staff(client: TestClient, db):
    c = create_user(db, role=Role.CLIENT)
    op = create_user(db, role=Role.OPERATOR)
    url = "/analytics?date_from=2026-01-01&date_to=2026-12-31"
    assert client.get(url, headers=auth_headers(c)).status_code == 403
    assert client.get(url, headers=auth_headers(op)).status_code == 200


def test_deactivated_user_loses_access_immediately(client: TestClient, db):
    c = create_user(db, role=Role.CLIENT)
    headers = auth_headers(c)
    assert client.get("/requests", headers=headers).status_code == 200
    c.is_active = False
    db.commit()
    assert client.get("/requests", headers=headers).status_code == 401


def test_admin_self_lockout_protection(client: TestClient, db):
    admin = create_user(db, role=Role.ADMIN)
    headers = auth_headers(admin)
    r = client.patch(f"/users/{admin.id}", json={"is_active": False}, headers=headers)
    assert r.status_code == 422
    r = client.patch(f"/users/{admin.id}", json={"role": "client"}, headers=headers)
    assert r.status_code == 422


def test_login_wrong_password_is_401(client: TestClient, db):
    create_user(db, role=Role.CLIENT, password="correct-password")
    # Need the email: fetch the most recent client.
    from sqlalchemy import select

    user = db.scalar(select(User).order_by(User.id.desc()))
    r = client.post("/auth/login", json={"email": user.email, "password": "wrong"})
    assert r.status_code == 401


def test_import_size_limit_enforced(client: TestClient, db, monkeypatch):
    import app.api.episodes as episodes_api

    op = create_user(db, role=Role.OPERATOR)
    headers = auth_headers(op)
    monkeypatch.setattr(
        episodes_api, "get_settings", lambda: type("S", (), {"max_import_bytes": 10})()
    )
    r = client.post(
        "/import",
        files={"file": ("ep.csv", "x" * 11, "text/csv")},
        headers=headers,
    )
    assert r.status_code == 413
    monkeypatch.undo()
    small = "episode_id,robot_id,task_name,recorded_at,duration_seconds,operator_name,quality\n"
    r = client.post(
        "/import", files={"file": ("ep.csv", small, "text/csv")}, headers=headers
    )
    assert r.status_code == 201


def test_import_history_lists_runs(client: TestClient, db):
    op = create_user(db, role=Role.OPERATOR)
    headers = auth_headers(op)
    small = "episode_id,robot_id,task_name,recorded_at,duration_seconds,operator_name,quality\n"
    r = client.post(
        "/import", files={"file": ("ep.csv", small, "text/csv")}, headers=headers
    )
    assert r.status_code == 201
    r = client.get("/imports", headers=headers)
    assert r.status_code == 200
    assert any(run["filename"] == "ep.csv" for run in r.json())
    # Clients cannot see import history.
    c = create_user(db, role=Role.CLIENT)
    assert client.get("/imports", headers=auth_headers(c)).status_code == 403


def test_analytics_rejects_inverted_range(client: TestClient, db):
    op = create_user(db, role=Role.OPERATOR)
    r = client.get(
        "/analytics?date_from=2026-12-31&date_to=2026-01-01",
        headers=auth_headers(op),
    )
    assert r.status_code == 422
