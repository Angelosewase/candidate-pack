import argparse
import json
import logging
from pathlib import Path

from app.db import SessionLocal
from app.models import Role
from app.schemas import UserCreate
from app.services import users as user_service

log = logging.getLogger(__name__)


def seed(users_file: Path) -> None:
    with users_file.open() as f:
        users = json.load(f)

    with SessionLocal() as db:
        for u in users:
            try:
                user_service.create_user(
                    db,
                    UserCreate(
                        email=u["email"],
                        name=u["name"],
                        password=u["password"],
                        role=Role(u["role"]),
                        organisation=u.get("organisation"),
                    ),
                )
                log.info(f"Created user: {u['email']} ({u['role']})")
            except Exception as e:
                log.warning(f"Skipped {u['email']}: {e}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument("--users", type=Path, default=Path("../seed/users.json"))
    args = parser.parse_args()
    seed(args.users)
