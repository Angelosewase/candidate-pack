"""Assignment rules and delivery precondition tests (service layer).

Covers the brief's assignment rules:
- Only good/usable episodes can be assigned.
- An episode can be assigned to at most one request at a time.
- Re-assigning to the *same* request is idempotent.
- Unassign releases the episode for another request.
- A request cannot move to delivered until it has episodes_requested assigned.
- Assigned episodes graded 'bad' by a later import block delivery.
"""

import pytest

from app.errors import Conflict, NotFound
from app.models import Quality, RequestStatus, Role
from app.services import assignments as assign_service
from app.services import requests as request_service
from tests.factories import (
    make_episode,
    make_request,
    make_user,
    move_to_in_progress,
)


# ---------------------------------------------------------------------------
# Basic assignment
# ---------------------------------------------------------------------------


class TestAssign:
    def test_assign_good_episode_succeeds(self, db):
        staff = make_user(db, Role.OPERATOR)
        client = make_user(db, Role.CLIENT)
        rid = make_request(db, client, 1)
        move_to_in_progress(db, staff, rid)
        ep = make_episode(db, Quality.GOOD)

        result = assign_service.assign(db, staff, rid, [ep.episode_id])
        assert len(result) == 1
        assert result[0].episode_id == ep.episode_id

    def test_assign_usable_episode_succeeds(self, db):
        staff = make_user(db, Role.OPERATOR)
        client = make_user(db, Role.CLIENT)
        rid = make_request(db, client, 1)
        move_to_in_progress(db, staff, rid)
        ep = make_episode(db, Quality.USABLE)

        result = assign_service.assign(db, staff, rid, [ep.episode_id])
        assert len(result) == 1

    def test_assign_bad_episode_rejected(self, db):
        staff = make_user(db, Role.OPERATOR)
        client = make_user(db, Role.CLIENT)
        rid = make_request(db, client, 1)
        move_to_in_progress(db, staff, rid)
        bad = make_episode(db, Quality.BAD)

        with pytest.raises(Conflict, match="Only 'good' or 'usable'"):
            assign_service.assign(db, staff, rid, [bad.episode_id])
        # Nothing was assigned.
        assert assign_service.list_assignments(db, rid) == []

    def test_assign_multiple_episodes_at_once(self, db):
        staff = make_user(db, Role.OPERATOR)
        client = make_user(db, Role.CLIENT)
        rid = make_request(db, client, 3)
        move_to_in_progress(db, staff, rid)
        eps = [make_episode(db, Quality.GOOD) for _ in range(3)]

        result = assign_service.assign(db, staff, rid, [e.episode_id for e in eps])
        assert {a.episode_id for a in result} == {e.episode_id for e in eps}


# ---------------------------------------------------------------------------
# Missing / unknown episodes
# ---------------------------------------------------------------------------


class TestAssignMissingEpisodes:
    def test_missing_episode_reports_id_and_assigns_nothing(self, db):
        staff = make_user(db, Role.OPERATOR)
        client = make_user(db, Role.CLIENT)
        rid = make_request(db, client, 1)
        move_to_in_progress(db, staff, rid)
        good = make_episode(db, Quality.GOOD)

        with pytest.raises(NotFound) as exc_info:
            assign_service.assign(db, staff, rid, [good.episode_id, "EP-000000001"])

        assert "EP-000000001" in str(exc_info.value.details)
        # All-or-nothing: the valid episode was NOT assigned.
        assert assign_service.list_assignments(db, rid) == []


# ---------------------------------------------------------------------------
# Duplicate / concurrent assignment
# ---------------------------------------------------------------------------


class TestDoubleAssignment:
    def test_episode_cannot_be_assigned_to_two_requests(self, db):
        staff = make_user(db, Role.OPERATOR)
        client = make_user(db, Role.CLIENT)
        rid1 = make_request(db, client, 1)
        rid2 = make_request(db, client, 1)
        move_to_in_progress(db, staff, rid1)
        move_to_in_progress(db, staff, rid2)
        ep = make_episode(db, Quality.GOOD)

        assign_service.assign(db, staff, rid1, [ep.episode_id])
        with pytest.raises(Conflict, match="already assigned"):
            assign_service.assign(db, staff, rid2, [ep.episode_id])

    def test_reassign_same_request_is_idempotent(self, db):
        staff = make_user(db, Role.OPERATOR)
        client = make_user(db, Role.CLIENT)
        rid = make_request(db, client, 1)
        move_to_in_progress(db, staff, rid)
        ep = make_episode(db, Quality.GOOD)

        assign_service.assign(db, staff, rid, [ep.episode_id])
        result = assign_service.assign(db, staff, rid, [ep.episode_id])
        # Still exactly one assignment.
        assert len(result) == 1
        assert result[0].episode_id == ep.episode_id


# ---------------------------------------------------------------------------
# Unassign
# ---------------------------------------------------------------------------


class TestUnassign:
    def test_unassign_releases_episode_for_another_request(self, db):
        staff = make_user(db, Role.OPERATOR)
        client = make_user(db, Role.CLIENT)
        rid1 = make_request(db, client, 1)
        rid2 = make_request(db, client, 1)
        move_to_in_progress(db, staff, rid1)
        move_to_in_progress(db, staff, rid2)
        ep = make_episode(db, Quality.USABLE)

        assign_service.assign(db, staff, rid1, [ep.episode_id])
        assign_service.unassign(db, staff, rid1, ep.episode_id)

        result = assign_service.assign(db, staff, rid2, [ep.episode_id])
        assert result[0].episode_id == ep.episode_id

    def test_unassign_unknown_episode_raises_not_found(self, db):
        staff = make_user(db, Role.OPERATOR)
        client = make_user(db, Role.CLIENT)
        rid = make_request(db, client, 1)
        move_to_in_progress(db, staff, rid)

        with pytest.raises(NotFound):
            assign_service.unassign(db, staff, rid, "EP-000000001")


# ---------------------------------------------------------------------------
# Status-gated assignment
# ---------------------------------------------------------------------------


class TestAssignStatusGating:
    def test_assign_blocked_in_submitted_status(self, db):
        staff = make_user(db, Role.OPERATOR)
        client = make_user(db, Role.CLIENT)
        rid = make_request(db, client, 1)  # still submitted
        ep = make_episode(db, Quality.GOOD)

        with pytest.raises(Conflict, match="only be assigned while the request is in progress"):
            assign_service.assign(db, staff, rid, [ep.episode_id])

    def test_unassign_blocked_when_not_in_progress(self, db):
        staff = make_user(db, Role.OPERATOR)
        client = make_user(db, Role.CLIENT)
        rid = make_request(db, client, 1)
        move_to_in_progress(db, staff, rid)
        ep = make_episode(db, Quality.GOOD)
        assign_service.assign(db, staff, rid, [ep.episode_id])
        request_service.transition(db, staff, rid, RequestStatus.DELIVERED)

        with pytest.raises(Conflict):
            assign_service.unassign(db, staff, rid, ep.episode_id)


# ---------------------------------------------------------------------------
# Delivery preconditions
# ---------------------------------------------------------------------------


class TestDeliveryPreconditions:
    def test_delivered_requires_enough_episodes(self, db):
        staff = make_user(db, Role.OPERATOR)
        client = make_user(db, Role.CLIENT)
        rid = make_request(db, client, 2)
        move_to_in_progress(db, staff, rid)
        ep = make_episode(db, Quality.GOOD)
        assign_service.assign(db, staff, rid, [ep.episode_id])

        # Only 1 assigned, need 2 — should fail.
        with pytest.raises(Conflict, match="needs 2 episodes"):
            request_service.transition(db, staff, rid, RequestStatus.DELIVERED)

        ep2 = make_episode(db, Quality.USABLE)
        assign_service.assign(db, staff, rid, [ep2.episode_id])
        result = request_service.transition(db, staff, rid, RequestStatus.DELIVERED)
        assert result.status == RequestStatus.DELIVERED

    def test_delivered_blocked_when_assigned_episode_regraded_bad(self, db):
        """If a re-imported CSV downgrades an assigned episode to 'bad',
        delivery must be blocked until the episode is unassigned."""
        from sqlalchemy import update as sa_update
        from app.models import Episode

        staff = make_user(db, Role.OPERATOR)
        client = make_user(db, Role.CLIENT)
        rid = make_request(db, client, 1)
        move_to_in_progress(db, staff, rid)
        ep = make_episode(db, Quality.GOOD)
        assign_service.assign(db, staff, rid, [ep.episode_id])

        # Simulate a re-import that downgrades the episode.
        db.execute(
            sa_update(Episode)
            .where(Episode.episode_id == ep.episode_id)
            .values(quality=Quality.BAD)
        )
        db.commit()

        with pytest.raises(Conflict, match="graded 'bad'"):
            request_service.transition(db, staff, rid, RequestStatus.DELIVERED)
