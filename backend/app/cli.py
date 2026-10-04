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


def import_csv_file(csv_file: Path, uploaded_by: int | None = None) -> dict:
    """CLI equivalent of POST /import (same service, same idempotency/report)."""
    from app.services import importer as importer_service

    text = csv_file.read_text(encoding="utf-8-sig")
    with SessionLocal() as db:
        report = importer_service.import_episodes(
            db, text, filename=csv_file.name, uploaded_by=uploaded_by
        )
    log.info(
        "import done: %s total=%d inserted=%d updated=%d unchanged=%d skipped=%d",
        csv_file.name,
        report["total_rows"],
        report["inserted"],
        report["updated"],
        report["unchanged"],
        report["skipped"],
    )
    return report


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument("--users", type=Path, default=Path("../seed/users.json"))
    parser.add_argument("--episodes", type=Path, default=None)
    args = parser.parse_args()
    if args.users and args.users.exists():
        seed(args.users)
    if args.episodes:
        import_csv_file(args.episodes)
