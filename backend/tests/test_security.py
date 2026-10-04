"""Authorization, status-transition, and endpoint security tests (HTTP layer).

Tests at this level verify that the HTTP-facing rules are enforced:
- every protected endpoint requires a valid JWT (401 without one);
- clients see only their own requests (404, not 403, for another client's);
- role ownership of status transitions;
- admin user management and self-lockout protection;
- deactivated users lose access immediately;
- import size limits;
- analytics date range validation.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.models import Episode, Quality, RequestStatus, Robot, Role, User
from app.security import create_access_token, hash_password
from app.services import assignments as assign_service
from app.services import requests as request_service
from tests.factories import make_episode, make_request, make_user, move_to_in_progress


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def auth_headers(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


def _post_request(api: TestClient, headers: dict, n: int = 1) -> dict:
    body = {
        "task_name": "pick cup",
        "episodes_requested": n,
        "deadline": (datetime.now(UTC) + timedelta(days=30)).date().isoformat(),
        "notes": "",
    }
    r = api.post("/requests", json=body, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


# ---------------------------------------------------------------------------
# Authentication guards
# ---------------------------------------------------------------------------


class TestAuthenticationGuards:
    def test_unauthenticated_gets_401(self, client: TestClient):
        assert client.get("/requests").status_code == 401
        assert client.get("/episodes").status_code == 401
        assert client.get("/analytics?date_from=2026-01-01&date_to=2026-12-31").status_code == 401
        assert client.get("/imports").status_code == 401
        assert client.get("/users").status_code == 401

    def test_invalid_token_gets_401(self, client: TestClient):
        bad_headers = {"Authorization": "Bearer not.a.real.token"}
        assert client.get("/requests", headers=bad_headers).status_code == 401

    def test_login_wrong_password_is_401(self, client: TestClient, db):
        user = make_user(db, Role.CLIENT)
        r = client.post("/auth/login", json={"email": user.email, "password": "wrong-password"})
        assert r.status_code == 401

    def test_login_unknown_email_is_401(self, client: TestClient):
        r = client.post("/auth/login", json={"email": "nobody@example.com", "password": "x"})
        assert r.status_code == 401

    def test_login_success_returns_token_and_user(self, client: TestClient, db):
        user = make_user(db, Role.OPERATOR)
        # Re-set known password so we can use it.
        user.password_hash = hash_password("secret123")
        db.commit()
        r = client.post("/auth/login", json={"email": user.email, "password": "secret123"})
        assert r.status_code == 200
        data = r.json()
        assert "access_token" in data
        assert data["user"]["email"] == user.email


# ---------------------------------------------------------------------------
# Visibility / isolation
# ---------------------------------------------------------------------------


class TestClientVisibility:
    def test_client_cannot_see_other_clients_request(self, client: TestClient, db):
        client_a = make_user(db, Role.CLIENT)
        client_b = make_user(db, Role.CLIENT)
        req = _post_request(client, auth_headers(client_a))

        # Anti-probing: 404, not 403.
        r = client.get(f"/requests/{req['id']}", headers=auth_headers(client_b))
        assert r.status_code == 404

    def test_other_clients_request_absent_from_list(self, client: TestClient, db):
        client_a = make_user(db, Role.CLIENT)
        client_b = make_user(db, Role.CLIENT)
        req = _post_request(client, auth_headers(client_a))

        r = client.get("/requests", headers=auth_headers(client_b))
        assert r.status_code == 200
        assert all(item["id"] != req["id"] for item in r.json()["items"])

    def test_operator_sees_all_requests(self, client: TestClient, db):
        client_a = make_user(db, Role.CLIENT)
        operator = make_user(db, Role.OPERATOR)
        req = _post_request(client, auth_headers(client_a))

        r = client.get(f"/requests/{req['id']}", headers=auth_headers(operator))
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# Status transition authorization
# ---------------------------------------------------------------------------


class TestTransitionAuthorization:
    def test_client_cannot_do_staff_transition(self, client: TestClient, db):
        c = make_user(db, Role.CLIENT)
        req = _post_request(client, auth_headers(c))

        r = client.post(
            f"/requests/{req['id']}/transitions",
            json={"to_status": "in_progress"},
            headers=auth_headers(c),
        )
        assert r.status_code == 403

    def test_operator_cannot_accept_delivery(self, client: TestClient, db):
        c = make_user(db, Role.CLIENT)
        op = make_user(db, Role.OPERATOR)
        req = _post_request(client, auth_headers(c))

        r = client.post(
            f"/requests/{req['id']}/transitions",
            json={"to_status": "accepted"},
            headers=auth_headers(op),
        )
        # Wrong transition from 'submitted' AND wrong role — must fail with 4xx.
        assert r.status_code in (403, 409)

    def test_full_happy_path_transitions(self, client: TestClient, db):
        """Operator moves submitted→in_progress→delivered; client accepts."""
        c = make_user(db, Role.CLIENT)
        op = make_user(db, Role.OPERATOR)
        req = _post_request(client, auth_headers(c), n=1)
        rid = req["id"]

        # submitted → in_progress
        r = client.post(
            f"/requests/{rid}/transitions",
            json={"to_status": "in_progress"},
            headers=auth_headers(op),
        )
        assert r.status_code == 200
        assert r.json()["status"] == "in_progress"

        # Assign one episode via service (avoids HTTP episode import complexity)
        ep = make_episode(db, Quality.GOOD)
        assign_service.assign(db, op, rid, [ep.episode_id])

        # in_progress → delivered
        r = client.post(
            f"/requests/{rid}/transitions",
            json={"to_status": "delivered"},
            headers=auth_headers(op),
        )
        assert r.status_code == 200
        assert r.json()["status"] == "delivered"

        # delivered → accepted
        r = client.post(
            f"/requests/{rid}/transitions",
            json={"to_status": "accepted"},
            headers=auth_headers(c),
        )
        assert r.status_code == 200
        assert r.json()["status"] == "accepted"

    def test_reject_without_reason_is_422(self, client: TestClient, db):
        c = make_user(db, Role.CLIENT)
        op = make_user(db, Role.OPERATOR)
        req = _post_request(client, auth_headers(c), n=1)
        rid = req["id"]

        ep = make_episode(db, Quality.GOOD)
        request_service.transition(db, op, rid, RequestStatus.IN_PROGRESS)
        assign_service.assign(db, op, rid, [ep.episode_id])
        request_service.transition(db, op, rid, RequestStatus.DELIVERED)

        r = client.post(
            f"/requests/{rid}/transitions",
            json={"to_status": "rejected"},
            headers=auth_headers(c),
        )
        assert r.status_code == 422

    def test_reject_with_reason_succeeds(self, client: TestClient, db):
        c = make_user(db, Role.CLIENT)
        op = make_user(db, Role.OPERATOR)
        req = _post_request(client, auth_headers(c), n=1)
        rid = req["id"]

        ep = make_episode(db, Quality.GOOD)
        request_service.transition(db, op, rid, RequestStatus.IN_PROGRESS)
        assign_service.assign(db, op, rid, [ep.episode_id])
        request_service.transition(db, op, rid, RequestStatus.DELIVERED)

        r = client.post(
            f"/requests/{rid}/transitions",
            json={"to_status": "rejected", "note": "Gripper was occluded."},
            headers=auth_headers(c),
        )
        assert r.status_code == 200
        assert r.json()["status"] == "rejected"

    def test_rework_cycle_rejected_back_to_in_progress(self, client: TestClient, db):
        """rejected → in_progress (rework) is allowed for staff."""
        c = make_user(db, Role.CLIENT)
        op = make_user(db, Role.OPERATOR)
        req = _post_request(client, auth_headers(c), n=1)
        rid = req["id"]

        ep = make_episode(db, Quality.GOOD)
        request_service.transition(db, op, rid, RequestStatus.IN_PROGRESS)
        assign_service.assign(db, op, rid, [ep.episode_id])
        request_service.transition(db, op, rid, RequestStatus.DELIVERED)
        request_service.transition(
            db, c, rid, RequestStatus.REJECTED, "Gripper occluded."
        )

        r = client.post(
            f"/requests/{rid}/transitions",
            json={"to_status": "in_progress"},
            headers=auth_headers(op),
        )
        assert r.status_code == 200
        assert r.json()["status"] == "in_progress"


# ---------------------------------------------------------------------------
# Role-based endpoint access
# ---------------------------------------------------------------------------


class TestEndpointAccess:
    def test_client_cannot_assign_episodes(self, client: TestClient, db):
        c = make_user(db, Role.CLIENT)
        req = _post_request(client, auth_headers(c))

        r = client.post(
            f"/requests/{req['id']}/assignments",
            json={"episode_ids": ["EP-000000001"]},
            headers=auth_headers(c),
        )
        assert r.status_code == 403

    def test_client_cannot_import_csv(self, client: TestClient, db):
        c = make_user(db, Role.CLIENT)
        r = client.post(
            "/import",
            files={"file": ("ep.csv", "episode_id\n", "text/csv")},
            headers=auth_headers(c),
        )
        assert r.status_code == 403

    def test_client_cannot_access_analytics(self, client: TestClient, db):
        c = make_user(db, Role.CLIENT)
        r = client.get(
            "/analytics?date_from=2026-01-01&date_to=2026-12-31",
            headers=auth_headers(c),
        )
        assert r.status_code == 403

    def test_operator_can_access_analytics(self, client: TestClient, db):
        op = make_user(db, Role.OPERATOR)
        r = client.get(
            "/analytics?date_from=2026-01-01&date_to=2026-12-31",
            headers=auth_headers(op),
        )
        assert r.status_code == 200

    def test_client_cannot_list_users(self, client: TestClient, db):
        c = make_user(db, Role.CLIENT)
        assert client.get("/users", headers=auth_headers(c)).status_code == 403

    def test_operator_cannot_manage_users(self, client: TestClient, db):
        op = make_user(db, Role.OPERATOR)
        assert client.get("/users", headers=auth_headers(op)).status_code == 403

    def test_client_cannot_view_episodes(self, client: TestClient, db):
        c = make_user(db, Role.CLIENT)
        assert client.get("/episodes", headers=auth_headers(c)).status_code == 403

    def test_client_cannot_view_import_history(self, client: TestClient, db):
        c = make_user(db, Role.CLIENT)
        assert client.get("/imports", headers=auth_headers(c)).status_code == 403


# ---------------------------------------------------------------------------
# User management
# ---------------------------------------------------------------------------


class TestUserManagement:
    def test_admin_can_create_and_list_users(self, client: TestClient, db):
        admin = make_user(db, Role.ADMIN)
        new_email = f"newuser-{uuid.uuid4().hex[:6]}@example.com"

        r = client.post(
            "/users",
            json={"email": new_email, "name": "New User", "password": "secret99", "role": "client"},
            headers=auth_headers(admin),
        )
        assert r.status_code == 201
        assert r.json()["email"] == new_email

        r = client.get("/users", headers=auth_headers(admin))
        assert r.status_code == 200
        assert any(u["email"] == new_email for u in r.json())

    def test_duplicate_email_returns_409(self, client: TestClient, db):
        admin = make_user(db, Role.ADMIN)
        existing = make_user(db, Role.CLIENT)

        r = client.post(
            "/users",
            json={"email": existing.email, "name": "Dup", "password": "secret99", "role": "client"},
            headers=auth_headers(admin),
        )
        assert r.status_code == 409

    def test_admin_self_lockout_protection(self, client: TestClient, db):
        admin = make_user(db, Role.ADMIN)

        r = client.patch(
            f"/users/{admin.id}", json={"is_active": False}, headers=auth_headers(admin)
        )
        assert r.status_code == 422

        r = client.patch(
            f"/users/{admin.id}", json={"role": "client"}, headers=auth_headers(admin)
        )
        assert r.status_code == 422

    def test_deactivated_user_loses_access_immediately(self, client: TestClient, db):
        c = make_user(db, Role.CLIENT)
        headers = auth_headers(c)
        assert client.get("/requests", headers=headers).status_code == 200

        c.is_active = False
        db.commit()

        assert client.get("/requests", headers=headers).status_code == 401


# ---------------------------------------------------------------------------
# Import endpoint
# ---------------------------------------------------------------------------


class TestImport:
    _HEADER = "episode_id,robot_id,task_name,recorded_at,duration_seconds,operator_name,quality\n"

    def test_import_empty_csv_succeeds(self, client: TestClient, db):
        op = make_user(db, Role.OPERATOR)
        r = client.post(
            "/import",
            files={"file": ("ep.csv", self._HEADER, "text/csv")},
            headers=auth_headers(op),
        )
        assert r.status_code == 201

    def test_import_size_limit_enforced(self, client: TestClient, db, monkeypatch):
        import app.api.episodes as episodes_api

        op = make_user(db, Role.OPERATOR)
        monkeypatch.setattr(
            episodes_api, "get_settings", lambda: type("S", (), {"max_import_bytes": 10})()
        )
        r = client.post(
            "/import",
            files={"file": ("ep.csv", "x" * 11, "text/csv")},
            headers=auth_headers(op),
        )
        assert r.status_code == 413

    def test_import_history_is_visible_to_staff(self, client: TestClient, db):
        op = make_user(db, Role.OPERATOR)
        client.post(
            "/import",
            files={"file": ("run.csv", self._HEADER, "text/csv")},
            headers=auth_headers(op),
        )
        r = client.get("/imports", headers=auth_headers(op))
        assert r.status_code == 200
        assert any(run["filename"] == "run.csv" for run in r.json())


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------


class TestAnalytics:
    def test_inverted_date_range_is_422(self, client: TestClient, db):
        op = make_user(db, Role.OPERATOR)
        r = client.get(
            "/analytics?date_from=2026-12-31&date_to=2026-01-01",
            headers=auth_headers(op),
        )
        assert r.status_code == 422

    def test_valid_range_returns_expected_shape(self, client: TestClient, db):
        op = make_user(db, Role.OPERATOR)
        r = client.get(
            "/analytics?date_from=2026-01-01&date_to=2026-12-31",
            headers=auth_headers(op),
        )
        assert r.status_code == 200
        data = r.json()
        assert "episodes_per_day" in data
        assert "request_fulfilment" in data
        assert "top_tasks_by_good_episodes" in data
        assert "by_status" in data["request_fulfilment"]


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


class TestHealth:
    def test_health_returns_ok(self, client: TestClient):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json() == {"status": "ok"}
