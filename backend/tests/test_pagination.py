"""Pagination totals and limit/offset slicing for list endpoints (HTTP layer)."""

from app.models import Quality, Role
from app.security import create_access_token
from tests.factories import make_episode, make_request, make_user


def auth_headers(user) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


def test_requests_pagination_total_and_slicing(client, db):
    client_a = make_user(db, Role.CLIENT)
    operator = make_user(db, Role.OPERATOR)
    for _ in range(5):
        make_request(db, client_a)
    headers = auth_headers(operator)

    first = client.get("/requests?limit=2&offset=0", headers=headers).json()
    assert first["total"] == 5
    assert [first["limit"], first["offset"]] == [2, 0]
    assert len(first["items"]) == 2
    assert first["has_more"] is True

    last = client.get("/requests?limit=2&offset=4", headers=headers).json()
    assert last["total"] == 5
    assert len(last["items"]) == 1
    assert last["has_more"] is False

    # Slices are stable and non-overlapping.
    ids_first = {r["id"] for r in first["items"]}
    ids_last = {r["id"] for r in last["items"]}
    assert not ids_first & ids_last


def test_requests_total_respects_client_scope_and_status_filter(client, db):
    client_a = make_user(db, Role.CLIENT)
    client_b = make_user(db, Role.CLIENT)
    make_request(db, client_a)
    make_request(db, client_a)
    make_request(db, client_b)

    body = client.get("/requests", headers=auth_headers(client_a)).json()
    assert body["total"] == 2

    body = client.get("/requests?status=delivered", headers=auth_headers(client_a)).json()
    assert body["total"] == 0
    assert body["items"] == []


def test_episodes_pagination_total_and_filter(client, db):
    operator = make_user(db, Role.OPERATOR)
    for _ in range(3):
        make_episode(db, Quality.GOOD)
    make_episode(db, Quality.BAD)
    headers = auth_headers(operator)

    body = client.get("/episodes?limit=2&offset=0", headers=headers).json()
    assert body["total"] == 4
    assert len(body["items"]) == 2
    assert body["has_more"] is True

    body = client.get("/episodes?quality=bad", headers=headers).json()
    assert body["total"] == 1
    assert len(body["items"]) == 1
    assert body["has_more"] is False
