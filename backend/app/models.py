"""ORM models. The schema itself is owned by Alembic migrations (see alembic/versions)."""

import enum
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Role(enum.StrEnum):
    CLIENT = "client"
    OPERATOR = "operator"
    ADMIN = "admin"


class Quality(enum.StrEnum):
    GOOD = "good"
    USABLE = "usable"
    BAD = "bad"


class RequestStatus(enum.StrEnum):
    SUBMITTED = "submitted"
    IN_PROGRESS = "in_progress"
    DELIVERED = "delivered"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


def _str_enum(e: type[enum.StrEnum]) -> Enum:
    # Stored as VARCHAR + CHECK constraint (created in the migration) rather than a
    # native Postgres ENUM type: adding a value later is a plain constraint change.
    return Enum(
        e,
        native_enum=False,
        create_constraint=False,
        length=20,
        values_callable=lambda members: [m.value for m in members],
        validate_strings=True,
    )


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    organisation: Mapped[str | None] = mapped_column(String(200))
    role: Mapped[Role] = mapped_column(_str_enum(Role))
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Robot(Base):
    __tablename__ = "robots"

    robot_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Episode(Base):
    __tablename__ = "episodes"

    # Natural key from the recording system; the import upserts on it.
    episode_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    robot_id: Mapped[str] = mapped_column(ForeignKey("robots.robot_id"))
    task_name: Mapped[str] = mapped_column(String(200))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    operator_name: Mapped[str | None] = mapped_column(String(200))
    quality: Mapped[Quality] = mapped_column(_str_enum(Quality))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DatasetRequest(Base):
    __tablename__ = "dataset_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    task_name: Mapped[str] = mapped_column(String(200))
    episodes_requested: Mapped[int] = mapped_column(Integer)
    deadline: Mapped[date] = mapped_column(Date)
    notes: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[RequestStatus] = mapped_column(_str_enum(RequestStatus))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    client: Mapped[User] = relationship(lazy="joined", innerjoin=True)


class RequestStatusEvent(Base):
    """Append-only audit log of every status change (including creation)."""

    __tablename__ = "request_status_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("dataset_requests.id"))
    from_status: Mapped[RequestStatus | None] = mapped_column(_str_enum(RequestStatus))
    to_status: Mapped[RequestStatus] = mapped_column(_str_enum(RequestStatus))
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    actor: Mapped[User] = relationship(lazy="joined", innerjoin=True)


class Assignment(Base):
    """An episode assigned to a request.

    Rows are never deleted: unassigning sets ``released_at``. A partial unique index
    on (episode_id) WHERE released_at IS NULL enforces "at most one request at a time"
    in the database itself, so concurrent assigns cannot both succeed.
    """

    __tablename__ = "assignments"

    __table_args__ = (
        # Mirrors migration 0001 (uq_assignments_active_episode): the DB itself
        # enforces "one active assignment per episode". Declared here too so
        # Base.metadata.create_all (used by tests) creates the same guard.
        Index(
            "uq_assignments_active_episode",
            "episode_id",
            unique=True,
            postgresql_where=text("released_at IS NULL"),
        ),
        Index(
            "ix_assignments_active_request",
            "request_id",
            postgresql_where=text("released_at IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("dataset_requests.id"))
    episode_id: Mapped[str] = mapped_column(ForeignKey("episodes.episode_id"))
    assigned_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    released_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))

    episode: Mapped[Episode] = relationship(lazy="joined", innerjoin=True)


class ImportRun(Base):
    __tablename__ = "import_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    filename: Mapped[str] = mapped_column(String(255))
    sha256: Mapped[str] = mapped_column(String(64))
    uploaded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    total_rows: Mapped[int] = mapped_column(Integer)
    inserted: Mapped[int] = mapped_column(Integer)
    updated: Mapped[int] = mapped_column(Integer)
    unchanged: Mapped[int] = mapped_column(Integer)
    skipped: Mapped[int] = mapped_column(Integer)
    report: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
