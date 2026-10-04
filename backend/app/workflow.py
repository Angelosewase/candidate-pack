"""The request status machine, as data.

    submitted -> in_progress -> delivered -> accepted
                                          \\-> rejected -> in_progress (rework)

Each allowed transition maps to the roles that own that step. Anything not in this
table is rejected. Pre-conditions that need the database (e.g. enough episodes
assigned before ``delivered``) are checked in services/requests.py.
"""

from app.models import RequestStatus as S
from app.models import Role

_STAFF = frozenset({Role.OPERATOR, Role.ADMIN})
_CLIENT = frozenset({Role.CLIENT})

TRANSITIONS: dict[tuple[S, S], frozenset[Role]] = {
    (S.SUBMITTED, S.IN_PROGRESS): _STAFF,
    (S.IN_PROGRESS, S.DELIVERED): _STAFF,
    (S.DELIVERED, S.ACCEPTED): _CLIENT,
    (S.DELIVERED, S.REJECTED): _CLIENT,
    (S.REJECTED, S.IN_PROGRESS): _STAFF,
}


def is_valid_transition(current: S, target: S) -> bool:
    return (current, target) in TRANSITIONS


def roles_for(current: S, target: S) -> frozenset[Role]:
    return TRANSITIONS.get((current, target), frozenset())


def allowed_targets(current: S, role: Role) -> list[S]:
    """Transitions a user with ``role`` may attempt from ``current`` (drives the UI)."""
    return [t for (c, t), roles in TRANSITIONS.items() if c == current and role in roles]
