from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import require_roles
from app.models import Role, User
from app.schemas import UserCreate, UserOut, UserUpdate
from app.services import users as service

router = APIRouter(prefix="/users", tags=["users"])
admin_only = require_roles(Role.ADMIN)


@router.get("", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), _: User = Depends(admin_only)) -> list[User]:
    return service.list_users(db)


@router.post("", response_model=UserOut, status_code=201)
def create_user(
    body: UserCreate, db: Session = Depends(get_db), _: User = Depends(admin_only)
) -> User:
    return service.create_user(db, body)


@router.patch("/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    body: UserUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(admin_only),
) -> User:
    return service.update_user(db, admin, user_id, body)
