"""User management endpoints (admin only)."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import require_roles
from app.models import Role, User
from app.schemas import UserCreate, UserOut, UserUpdate
from app.services import users as service

router = APIRouter(prefix="/users", tags=["users"])
admin_only = require_roles(Role.ADMIN)


@router.get(
    "",
    response_model=list[UserOut],
    summary="List all users",
    response_description="All users in the system, ordered by creation time",
)
def list_users(db: Session = Depends(get_db), _: User = Depends(admin_only)) -> list[User]:
    """Return all users (admin only).

    Includes deactivated accounts so admins can see the full roster and
    reactivate them if needed.
    """
    return service.list_users(db)


@router.post(
    "",
    response_model=UserOut,
    status_code=201,
    summary="Create a new user",
    response_description="The newly created user",
)
def create_user(
    body: UserCreate, db: Session = Depends(get_db), _: User = Depends(admin_only)
) -> User:
    """Create a new user account (admin only).

    - Email must be unique (case-insensitive, normalised to lowercase).
    - Password is hashed with Argon2id before storage; the plaintext is never
      persisted.
    - Returns `409 Conflict` if the email is already registered.
    """
    return service.create_user(db, body)


@router.patch(
    "/{user_id}",
    response_model=UserOut,
    summary="Update a user",
    response_description="The updated user",
)
def update_user(
    user_id: int,
    body: UserUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(admin_only),
) -> User:
    """Partially update a user (admin only). All fields are optional.

    Admins cannot deactivate their own account or downgrade their own role —
    this prevents accidental lock-out. Returns `422` if either is attempted.

    Setting `is_active: false` immediately revokes access; existing JWT tokens
    are rejected on the next request because the user record is re-fetched from
    the DB on every request.
    """
    return service.update_user(db, admin, user_id, body)
