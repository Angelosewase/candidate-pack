"""Initial schema.

Revision ID: 0001
Revises:
Create Date: 2026-10-04
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

STATUSES = "('submitted','in_progress','delivered','accepted','rejected')"
KNOWN_ROBOTS = ["arm-01", "arm-02", "arm-03", "mobile-01", "humanoid-01"]


def _ts(name: str, nullable: bool = False) -> sa.Column:
    return sa.Column(
        name,
        sa.DateTime(timezone=True),
        nullable=nullable,
        server_default=None if nullable else sa.func.now(),
    )


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("email", sa.String(254), nullable=False, unique=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("organisation", sa.String(200)),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        _ts("created_at"),
        sa.CheckConstraint("role IN ('client','operator','admin')", name="ck_users_role"),
        sa.CheckConstraint("email = lower(email)", name="ck_users_email_lower"),
    )

    robots = op.create_table(
        "robots",
        sa.Column("robot_id", sa.String(50), primary_key=True),
        _ts("created_at"),
    )
    op.bulk_insert(robots, [{"robot_id": r} for r in KNOWN_ROBOTS])

    op.create_table(
        "episodes",
        sa.Column("episode_id", sa.String(50), primary_key=True),
        sa.Column("robot_id", sa.String(50), sa.ForeignKey("robots.robot_id"), nullable=False),
        sa.Column("task_name", sa.String(200), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_seconds", sa.Integer),
        sa.Column("operator_name", sa.String(200)),
        sa.Column("quality", sa.String(20), nullable=False),
        _ts("created_at"),
        _ts("updated_at"),
        sa.CheckConstraint("quality IN ('good','usable','bad')", name="ck_episodes_quality"),
        sa.CheckConstraint("duration_seconds > 0", name="ck_episodes_duration_positive"),
    )
    # Covering index for the analytics queries (range scan on recorded_at, the
    # grouped columns are available without touching the heap -> index-only scans).
    op.execute(
        "CREATE INDEX ix_episodes_recorded_at ON episodes (recorded_at) "
        "INCLUDE (robot_id, task_name, quality)"
    )
    # Operator episode browser filters by task + quality.
    op.create_index("ix_episodes_task_quality", "episodes", ["task_name", "quality"])

    op.create_table(
        "dataset_requests",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("client_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("task_name", sa.String(200), nullable=False),
        sa.Column("episodes_requested", sa.Integer, nullable=False),
        sa.Column("deadline", sa.Date, nullable=False),
        sa.Column("notes", sa.Text, nullable=False, server_default=""),
        sa.Column("status", sa.String(20), nullable=False),
        _ts("created_at"),
        _ts("updated_at"),
        sa.CheckConstraint(f"status IN {STATUSES}", name="ck_requests_status"),
        sa.CheckConstraint("episodes_requested > 0", name="ck_requests_count_positive"),
    )
    op.create_index("ix_requests_client_created", "dataset_requests", ["client_id", "created_at"])
    op.create_index("ix_requests_created", "dataset_requests", ["created_at"])

    op.create_table(
        "request_status_events",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("request_id", sa.Integer, sa.ForeignKey("dataset_requests.id"), nullable=False),
        sa.Column("from_status", sa.String(20)),
        sa.Column("to_status", sa.String(20), nullable=False),
        sa.Column("actor_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("note", sa.Text),
        _ts("created_at"),
        sa.CheckConstraint(f"to_status IN {STATUSES}", name="ck_events_to_status"),
        sa.CheckConstraint(
            f"from_status IS NULL OR from_status IN {STATUSES}", name="ck_events_from_status"
        ),
    )
    op.create_index(
        "ix_events_request_created", "request_status_events", ["request_id", "created_at"]
    )

    op.create_table(
        "assignments",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("request_id", sa.Integer, sa.ForeignKey("dataset_requests.id"), nullable=False),
        sa.Column(
            "episode_id", sa.String(50), sa.ForeignKey("episodes.episode_id"), nullable=False
        ),
        sa.Column("assigned_by", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        _ts("assigned_at"),
        _ts("released_at", nullable=True),
        sa.Column("released_by", sa.Integer, sa.ForeignKey("users.id")),
    )
    # The core assignment invariant, enforced by the database.
    op.create_index(
        "uq_assignments_active_episode",
        "assignments",
        ["episode_id"],
        unique=True,
        postgresql_where=sa.text("released_at IS NULL"),
    )
    op.create_index(
        "ix_assignments_active_request",
        "assignments",
        ["request_id"],
        postgresql_where=sa.text("released_at IS NULL"),
    )

    op.create_table(
        "import_runs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("uploaded_by", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("total_rows", sa.Integer, nullable=False),
        sa.Column("inserted", sa.Integer, nullable=False),
        sa.Column("updated", sa.Integer, nullable=False),
        sa.Column("unchanged", sa.Integer, nullable=False),
        sa.Column("skipped", sa.Integer, nullable=False),
        sa.Column("report", postgresql.JSONB, nullable=False),
        _ts("created_at"),
    )


def downgrade() -> None:
    for table in [
        "import_runs",
        "assignments",
        "request_status_events",
        "dataset_requests",
        "episodes",
        "robots",
        "users",
    ]:
        op.drop_table(table)
