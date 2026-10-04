"""Authentication / authorization dependencies.

Every protected endpoint declares the roles it accepts via ``require_roles``. The user
is re-loaded from the database on every request, so deactivation and role changes take
effect immediately rather than when the token expires.
"""

from collections.abc import Callable

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.db import get_db
from app.errors import Forbidden, Unauthorized
from app.models import Role, User
from app.security import decode_access_token

_bearer = HTTPBearer(auto_error=False)

STAFF = (Role.OPERATOR, Role.ADMIN)


def user_from_token(db: Session, token: str | None) -> User:
    user_id = decode_access_token(token) if token else None
    user = db.get(User, user_id) if user_id is not None else None
    if user is None or not user.is_active:
        raise Unauthorized("Not authenticated")
    return user


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    user = user_from_token(db, credentials.credentials if credentials else None)
    # Picked up by the access-log middleware.
    request.state.user_id = user.id
    return user


def require_roles(*roles: Role) -> Callable[..., User]:
    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise Forbidden("You do not have permission to perform this action")
        return user

    return dependency


def is_staff(user: User) -> bool:
    return user.role in STAFF
