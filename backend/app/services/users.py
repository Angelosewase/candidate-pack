from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.errors import Conflict, InvalidInput, NotFound
from app.models import User
from app.schemas import UserCreate, UserUpdate
from app.security import hash_password


def list_users(db: Session) -> list[User]:
    return list(db.scalars(select(User).order_by(User.id)))


def create_user(db: Session, data: UserCreate) -> User:
    user = User(
        email=data.email,
        name=data.name,
        organisation=data.organisation,
        role=data.role,
        password_hash=hash_password(data.password),
        is_active=True,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise Conflict("A user with this email already exists") from None
    return user


def update_user(db: Session, admin: User, user_id: int, data: UserUpdate) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise NotFound("User not found")
    changes = data.model_dump(exclude_unset=True)
    if user.id == admin.id and (
        changes.get("is_active") is False or changes.get("role", admin.role) != admin.role
    ):
        # Prevents an admin locking everyone (including themselves) out by accident.
        raise InvalidInput("Admins cannot deactivate or change the role of their own account")
    if "password" in changes:
        user.password_hash = hash_password(changes.pop("password"))
    for key, value in changes.items():
        setattr(user, key, value)
    db.commit()
    return user
