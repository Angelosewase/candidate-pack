"""Workflow state-machine unit tests (no database required).

These test only the pure logic in ``app.workflow``:
- which transitions exist;
- which roles own each transition;
- which targets are presented to a given role from a given state.
"""

import pytest

from app.models import RequestStatus as S, Role
from app.workflow import allowed_targets, is_valid_transition, roles_for

_STAFF = frozenset({Role.OPERATOR, Role.ADMIN})
_CLIENT = frozenset({Role.CLIENT})


# ---------------------------------------------------------------------------
# is_valid_transition
# ---------------------------------------------------------------------------


class TestIsValidTransition:
    """All defined transitions return True; undefined ones return False."""

    @pytest.mark.parametrize(
        "current, target",
        [
            (S.SUBMITTED, S.IN_PROGRESS),
            (S.IN_PROGRESS, S.DELIVERED),
            (S.DELIVERED, S.ACCEPTED),
            (S.DELIVERED, S.REJECTED),
            (S.REJECTED, S.IN_PROGRESS),
        ],
    )
    def test_valid_transitions(self, current, target):
        assert is_valid_transition(current, target)

    @pytest.mark.parametrize(
        "current, target",
        [
            (S.SUBMITTED, S.DELIVERED),
            (S.SUBMITTED, S.ACCEPTED),
            (S.SUBMITTED, S.REJECTED),
            (S.IN_PROGRESS, S.SUBMITTED),
            (S.IN_PROGRESS, S.ACCEPTED),
            (S.IN_PROGRESS, S.REJECTED),
            (S.DELIVERED, S.SUBMITTED),
            (S.DELIVERED, S.IN_PROGRESS),
            (S.ACCEPTED, S.IN_PROGRESS),
            (S.ACCEPTED, S.REJECTED),
            (S.REJECTED, S.SUBMITTED),
            (S.REJECTED, S.DELIVERED),
            (S.REJECTED, S.ACCEPTED),
        ],
    )
    def test_invalid_transitions(self, current, target):
        assert not is_valid_transition(current, target)

    def test_self_transitions_are_invalid(self):
        for status in S:
            assert not is_valid_transition(status, status)


# ---------------------------------------------------------------------------
# roles_for
# ---------------------------------------------------------------------------


class TestRolesFor:
    """Each transition is owned by the correct role set."""

    def test_submitted_to_in_progress_is_staff(self):
        assert roles_for(S.SUBMITTED, S.IN_PROGRESS) == _STAFF

    def test_in_progress_to_delivered_is_staff(self):
        assert roles_for(S.IN_PROGRESS, S.DELIVERED) == _STAFF

    def test_delivered_to_accepted_is_client(self):
        assert roles_for(S.DELIVERED, S.ACCEPTED) == _CLIENT

    def test_delivered_to_rejected_is_client(self):
        assert roles_for(S.DELIVERED, S.REJECTED) == _CLIENT

    def test_rejected_to_in_progress_is_staff(self):
        assert roles_for(S.REJECTED, S.IN_PROGRESS) == _STAFF

    def test_invalid_transition_returns_empty(self):
        assert roles_for(S.SUBMITTED, S.ACCEPTED) == frozenset()
        assert roles_for(S.ACCEPTED, S.SUBMITTED) == frozenset()


# ---------------------------------------------------------------------------
# allowed_targets
# ---------------------------------------------------------------------------


class TestAllowedTargets:
    """allowed_targets returns the correct set of targets per role."""

    def test_operator_from_submitted(self):
        assert allowed_targets(S.SUBMITTED, Role.OPERATOR) == [S.IN_PROGRESS]

    def test_admin_from_submitted(self):
        assert allowed_targets(S.SUBMITTED, Role.ADMIN) == [S.IN_PROGRESS]

    def test_client_from_submitted_is_empty(self):
        assert allowed_targets(S.SUBMITTED, Role.CLIENT) == []

    def test_client_from_delivered(self):
        targets = set(allowed_targets(S.DELIVERED, Role.CLIENT))
        assert targets == {S.ACCEPTED, S.REJECTED}

    def test_operator_from_delivered_is_empty(self):
        assert allowed_targets(S.DELIVERED, Role.OPERATOR) == []

    def test_operator_from_in_progress(self):
        assert allowed_targets(S.IN_PROGRESS, Role.OPERATOR) == [S.DELIVERED]

    def test_nobody_can_leave_accepted(self):
        for role in Role:
            assert allowed_targets(S.ACCEPTED, role) == []
