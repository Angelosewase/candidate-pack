"""Authentication endpoints."""

import logging

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.errors import Unauthorized
from app.models import User
from app.normalize import normalize_email
from app.schemas import LoginIn, TokenOut, UserOut
from app.security import create_access_token, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])
log = logging.getLogger(__name__)


@router.post(
    "/login",
    response_model=TokenOut,
    summary="Log in and obtain a JWT",
    response_description="Bearer token and authenticated user profile",
)
def login(body: LoginIn, db: Session = Depends(get_db)) -> TokenOut:
    """Authenticate with email and password.

    Returns a Bearer JWT valid for `JWT_TTL_MINUTES` (default 8 hours). Include
    it as `Authorization: Bearer <token>` on all subsequent requests.

    The same error message is returned whether the email is unknown, the password
    is wrong, or the account is deactivated — this prevents user-enumeration.
    """
    user = db.scalar(select(User).where(User.email == normalize_email(body.email)))
    password_ok = verify_password(user.password_hash if user else None, body.password)
    if user is None or not password_ok or not user.is_active:
        log.warning("login_failed", extra={"fields": {"email": normalize_email(body.email)}})
        raise Unauthorized("Invalid email or password")
    log.info("login_succeeded", extra={"fields": {"user_id": user.id}})
    return TokenOut(access_token=create_access_token(user.id), user=UserOut.model_validate(user))


@router.get(
    "/me",
    response_model=UserOut,
    summary="Current authenticated user",
    response_description="The user associated with the provided JWT",
)
def me(user: User = Depends(get_current_user)) -> User:
    """Return the profile of the currently authenticated user.

    Useful for the frontend to bootstrap its session after a page reload.
    """
    return user
